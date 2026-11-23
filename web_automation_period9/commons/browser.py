"""创建本例独立的 Chrome 会话，并在用例结束时释放。"""

from contextlib import contextmanager
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# 隐性等待时间配置
DEFAULT_IMPLICIT_WAIT = 10

__all__ = ["By", "EC", "WebDriverWait", "DEFAULT_IMPLICIT_WAIT", "chrome_session"]


@contextmanager
def _chrome_profile(runtime: Path):
    directory = TemporaryDirectory(prefix="chrome-case-", dir=runtime)
    profile = Path(directory.name)
    if profile.resolve().parent != runtime:
        raise ValueError("浏览器临时配置须位于本例运行目录")
    try:
        yield str(profile)
    finally:
        for delay in (0.2, 0.5, 1, 2, 4, None):
            try:
                directory.cleanup()
                break
            except PermissionError as error:
                if getattr(error, "winerror", None) not in {32, 33} or delay is None:
                    raise
                # Chrome 退出后，Windows 短暂占用的临时文件需要等共享锁释放。
                sleep(delay)


@contextmanager
def chrome_session(project_root: Path, *, implicit_wait: float = DEFAULT_IMPLICIT_WAIT):
    """隐式等待单位为秒。用例可以传入 0 来单独使用显式等待。"""
    driver_path = project_root / "chromedriver.exe"
    if not driver_path.is_file():
        raise FileNotFoundError(f"缺少本地 ChromeDriver：{driver_path}")

    runtime = (project_root / ".local" / "browser-runtime").resolve()
    if not runtime.is_relative_to(project_root):
        raise ValueError("浏览器运行目录须位于 T9 项目内")
    runtime.mkdir(parents=True, exist_ok=True)

    with _chrome_profile(runtime) as profile:
        options = Options()
        options.add_argument(f"--user-data-dir={profile}")
        options.add_argument("--no-first-run")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-component-update")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--window-size=1280,900")
        if os.environ.get("RUOYI_UI_HEADLESS") == "1":
            options.add_argument("--headless=new")
        # Chrome 与驱动的临时文件随本例浏览器配置一起释放。
        service_env = os.environ.copy()
        service_env.update(TEMP=profile, TMP=profile)
        service_env.pop("SE_CHROMEDRIVER", None)
        service = Service(executable_path=str(driver_path), env=service_env)
        with webdriver.Chrome(service=service, options=options) as browser:
            browser.implicitly_wait(implicit_wait)
            browser.set_page_load_timeout(15)
            yield browser
