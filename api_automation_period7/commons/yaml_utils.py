"""读取和检查 YAML 用例；加载阶段只处理文件，不登录、不发请求。"""

from pathlib import Path
import yaml


class CaseFormatError(ValueError):
    """用例结构不符合 name / mark / steps 约定。"""


class UniqueKeyLoader(yaml.SafeLoader):
    """拒绝重复键，防止后一个 request/json 字段静默覆盖前一个。"""


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise CaseFormatError("YAML 字典键必须是唯一的字符串")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def read_yaml(path):
    """使用 SafeLoader 的受限子类，with 负责关闭文件，不执行 YAML 中的代码。"""
    path = Path(path)
    try:
        with path.open(encoding="utf-8-sig") as stream:
            return yaml.load(stream, Loader=UniqueKeyLoader)
    except FileNotFoundError:
        raise CaseFormatError(f"YAML 文件不存在：{path.name}") from None
    except yaml.YAMLError:
        # 不带出原文件正文，避免私有配置的密码出现在异常消息中。
        raise CaseFormatError(f"YAML 格式错误：{path.name}") from None


def load_cases(path):
    """一个文件既可写一条用例，也可写用例列表；各步骤只允许一个操作。"""
    value = read_yaml(path)
    cases = value if isinstance(value, list) else [value]
    if not cases:
        raise CaseFormatError("YAML 用例不能为空")
    allowed = {"name", "mark", "steps"}
    for index, case in enumerate(cases, 1):
        if not isinstance(case, dict) or set(case) - allowed:
            raise CaseFormatError("用例包含未知字段或不是字典")
        if not isinstance(case.get("name"), str) or not case["name"].strip():
            raise CaseFormatError("每条用例须有非空 name")
        marks = case.get("mark") or []
        marks = [marks] if isinstance(marks, str) else marks
        if not isinstance(marks, list) or any(not isinstance(mark, str) or not mark.isidentifier() for mark in marks):
            raise CaseFormatError("mark 应为标记名称或名称列表")
        case["mark"] = marks
        steps = case.get("steps")
        if not isinstance(steps, list) or not steps:
            raise CaseFormatError("steps 必须是非空列表")
        requested = False
        for step in steps:
            if not isinstance(step, dict) or len(step) != 1:
                raise CaseFormatError("每一步只能包含 request、response、extract 中的一个操作")
            action, settings = next(iter(step.items()))
            if action not in {"request", "response", "extract"} or not isinstance(settings, dict) or not settings:
                raise CaseFormatError("未知步骤或步骤配置为空")
            if action == "request":
                if not {"method", "url"} <= settings.keys():
                    raise CaseFormatError("request 缺少 method 或 url")
                if not all(isinstance(settings[key], str) and settings[key] for key in ("method", "url")):
                    raise CaseFormatError("request 的 method 和 url 必须是非空字符串")
                requested = True
            elif not requested:
                raise CaseFormatError("response/extract 之前必须有 request")
    return cases
