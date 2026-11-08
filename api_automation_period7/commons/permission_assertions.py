"""权限场景的完整分页、集合比较及A/B检查点；不替业务规则选择预期。"""

from copy import deepcopy
import json

import allure

from .client import require_code
from .config import PreparationError


def request_all_pages(client, method, path, options, settings, context):
    """保留每一页的真实响应，当前resp仍为最后一页，不伪造合并HTTP响应。"""
    if (method != "GET" or path != "/system/user/list" or not {"page_size", "max_pages"} <= set(settings)
            or set(settings) - {"page_size", "max_pages", "allow_rejected"}):
        raise ValueError("pagination仅用于GET用户列表，须填写page_size和max_pages")
    size, maximum = settings["page_size"], settings["max_pages"]
    if type(size) is not int or not 1 <= size <= 100 or type(maximum) is not int or not 1 <= maximum <= 200:
        raise ValueError("分页大小或页数上限无效")
    rows, pages, seen, declared = [], [], set(), None
    for page in range(1, maximum + 1):
        request_options = deepcopy(options)
        request_options.setdefault("params", {}).update(pageNum=page, pageSize=size,
                                                       orderByColumn="userId", isAsc="asc")
        response = client.request(method, path, **request_options)
        body = response.json()
        if body.get("code") != 200 and settings.get("allow_rejected") is True:
            if context["_case"].get("_requirement_status") != "pending" or body.get("code") not in {401, 403}:
                raise PreparationError("未决访问观察只允许记录明确的认证/权限拒绝")
            context["_collections"].append({"actor": client.actor, "complete": False,
                                              "rejected_code": body["code"], "pages": pages})
            return response
        body = require_code(response)
        current, total = body.get("rows"), body.get("total")
        if not isinstance(current, list) or type(total) is not int or total < 0:
            raise PreparationError("权限分页的rows/total无效")
        if declared is not None and total != declared:
            raise PreparationError("分页期间total变化，无法取得同一稳定基准")
        declared = total
        ids = []
        for row in current:
            number = row.get("userId") if isinstance(row, dict) else None
            if type(number) is not int or number <= 0 or number in seen:
                raise PreparationError("分页用户ID无效或重复，不能当作完整集合")
            seen.add(number)
            ids.append(number)
        pages.append({"page": page, "ids": ids, "total": total})
        rows.extend(current)
        if len(rows) == total:
            context["_page_collection"] = {"rows": rows, "ids": sorted(seen), "pages": pages,
                                            "actor": client.actor, "complete": True}
            context["_collections"].append({"actor": client.actor, "pages": pages, "complete": True,
                                              "ids": sorted(seen)})
            return response
        if not current or len(rows) > total:
            raise PreparationError("分页提前为空或多于total，不能确认完整范围")
    raise PreparationError("权限查询超过分页上限，停止而不截断集合")


def expected_ids(rule):
    """只从当前管理员完整基准按明确部门/本人筛选，不从普通用户结果反推预期。"""
    if not isinstance(rule, dict) or set(rule) - {"baseline", "departments", "self_id", "all", "empty", "user_name"}:
        raise ValueError("user_ids的基准或筛选字段无效")
    baseline = rule.get("baseline")
    if not isinstance(baseline, list) or any(not isinstance(row, dict) or type(row.get("userId")) is not int for row in baseline):
        raise ValueError("集合预期须引用本轮管理员完整分页基准")
    ids = [row["userId"] for row in baseline]
    if len(ids) != len(set(ids)):
        raise PreparationError("管理员基准包含重复ID")
    if rule.get("empty") is True:
        return set()
    if "departments" in rule:
        departments = rule["departments"]
        if not isinstance(departments, list) or any(type(x) is not int for x in departments):
            raise ValueError("departments应为实际部门ID列表")
        baseline = [row for row in baseline if row.get("deptId") in departments]
    elif "self_id" in rule:
        baseline = [row for row in baseline if row["userId"] == rule["self_id"]]
    elif rule.get("all") is not True:
        raise ValueError("集合预期须明确departments、self_id、all或empty")
    if "user_name" in rule:
        baseline = [row for row in baseline if row.get("userName") == rule["user_name"]]
    return {row["userId"] for row in baseline}


def inspect_user_ids(context, rule):
    collection = context.get("_page_collection")
    if not collection or not collection["complete"]:
        raise ValueError("集合断言之前须执行本次完整分页请求")
    actual, expected = set(collection["ids"]), expected_ids(rule)
    result = {"expected_ids": sorted(expected), "actual_ids": sorted(actual),
              "missing_ids": sorted(expected - actual), "extra_ids": sorted(actual - expected),
              "page_count": len(collection["pages"]), "passed": actual == expected}
    context["_set_checks"].append(result)
    allure.attach(json.dumps(result, ensure_ascii=False, indent=2), name="完整分页ID集合比较",
                  attachment_type=allure.attachment_type.JSON)
    return result


def assert_user_ids(context, rule):
    result = inspect_user_ids(context, rule)
    if not result["passed"]:
        raise AssertionError(f"数据范围ID集合不符：缺少{result['missing_ids']}，多出{result['extra_ids']}")


def capture_checkpoint(context, specification):
    """先保存A/B真实结果，最后统一断言；pending只记录观察，绝不自动判通过。"""
    allowed = {"name", "code", "user_ids", "values", "pending", "details"}
    if not isinstance(specification, dict) or set(specification) - allowed:
        raise ValueError("checkpoint字段无效")
    name = specification.get("name")
    if not isinstance(name, str) or not name.isidentifier() or name in context["_checkpoints"]:
        raise ValueError("检查点名称须唯一")
    response = context["resp"]
    body = response.json()
    event = context["_events"][-1]
    record = {"name": name, "actor": context.get("_last_request_actor"), "at": event.get("completed_at", event["at"]),
              "http_status": response.status_code, "actual_code": body.get("code"), "checks": [], "pending": False}
    if "code" in specification:
        record["expected_code"] = specification["code"]
        record["checks"].append(body.get("code") == specification["code"])
    if "user_ids" in specification:
        record["set_comparison"] = inspect_user_ids(context, specification["user_ids"])
        record["checks"].append(record["set_comparison"]["passed"])
    for comparison in specification.get("values", []):
        if not isinstance(comparison, dict) or set(comparison) != {"actual", "expected"}:
            raise ValueError("values须包含actual与expected")
        passed = (type(comparison["actual"]) is type(comparison["expected"])
                  and comparison["actual"] == comparison["expected"])
        record["checks"].append(passed)
        def numeric(value):
            return value if value is None or type(value) in {int, bool, float} else "<非数值对照未保存>"
        record.setdefault("value_comparisons", []).append({"actual": numeric(comparison["actual"]),
                                                           "expected": numeric(comparison["expected"]), "passed": passed})
    if "pending" in specification:
        if context["_case"].get("_requirement_status") != "pending" or not specification["pending"]:
            raise ValueError("只有已声明未决规则的用例能记录pending检查点")
        record.update(pending=True, rule_status="待确认", reason=specification["pending"])
        context["_pending_requirement"] = specification["pending"]
        if context.get("_page_collection"):
            record["actual_ids"] = context["_page_collection"]["ids"]
    if "details" in specification:
        from .report_utils import redact
        record["details"] = redact(specification["details"])
    if not record["checks"] and not record["pending"]:
        raise ValueError("检查点没有明确预期或未决说明")
    record["passed"] = all(record["checks"]) if record["checks"] else None
    context["_checkpoints"][name] = record
    allure.attach(json.dumps(record, ensure_ascii=False, indent=2), name=f"对照检查点：{name}",
                  attachment_type=allure.attachment_type.JSON)


def assert_checkpoints(context, names):
    if not isinstance(names, list) or not names or any(name not in context["_checkpoints"] for name in names):
        raise ValueError("checkpoints须引用已实际采集的检查点")
    failed = [name for name in names if context["_checkpoints"][name]["passed"] is False]
    if failed:
        raise AssertionError("权限对照不符：" + "、".join(failed) + "；A/B结果及集合差异已留证")
