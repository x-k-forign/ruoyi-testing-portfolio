"""若依接口自动化公共封装。导入时不会登录、创建数据或发送请求。"""

from .client import ApiClient, require_code
from .config import load_config

__all__ = ["ApiClient", "require_code", "load_config"]
