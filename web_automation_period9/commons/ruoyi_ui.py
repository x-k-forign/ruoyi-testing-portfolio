"""若依登录、管理菜单和用户管理页的 Selenium 操作。"""

import json
import re
from time import monotonic
from urllib.parse import urlsplit

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

from .browser import By, WebDriverWait
from .captcha import fill_login_captcha


def css(selector):
    return By.CSS_SELECTOR, selector


def xpath(selector):
    return By.XPATH, selector


def xpath_literal(value):
    if '"' not in value:
        return '"' + value + '"'
    return "concat(" + ', \'"\', '.join('"' + part + '"' for part in value.split('"')) + ")"


_LOGIN = "form.login-form"
_AVATAR = ".navbar .avatar-container"
_SEARCH = '.app-container form.el-form--inline input[placeholder="请输入用户名称"]'
_TABLE = ".app-container .el-table"
_ROLE_SEARCH = '.app-container form.el-form--inline input[placeholder="请输入角色名称"]'
_PAGE_TRANSITION = (".app-main > .fade-transform-enter-from, .app-main > .fade-transform-enter-active, "
                    ".app-main > .fade-transform-leave-to, .app-main > .fade-transform-leave-active")
_ADD_DIALOG = '[role="dialog"][aria-label="添加用户"]'
_DETAILS = '.detail-drawer[role="dialog"]'
_CONFIRM = ".el-message-box"
_TREE = ".el-select__popper .el-tree-node"
_SYSTEM_MENU = xpath('//*[@id="sidebar-container" or contains(concat(" ",normalize-space(@class)," ")," sidebar-container ")]'
                     '//div[contains(@class,"el-sub-menu__title")][.//*[normalize-space(.)="系统管理"]]')
_FORM_LABEL = '//*[contains(concat(" ",normalize-space(@class)," ")," el-form-item ")][./label[normalize-space(.)="{}"]]'


class RuoyiUi:
    def __init__(self, browser, *, timeout=12):
        self.browser = browser
        self.wait = WebDriverWait(browser, timeout, ignored_exceptions=(StaleElementReferenceException,))
        self.locators = {}

    def activate(self):
        self.browser.switch_to.window(self.browser.current_window_handle)

    def _visible(self, locator):
        return [element for element in self.browser.find_elements(*locator) if element.is_displayed()]

    def _one(self, locator, name, *, enabled=False, mouse_target=False):
        def locate(_browser):
            elements = self._visible(locator)
            if len(elements) > 1:
                raise AssertionError(f"{name}匹配到 {len(elements)} 个可见元素")
            if elements and (not enabled or elements[0].is_enabled()):
                element = elements[0]
                if mouse_target and not self.browser.execute_script("""
                    const item = arguments[0], rect = item.getBoundingClientRect();
                    return item.contains(document.elementFromPoint(
                        rect.left + rect.width / 2, rect.top + rect.height / 2
                    ));
                """, element):
                    return False
                return element
            return False

        element = self.wait.until(locate, f"{name}未就绪")
        self.locators[name] = {"by": locator[0], "selector": locator[1], "visible_matches": 1}
        return element

    def _click(self, locator, name):
        self._one(locator, name, enabled=True).click()

    def _type(self, locator, name, value, *, skip_unchanged=False):
        field = self._one(locator, name, enabled=True)
        current = field.get_property("value")
        if skip_unchanged and current == value:
            return
        if current:
            field.send_keys(Keys.CONTROL, "a", Keys.NULL, Keys.BACKSPACE)
            self.wait.until(lambda browser: browser.find_element(*locator).get_property("value") == "",
                            f"{name}没有清空")
            field = self._one(locator, name, enabled=True)
        field.send_keys(value)
        self.wait.until(lambda browser: browser.find_element(*locator).get_property("value") == value,
                        f"{name}没有正确接收输入")

    def _hidden(self, selector, message):
        self.wait.until(lambda _: not self._visible(css(selector)), message)

    def login(self, base_url, username, password, captcha_config):
        address = urlsplit(base_url)
        if (
            address.scheme not in {"http", "https"}
            or address.hostname not in {"localhost", "127.0.0.1", "::1"}
            or address.username is not None
            or address.path not in {"", "/"}
            or address.query
            or address.fragment
        ):
            raise ValueError("RUOYI_UI_BASE_URL 须为本机若依前端根地址")

        self.browser.get(address._replace(path="/login").geturl())
        self._one(css(_LOGIN), "登录表单")
        self._type(css(f'{_LOGIN} input[placeholder="账号"]'), "登录账号输入框", username)
        self._type(css(f'{_LOGIN} input[type="password"]'), "登录密码输入框", password)
        self._one(css(f'{_LOGIN} input[placeholder="验证码"]'), "登录验证码输入框")
        fill_login_captcha(self.browser, config_path=captcha_config)
        self._click(css(f"{_LOGIN} button.el-button--primary"), "登录按钮")
        self._one(css(_AVATAR), "登录后的账号菜单")
        self._dismiss_password_reminder()

    def _dismiss_password_reminder(self):
        locator = css('[role="dialog"][aria-label="安全提示"]')
        if not self._visible(locator):
            return
        reminder = self._one(locator, "登录密码安全提示")
        if not any(text in reminder.text for text in ("您的密码还是初始密码", "您的密码已过期")):
            raise AssertionError("登录后出现未识别的安全提示")
        cancel = xpath('//*[@role="dialog" and @aria-label="安全提示"]//button[normalize-space(.)="取消"]')
        self._click(cancel, "关闭可取消的密码提示")
        self._hidden(locator[1], "密码安全提示未关闭")

    def verify_identity(self, username):
        address = urlsplit(self.browser.current_url)
        self.browser.get(address._replace(path="/user/profile", query="", fragment="").geturl())
        locator = xpath('//ul[contains(@class,"list-group")]/li[normalize-space(text())="用户名称"]'
                        '/div[contains(@class,"pull-right")]')
        self._one(locator, "个人中心的当前用户名称")
        self.wait.until(lambda _: self.browser.find_element(*locator).text.strip() == username,
                        "个人中心显示的登录账号与预期身份不符")
        self._dismiss_password_reminder()

    def _open_account_item(self, item, name):
        if not self._visible(item):
            locator = css(f"{_AVATAR} .avatar-wrapper[role='button']")
            trigger = self._one(locator, "导航栏账号菜单按钮", enabled=True)
            if trigger.get_dom_attribute("aria-expanded") != "true":
                trigger.send_keys(Keys.ENTER)
            try:
                WebDriverWait(self.browser, 2, ignored_exceptions=(StaleElementReferenceException,)).until(
                    lambda _: self._visible(item)
                )
            except TimeoutException:
                # 部分桌面焦点状态下需沿用这个悬停菜单的原生鼠标入口。
                trigger = self._one(locator, "导航栏账号菜单按钮", enabled=True, mouse_target=True)
                ActionChains(self.browser).move_to_element(trigger).perform()

        self._one(item, name, enabled=True, mouse_target=True).click()

    def logout_if_authenticated(self):
        self.activate()
        if not self._visible(css(_AVATAR)):
            return False
        self._dismiss_password_reminder()
        self.dismiss_user_overlays()
        self._open_account_item(xpath('//li[@role="menuitem"][.//span[normalize-space(.)="退出登录"]]'), "退出登录菜单")
        self._confirm("确定注销并退出系统吗？", "确认注销")
        self._one(css(_LOGIN), "退出后的登录表单")
        return True

    def _system_link(self, route, name):
        if urlsplit(self.browser.current_url).path == route:
            return
        locator = css(f'.sidebar-container a[href="{route}"] > li[role="menuitem"]')
        if not self._visible(locator):
            self._click(_SYSTEM_MENU, "系统管理菜单")
        self._one(locator, name, enabled=True, mouse_target=True).click()
        self.wait.until(lambda _: urlsplit(self.browser.current_url).path == route, f"{name}未完成页面跳转")

    def _management_state(self, search):
        # 只记录页面结构和状态。避免把表单值或当前身份带入日志。
        return self.browser.execute_script("""
            const [selector, transitionSelector] = arguments;
            const fields = Array.from(document.querySelectorAll(selector));
            const activeTransitions = Array.from(document.querySelectorAll(transitionSelector));
            return {
                path: location.pathname,
                visibility: document.visibilityState,
                focused: document.hasFocus(),
                searchMatches: fields.length,
                searchLayouts: fields.map(field => ({
                    disabled: field.disabled,
                    hasBox: field.getClientRects().length > 0
                })),
                transitions: activeTransitions.map(node =>
                    Array.from(node.classList).filter(name => name.startsWith('fade-transform-'))
                ),
                loadingMasks: Array.from(document.querySelectorAll('.app-main .el-loading-mask'))
                    .filter(mask => mask.getClientRects().length > 0).length
            };
        """, search, _PAGE_TRANSITION)

    def _open_management_page(self, route, menu_name, search, search_name, number_heading):
        self.activate()
        self._system_link(route, menu_name)
        field_locator = css(f".app-main {search}")
        table_locator = css(f".app-main {_TABLE}")
        headings = css(f".app-main {_TABLE} .el-table__header th")
        masks = css(f".app-main {_TABLE} .el-loading-mask")
        start = monotonic()
        focus_recovered = False

        def ready(browser):
            nonlocal focus_recovered
            if urlsplit(browser.current_url).path != route:
                return False

            fields = self._visible(field_locator)
            if len(fields) > 1:
                raise AssertionError(f"{search_name}匹配到 {len(fields)} 个可见元素")

            if not focus_recovered and monotonic() - start >= 2:
                state = self._management_state(field_locator[1])
                if state["visibility"] != "visible" or (state["transitions"] and not state["focused"]):
                    self.activate()
                    focus_recovered = True
                    return False

            if not fields or not fields[0].is_enabled() or self._visible(css(_PAGE_TRANSITION)):
                return False
            if not any(heading.text.strip() == number_heading for heading in self._visible(headings)):
                return False
            tables = self._visible(table_locator)
            if len(tables) > 1:
                raise AssertionError("管理页数据表格匹配到多个可见元素")
            return bool(tables) and not self._visible(masks)

        try:
            self.wait.until(ready, f"{menu_name}的搜索框和列表未就绪")
        except TimeoutException as error:
            try:
                state = self._management_state(field_locator[1])
            except WebDriverException:
                raise error from None
            raise TimeoutException(
                f"{menu_name}的搜索框和列表未就绪。页面状态：{json.dumps(state, ensure_ascii=False)}"
            ) from error

        self.locators[search_name] = {
            "by": field_locator[0], "selector": field_locator[1], "visible_matches": 1,
            "focus_recovered": focus_recovered,
        }
        self.locators["管理页数据表格"] = {
            "by": table_locator[0], "selector": table_locator[1], "visible_matches": 1,
        }

    def role_name(self, role_id):
        self._open_management_page(
            "/system/role", "角色管理入口", _ROLE_SEARCH, "角色管理搜索区", "角色编号",
        )
        matches = [row["角色名称"] for row in self._rows() if row.get("角色编号") == str(role_id)]
        if len(matches) != 1:
            raise AssertionError(f"角色管理的当前列表中未找到唯一的配置角色编号 {role_id}")
        return matches[0]

    def role_scope(self, role_id):
        name = self.role_name(role_id)
        headers = self._visible(css(f"{_TABLE} .el-table__header th"))
        number_column = [head.text.strip() for head in headers].index("角色编号") + 1
        row = (f'//div[contains(@class,"app-container")]//tbody/tr'
               f'[td[{number_column}][normalize-space(.)="{role_id}"]]')
        # CircleCheck 是角色表格的“数据权限”控件。读取对话框后直接关闭，不提交。
        scope_button = xpath(row + '//td[last()]//button[.//*[local-name()="path" and starts-with(@d,"M512 896a384")]]')
        self._click(scope_button, "查看指定角色数据范围")
        dialog = '[role="dialog"][aria-label="分配数据权限"]'
        field = css(f"{dialog} .el-select .el-select__selected-item")
        scope = self._one(field, "角色实际范围").text.strip()
        self._click(css(f"{dialog} .el-dialog__headerbtn"), "关闭数据权限只读检查")
        self._hidden(dialog, "角色数据权限对话框未关闭")
        return name, scope

    def open_users(self):
        self._open_management_page(
            "/system/user", "用户管理入口", _SEARCH, "用户管理搜索区用户名输入框", "用户编号",
        )


    def _table_ready(self):
        self._one(css(_TABLE), "管理页数据表格")
        self._hidden(f"{_TABLE} .el-loading-mask", "数据表格遮罩未消失")

    def _rows(self):
        headers = [head.text.strip() for head in self._visible(css(f"{_TABLE} .el-table__header th"))]
        records = []
        for row in self._visible(css(f"{_TABLE} .el-table__body tbody tr.el-table__row")):
            cells = [cell.text.strip() for cell in row.find_elements(By.CSS_SELECTOR, "td")]
            records.append(dict(zip(headers, cells, strict=True)))
        return records

    def department_path(self, department_id):
        node = self._one(css(f'.tree-sidebar .el-tree-node[data-key="{department_id}"]'), "测试部门树节点")
        name = node.find_element(By.CSS_SELECTOR, ":scope > .el-tree-node__content .node-label").text.strip()
        ancestors = node.find_elements(By.XPATH, 'ancestor::div[@data-key][contains(@class,"el-tree-node")]')
        return name, [ancestor.get_dom_attribute("data-key") for ancestor in ancestors]

    def search(self, username):
        self._type(css(_SEARCH), "搜索区用户名输入框", username, skip_unchanged=True)
        self._click(xpath('//form[contains(@class,"el-form--inline")]//button[normalize-space(.)="搜索"]'), "用户搜索按钮")
        self._table_ready()

    def reset_user_filters(self):
        self._click(xpath('//form[contains(@class,"el-form--inline")]//button[normalize-space(.)="重置"]'),
                    "重置用户筛选")
        self._table_ready()
        self.wait.until(lambda browser: browser.find_element(*css(_SEARCH)).get_property("value") == "",
                        "重置后用户名筛选未清空")
        self._hidden(".tree-sidebar .el-tree-node.is-current", "重置后仍选中了部门节点")

    def add_entry_state(self):
        self._table_ready()
        locator = xpath('//div[contains(@class,"app-container")]//button[normalize-space(.)="新增"]')
        buttons = self.browser.find_elements(*locator)
        visible = [button for button in buttons if button.is_displayed()]
        assert len(buttons) <= 1, "新增入口定位不唯一"
        if not buttons:
            return "DOM 缺失"
        if not visible:
            return "隐藏"
        return "可用" if visible[0].is_enabled() else "禁用"

    def user_pages(self):
        self.reset_user_filters()
        pager = ".app-container .pagination-container"
        total_text = self._one(css(f"{pager} .el-pagination__total"), "用户列表分页总数").text
        total = int(re.search(r"\d+", total_text).group())
        size_text = self._one(css(f"{pager} .el-pagination__sizes"), "用户列表每页条数").text
        page_size = int(re.search(r"\d+", size_text).group())
        active = css(f"{pager} .el-pager .is-active")
        next_page = css(f"{pager} button.btn-next")
        pages = []
        previous_ids = None
        for page in range(1, (total + page_size - 1) // page_size + 1):
            expected_count = min(page_size, total - (page - 1) * page_size)

            def page_rows(_browser):
                if any(self._visible(css(f"{_TABLE} .el-loading-mask"))):
                    return False
                if int(self.browser.find_element(*active).text) != page:
                    return False
                rows = self._rows()
                ids = tuple(row["用户编号"] for row in rows)
                return rows if len(rows) == expected_count and ids != previous_ids else False

            rows = self.wait.until(page_rows, f"用户列表第 {page} 页未完成加载")
            previous_ids = tuple(row["用户编号"] for row in rows)
            pages.append(rows)
            if sum(map(len, pages)) < total:
                self._click(next_page, "用户列表下一页")

        assert not self._one(next_page, "用户列表末页 下一页按钮").is_enabled(), "末页仍可进入下一页"
        assert self._one(css(f"{pager} .el-pagination__total"), "用户列表分页总数").text == total_text
        assert len({row["用户编号"] for page in pages for row in page}) == total, "分页存在重复或遗漏的用户编号"
        return {"total": total, "page_size": page_size, "pages": pages}

    def exact_users(self, username):
        return [row for row in self._rows() if row.get("用户名称") == username]

    def wait_for_user(self, username):
        return self.wait.until(lambda _: self.exact_users(username), "重新搜索后未出现本轮用户")

    def wait_for_empty_users(self):
        self._one(css(f"{_TABLE} .el-table__empty-text"), "用户表格无数据状态")

    def prepare_new_user(self, username, nickname, password, marker, department_id, ancestors, role_name):
        self._click(xpath('//div[contains(@class,"app-container")]//button[normalize-space(.)="新增"]'), "用户新增按钮")
        self._one(css(_ADD_DIALOG), "添加用户弹窗")
        self._type(css(f'{_ADD_DIALOG} input[placeholder="请输入用户名称"]'), "新增弹窗用户名输入框", username)
        self._type(css(f'{_ADD_DIALOG} input[placeholder="请输入用户昵称"]'), "新增弹窗昵称输入框", nickname)
        self._type(css(f'{_ADD_DIALOG} input[placeholder="请输入用户密码"]'), "新增弹窗密码输入框", password)
        self._type(css(f'{_ADD_DIALOG} textarea[placeholder="请输入内容"]'), "新增弹窗备注输入框", marker)

        dialog = '//*[@role="dialog" and @aria-label="添加用户"]'
        department = dialog + _FORM_LABEL.format("归属部门")
        self._click(xpath(department + '//*[contains(@class,"el-select__wrapper")]'), "归属部门树形选择控件")
        for ancestor in ancestors:
            node_locator = css(f'{_TREE}[data-key="{ancestor}"]')
            node = self._one(node_locator, f"部门上级节点 {ancestor}")
            if node.get_dom_attribute("aria-expanded") != "true":
                expand = css(f'{node_locator[1]} > .el-tree-node__content .el-tree-node__expand-icon')
                self._click(expand, f"展开部门上级节点 {ancestor}")
        self._click(css(f'{_TREE}[data-key="{department_id}"] > .el-tree-node__content'), "表单选中目标部门")
        self._hidden(".el-select__popper .el-tree", "部门选项弹层未关闭")

        role = dialog + _FORM_LABEL.format("角色")
        control = xpath(role + '//*[contains(@class,"el-select__wrapper")]')
        self._click(control, "角色多选控件")
        role_options = xpath(
            '//div[contains(@class,"el-select__popper") and not(contains(@class,"-enter-active"))]'
            '//li[@role="option"][normalize-space(.)=' + xpath_literal(role_name) + ']'
        )
        option = self._one(role_options, "唯一匹配的角色选项")
        # 滚动选项区域后检查实际点击点，避免可见选项的位置还在过渡。
        self.browser.execute_script(
            "arguments[0].scrollIntoView({block: 'nearest', inline: 'nearest', behavior: 'instant'});", option
        )
        self._one(role_options, "就绪的角色选项", enabled=True, mouse_target=True).click()
        item = self._one(control, "已选角色控件")
        self.wait.until(lambda _: role_name in item.text, "表单中未显示选中的角色")
        self._click(css(f'{_ADD_DIALOG} input[placeholder="请输入用户昵称"]'), "回到新增弹窗输入区")
        self._hidden(".el-select__popper .el-select-dropdown__item", "角色选项弹层未关闭")

    def save_new_user(self):
        button = '//*[@role="dialog" and @aria-label="添加用户"]//button[translate(normalize-space(.)," ","")="确定"]'
        self._click(xpath(button), "新增弹窗保存按钮")
        self._hidden(_ADD_DIALOG, "保存后新增弹窗未关闭")
        self._table_ready()

    def _user_link(self, username):
        # 用本轮生成的字母数字账号做精确匹配。
        return xpath(f'//div[contains(@class,"app-container")]//a[contains(@class,"link-type")][normalize-space(.)="{username}"]')

    def user_details(self, username, labels=("登录账号", "用户名称", "归属部门", "角色", "备注")):
        self.activate()
        self._click(self._user_link(username), "本轮用户详情链接")
        self._one(css(_DETAILS), "用户信息详情抽屉")
        self._hidden(f"{_DETAILS} .el-loading-mask", "用户详情加载遮罩未消失")
        values = {}
        for label in labels:
            locator = xpath(
                '//*[contains(@class,"detail-drawer") and @role="dialog"]'
                f'//div[contains(@class,"info-item")][./label[normalize-space(.)="{label}："]]'
                '/*[contains(@class,"info-value")]'
            )
            values[label] = self._one(locator, f"详情字段 {label}").text.strip()
        self.dismiss_user_overlays()
        return values

    def dismiss_user_overlays(self):
        for container, button, title in (
            (_DETAILS, ".el-drawer__close-btn", "用户详情"),
            (_ADD_DIALOG, ".el-dialog__headerbtn", "添加用户"),
        ):
            if self._visible(css(container)):
                self._click(css(f"{container} {button}"), f"关闭{title}")
                self._hidden(container, f"{title}未关闭")

    def delete_user(self, username, user_id):
        self._click(xpath(self._user_link(username)[1] + '/ancestor::tr[1]//label[contains(@class,"el-checkbox")]'),
                    "勾选本轮用户所在行")
        self._click(xpath('//div[contains(@class,"app-container")]//button[normalize-space(.)="删除"]'), "用户删除按钮")
        self._confirm(f'是否确认删除用户编号为"{user_id}"的数据项？', "确认本轮用户编号并删除")
        self._table_ready()

    def _confirm(self, expected_message, name):
        box = self._one(css(_CONFIRM), "操作确认框")
        if expected_message not in box.text:
            raise AssertionError(f"{name}的确认内容与预期不符")
        self._click(css(f"{_CONFIRM} .el-message-box__btns button.el-button--primary"), name)
        self._hidden(_CONFIRM, f"{name}后确认框未关闭")
