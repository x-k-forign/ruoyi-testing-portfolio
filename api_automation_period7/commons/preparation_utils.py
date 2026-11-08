"""公共夹具使用的辅助准备。目标业务动作仍由各自YAML执行。"""

from contextlib import contextmanager
import json

import allure

from .config import PreparationError
from .runner_utils import runner
from .business_utils import compensate_preparation


class ControlledPreparationFailure(PreparationError):
    """只用于已明确声明的创建流程中断用例，其他异常不按预期中断处理。"""


def perform(context, action, settings, title):
    """保留真实请求和中文前置步骤，不把辅助准备写成虚构的HTTP响应。"""
    context["_last_preparation_step"] = title
    with allure.step(title):
        runner(action, settings, context)


def request(context, method, path, token=None, *, params=None, payload=None, title="前置：发送请求"):
    settings = {"method": method, "url": "${base_url}" + path}
    if token:
        settings["headers"] = {"Authorization": "Bearer ${" + token + "}"}
    if params is not None:
        settings["params"] = params
    if payload is not None:
        settings["json"] = payload
    perform(context, "request", settings, title)


def check(context, body=None, **extra):
    perform(context, "response", {"status_code": 200, "json": {"code": 200, **(body or {})}, **extra},
            "前置：核对HTTP、业务状态和关键字段")


def extract_value(context, name, expression):
    perform(context, "extract", {name: ["json", expression]}, "前置：提取本次动态字段")


def login_identity(context, username, password, token_name, *, expected_user_id=None):
    request(context, "GET", "/captchaImage", title="前置：取得本次验证码（保持开启）")
    check(context)
    request(context, "POST", "/login", payload={"username": username, "password": password,
            "code": "${captcha_code}", "uuid": "${captcha_uuid}"}, title="前置：本身份使用独立会话登录")
    check(context, present=["token"])
    extract_value(context, token_name, "$.token")
    request(context, "GET", "/getInfo", token_name, title="前置：核对实际登录身份")
    expected = {"userName": username}
    if expected_user_id is not None:
        expected.update(userId=expected_user_id, deptId="${dept_id}")
    check(context, {"user": expected})


def prepare_admin(context):
    login_identity(context, "${admin_username}", "${admin_password}", "admin_token")
    extract_value(context, "admin_user_id", "$.user.userId")
    if type(context["admin_user_id"]) is not int or context["admin_user_id"] <= 0:
        raise PreparationError("管理员身份编号无效")


def prepare_creation_fields(context, *, maintainer=False):
    request(context, "GET", "/system/dept/${dept_id}", "admin_token", title="前置：确认目标部门有效")
    check(context, {"data": {"deptId": "${dept_id}", "status": "0"}})
    request(context, "GET", "/system/role/${role_id}", "admin_token", title="前置：确认查询角色及数据范围")
    check(context, {"data": {"roleId": "${role_id}", "status": "0", "dataScope": "3"}})
    if maintainer:
        request(context, "GET", "/system/role/${maintainer_role_id}", "admin_token", title="前置：确认维护角色有效")
        check(context, {"data": {"roleId": "${maintainer_role_id}", "status": "0"}})


class UserFactory:
    """function作用域资源工厂；每个创建意图都经既有归属保护及台账登记。"""
    def __init__(self, context):
        self.context = context

    def __repr__(self):
        return "<UserFactory: 仅管理本例账号>"

    def create(self, *, maintainer=False):
        context = self.context
        role = "${maintainer_role_id}" if maintainer else "${role_id}"
        if maintainer:
            prepare_creation_fields(context, maintainer=True)
        payload = {"userName": "${new_username}", "nickName": "${new_nickname}", "password": "${new_password}",
                   "deptId": "${dept_id}", "roleIds": [role], "postIds": "${post_ids}",
                   "status": "0", "sex": "2", "remark": "${batch_tag}"}
        request(context, "POST", "/system/user", "admin_token", payload=payload,
                title="前置：创建本例唯一专用账号，写入前登记清理意图")
        check(context)
        request(context, "GET", "/system/user/list", "admin_token",
                params={"userName": "${new_username}", "pageNum": 1, "pageSize": 20},
                title="前置：精确确认本例账号并取得动态ID")
        check(context, {"total": 1, "rows": [{"userName": "${new_username}", "remark": "${batch_tag}"}]})
        extract_value(context, "new_user_id", "$.rows[0].userId")
        request(context, "GET", "/system/user/${new_user_id}", "admin_token", title="前置：核对专用账号的实际关联")
        check(context, {"data": {"userId": "${new_user_id}", "userName": "${new_username}",
                       "nickName": "${new_nickname}", "deptId": "${dept_id}", "status": "0", "remark": "${batch_tag}"},
                       "roleIds": [role], "postIds": "${post_ids}"})
        return context["new_user_id"]


def prepare_subject_session(context, *, maintainer=False):
    token_name = "before_token" if maintainer else "user_token"
    login_identity(context, "${new_username}", "${new_password}", token_name, expected_user_id="${new_user_id}")
    check(context, contains={"$.permissions": ["system:user:list", "system:user:query"]},
          not_contains={"$.permissions": ["*:*:*"]})
    if maintainer:
        check(context, contains={"$.permissions": ["system:user:add"]})
    else:
        check(context, not_contains={"$.permissions": ["system:user:add"]})
        context["before_token"] = context["user_token"]


@contextmanager
def account_preparation_scope(context, factory):
    """try/finally覆盖全部准备过程；即使在yield前中断，也立即补偿已有资源。"""
    try:
        factory.create()
        prepare_subject_session(context)
        context["interrupted_admin_token"] = context["admin_token"]
        context["interrupted_user_token"] = context["user_token"]
        context["_preparation"].update(created_user_ids=[context["new_user_id"]],
                                       failure_point="after_account_and_session_ready", before_yield=True)
        raise ControlledPreparationFailure("受控中断：专用账号及会话已准备，后续准备在yield前中断")
        yield context  # 明确的中断点位于此行之前；不能依靠此行之后的普通代码清理。
    finally:
        compensate_preparation(context)


def prepare_interrupted(context, factory):
    """仅捕获本例声明的中断；清理错误或其他异常直接向pytest暴露。"""
    expected = context["_case"].get("_expected_preparation", {})
    if expected != {"error_type": "ControlledPreparationFailure", "failure_point": "after_account_and_session_ready", "before_yield": True}:
        raise PreparationError("本例没有准确声明预期准备中断，停止受控演练")
    with allure.step("验证指定的准备中断发生，并在yield前完成补偿清理"):
        observed = False
        try:
            with account_preparation_scope(context, factory):
                raise PreparationError("未观察到本例要求的准备中断")
        except ControlledPreparationFailure:
            observed = True
        if not observed:
            raise PreparationError("本例要求的受控中断没有发生")
        cleanup = list(context["_cleanup_latest"].values())
        sessions = [item for item in context["_session_cleanup"] if item["phase"] == "setup_compensation"
                    and item.get("logged_out") and item.get("old_token_rejected")]
        if len(cleanup) != 1 or not cleanup[0].get("absence_verified") or len(sessions) != 2:
            raise PreparationError("准备中断后的账号或原会话未完成补偿验证")
        context["_preparation"].update(status="compensated", controlled=True, expected_interruption_observed=True,
                                       error_type="ControlledPreparationFailure", deleted_user_count=1,
                                       post_cleanup_matches=0, original_sessions_invalidated=2)
        allure.attach(json.dumps(context["_preparation"], ensure_ascii=False, indent=2),
                      name="创建后准备中断与补偿清理（真实执行）", attachment_type=allure.attachment_type.JSON)
    # 新建独立管理会话做后续回查；被中断准备使用的两份旧令牌留给YAML验证401。
    with allure.step("补偿完成后，建立独立验证会话供YAML回查"):
        prepare_admin(context)


def assert_preparation(context, expected):
    """检验准备过程观测事实，不把测试端中断伪写成后端接口失败。"""
    if not isinstance(expected, dict) or not expected:
        raise ValueError("preparation须为非空结果约定")
    observed = context["_preparation"]
    for key, value in expected.items():
        if key not in observed or type(observed[key]) is not type(value) or observed[key] != value:
            raise AssertionError(f"准备中断或清理证据不符：{key}")
