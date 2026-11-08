"""执行 request → response → extract；每条用例使用自己的 my_var 和 Session。"""

from datetime import datetime, timedelta
import time

import allure

from .assert_utils import assert_response
from .client import ApiClient, json_body
from .extract_utils import extract
from .safe_evidence import register_sensitive
from .variable_utils import replace_variables, check_name
from .permission_assertions import (request_all_pages, assert_user_ids, capture_checkpoint, assert_checkpoints)
from .captcha_utils import prepare_login_input, refresh_captcha
from .business_utils import (LOCAL_ZONE, business_variables, select_client, guard_write,
                             assert_owned_count, remember_owned_response, finish_context, capture_password_input)


class CaseVariables(dict):
    def __repr__(self):
        # pytest 失败展示函数参数时，不把实际 token、密码放进报告。
        return "<CaseVariables: 本条用例独立变量，敏感值不展示>"


def create_context(cfg, actor="yaml_case"):
    events = []
    client = ApiClient(cfg["base_url"], (cfg["connect_timeout"], cfg["read_timeout"]), actor, events)
    try:
        context = CaseVariables(base_url=cfg["base_url"], admin_username=cfg["admin_username"],
                                dept_id=cfg["dept_id"], role_id=cfg["role_id"], post_ids=cfg["post_ids"],
                                resp=None, _client=client, _events=events)
        context.update(business_variables(cfg))
        context["_captcha_settings"] = cfg.get("_captcha_settings", {"mode": "manual", "max_attempts": 3})
        context["_captcha_evidence"] = {"mode": context["_captcha_settings"]["mode"], "enabled": None,
                                      "answers_read": 0, "refreshes": 0, "login_retries": 0}
        client.evidence_context = context
        register_sensitive(cfg)
    except BaseException:
        client.close()
        raise
    return context


def login_request(context, original_settings, options):
    """只有自动正确验证码登录才限次刷新；密码错误、禁用及权限失败不重试。"""
    payload = original_settings.get("json", {})
    automatic = (context["_captcha_settings"]["mode"] == "redis"
                 and payload.get("code") == "${captcha_code}" and payload.get("uuid") == "${captcha_uuid}")
    attempts = context["_captcha_settings"]["max_attempts"] if automatic else 1
    for attempt in range(attempts):
        client = select_client(context, "POST", "/login", options)
        response = client.request("POST", "/login", **options)
        body = json_body(response)
        token = body.get("token")
        if isinstance(token, str) and token:
            client.set_token(token)
        context["login_end_time"] = (datetime.now(LOCAL_ZONE) + timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S")
        retryable = (automatic and response.status_code == 200 and body.get("code") == 500
                     and body.get("msg") in {"验证码错误", "验证码已失效"} and not token)
        if not retryable or attempt + 1 == attempts:
            return response, client
        with allure.step("验证码校验未成功，限次刷新后重新登录"):
            context["_captcha_evidence"]["login_retries"] += 1
            refresh_captcha(context)
            prepare_login_input(context, original_settings)
            resolved = replace_variables(original_settings, context)
            options = {key: value for key, value in resolved.items() if key not in {"method", "url", "poll"}}


def request_with_poll(client, method, path, options, poll, input_evidence=None):
    """只有YAML显式声明的只读GET才能轮询；写操作从不自动重发。"""
    attempts, interval, until = 1, 0, None
    if poll is not None:
        if (method != "GET" or not isinstance(poll, dict)
                or set(poll) != {"attempts", "interval", "until"}):
            raise ValueError("poll仅用于GET，须填写attempts、interval、until")
        attempts, interval, until = poll["attempts"], poll["interval"], poll["until"]
        if (type(attempts) is not int or not 1 <= attempts <= 10
                or type(interval) not in (int, float) or not 0 <= interval <= 2
                or not isinstance(until, dict) or "owned_users" in until):
            raise ValueError("轮询次数须1～10、间隔须0～2秒，until只填写响应断言")
    for index in range(attempts):
        response = client.request(method, path, _input_evidence=input_evidence, **options)
        if until is None:
            return response
        # 认证错误和服务错误立即交给后续response判断，不把它们当日志延迟重试。
        body = json_body(response)
        if response.status_code != 200 or body.get("code") != 200:
            return response
        try:
            assert_response(response, until)
            return response
        except AssertionError:
            if index + 1 == attempts:
                return response  # 最后的真实响应仍由显式response步骤判定。
            time.sleep(interval)


def runner(k, v, my_var):
    """与笔记一致的三个分支；请求结果和提取值都保存回 my_var。"""
    if not isinstance(v, dict) or not v:
        raise ValueError("步骤配置必须是非空字典")
    original_settings = v
    if k == "request" and v.get("method", "").upper() == "POST" and v.get("url", "").rstrip("/").endswith("/login"):
        prepare_login_input(my_var, v)
    v = replace_variables(v, my_var)
    match k:
        case "request":
            if set(v) - {"method", "url", "headers", "params", "json", "data", "poll", "pagination"}:
                raise ValueError("request 含不支持的字段；超时由环境配置统一控制")
            anonymous = my_var["_client"]
            method = v["method"].upper()
            if method not in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}:
                raise ValueError("不支持的 HTTP 方法")
            url = v["url"]
            # 只允许本例明确选择的后端；不能通过变量误发到其他环境。
            if url.startswith("/"):
                path = url
            elif url.startswith(anonymous.base_url + "/"):
                path = url[len(anonymous.base_url):]
            else:
                raise ValueError("请求地址必须属于当前配置的本机后端")
            options = {key: value for key, value in v.items() if key not in {"method", "url", "poll", "pagination"}}
            my_var["_page_collection"] = None  # 集合只能属于本次请求，不能误用前一份管理员基准。
            input_evidence = capture_password_input(my_var, method, path, options)
            guard_write(my_var, method, path, options)
            # 登录要在任何报告处理之前登记令牌，避免断言或记录失败时漏掉退出。
            if path == "/login" and method == "POST":
                if "poll" in v:
                    raise ValueError("登录请求不允许自动重试")
                resp, client = login_request(my_var, original_settings, options)
            else:
                client = select_client(my_var, method, path, options)
                if "pagination" in v:
                    if "poll" in v:
                        raise ValueError("完整分页与轮询不能同时使用")
                    resp = request_all_pages(client, method, path, options, v["pagination"], my_var)
                else:
                    resp = request_with_poll(client, method, path, options, v.get("poll"), input_evidence=input_evidence)
            my_var["resp"] = resp
            my_var["_last_request_actor"] = client.actor
            if method == "GET" and path.startswith("/system/user"):
                remember_owned_response(my_var, resp)
            if path == "/captchaImage" and method == "GET":
                my_var["_captcha"] = json_body(resp)
            # 立即登记已取得的会话，后续断言或提取失败时 fixture 仍能退出。
            if path == "/login" and method == "POST":
                my_var.pop("_captcha", None)
                my_var.pop("captcha_code", None)
                my_var.pop("captcha_uuid", None)
            if path == "/logout" and method == "POST" and resp.status_code == 200 and json_body(resp).get("code") == 200:
                if client.token:
                    my_var["_retired_sessions"].append((client, client.token))
                client.token = None
                client.session.headers.pop("Authorization", None)
        case "response":
            if my_var.get("resp") is None:
                raise ValueError("尚无响应，请先执行 request")
            try:
                actual = my_var["resp"].json()
            except ValueError:
                actual = {}
            my_var["_last_assertion"] = {"expected_http": v.get("status_code"),
                "actual_http": my_var["resp"].status_code,
                "expected_business_code": v.get("json", {}).get("code"),
                "actual_business_code": actual.get("code") if isinstance(actual, dict) else None,
                "checkpoints": v.get("checkpoints", [])}
            # owned_users是本批资源的独立分页回查，不是服务端返回的JSON字段。
            rules = {key: value for key, value in v.items() if key not in {"owned_users", "preparation", "user_ids", "checkpoint", "checkpoints"}}
            if rules:
                assert_response(my_var["resp"], rules)
            if "owned_users" in v:
                assert_owned_count(my_var, v["owned_users"])
            if "preparation" in v:
                from .preparation_utils import assert_preparation
                assert_preparation(my_var, v["preparation"])
            if "user_ids" in v:
                assert_user_ids(my_var, v["user_ids"])
            if "checkpoint" in v:
                capture_checkpoint(my_var, v["checkpoint"])
            if "checkpoints" in v:
                assert_checkpoints(my_var, v["checkpoints"])
        case "extract":
            if my_var.get("resp") is None:
                raise ValueError("尚无响应，请先执行 request")
            for var_name, var_exp in v.items():
                check_name(var_name)
                if not isinstance(var_exp, list) or len(var_exp) != 2 or any(not isinstance(item, str) for item in var_exp):
                    raise ValueError("extract 的值应为 [json/headers/text/xpath, 表达式]")
                if var_exp[0] == "pages":
                    collection = my_var.get("_page_collection")
                    if not collection or var_exp[1] not in {"rows", "ids"}:
                        raise ValueError("pages只提取本次已完整收集的rows或ids")
                    my_var[var_name] = collection[var_exp[1]]
                else:
                    my_var[var_name] = extract(my_var["resp"], *var_exp)
        case _:
            raise ValueError("未知操作，仅支持 request、response、extract")


def execute_case(case, my_var):
    names = {"request": "发送请求", "response": "断言响应", "extract": "提取变量"}
    my_var["_case"] = case
    try:
        for index, step in enumerate(case["steps"], 1):
            action, settings = next(iter(step.items()))
            my_var["_last_step"] = {"number": index, "action": action}
            with allure.step(f"第{index}步：{names[action]}"):
                runner(action, settings, my_var)
        my_var["_steps_completed"] = True
        if my_var["_pending_requirement"]:
            import pytest
            my_var["_business_verdict"] = "pending_requirement"
            allure.dynamic.label("business_verdict", "待确认（已实际执行）")
            pytest.skip("已执行A/B请求并留证；业务规则待确认：" + my_var["_pending_requirement"])
        my_var["_business_verdict"] = "passed"
    except BaseException as error:
        my_var["_case_error_type"] = type(error).__name__
        if my_var["_business_verdict"] != "pending_requirement":
            my_var["_business_verdict"] = "failed"
        raise


def close_context(my_var):
    """公共fixture统一收尾；业务失败和清理失败分别保留。"""
    finish_context(my_var)
