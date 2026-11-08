"""pytest可复用的真实业务流程。需要人工输入两次新验证码，自动登记并清理本批用户。"""

import argparse
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path
import secrets
import sys
import uuid
import requests

from .client import ApiClient, require_code, ResponseFormatError
from .config import PROJECT_ROOT, CONFIG_ROOT, load_config, read_json, save_json, PreparationError
from .interaction_utils import read_secret


def find_user(client, username):
    """列表筛选是模糊查询；读完分页后再次完整匹配，才动态提取ID。"""
    matches, seen = [], set()
    for page in range(1, 21):
        body = require_code(client.request("GET", "/system/user/list",
                            params={"userName": username, "pageNum": page, "pageSize": 50}))
        rows, total = body.get("rows"), body.get("total")
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise ResponseFormatError("用户列表字段无效")
        for row in rows:
            user_id = row.get("userId")
            if type(user_id) is not int or user_id <= 0 or user_id in seen:
                raise ResponseFormatError("用户列表ID无效或重复")
            seen.add(user_id)
            if row.get("userName") == username:
                matches.append(row)
        if len(seen) >= total:
            break
        if not rows:
            raise ResponseFormatError("分页提前为空，不能假装已经查全")
    else:
        raise ResponseFormatError("分页超出本节安全上限")
    if len(matches) > 1:
        raise ResponseFormatError("账号精确匹配多条")
    return matches[0] if matches else None


def login(client, username, password, private_dir):
    """每次登录新取验证码；答案由人输入，绝不读取Redis答案。"""
    captcha = require_code(client.request("GET", "/captchaImage"))
    payload = {"username": username, "password": password}
    if captcha.get("captchaEnabled", True):
        if not captcha.get("uuid") or not captcha.get("img"):
            raise ResponseFormatError("验证码响应缺少必要字段")
        image = private_dir / f"captcha_{client.actor}.png"
        image.write_bytes(base64.b64decode(captcha["img"], validate=True))
        # 此行只给出私有图片路径，便于查看；不打印uuid或答案。
        print(f"T74_CAPTCHA actor={client.actor} image={image}", flush=True)
        answer = read_secret(f"请输入{client.actor}本次验证码（数学题填结果）：", image_path=image)
        if not answer:
            raise PreparationError("验证码为空，未提交登录；重新运行会重新取图")
        payload.update({"uuid": captcha["uuid"], "code": answer})
    body = require_code(client.request("POST", "/login", json=payload))
    client.set_token(body.get("token"))
    identity = require_code(client.request("GET", "/getInfo"))
    user = identity.get("user", {})
    if user.get("userName") != username or type(user.get("userId")) is not int:
        raise ResponseFormatError("登录后的实际身份不符")
    return user


def owned_detail(admin, user_id, username):
    """清理前同时核对本批账号和备注，不能只拿一个ID就删除。"""
    body = require_code(admin.request("GET", f"/system/user/{user_id}"))
    user = body.get("data", {})
    if user.get("userId") != user_id or user.get("userName") != username or user.get("remark") != username:
        raise PreparationError("资源归属不符，停止清理并保留台账")
    return body


def run(config_path):
    cfg = load_config(config_path)
    scenario = read_json(CONFIG_ROOT / "user_template.json")
    stamp = datetime.now(timezone(timedelta(hours=8)))
    username = "t74" + stamp.strftime("%y%m%d%H%M%S") + uuid.uuid4().hex[:4]
    private_dir = PROJECT_ROOT / ".private/t74_runs" / username
    private_dir.mkdir(parents=True, exist_ok=False)
    evidence = PROJECT_ROOT / "evidence" / ("T74_" + username)
    evidence.mkdir(parents=True, exist_ok=False)
    events = []
    timeout = (cfg["connect_timeout"], cfg["read_timeout"])
    anonymous = ApiClient(cfg["base_url"], timeout, "anonymous", events)
    admin = ApiClient(cfg["base_url"], timeout, "admin", events)
    ordinary = ApiClient(cfg["base_url"], timeout, "new_user", events)
    # 成功取得ID立即写台账。即使POST响应不明确，也保留attempted用于回查。
    ledger = {"username": username, "attempted_create": False, "user_id": None,
              "user_deleted": False, "admin_logged_out": False, "new_user_logged_out": False}

    def persist():
        save_json(private_dir / "ledger.json", ledger)

    persist()
    primary_error, cleanup_errors = None, []
    completed = False
    try:
        # 未认证对照只能携带自己的匿名Session，不能误用管理员令牌。
        anonymous_body = require_code(anonymous.request("GET", "/getInfo"), 401)
        assert "user" not in anonymous_body, "匿名请求不应返回身份"
        admin_user = login(admin, cfg["admin_username"], cfg["admin_password"], private_dir)
        assert find_user(admin, cfg["admin_username"])["userId"] == admin_user["userId"], "只读查询身份不符"
        dept = require_code(admin.request("GET", f"/system/dept/{cfg['dept_id']}"))["data"]
        role = require_code(admin.request("GET", f"/system/role/{cfg['role_id']}"))["data"]
        assert dept["deptId"] == cfg["dept_id"] and dept["status"] == "0", "部门前置不符"
        assert role["roleId"] == cfg["role_id"] and role["status"] == "0" and role["dataScope"] == "3", "角色前置不符"
        assert find_user(admin, username) is None, "本批账号名已存在，停止创建"
        # 本轮口令只留在内存，满足6～20位规则，不进入输出或公开JSON。
        new_password = "T73a!" + secrets.token_hex(5)
        payload = {"userName": username, "nickName": scenario["nickName"],
                   "password": new_password, "deptId": cfg["dept_id"],
                   "roleIds": [cfg["role_id"]], "postIds": cfg["post_ids"],
                   "status": scenario["status"], "sex": scenario["sex"], "remark": username}
        ledger["attempted_create"] = True
        persist()
        require_code(admin.request("POST", "/system/user", json=payload))
        row = find_user(admin, username)
        assert row is not None, "创建后未查到本轮账号"
        ledger["user_id"] = row["userId"]
        persist()
        detail = owned_detail(admin, row["userId"], username)
        assert detail["data"]["deptId"] == cfg["dept_id"], "部门保存不符"
        assert detail["data"]["status"] == "0", "用户状态不符"
        assert set(detail["roleIds"]) == {cfg["role_id"]}, "角色关联不符"
        assert set(detail["postIds"]) == set(cfg["post_ids"]), "岗位关联不符"
        user = login(ordinary, username, new_password, private_dir)
        assert user["userId"] == ledger["user_id"] and user["deptId"] == cfg["dept_id"], "新用户身份或部门不符"
        own_row = find_user(ordinary, username)
        assert own_row and own_row["userId"] == ledger["user_id"], "新用户获准查询结果不符"
        completed = True
    except BaseException as error:
        # 仅在编排边界保存原失败，以便finally收尾；后面仍会重新抛出。
        primary_error = error
    finally:
        if ledger["attempted_create"] and admin.token:
            try:
                # 包括创建响应超时在内，都先按本批标记回查，绝不自动重发POST。
                row = find_user(admin, username)
                if row is not None:
                    user_id = row["userId"]
                    if ledger["user_id"] is not None and user_id != ledger["user_id"]:
                        raise PreparationError("清理ID与本批台账冲突")
                    ledger["user_id"] = user_id
                    persist()
                    owned_detail(admin, user_id, username)
                    require_code(admin.request("DELETE", f"/system/user/{user_id}"))
                assert find_user(admin, username) is None, "清理后账号仍可见"
                ledger["user_deleted"] = True
            except Exception as error:
                cleanup_errors.append(error)  # 保留错误并继续尝试会话收尾。
        for client, key in [(ordinary, "new_user_logged_out"), (admin, "admin_logged_out")]:
            try:
                had_token = bool(client.token)
                client.logout()
                # 没有创建过会话时记为None，不冒称执行了服务端退出。
                ledger[key] = True if had_token else None
            except Exception as error:
                cleanup_errors.append(error)
            finally:
                client.close()
        anonymous.close()
        persist()
        result = {"run_tag": username, "python_executable": sys.executable,
                  "requests_version": requests.__version__, "environment": cfg["environment"],
                  "base_url": cfg["base_url"], "normal_flow_completed": completed,
                  "resource": ledger, "primary_error_type": type(primary_error).__name__ if primary_error else None,
                  "cleanup_error_types": [type(e).__name__ for e in cleanup_errors],
                  "success": completed and primary_error is None and not cleanup_errors,
                  "http_request_count": len(events), "evidence_scope": "pytest正常链的Requests请求证据；pytest结果另见运行报告"}
        save_json(evidence / "request_events.json", events)
        save_json(evidence / "run_summary.json", result)
        print(f"T74_RESULT success={result['success']} evidence={evidence}", flush=True)
    errors = ([primary_error] if primary_error is not None else []) + cleanup_errors
    if errors:
        raise BaseExceptionGroup("本次练习失败，原失败和收尾失败分别保留", errors)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / ".private/t74.local.json")
    args = parser.parse_args()
    run(args.config)
