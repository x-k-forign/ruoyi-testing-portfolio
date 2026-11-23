"""TC-A02-01：同部门查询与维护角色的新增入口对照。"""

import allure

from commons.allure_labels import ui_case


QUERY_ADD_STATE = "DOM 缺失"


@ui_case(feature="菜单操作与数据访问", story="功能操作权限",
         title="同部门查询角色与维护角色的新增权限对照", tc="TC-A02-01")
def test_tc_a02_01(make_permission_scenario):
    run = make_permission_scenario("TC-A02-01")
    with allure.step("准备同部门的独立查询账号和维护账号"):
        query_user = run.prepare(run.dept_a, run.query)
        maintainer = run.prepare(run.dept_a, run.maintainer)

    with allure.step("查询角色和维护角色分别登录并查询同一条可见记录"):
        query_ui = run.login(query_user, "甲 查询角色")
        run.query_one(query_ui, query_user)
        query_state = query_ui.add_entry_state()

        maintenance_ui = run.login(maintainer, "乙 维护角色")
        run.query_one(maintenance_ui, query_user)
        maintain_state = maintenance_ui.add_entry_state()
        run.record("新增入口对照", 部门编号=run.dept_a, 查询角色=query_state, 维护角色=maintain_state)
        assert maintain_state == "可用", "维护角色的新增入口应可用"

    with allure.step("维护角色走新增表单提交并回查，管理员核对实际关联"):
        target, _ = run.register_user(run.dept_a, run.query)
        _, path = maintenance_ui.department_path(run.dept_a)
        target.create_user(path, run.roles[run.query], actor=maintenance_ui)
        run.verify_user(target, run.dept_a, run.query)
        run.query_one(maintenance_ui, target)
        run.record("维护角色页面写入", 操作账号编号=maintainer.user_id, 创建编号=target.user_id)

    with allure.step("验证查询角色在同一已就绪列表上的新增入口状态"):
        assert query_state == QUERY_ADD_STATE, "查询角色新增入口的实际状态与预期不符"
