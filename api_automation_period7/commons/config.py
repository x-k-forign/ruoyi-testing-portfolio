"""读取JSON配置。真实凭据放在项目.private中，模板不填写真实密码。"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = PROJECT_ROOT / "data/templates"


class PreparationError(ValueError):
    """配置或前置数据不足，不能继续发送依赖它的请求。"""


def read_json(path):
    path = Path(path)
    try:
        with path.open(encoding="utf-8-sig") as file:
            value = json.load(file)
    except FileNotFoundError:
        raise PreparationError(f"文件不存在：{path.name}") from None
    except json.JSONDecodeError:
        # 不输出原文件内容，避免错误信息包含密码。
        raise PreparationError(f"JSON格式无效：{path.name}") from None
    if not isinstance(value, dict):
        raise PreparationError(f"JSON顶层必须是对象：{path.name}")
    return value


def load_config(path, *, require_credentials=True):
    # 旧私有 JSON 配置继续可用，新模板使用 YAML；不改写原凭据文件。
    path = Path(path)
    if path.suffix.lower() in {".yaml", ".yml"}:
        from .yaml_utils import read_yaml
        cfg = read_yaml(path)
        if not isinstance(cfg, dict):
            raise PreparationError("环境配置顶层必须是对象")
    else:
        cfg = read_json(path)
    required = ("environment", "base_url", "connect_timeout", "read_timeout",
                "dept_id", "role_id", "post_ids", "admin_username", "admin_password")
    if any(key not in cfg for key in required):
        raise PreparationError("配置缺少必要字段，请对照模板")
    # 本节明确选择共用环境；失败时绝不悄悄切到隔离环境。
    if cfg["environment"] != "shared" or cfg["base_url"] != "http://127.0.0.1:8080":
        raise PreparationError("目标必须明确为本节共用环境127.0.0.1:8080")
    for key in ("connect_timeout", "read_timeout"):
        if type(cfg[key]) not in (int, float) or not 0 < cfg[key] <= 60:
            raise PreparationError(f"{key}必须是0到60之间的正数")
    for key in ("dept_id", "role_id"):
        if type(cfg[key]) is not int or cfg[key] <= 0:
            raise PreparationError(f"{key}必须是正整数")
    if "maintainer_role_id" in cfg and (type(cfg["maintainer_role_id"]) is not int or cfg["maintainer_role_id"] <= 0):
        raise PreparationError("maintainer_role_id必须是正整数")
    if not isinstance(cfg["post_ids"], list) or any(type(x) is not int or x <= 0 for x in cfg["post_ids"]):
        raise PreparationError("post_ids必须是正整数列表，可以为空")
    if require_credentials and any(not isinstance(cfg[key], str) or not cfg[key] for key in ("admin_username", "admin_password")):
        raise PreparationError("请在本地私有配置中提供管理员账号和密码")
    return cfg


def save_json(path, value):
    """显式UTF-8保存结构化记录，先写临时文件再替换，减少中断损坏。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
