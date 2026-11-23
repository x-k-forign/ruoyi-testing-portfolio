"""若依 UI 用例的专用用户准备、归属核对及收尾。"""

from dataclasses import dataclass, field
from functools import partial
import json
import os
from pathlib import Path
import secrets

import allure
import pytest

from commons.ruoyi_ui import RuoyiUi


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT.parent / "api_automation_period7" / ".private" / "t74.local.json"


def attach_json(data, name):
    allure.attach(json.dumps(data, ensure_ascii=False, indent=2), name, allure.attachment_type.JSON)


@dataclass
class UserCase:
    admin: RuoyiUi
    config_path: Path
    config: dict = field(repr=False)
    tc: str
    username: str = field(init=False)
    password: str = field(init=False, repr=False)
    nickname: str = field(init=False)
    marker: str = field(init=False)
    submission_attempted: bool = False
    user_id: int | None = None
    base_url: str = field(default_factory=lambda: os.environ.get("RUOYI_UI_BASE_URL", "http://127.0.0.1:5173/"))

    def __post_init__(self):
        prefix = self.tc.removeprefix("TC-").replace("-", "").lower()
        self.username = f"t9{prefix}{secrets.token_hex(6)}"
        self.password = "T9a!" + secrets.token_hex(6)
        self.nickname = f"T9.3 {self.username}"
        self.marker = f"{self.tc} {self.username}"

    def login_admin(self):
        self.admin.login(self.base_url, self.config["admin_username"], self.config["admin_password"], self.config_path)
        self.admin.verify_identity(self.config["admin_username"])

    def associations(self):
        role_name = self.admin.role_name(self.config["role_id"])
        self.admin.open_users()
        dept_name, ancestors = self.admin.department_path(self.config["dept_id"])
        self.admin.search(self.username)
        self.admin.wait_for_empty_users()
        return dept_name, ancestors, role_name

    def create_user(self, ancestors, role_name, *, actor=None):
        actor = self.admin if actor is None else actor
        actor.activate()
        actor.prepare_new_user(
            self.username, self.nickname, self.password, self.marker, self.config["dept_id"], ancestors, role_name,
        )
        self.submission_attempted = True
        actor.save_new_user()

    def register_saved_user(self):
        self.admin.activate()
        self.admin.search(self.username)
        rows = self.admin.wait_for_user(self.username)
        assert len(rows) == 1, "应只查到一条本轮用户记录"
        actual_id = int(rows[0]["用户编号"])
        assert actual_id > 1, "本轮用户编号异常"
        self.user_id = actual_id
        return rows[0]

    def cleanup(self):
        with allure.step("按本轮标记和实际用户编号清理，重新搜索确认"):
            try:
                self._cleanup()
            except Exception as error:
                self._cleanup_evidence("清理失败", 错误类型=type(error).__name__)
                raise

    def _cleanup(self):
        if not self.submission_attempted:
            self._cleanup_evidence("未尝试提交新增")
            return

        self.admin.activate()
        self.admin.dismiss_user_overlays()
        self.admin.open_users()
        self.admin.search(self.username)
        matches = self.admin.exact_users(self.username)
        if not matches:
            self.admin.wait_for_empty_users()
            self._cleanup_evidence("已回查，无本轮记录")
            return

        assert len(matches) == 1, "必须只匹配一条本轮用户记录"
        row = matches[0]
        actual_id = int(row["用户编号"])
        assert actual_id > 1 and self.user_id in (None, actual_id), "清理目标用户编号与本轮记录不符"
        assert row["用户昵称"] == self.nickname, "清理目标昵称与本轮标记不符"
        details = self.admin.user_details(self.username, labels=("登录账号", "备注"))
        assert details == {"登录账号": self.username, "备注": self.marker}, "清理目标详情与本轮标记不符"

        self.user_id = actual_id
        self.admin.delete_user(self.username, actual_id)
        self.admin.search(self.username)
        self.admin.wait_for_empty_users()
        assert not self.admin.exact_users(self.username), "清理后仍能查到本轮用户"
        self._cleanup_evidence("按编号删除并重新搜索，无记录")

    def _cleanup_evidence(self, result, **extra):
        attach_json({"用户名": self.username, "用户编号": self.user_id, "清理结果": result, **extra}, "专用数据收尾")


def finish_identity(ui, identity, capture_ui_failure):
    try:
        logged_out = ui.logout_if_authenticated()
        result = "已退出并返回登录页" if logged_out else "浏览器当前没有已登录菜单"
        attach_json({"角色": identity, "退出结果": result}, "会话收尾")
    except Exception as error:
        attach_json({"角色": identity, "退出结果": "注销失败", "错误类型": type(error).__name__}, "会话收尾")
        capture_ui_failure(ui.browser, identity, "teardown")
        raise


def _load_settings():
    config_path = Path(os.environ.get("RUOYI_UI_CONFIG", DEFAULT_CONFIG))
    try:
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        credentials = (config["admin_username"], config["admin_password"])
        associations = (config["dept_id"], config["role_id"])
        if not all(isinstance(value, str) and value for value in credentials):
            raise ValueError
        if not all(type(value) is int and value > 0 for value in associations):
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        pass
    else:
        return config_path, config
    pytest.fail("无法使用私有测试配置，请核对 RUOYI_UI_CONFIG 以及管理员、部门和角色字段", pytrace=False)


@pytest.fixture
def ui_settings():
    return _load_settings()


@pytest.fixture
def open_ui_identity(new_browser, request, capture_ui_failure):
    def open_identity(identity):
        ui = RuoyiUi(new_browser(implicit_wait=0, identity=identity))
        request.addfinalizer(partial(attach_json, ui.locators, f"{identity} DOM 定位唯一性"))
        request.addfinalizer(partial(finish_identity, ui, identity, capture_ui_failure))
        return ui

    return open_identity


@pytest.fixture
def make_user_case(open_ui_identity, request, ui_settings, capture_ui_failure):
    """每例共用一个管理员会话，每个专用账号提前登记独立清理。"""
    config_path, base_config = ui_settings
    admin = None

    def create_case(tc, *, dept_id=None, role_id=None):
        nonlocal admin
        if admin is None:
            admin = open_ui_identity("管理员")
        config = {
            **base_config,
            "dept_id": base_config["dept_id"] if dept_id is None else dept_id,
            "role_id": base_config["role_id"] if role_id is None else role_id,
        }
        case = UserCase(admin, config_path, config, tc)
        def cleanup():
            try:
                case.cleanup()
            except Exception:
                capture_ui_failure(admin.browser, "管理员", "teardown")
                raise

        request.addfinalizer(cleanup)
        return case

    return create_case
