"""接收运行者输入的本次验证码。"""

from getpass import getpass

from .browser import By, EC, WebDriverWait


def fill_login_captcha(browser, *, config_path, timeout=10):
    locator = (By.CSS_SELECTOR, 'form.login-form input[placeholder="验证码"]')
    field = WebDriverWait(browser, timeout).until(EC.element_to_be_clickable(locator))
    answer = getpass("请查看 Chrome 登录页，在此输入当前验证码答案：").strip()
    if not answer:
        raise ValueError("验证码答案不能为空")
    field.clear()
    field.send_keys(answer)
