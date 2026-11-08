"""本轮业务资源与独立会话：只管理本例生成的账号，异常后仍尝试回查和清理。"""

from datetime import datetime, timedelta, timezone
import json
import secrets
import uuid

import allure

from .client import ApiClient, require_code
from .config import PROJECT_ROOT, PreparationError, save_json
from .stage import CURRENT_STAGE, STAGE_KEY, TAG_PREFIX

LOCAL_ZONE = timezone(timedelta(hours=8))


def business_variables(cfg):
    """只生成内存数据，不访问接口；每条用例有自己的短账号和资源标记。"""
    tag = TAG_PREFIX + uuid.uuid4().hex[:12]
    return {
        "batch_tag": tag, "new_username": tag + "u", "allowed_username": tag + "a",
        "denied_username": tag + "d", "new_nickname": STAGE_KEY + "_" + tag,
        "new_password": "T74a!" + secrets.token_hex(5),
        "wrong_password": "Wrong!" + secrets.token_hex(5),
        "password_5": "T7a!1", "password_6": "T74a!1",
        "password_20": "T74a!" + secrets.token_hex(7) + "Z",
        "password_21": "T74a!" + secrets.token_hex(8),
        # 项目已有维护角色为102；YAML会先读取角色并确认有效，不修改共享角色。
        "maintainer_role_id": cfg.get("maintainer_role_id", 102),
        "_admin_username": cfg["admin_username"], "_clients": [], "_retired_sessions": [],
        "_owned_users": {}, "_case": {}, "_steps_completed": False, "_case_error_type": None,
        "_input_evidence": [],
        "_stage": CURRENT_STAGE, "_preparation": {"status": "not_started"}, "_setup_error_type": None,
        "_cleanup_latest": {}, "_cleanup_history": [], "_session_cleanup": [],
        "_allowed_usernames": set(), "_owned_roles": {}, "_owned_departments": {},
        "_permission_resources": None, "_permission_matrix": {}, "_resource_cleanup": [], "_restorations": [],
        "_collections": [], "_page_collection": None, "_set_checks": [], "_checkpoints": {},
        "_pending_requirement": None, "_business_verdict": None,
        "_last_assertion": {},
    }


def send(client, method, path, **options):
    """生命周期中的回查同样保留脱敏HTTP证据，不覆盖 YAML 的当前响应。"""
    response = client.request(method, path, **options)
    return response


def select_client(context, method, path, options):
    """每次登录新建Session；其他请求根据显式Bearer令牌选择对应会话。"""
    if method == "POST" and path == "/login":
        # 登录请求不继承管理员头；失败登录后的无凭证请求也一直使用匿名会话。
        if any(str(key).lower() == "authorization" for key in options.get("headers", {})):
            raise PreparationError("登录请求不应携带其他身份的Authorization头")
        username = options.get("json", {}).get("username")
        allowed = {context["_admin_username"], context["new_username"],
                   context["allowed_username"], context["denied_username"], *context["_allowed_usernames"]}
        if username not in allowed:
            raise PreparationError("本批登录仅使用配置管理员或本例生成的账号")
        anonymous = context["_client"]
        actor = ("管理员" if username == context["_admin_username"] else "本例用户") + f"#{len(context['_clients'])+1}"
        client = ApiClient(anonymous.base_url, anonymous.timeout, actor, context["_events"])
        client.evidence_context = context
        context["_clients"].append((username, client))
        context["login_begin_time"] = datetime.now(LOCAL_ZONE).strftime("%Y-%m-%d %H:%M:%S")
        return client
    authorization = next((value for key, value in options.get("headers", {}).items()
                          if str(key).lower() == "authorization"), None)
    for _, client in reversed(context["_clients"]):
        if client.token and authorization == "Bearer " + client.token:
            return client
    return context["_client"]


def admin_client(context):
    for username, client in reversed(context["_clients"]):
        if username == context["_admin_username"] and client.token:
            return client
    raise PreparationError("缺少本条用例的有效管理员会话，资源台账已保留")


def persist_ledger(context):
    # 账号是本批测试数据；不把口令、令牌、验证码或完整响应写入台账。
    save_json(PROJECT_ROOT / ".private/yaml_runs" / context["batch_tag"] / "ledger.json",
              {"batch_tag": context["batch_tag"], "case_source": context["_case"].get("_source"),
               "users": list(context["_owned_users"].values()),
               "roles": list(context["_owned_roles"].values()), "departments": list(context["_owned_departments"].values())})


def capture_password_input(context, method, path, options):
    """在变量替换后、请求发送前实测长度；设计长度与实测长度不符就停止写入。"""
    expected = context["_case"].get("_input_expectations", {})
    if method != "POST" or path != "/system/user" or "password_length" not in expected:
        return None
    password = options.get("json", {}).get("password")
    actual = len(password) if isinstance(password, str) else None
    ascii_only = isinstance(password, str) and password.isascii()
    limits = expected["allowed_password_length"]
    valid = actual == expected["password_length"] and (ascii_only or not expected.get("ascii_only", True))
    record = {"request_step": context.get("_last_step", {}).get("number"), "method": method, "path": path,
              "password": "***", "actual_password_length": actual, "expected_input_length": expected["password_length"],
              "ascii_only": ascii_only, "input_contract_passed": valid, "allowed_length_range": limits,
              "within_allowed_range": actual is not None and limits[0] <= actual <= limits[1],
              "measurement_source": "变量替换后的实际请求参数，在发送前计算len(password)",
              "measured_at": datetime.now(LOCAL_ZONE).isoformat(), "http_response_received": False}
    context["_input_evidence"].append(record)
    with allure.step(f"发送前核对创建密码：实测{actual}位，设计{expected['password_length']}位"):
        before_send = {key: value for key, value in record.items() if key != "http_response_received"}
        allure.attach(json.dumps(before_send, ensure_ascii=False, indent=2), name="创建密码输入长度（运行时实测）",
                      attachment_type=allure.attachment_type.JSON)
        if not valid:
            raise PreparationError(f"测试输入长度不符：设计{expected['password_length']}位、实际{actual}位；未发送创建请求")
    return record


def remember_owned_response(context, response):
    """列表或详情读到本批ID后立即登记；不保存完整响应或密码字段。"""
    try:
        body = response.json()
    except ValueError:
        return  # 无法解析的响应仍由随后显式断言报告，创建意图已经登记。
    if not isinstance(body, dict):
        return
    rows = body.get("rows", [])
    rows = list(rows) if isinstance(rows, list) else []
    if isinstance(body.get("data"), dict):
        rows.append(body["data"])
    changed = False
    for user in rows:
        if not isinstance(user, dict):
            continue
        entry = context["_owned_users"].get(user.get("userName"))
        user_id = user.get("userId")
        if (entry is not None and user.get("remark") == context["batch_tag"]
                and user.get("nickName") == context["new_nickname"]
                and type(user_id) is int and user_id > 0 and user_id not in entry["ids"]):
            entry["ids"].append(user_id)
            entry["creation_observed"] = True
            entry["state"] = "created"
            changed = True
    if changed:
        persist_ledger(context)


def find_rows(context, username):
    """列表是模糊查询，读完分页后精确匹配；空用户名按本批备注查找。"""
    client, result, seen = admin_client(context), [], set()
    for page in range(1, 21):
        params = {"pageNum": page, "pageSize": 100}
        if username:
            params["userName"] = username
        body = require_code(send(client, "GET", "/system/user/list", params=params))
        rows, total = body.get("rows"), body.get("total")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise PreparationError("资源回查的用户列表格式不正确")
        for row in rows:
            user_id = row.get("userId")
            if type(user_id) is not int or user_id <= 0 or user_id in seen:
                raise PreparationError("资源回查的用户编号无效或分页重复")
            seen.add(user_id)
            if username:
                if row.get("userName") == username:
                    result.append(row)
            elif row.get("remark") == context["batch_tag"]:
                result.append(row)
        if len(seen) >= total:
            return result
        if not rows:
            raise PreparationError("用户分页提前为空，无法确认资源状态")
    raise PreparationError("用户回查超过20页，保留台账供检查")


def owned_detail(context, row):
    user_id = row.get("userId")
    response = send(admin_client(context), "GET", f"/system/user/{user_id}")
    body = require_code(response)
    user = body.get("data")
    if (not isinstance(user, dict) or user.get("userId") != user_id
            or user.get("remark") != context["batch_tag"]
            or user.get("nickName") != context["new_nickname"]
            or user.get("userName") not in context["_owned_users"]):
        raise PreparationError("账号归属与本批标记不符，停止修改或删除该对象")
    remember_owned_response(context, response)
    return body


def guard_write(context, method, path, options):
    """写入前登记意图；即使超时或断言失败，也知道应按什么标记回查。"""
    if method in {"POST", "PUT", "PATCH", "DELETE"} and path.startswith(("/system/role", "/system/dept")):
        resources = context["_permission_resources"]
        if resources is None:
            raise PreparationError("角色和部门写入须先建立本例资源夹具")
        resources.guard(method, path, options)
    if method == "POST" and path == "/system/user":
        payload = options.get("json", {})
        username = payload.get("userName")
        allowed = {"", context["new_username"], context["allowed_username"], context["denied_username"], *context["_allowed_usernames"]}
        if (username not in allowed or payload.get("remark") != context["batch_tag"]
                or payload.get("nickName") != context["new_nickname"]):
            raise PreparationError("新增请求必须使用本例生成的账号、昵称和资源标记")
        if username not in context["_owned_users"]:
            if username and find_rows(context, username):
                raise PreparationError("本批随机账号名已经存在，停止创建")
            context["_owned_users"][username] = {"username": username, "attempted": True,
                                               "attempted_at": datetime.now(LOCAL_ZONE).isoformat(),
                                               "ids": [], "creation_observed": False,
                                               "state": "attempted", "deleted": False}
        persist_ledger(context)
    elif method in {"PUT", "PATCH", "DELETE"} and path.startswith("/system/user"):
        # 本批只修改单个已登记账号，不支持拿任意历史ID或批量ID写入。
        if method == "DELETE":
            raw_id = path.rsplit("/", 1)[-1]
            if not raw_id.isdigit():
                raise PreparationError("本批仅允许删除一个已核对归属的用户ID")
            user_id = int(raw_id)
        else:
            user_id = options.get("json", {}).get("userId", options.get("params", {}).get("userId"))
        if type(user_id) is not int or user_id <= 0:
            raise PreparationError("修改请求缺少有效的本批用户ID")
        detail = owned_detail(context, {"userId": user_id})
        if method != "DELETE" and context["_permission_resources"] is not None:
            context["_permission_resources"].remember_user_before_change(detail)


def assert_owned_count(context, expected):
    """拒绝场景的独立回查：不把“返回拒绝”直接等同于“没有写入”。"""
    if type(expected) is not int or expected < 0:
        raise ValueError("owned_users应为非负整数")
    actual = 0
    for username, entry in context["_owned_users"].items():
        for row in find_rows(context, username):
            owned_detail(context, row)
            actual += 1
            if row["userId"] not in entry["ids"]:
                entry["ids"].append(row["userId"])
    persist_ledger(context)
    if actual != expected:
        raise AssertionError(f"本批账号回查不符：预期{expected}个，实际{actual}个")


def cleanup_owned_users(context, *, phase="teardown"):
    """逐项回查本例资源，区分没有创建、已删除和状态不明确；错误聚合后抛出。"""
    errors = []
    for username, entry in context["_owned_users"].items():
        deleted_now = False
        try:
            with allure.step("按本批账号及标记核对归属，删除并回查"):
                for row in find_rows(context, username):
                    owned_detail(context, row)
                    require_code(send(admin_client(context), "DELETE", f"/system/user/{row['userId']}"))
                    deleted_now = True
                if find_rows(context, username):
                    raise AssertionError("清理后仍能查到本例账号")
                observed = bool(entry["ids"])
                state = "deleted" if deleted_now else ("already_absent" if observed else "not_created")
                entry.update(state=state, creation_observed=observed, deleted=observed, absence_verified=True)
                event = {"username": username, "user_ids": list(entry["ids"]), "phase": phase,
                         "creation_observed": observed, "delete_requested": deleted_now,
                         "cleanup_state": state, "deleted": observed, "post_cleanup_matches": 0,
                         "absence_verified": True, "deletion_verified": observed}
        except Exception as error:
            entry.update(state="cleanup_failed", absence_verified=False)
            errors.append(error)
            event = {"username": username, "user_ids": list(entry["ids"]), "phase": phase,
                     "cleanup_state": "cleanup_failed", "absence_verified": False,
                     "error_type": type(error).__name__}
        context["_cleanup_latest"][username] = event
        context["_cleanup_history"].append(event)
        try:
            persist_ledger(context)
        except Exception as error:
            errors.append(error)
    if errors:
        raise ExceptionGroup("本例账号清理或台账保存失败", errors)


def logout_clients(context, *, phase="teardown"):
    """逐个退出并核对旧令牌，不因一个失败而跳过其他会话；只记录安全状态。"""
    errors = []
    for _, client in reversed(context["_clients"]):
        try:
            if client.token:
                with allure.step("退出本例会话并核对原令牌失效"):
                    client.logout()
                context["_session_cleanup"].append({"actor": client.actor, "phase": phase,
                                                     "logged_out": True, "old_token_rejected": True,
                                                     "session_fingerprint": client.session_fingerprint})
        except Exception as error:
            errors.append(error)
            context["_session_cleanup"].append({"actor": client.actor, "phase": phase,
                                                 "logged_out": False, "error_type": type(error).__name__,
                                                 "session_fingerprint": client.session_fingerprint})
        finally:
            client.close()
    for client, token in context["_retired_sessions"]:
        try:
            body = require_code(send(context["_client"], "GET", "/getInfo",
                                     headers={"Authorization": f"Bearer {token}"}), 401)
            if "user" in body:
                raise AssertionError("显式退出后的旧令牌仍返回身份")
            context["_session_cleanup"].append({"actor": client.actor, "phase": phase,
                                                 "logged_out": True, "old_token_rejected": True,
                                                 "session_fingerprint": client.session_fingerprint})
        except Exception as error:
            errors.append(error)
    context["_retired_sessions"].clear()
    if errors:
        raise ExceptionGroup("本例部分会话退出或令牌回查失败", errors)


def compensate_preparation(context):
    """准备函数尚未yield时也能补偿；账号清理和会话退出的错误都保留。"""
    errors = []
    for action in (cleanup_owned_users, logout_clients):
        try:
            action(context, phase="setup_compensation")
        except Exception as error:
            errors.append(error)
    if errors:
        raise ExceptionGroup("准备中断后的补偿清理未完成", errors)


def finish_context(context):
    """父fixture提前登记的finalizer：准备、执行失败均收尾，并保存各阶段证据。"""
    errors = []
    try:
        resources = context["_permission_resources"]
        actions = ([lambda _: resources.restore()] if resources is not None else [])
        actions += [cleanup_owned_users]
        if resources is not None:
            actions += [lambda _: resources.cleanup()]
        actions += [logout_clients]
        for action in actions:
            try:
                action(context)
            except Exception as error:
                errors.append(error)
    finally:
        for _, client in context["_clients"]:
            client.close()
        context["_client"].close()
        case = context["_case"]
        summary = {"batch_tag": context["batch_tag"], "case_name": case.get("name"),
                   "stage": context["_stage"], "case_id": case.get("_id"),
                   "case_source": case.get("_source"), "source_tcs": case.get("_source_tcs", []),
                   "origin_source": case.get("_origin_source", case.get("_source")),
                   "known_issue": case.get("_known_issue", ""),
                   "case_kind": "assertion_copy" if case.get("_assertion_copy") else "business",
                   "exercise": case.get("_exercise", {}),
                   "business_steps_completed": context["_steps_completed"],
                   "business_error_type": context["_case_error_type"],
                   "last_step": context.get("_last_step"), "cleanup_ok": not errors,
                   "nodeid": context.get("_nodeid"), "last_assertion": context["_last_assertion"],
                   "preparation": context["_preparation"], "setup_error_type": context["_setup_error_type"],
                   "scenario": case.get("_scenario", {}),
                   "cleanup": list(context["_cleanup_latest"].values()), "cleanup_history": context["_cleanup_history"],
                   "session_cleanup": context["_session_cleanup"],
                   "cleanup_error_types": [type(e).__name__ for e in errors],
                   "http_request_count": len(context["_events"]), "http_events": context["_events"],
                   "captcha": context["_captcha_evidence"], "input_evidence": context["_input_evidence"],
                   "permission_matrix": context["_permission_matrix"], "collections": context["_collections"],
                   "set_checks": context["_set_checks"], "checkpoints": context["_checkpoints"],
                   "pending_requirement": context["_pending_requirement"], "business_verdict": context["_business_verdict"],
                   "resource_cleanup": context["_resource_cleanup"], "restorations": context["_restorations"]}
        try:
            directory = context.get("_evidence_dir", PROJECT_ROOT / ".local/lifecycle_evidence" / context["batch_tag"])
            save_json(directory / "run_summary.json", summary)
        except Exception as error:
            errors.append(error)
        finally:
            context.clear()
    if errors:
        raise ExceptionGroup("本条用例清理或证据保存失败；原测试失败由pytest另行保留", errors)
