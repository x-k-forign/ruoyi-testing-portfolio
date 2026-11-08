"""只从 tests 的 YAML 文件发现业务用例，文件夹就是 Allure 分组。"""

from hashlib import sha256
from copy import deepcopy
import re

from .config import PROJECT_ROOT
from .yaml_utils import load_cases, read_yaml, CaseFormatError

CASE_ROOT = PROJECT_ROOT / "tests"
BUSINESS_LINES = ("用户创建与授权", "新用户登录", "菜单操作与数据访问", "授权变更与账号禁用", "相关日志核对")
ASSERTION_COPY_DIR = "断言失败副本测试"


def needs_login(case):
    return any(step.get("request", {}).get("method", "").upper() == "POST"
               and step["request"].get("url", "").rstrip("/").endswith("/login")
               for step in case["steps"])


def discover_cases(groups=None, *, assertion_copy=False):
    """按目录筛选；读 YAML 时不读密码、不发请求，也不创建测试结果。"""
    suite_root = CASE_ROOT / ASSERTION_COPY_DIR if assertion_copy else CASE_ROOT
    roots = []
    for group in groups or []:
        directory = (suite_root / group).resolve()
        if (not directory.is_relative_to(suite_root.resolve()) or not directory.is_dir()
                or not directory.relative_to(suite_root.resolve()).parts
                or directory.relative_to(suite_root.resolve()).parts[0] not in BUSINESS_LINES):
            raise CaseFormatError(f"业务分组目录不存在：{group}")
        roots.append(directory)
    # 默认仅从正式五条主线发现用例；副本目录必须显式选择，避免混入正常回归。
    roots = roots or [suite_root / name for name in BUSINESS_LINES]
    paths = sorted({path for directory in roots for pattern in ("*.yaml", "*.yml")
                    for path in directory.rglob(pattern)})
    if not paths:
        raise CaseFormatError("tests 中没有 YAML 业务用例")
    mappings = read_yaml(PROJECT_ROOT / "data/case_mapping.yaml")
    copies = read_yaml(PROJECT_ROOT / "data/assertion_copy_mapping.yaml") if assertion_copy else {}
    scenarios = read_yaml(PROJECT_ROOT / "data/scenarios/password_boundaries.yaml")
    if not isinstance(scenarios, dict):
        raise CaseFormatError("场景参数文件应为字典")
    if not isinstance(mappings, dict):
        raise CaseFormatError("原TC映射文件应为字典")
    result = []
    for path in paths:
        relative = path.relative_to(suite_root)
        if len(relative.parts) < 3 or relative.parts[0] not in BUSINESS_LINES:
            raise CaseFormatError("业务 YAML 应放在 tests/五条业务主线之一/功能分组/ 下")
        for index, case in enumerate(load_cases(path), 1):
            # 下划线字段由执行器生成，不需要写入 YAML。
            case["_source"] = path.relative_to(PROJECT_ROOT).as_posix()
            case["_origin_source"] = "tests/" + relative.as_posix()
            case["_assertion_copy"] = assertion_copy
            # epic 固定为项目；feature 取业务主线；story 取功能分组目录。
            case["_group"] = relative.parts[0]
            case["_story"] = "/".join(relative.parts[1:-1])
            case["_id"] = "api_" + sha256(f"{relative.as_posix()}:{index}".encode()).hexdigest()[:12]
            case["_needs_login"] = needs_login(case)
            mapping = mappings.get(case["_origin_source"], {})
            if not isinstance(mapping, dict) or not isinstance(mapping.get("source_tcs", []), list):
                raise CaseFormatError("原TC映射格式错误")
            case["_source_tcs"] = mapping.get("source_tcs", [])
            if any(not isinstance(tc, str) or not tc.startswith("TC-") for tc in case["_source_tcs"]):
                raise CaseFormatError("原TC映射应填写TC编号字符串")
            case["_source_note"] = mapping.get("note", "")
            case["_known_issue"] = mapping.get("known_issue", "")
            profile = mapping.get("preparation", "none")
            if profile not in {"none", "admin", "creation_ready", "prepared_user", "query_session", "maintainer_session", "interrupted", "permission"}:
                raise CaseFormatError("未知公共前置配置")
            case["_preparation"] = profile
            case["_permission_spec"] = mapping.get("permission_fixture", {})
            case["_requirement_status"] = mapping.get("requirement_status", "confirmed")
            if case["_requirement_status"] not in {"confirmed", "pending"}:
                raise CaseFormatError("业务规则状态无效")
            case["_needs_login"] = needs_login(case) or profile != "none"
            scenario_key = mapping.get("scenario")
            scenario = deepcopy(scenarios.get(scenario_key, {})) if scenario_key else {}
            if scenario_key and (not scenario or scenario.get("source_tc") not in case["_source_tcs"]):
                raise CaseFormatError("参数组与原TC映射不一致")
            if scenario and (type(scenario.get("expected_business_code")) is not int
                    or type(scenario.get("expected_owned_users")) is not int
                    or scenario["expected_owned_users"] < 0 or scenario.get("identity") != "admin"):
                raise CaseFormatError("密码参数组的身份或结果约定格式不正确")
            case["_scenario"] = scenario
            case_id = scenario.get("case_id") or mapping.get("case_id") or case["_id"]
            if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", case_id):
                raise CaseFormatError("case_id须使用字母、数字、下划线、点或连字符")
            case["_id"] = case_id
            if assertion_copy:
                copied = copies.get(case["_source"])
                if not isinstance(copied, dict) or copied.get("origin") != case["_origin_source"]:
                    raise CaseFormatError("副本未登记与正式用例的对应关系")
                case["_id"] = "copy__" + case_id
                case["_exercise"] = deepcopy(copied.get("fault", {}))
                case["name"] = "【断言失败副本】" + case["name"]
                if case["_exercise"]:
                    step = case["steps"][case["_exercise"]["response_step"] - 1]
                    expected = step.get("response", {}).get("status_code")
                    case["_exercise"]["expected_in_file"] = expected
                    case["_exercise"]["phase"] = "fault" if expected == 999 else "restored" if expected == 200 else "custom"
            else:
                case["_exercise"] = {}
            case["_expected_preparation"] = mapping.get("expected_preparation", {})
            expectations = ({"password_length": scenario["password_length"],
                             "allowed_password_length": scenario["allowed_length_range"], "ascii_only": True}
                            if scenario else mapping.get("input_expectations", {}))
            if not isinstance(expectations, dict) or set(expectations) - {"password_length", "allowed_password_length", "ascii_only"}:
                raise CaseFormatError("输入约定只支持password_length、allowed_password_length和ascii_only")
            if expectations:
                length = expectations.get("password_length")
                limits = expectations.get("allowed_password_length")
                if (type(length) is not int or length <= 0 or not isinstance(limits, list) or len(limits) != 2
                        or any(type(value) is not int for value in limits) or not 0 < limits[0] <= limits[1]
                        or type(expectations.get("ascii_only", True)) is not bool):
                    raise CaseFormatError("密码边界输入约定格式不正确")
            if relative.parts[1] == "创建密码边界" and not expectations:
                raise CaseFormatError("密码边界用例须在data/case_mapping.yaml登记输入长度约定，避免重命名后证据丢失")
            case["_input_expectations"] = expectations
            result.append(case)
    if len({case["_id"] for case in result}) != len(result):
        raise CaseFormatError("参数实例case_id重复，请为每个实例提供稳定且唯一的标识")
    return result
