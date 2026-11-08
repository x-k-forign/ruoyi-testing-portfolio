"""统一响应断言，调用笔记中的 responses-validator，并补充字段存在性检查。"""

import requests
import responses_validator

from .extract_utils import extract


def _json_subset(actual, expected, path="$"):
    """JSON对象只核对列出的字段；数组必须长度和顺序都符合预期，空数组也要真为空。"""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise AssertionError(f"JSON类型不符：{path}应为对象")
        for key, value in expected.items():
            if key not in actual:
                raise AssertionError(f"JSON缺少字段：{path}.{key}")
            _json_subset(actual[key], value, f"{path}.{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise AssertionError(f"JSON数组长度不符：{path}预期{len(expected)}项")
        for index, (value, rule) in enumerate(zip(actual, expected)):
            _json_subset(value, rule, f"{path}[{index}]")
    elif type(actual) is not type(expected) or actual != expected:
        # 不带出实际字段值，防止身份响应中的敏感内容进入异常。
        raise AssertionError(f"JSON字段不符：{path}")


def assert_response(resp, rules):
    allowed = {"status_code", "headers", "text", "json", "absent", "present",
               "contains", "not_contains", "within"}
    if not isinstance(rules, dict) or not rules or set(rules) - allowed:
        raise ValueError("response包含不支持的断言字段")
    # 不允许 YAML 传入 raise_exception=False，使断言失败被悄悄忽略。
    # 给第三方库单独的 Response 副本，保持原响应可继续提取和检查。
    copy = requests.Response()
    copy.status_code = resp.status_code
    copy.headers.update(resp.headers)
    copy._content = resp.content
    copy.encoding = resp.encoding
    check = {key: value for key, value in rules.items() if key in {"status_code", "headers", "text"}}
    if check:
        try:
            responses_validator.validator(copy, **check)
        except Exception:
            expected_http = check.get("status_code", "未指定")
            raise AssertionError(f"HTTP/头/正文断言失败：预期HTTP={expected_http}，实际HTTP={resp.status_code}") from None
    if "json" in rules:
        try:
            body = resp.json()
        except ValueError:
            raise AssertionError("响应正文不是JSON") from None
        # 先报安全的HTTP及业务码，便于定位已知密码边界失败；不打印完整响应。
        expected = rules["json"]
        if isinstance(expected, dict) and "code" in expected:
            actual_code = body.get("code") if isinstance(body, dict) else None
            if type(actual_code) is not type(expected["code"]) or actual_code != expected["code"]:
                raise AssertionError(f"业务码不符：HTTP={resp.status_code}，预期code={expected['code']}，实际code={actual_code}")
        _json_subset(body, expected)
    for operation in ("absent", "present"):
        if operation not in rules:
            continue
        names = rules[operation]
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
            raise ValueError(f"{operation} 必须是顶层 JSON 字段名列表")
        try:
            body = resp.json()
        except ValueError:
            raise AssertionError("字段存在性断言要求 JSON 响应") from None
        if not isinstance(body, dict):
            raise AssertionError("字段存在性断言要求 JSON 对象")
        for name in names:
            if (name in body) != (operation == "present"):
                raise AssertionError(f"响应字段存在性不符合预期：{name}")
    for operation in ("contains", "not_contains"):
        for expression, expected_items in rules.get(operation, {}).items():
            actual = extract(resp, "json", expression)
            if not isinstance(actual, list) or not isinstance(expected_items, list):
                raise ValueError("contains/not_contains用于JSONPath定位的数组，预期也须为数组")
            if any((item in actual) != (operation == "contains") for item in expected_items):
                raise AssertionError(f"数组成员断言失败：{expression}（{operation}）")
    for expression, limits in rules.get("within", {}).items():
        if not isinstance(limits, list) or len(limits) != 2:
            raise ValueError("within须填写[下界,上界]")
        value = extract(resp, "json", expression)
        try:
            valid = limits[0] <= value <= limits[1]
        except TypeError:
            raise AssertionError(f"区间字段类型不匹配：{expression}") from None
        if not valid:
            raise AssertionError(f"区间断言失败：{expression}")
