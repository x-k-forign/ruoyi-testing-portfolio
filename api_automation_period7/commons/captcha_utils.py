"""处理 YAML 中当前这次验证码响应；请求本身仍由 YAML 明确列出。"""

import base64
import json
import re
import uuid

import allure

from .config import PROJECT_ROOT, PreparationError
from .interaction_utils import read_secret
from .client import require_code


def validate_captcha_settings(cfg, mode):
    """连接信息只来自显式私有配置，不从其他Redis库猜测或寻找验证码。"""
    if mode not in {"redis", "manual"}:
        raise PreparationError("验证码模式仅支持redis或manual")
    settings = cfg.get("captcha", {})
    if not isinstance(settings, dict):
        raise PreparationError("captcha配置须为对象")
    attempts = settings.get("max_attempts", 3)
    if type(attempts) is not int or not 1 <= attempts <= 3:
        raise PreparationError("验证码最大尝试次数须为1～3")
    if mode == "redis":
        connection = settings.get("redis", {})
        if (not isinstance(connection, dict) or not isinstance(connection.get("host"), str)
                or not connection["host"] or type(connection.get("port")) is not int
                or not 1 <= connection["port"] <= 65535 or type(connection.get("db")) is not int
                or connection["db"] < 0):
            raise PreparationError("请在私有captcha.redis配置中显式填写host、port和db")
        for field in ("username", "password"):
            if connection.get(field) is not None and not isinstance(connection[field], str):
                raise PreparationError(f"Redis的{field}配置格式错误")
    return {**settings, "mode": mode, "max_attempts": attempts}


def read_redis_answer(captcha_uuid, settings):
    """仅GET当前uuid的验证码键；不扫描、不改写、不删除任何Redis键。"""
    if not isinstance(captcha_uuid, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", captcha_uuid):
        raise PreparationError("本次验证码uuid格式不正确")
    try:
        import redis
    except ImportError:
        raise PreparationError("请在本项目虚拟环境安装已记录的redis依赖") from None
    connection = settings["redis"]
    client = redis.Redis(host=connection["host"], port=connection["port"], db=connection["db"],
                         username=connection.get("username") or None,
                         password=connection.get("password") or None,
                         decode_responses=True, socket_connect_timeout=3, socket_timeout=3,
                         retry_on_timeout=False)
    try:
        raw = client.get("captcha_codes:" + captcha_uuid)
    except redis.RedisError:
        raise PreparationError("读取本次测试验证码失败，请核对Redis连接、凭据和数据库；未回落到其他地址") from None
    finally:
        client.close()
    if raw is None:
        return None
    # 当前后端使用FastJson序列化，字符串可能带JSON引号；普通字符串也可读取。
    try:
        answer = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        answer = raw
    if type(answer) is int:
        answer = str(answer)
    if not isinstance(answer, str) or not re.fullmatch(r"[-+A-Za-z0-9]{1,16}", answer):
        raise PreparationError("本次验证码缓存序列化格式不符合预期")
    return answer


def refresh_captcha(context):
    """失效时新取验证码和uuid，保留正常HTTP证据；不重发任何业务写请求。"""
    response = context["_client"].request("GET", "/captchaImage")
    context["_captcha"] = require_code(response)
    context["_captcha_evidence"]["refreshes"] += 1


def prepare_login_input(my_var, request_settings):
    """保留真实验证码校验；按所选模式取得本次答案，不持久化答案或uuid。"""
    payload = request_settings.get("json", {})
    if not isinstance(payload, dict):
        return
    if payload.get("code") != "${captcha_code}" and payload.get("uuid") != "${captcha_uuid}":
        return
    settings = my_var["_captcha_settings"]
    for attempt in range(settings["max_attempts"]):
        captcha = my_var.get("_captcha")
        if not isinstance(captcha, dict) or captcha.get("code") != 200:
            raise PreparationError("登录前须在YAML中请求/captchaImage，并断言验证码响应")
        if captcha.get("captchaEnabled") is not True:
            raise PreparationError("本轮要求验证码保持开启；服务端返回未开启，停止登录")
        if not captcha.get("uuid") or not captcha.get("img"):
            raise PreparationError("验证码响应缺少uuid或img")
        my_var["_captcha_evidence"]["enabled"] = True
        allure.dynamic.label("captcha_enabled", "true")
        if settings["mode"] == "manual":
            break
        answer = read_redis_answer(captcha["uuid"], settings)
        if answer is not None:
            my_var.update(captcha_uuid=captcha["uuid"], captcha_code=answer)
            my_var["_captcha_evidence"]["answers_read"] += 1
            return
        if attempt + 1 < settings["max_attempts"]:
            with allure.step("当前验证码已失效，重新取得本次图片和uuid"):
                refresh_captcha(my_var)
    else:
        raise PreparationError("限定次数内未取得本次验证码答案，停止本条用例")
    folder = PROJECT_ROOT / ".private/yaml_runs" / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    image = folder / "captcha.png"
    image.write_bytes(base64.b64decode(captcha["img"], validate=True))
    my_var["captcha_uuid"] = captcha["uuid"]
    my_var["captcha_code"] = read_secret("请输入本次验证码（数学题只填结果）：", image_path=image)
