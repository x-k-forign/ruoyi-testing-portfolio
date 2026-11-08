"""按响应类型提取值；不修改 Response.json 方法，支持重复提取。"""

import re
import jsonpath
from lxml import html


class ExtractionError(ValueError):
    pass


def extract(resp, attr_name, exp):
    """json/headers 用 JSONPath；text 用正则；xpath 用 HTML XPath，返回首个匹配。"""
    if attr_name in {"json", "headers"}:
        if attr_name == "json":
            try:
                data = resp.json()  # 用局部变量，绝不写成 resp.json = resp.json()。
            except ValueError:
                raise ExtractionError("响应不是 JSON，不能使用 JSONPath") from None
        else:
            data = dict(resp.headers)
        try:
            matches = jsonpath.jsonpath(data, exp, use_eval=False)
        except Exception:
            raise ExtractionError("JSONPath 表达式无效；不支持需要 eval 的过滤表达式") from None
        if not isinstance(matches, list) or not matches:
            raise ExtractionError("JSONPath 没有匹配值")
        return matches[0]
    if attr_name == "text":
        try:
            match = re.search(exp, resp.text)
        except re.error:
            raise ExtractionError("正则表达式无效") from None
        if match is None:
            raise ExtractionError("正则没有匹配值")
        return match.group(1) if match.lastindex else match.group(0)
    if attr_name == "xpath":
        try:
            matches = html.fromstring(resp.text).xpath(exp)
        except (ValueError, TypeError, SyntaxError, html.etree.LxmlError):
            raise ExtractionError("HTML 或 XPath 无效") from None
        if not isinstance(matches, list) or not matches:
            raise ExtractionError("XPath 没有匹配值；请使用返回节点列表的表达式")
        return matches[0]
    raise ExtractionError("提取类型仅支持 json、headers、text、xpath")
