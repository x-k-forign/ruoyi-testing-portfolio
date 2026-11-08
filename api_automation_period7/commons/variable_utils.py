"""递归替换 ${变量名}；不使用 eval，不把变量值拼进异常消息。"""

import re

VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
RESERVED = {"resp"}


def check_name(name):
    if not isinstance(name, str) or not name.isidentifier() or name.startswith("_") or name in RESERVED:
        raise ValueError("变量名必须是非内部标识符，不能覆盖 resp")


def replace_variables(value, my_var):
    if isinstance(value, dict):
        return {key: replace_variables(item, my_var) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_variables(item, my_var) for item in value]
    if not isinstance(value, str):
        return value

    def lookup(match):
        name = match.group(1)
        check_name(name)
        if name not in my_var:
            raise ValueError(f"变量未定义：{name}")
        return my_var[name]

    match = VARIABLE.fullmatch(value)
    if match:
        # 整个值就是一个变量时保留整数、列表等类型。
        return lookup(match)
    return VARIABLE.sub(lambda match: str(lookup(match)), value)
