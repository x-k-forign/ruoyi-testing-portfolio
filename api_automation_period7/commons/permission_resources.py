"""T7.6每例专属部门、角色和多账号夹具；所有写入先核对归属并登记意图。"""

from copy import deepcopy
import json

import allure

from .business_utils import admin_client, send, find_rows, owned_detail, persist_ledger
from .client import require_code
from .config import PreparationError


QUERY = ["system:user:list", "system:user:query"]


class PermissionResources:
    def __init__(self, context):
        self.context = context
        self.depts = context["_owned_departments"]
        self.roles = context["_owned_roles"]
        self.restore_users = {}
        self.restoring = False
        self.parent = context["dept_id"]

    def __repr__(self):
        return "<PermissionResources: 本例独立部门、角色、账号>"

    def call(self, method, path, **options):
        from .business_utils import guard_write
        guard_write(self.context, method, path, options)
        return send(admin_client(self.context), method, path, **options)

    def role_rows(self, key):
        body = require_code(send(admin_client(self.context), "GET", "/system/role/list",
                                 params={"roleKey": key, "pageNum": 1, "pageSize": 100}))
        if len(body["rows"]) != body["total"]:
            raise PreparationError("专用角色查找未读取完整结果")
        return [row for row in body["rows"] if row.get("roleKey") == key]

    def dept_rows(self, name):
        body = require_code(send(admin_client(self.context), "GET", "/system/dept/list", params={"deptName": name}))
        return [row for row in body["data"] if row.get("deptName") == name]

    def create_dept(self, alias, parent):
        name = self.context["_stage"].replace(".", "") + "_" + self.context["batch_tag"] + "_" + alias
        if self.dept_rows(name):
            raise PreparationError("本例部门名称已存在")
        entry = {"deptName": name, "parentId": parent, "id": None, "attempted": True}
        self.depts[name] = entry
        persist_ledger(self.context)
        require_code(self.call("POST", "/system/dept", json={"deptName": name, "parentId": parent,
                                                              "orderNum": 20, "status": "0"}))
        rows = self.dept_rows(name)
        if len(rows) != 1 or rows[0].get("parentId") != parent:
            raise PreparationError("专用部门创建回查不唯一或父部门不符")
        entry["id"] = rows[0]["deptId"]
        persist_ledger(self.context)
        return entry["id"]

    def create_role(self, alias, scope="3", *, add=False, departments=None):
        key = self.context["batch_tag"] + alias
        name = self.context["_stage"].replace(".", "") + "_" + key
        if self.role_rows(key):
            raise PreparationError("本例角色权限字符已存在")
        entry = {"roleKey": key, "roleName": name, "id": None, "attempted": True, "status": "0"}
        self.roles[key] = entry
        permissions = QUERY + (["system:user:add"] if add else [])
        payload = {"roleName": name, "roleKey": key, "roleSort": 20, "dataScope": scope,
                   "menuCheckStrictly": True, "deptCheckStrictly": True, "status": "0",
                   "menuIds": [self.menu_ids[item] for item in permissions], "remark": self.context["batch_tag"]}
        persist_ledger(self.context)
        require_code(self.call("POST", "/system/role", json=payload))
        rows = self.role_rows(key)
        if len(rows) != 1 or rows[0].get("remark") != self.context["batch_tag"] or rows[0].get("roleName") != name:
            raise PreparationError("专用角色创建回查不符")
        entry["id"] = rows[0]["roleId"]
        persist_ledger(self.context)
        if scope == "2":
            require_code(self.call("PUT", "/system/role/dataScope", json={"roleId": entry["id"], "dataScope": scope,
                                                                          "deptCheckStrictly": True, "deptIds": departments}))
            observed = require_code(send(admin_client(self.context), "GET", f"/system/role/deptTree/{entry['id']}"))
            if set(observed["checkedKeys"]) != set(departments):
                raise PreparationError("专用角色自定义部门关联不符")
        role = require_code(send(admin_client(self.context), "GET", f"/system/role/{entry['id']}"))["data"]
        if role["status"] != "0" or role["dataScope"] != scope:
            raise PreparationError("专用角色状态或数据范围不符")
        return entry["id"]

    def create_user(self, name, dept, roles):
        context = self.context
        context["_allowed_usernames"].add(name)
        payload = {"userName": name, "nickName": context["new_nickname"], "password": context["new_password"],
                   "deptId": dept, "roleIds": roles, "postIds": context["post_ids"], "status": "0", "sex": "2",
                   "remark": context["batch_tag"]}
        require_code(self.call("POST", "/system/user", json=payload))
        rows = find_rows(context, name)
        if len(rows) != 1:
            raise PreparationError("专用账号创建后精确回查不唯一")
        entry = context["_owned_users"][name]
        entry["ids"] = [rows[0]["userId"]]
        entry.update(creation_observed=True, state="created")
        persist_ledger(context)
        body = owned_detail(context, rows[0])
        if body["data"]["deptId"] != dept or set(body["roleIds"]) != set(roles) or set(body["postIds"]) != set(context["post_ids"]):
            raise PreparationError("专用账号部门、角色或岗位关联不符")
        return rows[0]["userId"]

    def guard(self, method, path, options):
        """角色和部门的新增、变更、删除只能指向当前夹具已登记的对象。"""
        if method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        payload = options.get("json", {})
        if path.startswith("/system/role"):
            if method == "POST" and path == "/system/role":
                entry = self.roles.get(payload.get("roleKey"))
                if not entry or payload.get("roleName") != entry["roleName"] or payload.get("remark") != self.context["batch_tag"]:
                    raise PreparationError("禁止创建未登记归属的角色")
                return
            number = int(path.rsplit("/", 1)[-1]) if method == "DELETE" and path.rsplit("/", 1)[-1].isdigit() else payload.get("roleId")
            entries = [entry for entry in self.roles.values() if entry["id"] == number and number is not None]
            if len(entries) != 1 or path not in {"/system/role/changeStatus", "/system/role/dataScope", f"/system/role/{number}"}:
                raise PreparationError("禁止修改或删除共用或未登记角色")
            role = require_code(send(admin_client(self.context), "GET", f"/system/role/{number}"))["data"]
            if not role or role.get("roleKey") != entries[0]["roleKey"] or role.get("remark") != self.context["batch_tag"]:
                raise PreparationError("角色归属核验失败")
            if path.endswith("dataScope") and any(number not in {entry['id'] for entry in self.depts.values()} for number in payload.get('deptIds', [])):
                raise PreparationError("自定义范围仅能绑定本例部门")
        elif path.startswith("/system/dept"):
            if method == "POST" and path == "/system/dept":
                entry = self.depts.get(payload.get("deptName"))
                if not entry or payload.get("parentId") != entry["parentId"]:
                    raise PreparationError("禁止创建未登记归属的部门")
                if entry["parentId"] not in {self.parent, *[item["id"] for item in self.depts.values() if item["id"]]}:
                    raise PreparationError("专用部门的父部门不属于本例配置")
                return
            if method != "DELETE" or not path.rsplit("/", 1)[-1].isdigit():
                raise PreparationError("本阶段部门仅新增和按归属删除，不修改公共部门")
            number = int(path.rsplit("/", 1)[-1])
            entries = [entry for entry in self.depts.values() if entry["id"] == number]
            if len(entries) != 1:
                raise PreparationError("禁止删除非本例部门")
            dept = require_code(send(admin_client(self.context), "GET", f"/system/dept/{number}"))["data"]
            if not dept or dept.get("deptName") != entries[0]["deptName"] or dept.get("parentId") != entries[0]["parentId"]:
                raise PreparationError("部门归属核验失败")

    def remember_user_before_change(self, body):
        if self.restoring:
            return
        user = body["data"]
        number = user["userId"]
        if number not in self.restore_users:
            self.restore_users[number] = {key: deepcopy(user.get(key)) for key in
                                         ("userId", "userName", "nickName", "deptId", "status", "sex", "remark")}
            self.restore_users[number].update(roleIds=body["roleIds"], postIds=body["postIds"])

    def restore(self):
        errors = []
        self.restoring = True
        try:
            for number, baseline in self.restore_users.items():
                try:
                    current = owned_detail(self.context, {"userId": number})
                    unchanged = all(current["data"].get(k) == v for k, v in baseline.items() if k not in {"roleIds", "postIds"})
                    unchanged = unchanged and set(current["roleIds"]) == set(baseline["roleIds"]) and set(current["postIds"]) == set(baseline["postIds"])
                    if not unchanged:
                        require_code(self.call("PUT", "/system/user", json=baseline))
                        current = owned_detail(self.context, {"userId": number})
                    valid = all(current["data"].get(k) == v for k, v in baseline.items() if k not in {"roleIds", "postIds"})
                    valid = valid and set(current["roleIds"]) == set(baseline["roleIds"]) and set(current["postIds"]) == set(baseline["postIds"])
                    if not valid:
                        raise AssertionError("专用账号恢复回查不符")
                    self.context["_restorations"].append({"userId": number, "restored": True, "was_unchanged": unchanged})
                except Exception as error:
                    errors.append(error)
                    self.context["_restorations"].append({"userId": number, "restored": False, "error_type": type(error).__name__})
        finally:
            self.restoring = False
        if errors:
            raise ExceptionGroup("本例变更对象恢复未完成", errors)

    def cleanup(self):
        """用户清理后解除角色和部门；即使创建响应不明确也按唯一名称回查。"""
        errors = []
        for kind, entries in (("role", list(self.roles.values())), ("dept", list(reversed(list(self.depts.values()))))):
            for entry in entries:
                try:
                    rows = self.role_rows(entry["roleKey"]) if kind == "role" else self.dept_rows(entry["deptName"])
                    if len(rows) > 1:
                        raise PreparationError("专用资源名称回查不唯一")
                    for row in rows:
                        entry["id"] = row["roleId" if kind == "role" else "deptId"]
                        if kind == "role":
                            linked = require_code(send(admin_client(self.context), "GET", "/system/role/authUser/allocatedList",
                                                       params={"roleId": entry["id"], "pageNum": 1, "pageSize": 100}))
                            if linked["total"] != 0:
                                raise PreparationError("本例角色仍有关联用户，停止删除")
                        require_code(self.call("DELETE", f"/system/{kind}/{entry['id']}"))
                    remaining = self.role_rows(entry["roleKey"]) if kind == "role" else self.dept_rows(entry["deptName"])
                    if remaining:
                        raise AssertionError("专用角色或部门清理后仍存在")
                    self.context["_resource_cleanup"].append({"kind": kind, "id": entry["id"], "absent": True})
                except Exception as error:
                    errors.append(error)
                    self.context["_resource_cleanup"].append({"kind": kind, "id": entry["id"], "absent": False,
                                                              "error_type": type(error).__name__})
        if errors:
            raise ExceptionGroup("专用角色或部门清理未完成", errors)

    def prepare(self, spec):
        """准备真实业务前提，目标请求和断言继续由各自YAML执行。"""
        from .preparation_utils import login_identity
        context = self.context
        parent = require_code(send(admin_client(context), "GET", f"/system/dept/{self.parent}"))["data"]
        if parent["status"] != "0":
            raise PreparationError("本轮配置父部门不可用")
        menus = require_code(send(admin_client(context), "GET", "/system/menu/list"))["data"]
        self.menu_ids = {}
        for permission in QUERY + ["system:user:add"]:
            matches = [row["menuId"] for row in menus if row.get("perms") == permission and row.get("status") == "0"]
            if len(matches) != 1:
                raise PreparationError("必要的有效权限菜单不唯一")
            self.menu_ids[permission] = matches[0]
        with allure.step("前置：通过接口建立本例专属部门、角色与对照账号"):
            context["dept_a"] = self.create_dept("A", self.parent)
            context["dept_b"] = self.create_dept("B", self.parent)
            if spec.get("child"):
                context["dept_child"] = self.create_dept("Achild", context["dept_a"])
            context["role_id"] = self.create_role("q")
            subject_role = context["role_id"]
            if spec.get("scope", "3") != "3":
                subject_role = self.create_role("s", spec["scope"], departments=[context["dept_b"]])
            if spec.get("maintainer"):
                context["maintainer_role_id"] = self.create_role("m", add=True)
            if spec.get("subject_role") == "maintainer":
                subject_role = context["maintainer_role_id"]
            extra = spec.get("extra")
            if extra:
                context["extra_role_id"] = self.create_role("x", "2" if extra == "custom_add" else "3",
                                                            add=extra != "query", departments=[context["dept_b"]])
            subject_roles = [subject_role] + ([context["extra_role_id"]] if spec.get("assigned_extra") else [])
            context["initial_role_ids"] = subject_roles
            context["target_username"] = context["batch_tag"] + "t"
            context["other_username"] = context["batch_tag"] + "o"
            context["target_user_id"] = self.create_user(context["target_username"], context["dept_a"], [context["role_id"]])
            context["other_user_id"] = self.create_user(context["other_username"], context["dept_b"], [context["role_id"]])
            if spec.get("child"):
                context["child_username"] = context["batch_tag"] + "c"
                context["child_user_id"] = self.create_user(context["child_username"], context["dept_child"], [context["role_id"]])
            context["dept_id"] = context["dept_b"] if spec.get("subject_dept") == "B" else context["dept_a"]
            context["new_denied_username"] = context["batch_tag"] + "e"
            context["no_match_username"] = context["batch_tag"] + "z"
            context["_allowed_usernames"].add(context["new_denied_username"])
            context["new_user_id"] = self.create_user(context["new_username"], context["dept_id"], subject_roles)
            login_identity(context, "${new_username}", "${new_password}", "before_token", expected_user_id="${new_user_id}")
            if spec.get("second_maintainer"):
                context["maintainer_username"] = context["batch_tag"] + "m"
                context["maintainer_user_id"] = self.create_user(context["maintainer_username"], context["dept_a"], [context["maintainer_role_id"]])
                login_identity(context, "${maintainer_username}", "${new_password}", "maintainer_token",
                               expected_user_id="${maintainer_user_id}")
            context["_permission_matrix"] = {"subject_user_id": context["new_user_id"], "initial_roles": subject_roles,
                                              "initial_dept": context["dept_id"], "dept_a": context["dept_a"],
                                              "dept_b": context["dept_b"], "scope": spec.get("scope", "3"),
                                              "target_ids": [context["target_user_id"], context["other_user_id"]],
                                              "fixture_spec": spec}
            allure.attach(json.dumps(context["_permission_matrix"], ensure_ascii=False, indent=2), name="本例身份与数据范围矩阵",
                          attachment_type=allure.attachment_type.JSON)
