"""最小Requests客户端：每个身份一个Session，返回原始Response供场景判断。"""

from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
import hashlib
import requests
from .safe_evidence import META, register_sensitive, register_secret, record_http, safe_route


class ConnectionFailure(RuntimeError):
    pass


class RequestTimeout(RuntimeError):
    pass


class ResponseFormatError(ValueError):
    pass


class BusinessRejected(RuntimeError):
    pass


def json_body(response):
    """JSON能解析，只说明格式正确；业务成功还要另外判断。"""
    try:
        body = response.json()
    except requests.exceptions.JSONDecodeError:
        raise ResponseFormatError("响应不是有效JSON") from None
    if not isinstance(body, dict):
        raise ResponseFormatError("响应JSON顶层不是对象")
    return body


def require_code(response, expected=200):
    body = json_body(response)
    if response.status_code != 200 or body.get("code") != expected:
        # 保留安全的HTTP/业务状态；不输出完整正文、登录参数或token。
        reason = "业务拒绝"
        message = str(body.get("msg", ""))
        for keyword in ("验证码", "密码", "权限", "账号"):
            if keyword in message:
                reason = keyword + "相关拒绝"
                break
        raise BusinessRejected(f"{reason}：HTTP={response.status_code}，code={body.get('code')}")
    return body


class ApiClient:
    def __init__(self, base_url, timeout, actor, events):
        parsed = urlsplit(base_url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.path:
            raise ValueError("本节客户端只访问明确的本机HTTP地址")
        self.base_url = base_url
        self.timeout = timeout
        self.actor = actor
        self.events = events
        self.session = requests.Session()
        self.session.trust_env = False  # 本机练习不继承代理或netrc认证。
        self.token = None
        self.session_fingerprint = None
        self.evidence_context = None

    def set_token(self, token):
        if not isinstance(token, str) or not token:
            raise ResponseFormatError("登录响应缺少有效token")
        self.token = token
        register_secret(token)
        # 仅保存令牌的短摘要用于跨轮会话隔离核对，报告不保存实际令牌。
        self.session_fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
        self.session.headers["Authorization"] = f"Bearer {token}"

    def request(self, method, path, *, _input_evidence=None, **kwargs):
        register_sensitive(kwargs)
        if not path.startswith("/") or "://" in path or "?" in path:
            raise ValueError("路径必须是相对接口路径，查询字段使用params")
        event = {"at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                 "actor": self.actor, "method": method, "path": safe_route(path),
                 "phase": META.get().get("phase", "outside_pytest")}
        # 不自动raise_for_status、不无限重试；保留真实响应用于判断拒绝场景。
        try:
            response = self.session.request(method, self.base_url + path,
                                            timeout=self.timeout, allow_redirects=False, **kwargs)
        except requests.Timeout:
            event["error_type"] = "Timeout"
            self.events.append(event)
            record_http(self, method, path, kwargs, None, error_type="Timeout")
            raise RequestTimeout(f"{self.actor}请求超时：{method} {safe_route(path)}") from None
        except requests.ConnectionError:
            event["error_type"] = "ConnectionError"
            self.events.append(event)
            record_http(self, method, path, kwargs, None, error_type="ConnectionError")
            raise ConnectionFailure(f"{self.actor}连接失败：{method} {safe_route(path)}") from None
        event["http_status"] = response.status_code
        event["completed_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
        try:
            body = response.json()
            if isinstance(body, dict):
                event["business_code"] = body.get("code")
                # 登录证据落盘前先登记已取得的会话，日志故障也不能使令牌失去收尾归属。
                if method == "POST" and path == "/login" and isinstance(body.get("token"), str) and body["token"]:
                    self.set_token(body["token"])
        except requests.exceptions.JSONDecodeError:
            event["response_format"] = "non_json"
        if _input_evidence is not None:
            _input_evidence.update(http_response_received=True, http_status=response.status_code,
                                   business_code=event.get("business_code"))
            event["input_evidence"] = dict(_input_evidence)
        self.events.append(event)
        # 统一在HTTP返回后、复杂解析和业务断言前保存摘要；所有调用入口均生效。
        record_http(self, method, path, kwargs, response, input_evidence=_input_evidence)
        return response

    def logout(self):
        if self.token:
            require_code(self.request("POST", "/logout"))
            # 保留原令牌再查一次，证明退出后它确实失效。
            body = require_code(self.request("GET", "/getInfo"), 401)
            if "user" in body:
                raise ResponseFormatError("退出后不应返回身份")
            self.token = None
            self.session.headers.pop("Authorization", None)

    def close(self):
        self.session.close()  # 关连接不能代替上面的服务端logout。
