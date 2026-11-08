"""T7.8证据白名单与输出脱敏；实际Response留在内存，日志只保存必要摘要。"""

from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import logging
import re
import sys

import allure

META = ContextVar("ruoyi_evidence_metadata", default={})
SECRETS = set()
PHASES = []
RESULTS = None
RUN_TOKEN = None
_FACTORY = None
_PREVIOUS_FACTORY = None
_STREAMS = []


def secret_key(key):
    name = re.sub(r"[^a-z0-9]", "", str(key).lower())
    if name in {"passwordlength", "actualpasswordlength", "expectedpasswordlength", "allowedpasswordlength", "passwordsupplied"}:
        return False  # 长度/存在性是安全的测试输入证据，不是口令本身。
    return any(word in name for word in ["password", "passwd", "secret", "authorization", "cookie", "accesstoken", "apikey"]) or name in {"token", "pwd", "uuid", "img", "captchacode", "captchaanswer"}


def register_secret(value):
    if isinstance(value, str) and 4 <= len(value) <= 100000:
        SECRETS.add(value)


def register_sensitive(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if secret_key(key):
                register_secret(item)
                if str(key).lower() == "authorization" and isinstance(item, str):
                    register_secret(item.removeprefix("Bearer "))
            else:
                register_sensitive(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            register_sensitive(item)


def safe_text(value):
    text = str(value)
    for secret in sorted(SECRETS, key=len, reverse=True):
        text = text.replace(secret, "***")
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer ***", text)
    text = re.sub(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "***", text)
    text = re.sub(r"(?i)(\b(?:password|passwd|pwd|secret|access_token|api_key|captcha_code|captcha_answer|uuid)\s*[=:]\s*)[A-Za-z0-9_+./=-]+", r"\1***", text)
    # 不按键名替换Allure结构UUID；验证码UUID由已登记的实际值脱敏。
    text = re.sub(r'''(?i)(["'](?:password|passwd|pwd|secret|access_token|api_key|captcha_code|captcha_answer)["']\s*:\s*)(["'])(.*?)(\2)''',
                  lambda match: match.group(1) + match.group(2) + "***" + match.group(4), text)
    return text


def scrub(value):
    if isinstance(value, dict):
        return {safe_text(k): ("***" if secret_key(k) else scrub(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    return safe_text(value) if isinstance(value, str) else value


def begin_run(results, token):
    global RESULTS, RUN_TOKEN
    if token != RUN_TOKEN:
        PHASES.clear()
        SECRETS.clear()
    RESULTS, RUN_TOKEN = Path(results), token


def set_case(metadata):
    META.set(dict(metadata))


def set_phase(phase):
    META.set({**META.get(), "phase": phase})


def install_log_filter():
    global _FACTORY, _PREVIOUS_FACTORY
    if _FACTORY is not None:
        return
    previous = logging.getLogRecordFactory()
    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        record.msg, record.args = safe_text(record.getMessage()), ()
        if record.exc_info:
            record.exc_text = safe_text(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return record
    _PREVIOUS_FACTORY, _FACTORY = previous, factory
    logging.setLogRecordFactory(factory)


def restore_log_filter():
    global _FACTORY, _PREVIOUS_FACTORY
    if _FACTORY is not None and logging.getLogRecordFactory() is _FACTORY:
        logging.setLogRecordFactory(_PREVIOUS_FACTORY)
    _FACTORY = _PREVIOUS_FACTORY = None


class RedactingStream:
    def __init__(self, stream):
        self.stream = stream
    def write(self, value):
        self.stream.write(safe_text(value))
        return len(value)
    def flush(self):
        return self.stream.flush()
    def __getattr__(self, name):
        return getattr(self.stream, name)


def install_console_filter():
    if _STREAMS:
        return
    for name in ["stdout", "stderr"]:
        original = getattr(sys, name)
        wrapper = RedactingStream(original)
        _STREAMS.append((name, original, wrapper))
        setattr(sys, name, wrapper)


def restore_console_filter():
    for name, original, wrapper in _STREAMS:
        if getattr(sys, name) is wrapper:
            setattr(sys, name, original)
    _STREAMS.clear()


def safe_route(path):
    route = str(path).split("?", 1)[0].split("#", 1)[0]
    patterns = [r"/(?:login|logout|getInfo|captchaImage)",
                r"/system/user(?:/(?:list|changeStatus|authRole|\d+))?",
                r"/system/role(?:/(?:list|changeStatus|dataScope|\d+|deptTree/\d+|authUser/allocatedList))?",
                r"/system/dept(?:/(?:list|\d+))?", r"/system/menu/list", r"/monitor/logininfor/list"]
    return route if any(re.fullmatch(pattern, route) for pattern in patterns) else "<未登记接口路径>"


NUMERIC = {"userId", "deptId", "roleId", "postId", "parentId", "menuId", "infoId", "operId", "pageNum", "pageSize", "total"}
ARRAYS = {"roleIds", "postIds", "menuIds", "deptIds", "checkedKeys"}
STATES = {"status", "sex", "dataScope", "delFlag"}
OWN_TEXT = {"userName", "nickName", "roleName", "roleKey", "deptName", "remark"}
PERMISSIONS = {"system:user:list", "system:user:query", "system:user:add", "system:user:edit", "*:*:*"}


def fields(data, tag):
    """只保留业务ID、状态及本例生成的标识，不保存联系方式或任意文本。"""
    if not isinstance(data, dict):
        return {}
    output = {}
    for key, value in data.items():
        if key in NUMERIC and (type(value) is int or value is None):
            output[key] = value
        elif key in ARRAYS and isinstance(value, list):
            output[key] = [x for x in value if type(x) is int][:100]
        elif key in STATES and str(value) in {"0", "1", "2", "3", "4", "5"}:
            output[key] = value
        elif key in {"menuCheckStrictly", "deptCheckStrictly", "captchaEnabled"} and type(value) is bool:
            output[key] = value
        elif key in OWN_TEXT:
            output[key] = value if value == "" or (tag and isinstance(value, str) and tag in value) else "<非本例文本未保存>"
        elif key == "perms" and isinstance(value, str) and value in PERMISSIONS:
            output[key] = value
        elif key in {"loginTime", "createTime", "beginTime", "endTime"} and isinstance(value, str):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:\+\d{2}:\d{2})?)?", value):
                output[key] = value
    return output


def response_excerpt(body, tag):
    if not isinstance(body, dict):
        return {"format": "non_object_json"}
    result = {"code": body.get("code") if type(body.get("code")) is int else None}
    if type(body.get("total")) is int:
        result["total"] = body["total"]
    if type(body.get("captchaEnabled")) is bool:
        result["captchaEnabled"] = body["captchaEnabled"]
    if "token" in body:
        result["token_present"] = isinstance(body["token"], str) and bool(body["token"])
    for name in ["user", "data"]:
        if isinstance(body.get(name), dict):
            result[name] = fields(body[name], tag)
    for name in ["rows", "data"]:
        if isinstance(body.get(name), list):
            result[name + "_count"] = len(body[name])
            result[name] = [fields(x, tag) for x in body[name][:100]]
            result[name + "_omitted_count"] = max(0, len(body[name]) - 100)
    for key in ARRAYS:
        if key in body:
            result.update(fields({key: body[key]}, tag))
    if isinstance(body.get("permissions"), list):
        result["permissions"] = [x for x in body["permissions"] if isinstance(x, str) and x in PERMISSIONS]
    if isinstance(body.get("roles"), list):
        result["roles"] = [fields(x, tag) for x in body["roles"][:30]]
    if "msg" in body:
        messages = {"操作成功", "查询成功", "没有权限，请联系管理员授权", "用户名或密码错误", "用户已封禁，请联系管理员", "验证码错误", "验证码已失效"}
        result["message_class"] = body["msg"] if isinstance(body["msg"], str) and body["msg"] in messages else "其他业务消息（原文未保存）"
    return result


def record_http(client, method, path, options, response, *, input_evidence=None, error_type=None):
    context = getattr(client, "evidence_context", None) or {}
    metadata = META.get()
    tag = context.get("batch_tag")
    event = client.events[-1] if client.events else {}
    route = safe_route(path)
    request = {"method": method, "path": route, "headers_recorded": False}
    params = options.get("params", {})
    if isinstance(params, dict):
        request["params"] = fields(params, tag)
        for key in ["orderByColumn", "isAsc"]:
            if isinstance(params.get(key), str) and params[key] in {"userId", "asc", "desc"}:
                request["params"][key] = params[key]
    if route in {"/login", "/captchaImage"}:
        request["body_recorded"] = False
    elif isinstance(options.get("json"), dict):
        request["json"] = fields(options["json"], tag)
        password = options["json"].get("password")
        if isinstance(password, str):
            request["password_length"] = len(password)
    if input_evidence:
        request["input_evidence"] = {k: v for k, v in input_evidence.items() if k != "password"}
    details = None
    if response is not None:
        try:
            body = response.json()
        except ValueError:
            body = None
        register_sensitive(body)
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        details = {"status_code": response.status_code,
                   "content_type": content_type if content_type in {"application/json", "text/html", "text/plain"} else "<未收录类型>",
                   "summary": response_excerpt(body, tag) if body is not None else {"format": "non_json", "body_recorded": False}}
    identifier = f"{tag or 'unbound'}_http_{len(client.events):04d}"
    value = {"event_id": identifier, "batch_tag": tag, "nodeid": metadata.get("nodeid"),
             "case_id": metadata.get("case_id"), "phase": metadata.get("phase", "outside_pytest"),
             "actor": client.actor, "at": event.get("at"), "completed_at": event.get("completed_at"),
             "request": request, "response_received": response is not None, "response": details}
    if error_type:
        value["error_type"] = error_type
    value = scrub(value)
    if RESULTS is not None and metadata.get("nodeid"):
        key = tag if isinstance(tag, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", tag) else ("case_" + hashlib.sha256(metadata["nodeid"].encode()).hexdigest()[:12])
        directory = RESULTS / "cases" / key
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "http.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")
    text = json.dumps(value, ensure_ascii=False)
    logging.getLogger("ruoyi.http").info(text)
    if metadata.get("nodeid"):
        allure.attach(text, name=f"HTTP {method} {route}（白名单摘要）", attachment_type=allure.attachment_type.JSON)
    return value


def sanitize_artifacts(results, extra_files=()):
    paths = [p for p in Path(results).rglob("*") if p.is_file() and p.suffix in {".json", ".jsonl", ".txt", ".log", ".xml"}]
    paths += [Path(p) for p in extra_files if p and Path(p).is_file()]
    changed = 0
    for path in dict.fromkeys(paths):
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            continue
        safe = safe_text(text)
        if path.name.endswith("-result.json"):
            value = json.loads(safe)
            value["parameters"] = [entry for entry in value.get("parameters", []) if entry.get("name") == "case_id"]
            safe = json.dumps(value, ensure_ascii=False)
        if safe != text:
            path.write_text(safe, encoding="utf-8")
            changed += 1
    return {"scanned_files": len(paths), "sanitized_files": changed}
