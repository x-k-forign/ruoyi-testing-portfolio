"""T9 的浏览器夹具和失败证据。"""

from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import allure
import pytest

from commons.browser import DEFAULT_IMPLICIT_WAIT, chrome_session


PROJECT_ROOT = Path(__file__).resolve().parent
ACTIVE_BROWSERS = pytest.StashKey()
_SCREENSHOT_PATHS = {"/system/user", "/system/role"}

# 在用户与角色管理页截图，遮挡账号、表格内容、表单值及站点图片。
_SCREENSHOT_MASK = """
    input, textarea, [contenteditable], img, svg image, canvas, iframe, video,
    .el-table__body tbody, .el-drawer, .tree-sidebar, .navbar .avatar-container,
    .el-select__selected-item, .el-select__popper, .el-message, .el-message-box,
    .el-notification, .el-overlay-dialog label, .el-form-item__error {
        visibility: hidden !important;
    }
"""


def _attach_status(name, **data):
    allure.attach(json.dumps(data, ensure_ascii=False), name, allure.attachment_type.JSON)


def _capture_failure(browser, identity, phase):
    try:
        address = urlsplit(browser.current_url)
        route = address.path if address.hostname in {"localhost", "127.0.0.1", "::1"} else ""
        if route not in _SCREENSHOT_PATHS:
            _attach_status("失败现场", 角色=identity, 阶段=phase, 截图="仅用户管理与角色管理页支持受控截图")
            return

        browser.switch_to.window(browser.current_window_handle)
        style = browser.execute_script("""
            const mask = document.createElement("style");
            mask.textContent = arguments[0];
            document.head.appendChild(mask);
            void document.documentElement.offsetHeight;
            return mask;
        """, _SCREENSHOT_MASK)
        try:
            allure.attach(browser.get_screenshot_as_png(), f"失败现场（{identity}）", allure.attachment_type.PNG)
        finally:
            browser.execute_script("arguments[0].remove();", style)
        _attach_status("失败现场", 角色=identity, 阶段=phase, 页面=route, 截图="已保存遮挡后的页面")
    except Exception as error:
        _attach_status("失败现场", 角色=identity, 阶段=phase, 截图="采集失败", 错误类型=type(error).__name__)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if report.failed and report.when in {"setup", "call"}:
        browsers = item.stash.get(ACTIVE_BROWSERS, {})
        if not browsers:
            _attach_status("失败现场", 阶段=report.when, 截图="当前没有已建立的浏览器")
        for identity, browser in browsers.items():
            _capture_failure(browser, identity, report.when)
    return report


@contextmanager
def _managed_browser(browsers, identity, implicit_wait):
    profile = None
    try:
        with chrome_session(PROJECT_ROOT, implicit_wait=implicit_wait) as browser:
            profile = Path(browser.capabilities["chrome"]["userDataDir"])
            browsers[identity] = browser
            _attach_status(
                "浏览器环境",
                角色=identity,
                浏览器=browser.capabilities["browserVersion"],
                驱动=browser.capabilities["chrome"]["chromedriverVersion"].split()[0],
                窗口=browser.get_window_size(),
                模式="无头" if os.environ.get("RUOYI_UI_HEADLESS") == "1" else "有头",
            )
            yield browser
        if profile.exists():
            raise RuntimeError("浏览器临时配置未释放")
    except Exception as error:
        phase = "启动失败，未取得 WebDriver" if profile is None else "释放失败"
        _attach_status("浏览器生命周期", 角色=identity, 结果=phase, 错误类型=type(error).__name__)
        raise
    else:
        _attach_status("浏览器生命周期", 角色=identity, 结果="WebDriver 已退出，临时配置已释放")
    finally:
        browsers.pop(identity, None)


@pytest.fixture
def capture_ui_failure():
    return _capture_failure


@pytest.fixture
def new_browser(request):
    """在一例内可多次打开独立会话，按建会话的逆序收尾。"""
    browsers = request.node.stash[ACTIVE_BROWSERS] = {}
    def open_browser(*, implicit_wait: float = DEFAULT_IMPLICIT_WAIT, identity=None):
        label = identity or f"会话 {len(browsers) + 1}"
        if label in browsers:
            raise ValueError("同一用例的浏览器身份标签必须唯一")
        with ExitStack() as opening:
            browser = opening.enter_context(_managed_browser(browsers, label, implicit_wait))
            request.addfinalizer(opening.pop_all().close)
        return browser

    return open_browser

@pytest.fixture
def browser(new_browser):
    """单身份用例可直接使用 browser。"""
    return new_browser()
