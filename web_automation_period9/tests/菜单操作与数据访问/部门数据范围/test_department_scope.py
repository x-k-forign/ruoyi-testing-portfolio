"""部门数据范围与范围外精确搜索。"""

import allure

from commons.allure_labels import ui_case


@ui_case(feature="菜单操作与数据访问", story="部门数据范围",
         title="部门 A 查询账号只看到本部门记录", tc="TC-A05-01")
def test_tc_a05_01(make_permission_scenario):
    run = make_permission_scenario("TC-A05-01")
    run.assert_department_scope(run.dept_a)


@ui_case(feature="菜单操作与数据访问", story="部门数据范围",
         title="部门 B 查询账号只看到本部门记录", tc="TC-A05-02")
def test_tc_a05_02(make_permission_scenario):
    run = make_permission_scenario("TC-A05-02")
    run.assert_department_scope(run.dept_b)


@ui_case(feature="菜单操作与数据访问", story="部门数据范围",
         title="普通用户按账号搜索范围外记录时返回空", tc="TC-A10-02")
def test_tc_a10_02(make_permission_scenario):
    run = make_permission_scenario("TC-A10-02")
    with allure.step("准备部门 A 查询账号和部门 B 的唯一目标"):
        subject = run.prepare(run.dept_a, run.query)
        outside = run.prepare(run.dept_b, run.query)
        run.admin.reset_user_filters()
        run.query_one(run.admin, outside)

    with allure.step("部门 A 账号验证本部门可见，并用同口径搜索范围外目标"):
        ui = run.login(subject, "甲 部门 A 查询角色")
        ui.reset_user_filters()
        run.query_one(ui, subject)
        ui.search(outside.username)
        ui.wait_for_empty_users()
        assert not ui.exact_users(outside.username), "范围外精确搜索泄漏记录"
        run.record(
            "范围外搜索对照",
            本部门可见编号=subject.user_id,
            范围外目标编号=outside.user_id,
            管理员精确匹配=1,
            查询账号精确匹配=0,
        )
