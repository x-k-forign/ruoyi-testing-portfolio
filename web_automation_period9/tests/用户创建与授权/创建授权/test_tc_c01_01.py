"""TC-C01-01：管理员创建用户并回查部门与角色。"""

import json

import allure

from commons.allure_labels import ui_case


@ui_case(feature="用户创建与授权", story="创建授权", title="管理员创建用户并回查部门与角色", tc="TC-C01-01")
def test_tc_c01_01(make_user_case):
    case = make_user_case("TC-C01-01")

    with allure.step("提交若依登录表单并核对个人中心当前账号"):
        case.login_admin()

    with allure.step("核对配置角色和部门，确认本轮唯一标记尚未存在"):
        dept_name, ancestors, role_name = case.associations()

    with allure.step("从页面填写新增表单、选择部门和角色并提交"):
        case.create_user(ancestors, role_name)

    with allure.step("重新搜索并核对唯一记录的编号、账号、部门和角色"):
        row = case.register_saved_user()
        assert row["用户昵称"] == case.nickname
        assert row["部门"] == dept_name

        expected = {
            "登录账号": case.username,
            "用户名称": case.nickname,
            "归属部门": dept_name,
            "角色": role_name,
            "备注": case.marker,
        }
        details = case.admin.user_details(case.username)
        assert details == expected
        evidence = {
            "用户编号": case.user_id,
            "表格精确匹配条数": 1,
            "部门编号": case.config["dept_id"],
            "角色编号": case.config["role_id"],
            "实际详情": details,
        }
        allure.attach(json.dumps(evidence, ensure_ascii=False), "新增后重新搜索与详情核对", allure.attachment_type.JSON)
