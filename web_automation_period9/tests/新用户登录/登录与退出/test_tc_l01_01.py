"""TC-L01-01：新用户在独立会话登录并查询本轮获准记录。"""

import json

import allure
import pytest

from commons.allure_labels import ui_case
from commons.ruoyi_ui import RuoyiUi


@pytest.fixture
def new_user_context(make_user_case, new_browser):
    case = make_user_case("TC-L01-01")
    with allure.step("管理员走页面准备本例独立账号并登记实际用户编号"):
        case.login_admin()
        dept_name, ancestors, role_name = case.associations()
        case.create_user(ancestors, role_name)
        row = case.register_saved_user()
        assert row["用户昵称"] == case.nickname
        assert row["部门"] == dept_name

    with allure.step("建立新用户的独立 Chrome 会话"):
        user_ui = RuoyiUi(new_browser(implicit_wait=0, identity="新用户"))

    try:
        yield case, user_ui
    finally:
        try:
            with allure.step("释放前检查并退出新用户会话"):
                if user_ui.logout_if_authenticated():
                    allure.attach("已退出并返回登录页", "新用户补偿注销", allure.attachment_type.TEXT)
        except Exception as error:
            allure.attach(type(error).__name__, "新用户注销失败", allure.attachment_type.TEXT)
            raise
        finally:
            allure.attach(
                json.dumps(user_ui.locators, ensure_ascii=False),
                "新用户 DOM 定位唯一性",
                allure.attachment_type.JSON,
            )


@ui_case(feature="新用户登录", story="登录与退出", title="新用户独立登录并查询获准记录", tc="TC-L01-01")
def test_tc_l01_01(new_user_context):
    case, user_ui = new_user_context

    with allure.step("核对两次浏览器启动得到独立会话与配置"):
        admin_browser = case.admin.browser
        new_browser = user_ui.browser
        assert new_browser.session_id != admin_browser.session_id
        assert new_browser.capabilities["chrome"]["userDataDir"] != admin_browser.capabilities["chrome"]["userDataDir"]

    with allure.step("新用户提交真实登录表单并核对个人中心身份"):
        user_ui.login(case.base_url, case.username, case.password, case.config_path)
        user_ui.verify_identity(case.username)

    with allure.step("通过菜单进入用户管理，查询本轮获准记录"):
        user_ui.open_users()
        user_ui.search(case.username)
        matches = user_ui.wait_for_user(case.username)
        assert len(matches) == 1, "新用户的精确搜索应仅匹配本轮记录"
        assert int(matches[0]["用户编号"]) == case.user_id, "新用户查到的编号与管理员登记不符"
        assert matches[0]["用户昵称"] == case.nickname

        evidence = {
            "实际账号": case.username,
            "管理员登记编号": case.user_id,
            "新用户查询编号": int(matches[0]["用户编号"]),
            "精确匹配行数": len(matches),
            "身份核对": "个人中心账号一致",
            "会话隔离": "WebDriver 与 Chrome 配置目录均独立",
        }
        allure.attach(json.dumps(evidence, ensure_ascii=False), "新用户身份与获准查询", allure.attachment_type.JSON)

    with allure.step("从页面注销新用户并等待登录表单"):
        assert user_ui.logout_if_authenticated(), "新用户未通过页面注销"
        allure.attach("已从头像菜单注销并回到登录表单", "新用户页面退出", allure.attachment_type.TEXT)
