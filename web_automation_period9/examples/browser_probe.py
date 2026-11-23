"""在本机核对若依登录页以及 Selenium 会话的启动和退出。"""

import csv
from datetime import datetime
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
from urllib.parse import urlsplit

from commons.browser import By, EC, WebDriverWait, chrome_session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "http://127.0.0.1:5173/"


def probe_login_page(browser, url):
    """只记录控件状态，避免记录登录字段内容或验证码图片。"""
    browser.get(url)
    form = WebDriverWait(browser, 12).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "form.login-form")),
        "等待若依登录表单可见",
    )
    address = urlsplit(browser.current_url)
    if address[:2] != urlsplit(url)[:2] or address.path != "/login":
        raise RuntimeError("实际地址不是目标前端的登录页")
    title = form.find_element(By.CSS_SELECTOR, "h3.title")
    if not title.is_displayed() or title.text != "若依管理系统":
        raise RuntimeError("若依登录标题不符")

    for selector in ('input[placeholder="账号"]', 'input[type="password"]', "button.el-button--primary"):
        matches = form.find_elements(By.CSS_SELECTOR, selector)
        if len(matches) != 1 or not matches[0].is_displayed() or not matches[0].is_enabled():
            raise RuntimeError(f"登录表单控件未就绪：{selector}")

    def captcha_loaded(current_browser):
        images = current_browser.find_elements(By.CSS_SELECTOR, "form.login-form img.login-code-img")
        return len(images) == 1 and images[0].is_displayed() and images[0].get_property("naturalWidth") > 0

    WebDriverWait(browser, 8).until(captcha_loaded, "等待验证码图片显示")
    return {
        "address": address._replace(query="", fragment="").geturl(),
        "heading": title.text,
        "login_fields_ready": True,
        "captcha_image_displayed": True,
    }


def chrome_exited(pid):
    # 只查询本次 Chrome 的 PID，避免误把用户已打开的 Chrome 算进来。
    output = subprocess.check_output(
        ["tasklist.exe", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        text=True,
        errors="replace",
        timeout=10,
    )
    return not any(len(row) > 1 and row[1] == str(pid) for row in csv.reader(output.splitlines()))


def main():
    url = os.environ.get("RUOYI_UI_BASE_URL", DEFAULT_URL)
    address = urlsplit(url)
    if (
        address.scheme not in {"http", "https"} or address.hostname not in {"127.0.0.1", "localhost"}
        or address.username is not None or address.query or address.fragment
    ):
        raise ValueError("请选择不带凭据、查询参数和片段的本机若依前端地址")

    result = {
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target": url,
        "python": platform.python_version(),
        "pytest": version("pytest"),
        "selenium": version("selenium"),
        "allure_pytest": version("allure-pytest"),
        "mode": "headed",
        "driver": "chromedriver.exe",
    }
    step = "启动浏览器"
    try:
        with chrome_session(PROJECT_ROOT) as browser:
            driver_process = browser.service.process
            chrome_pid = browser.capabilities["goog:processID"]
            profile = Path(browser.capabilities["chrome"]["userDataDir"])
            result.update(
                chrome=browser.capabilities["browserVersion"],
                chromedriver=browser.capabilities["chrome"]["chromedriverVersion"].split()[0],
                chrome_pid=chrome_pid,
                chromedriver_pid=driver_process.pid,
                window=browser.get_window_size(),
            )
            step = "访问若依登录页"
            result["page"] = probe_login_page(browser, url)
            step = "退出并检查资源释放"

        result["release"] = {
            "chrome_exited": chrome_exited(chrome_pid),
            "chromedriver_exited": driver_process.poll() is not None,
            "profile_removed": not profile.exists(),
        }
        if not all(result["release"].values()):
            raise RuntimeError("探测会话仍有资源未释放")
        result["status"] = "passed"
    except Exception as error:
        result.update(status="failed", failed_step=step, error_type=type(error).__name__)
    finally:
        result["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
