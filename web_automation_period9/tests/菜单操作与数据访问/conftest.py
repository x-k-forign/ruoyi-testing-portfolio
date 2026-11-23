"""T9.4 权限对照的专用身份和可比较的基准数据。"""

import json

import allure
import pytest


class PermissionScenario:
    def __init__(self, tc, make_user_case, open_identity, config):
        self.tc = tc
        self.make_user_case = make_user_case
        self.open_identity = open_identity
        self.dept_a = config["dept_id"]
        self.dept_b = config.get("dept_b_id", 204)
        self.query = config["role_id"]
        self.maintainer = config.get("maintainer_role_id", 102)
        assert all(type(value) is int and value > 0 for value in (self.dept_a, self.dept_b, self.query, self.maintainer))
        assert self.dept_a != self.dept_b and self.query != self.maintainer
        self.admin = None
        self.roles = {}
        self.departments = {}

    def record(self, name, **evidence):
        allure.attach(json.dumps(evidence, ensure_ascii=False, indent=2), name, allure.attachment_type.JSON)

    def register_user(self, department, role):
        account = self.make_user_case(self.tc, dept_id=department, role_id=role)
        if self.admin is None:
            account.login_admin()
            self.admin = account.admin

        if role not in self.roles:
            name, scope = self.admin.role_scope(role)
            assert scope == "本部门数据权限", f"角色 {role} 的本轮范围不符"
            self.roles[role] = name
            self.record("角色基准", 角色编号=role, 角色名称=name, 数据范围=scope)

        self.admin.open_users()
        dept_name, path = self.admin.department_path(department)
        self.departments[department] = dept_name
        self.admin.search(account.username)
        self.admin.wait_for_empty_users()
        return account, path

    def verify_user(self, account, department, role):
        row = account.register_saved_user()
        assert row["部门"] == self.departments[department]
        detail = self.admin.user_details(account.username, labels=("归属部门", "角色", "备注"))
        assert detail == {
            "归属部门": self.departments[department],
            "角色": self.roles[role],
            "备注": account.marker,
        }
        self.record("本例用户归属", 用户编号=account.user_id, 部门编号=department, 角色编号=role)

    def prepare(self, department, role):
        account, path = self.register_user(department, role)
        account.create_user(path, self.roles[role])
        self.verify_user(account, department, role)
        return account

    def login(self, account, identity):
        ui = self.open_identity(identity)
        ui.login(account.base_url, account.username, account.password, account.config_path)
        ui.verify_identity(account.username)
        ui.open_users()
        return ui

    def query_one(self, ui, account):
        ui.activate()
        ui.search(account.username)
        rows = ui.wait_for_user(account.username)
        assert len(rows) == 1
        assert int(rows[0]["用户编号"]) == account.user_id
        return rows[0]

    def assert_department_scope(self, department):
        other_dept = self.dept_b if department == self.dept_a else self.dept_a
        with allure.step("准备本部门查询账号和范围外记录"):
            subject = self.prepare(department, self.query)
            outside = self.prepare(other_dept, self.query)

        with allure.step("管理员去除筛选并逐页记录完整基准"):
            baseline = self.admin.user_pages()
            target_name = self.departments[department]
            expected = {
                int(row["用户编号"]) for page in baseline["pages"]
                for row in page if row["部门"] == target_name
            }
            all_ids = {int(row["用户编号"]) for page in baseline["pages"] for row in page}
            assert subject.user_id in expected and len(expected) > 1
            assert outside.user_id in all_ids and outside.user_id not in expected

        with allure.step("查询账号验证同口径完整分页集合"):
            ui = self.login(subject, "本部门查询账号")
            observed = ui.user_pages()
            assert observed["page_size"] == baseline["page_size"]
            actual = {int(row["用户编号"]) for page in observed["pages"] for row in page}
            self.record(
                "部门分页对照",
                部门编号=department,
                范围外目标编号=outside.user_id,
                管理员总数=baseline["total"],
                管理员各页条数=[len(page) for page in baseline["pages"]],
                查询角色各页条数=[len(page) for page in observed["pages"]],
                每页条数=observed["page_size"],
                预期编号=sorted(expected),
                实际编号=sorted(actual),
                缺失=sorted(expected - actual),
                多出=sorted(actual - expected),
            )
            assert actual == expected, "本部门实际分页 ID 集合与管理员基准不一致"


@pytest.fixture
def make_permission_scenario(make_user_case, open_ui_identity, ui_settings):
    _, config = ui_settings

    def create(tc):
        return PermissionScenario(tc, make_user_case, open_ui_identity, config)

    return create
