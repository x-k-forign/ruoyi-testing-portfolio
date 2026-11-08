"""公共执行配置：从 tests 读取业务 YAML，为每条用例提供独立会话。"""

from pathlib import Path
from copy import deepcopy

import allure
import pytest

from commons.allure_utils import apply_case_title, case_marks
from commons.case_catalog import discover_cases
from commons.config import PROJECT_ROOT, load_config
from commons.runner_utils import create_context, close_context
from commons.captcha_utils import validate_captcha_settings
from commons.preparation_utils import (prepare_admin, prepare_creation_fields, UserFactory,
                                       prepare_subject_session, prepare_interrupted)
from commons.business_utils import admin_client as current_admin_client
from commons import safe_evidence
from commons.pytest_evidence import prepare_item, phase_report
import json
import uuid


def pytest_addoption(parser):
    parser.addoption("--api-config", default=str(PROJECT_ROOT / ".private/t74.local.json"),
                     help="本地私有 JSON/YAML 环境配置")
    parser.addoption("--group", action="append", default=[], help="tests 下的业务分组目录，可重复指定")
    parser.addoption("--assertion-copy", action="store_true", default=False, help="显式运行断言失败副本，默认正式回归不包含它")
    parser.addoption("--business", action="store_true", default=False, help="明确运行正式用例，覆盖环境中预设的副本开关")
    parser.addoption("--run-token", default=None, help="总调度为本次运行生成的唯一标识，不含凭据")
    parser.addoption("--case-id", action="append", default=[], help="精确选择参数实例ID，可重复指定")
    parser.addoption("--captcha-mode", choices=("redis", "manual"), default="redis", help="验证码保持开启，默认从测试Redis自动取本次答案")


def pytest_generate_tests(metafunc):
    if "yaml_case" not in metafunc.fixturenames:
        return
    registered = {line.split(":", 1)[0].split("(", 1)[0].strip()
                  for line in metafunc.config.getini("markers")}
    parameters = []
    copy_mode = metafunc.config.getoption("--assertion-copy") and not metafunc.config.getoption("--business")
    cases = discover_cases(metafunc.config.getoption("--group"), assertion_copy=copy_mode)
    selected = metafunc.config.getoption("--case-id")
    if set(selected) - {case["_id"] for case in cases}:
        raise pytest.UsageError("--case-id未匹配当前模式中的实例，请先用--list查看")
    for case in cases:
        if selected and case["_id"] not in selected:
            continue
        if set(case["mark"]) - registered:
            raise pytest.UsageError("YAML 使用了未注册的 mark，请先在 pytest.ini 注册")
        # 使用 YAML 声明的业务标记；Allure 分组仍根据用例目录生成。
        marks = [*[getattr(pytest.mark, name) for name in case["mark"]], *case_marks(case)]
        if case["_assertion_copy"]:
            marks.append(pytest.mark.assertion_copy)
        # Redis模式不需要人工；显式manual模式才动态添加interactive标记。
        if (case["_needs_login"] and metafunc.config.getoption("--captcha-mode") == "manual"
                and "interactive" not in case["mark"]):
            marks.append(pytest.mark.interactive)
        parameters.append(pytest.param(case, id=case["_id"], marks=marks))
    metafunc.parametrize("yaml_case", parameters)


def pytest_collection_modifyitems(config, items):
    if not config.option.collectonly:
        if config.getoption("numprocesses", default=None) not in (None, 0):
            raise pytest.UsageError("当前业务集合涉及独立账号和登录状态，请串行执行")
        if config.getoption("reruns", default=0):
            raise pytest.UsageError("业务登录和验证码流程不自动重跑，请修正问题后重新执行")


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    prepare_item(item)
    case = getattr(getattr(item, "callspec", None), "params", {}).get("yaml_case")
    if case is not None:
        apply_case_title(item, case)
        token = item.config.getoption("--run-token")
        if token:
            allure.dynamic.label("run_token", token)
    if item.get_closest_marker("interactive") and item.config.getoption("capture") != "no":
        raise pytest.UsageError("登录用例需人工输入验证码，请用 main.py 运行，或为 pytest 添加 -s")


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    if config.option.collectonly:
        return
    if config.getoption("showlocals", default=False):
        raise pytest.UsageError("报告脱敏模式不启用--showlocals，请移除局部变量展示选项")
    token = config.getoption("--run-token") or uuid.uuid4().hex
    config._evidence_run_token = token
    directory = Path(config.getoption("allure_report_dir") or PROJECT_ROOT / "data/temps")
    config._evidence_results_dir = directory if directory.is_absolute() else PROJECT_ROOT / directory
    if not config._evidence_results_dir.resolve().is_relative_to(PROJECT_ROOT.resolve()):
        raise pytest.UsageError("本项目的Allure原始结果目录必须位于项目内")
    safe_evidence.begin_run(config._evidence_results_dir, token)
    safe_evidence.install_log_filter()
    if config.getoption("capture") == "no":
        safe_evidence.install_console_filter()


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item):
    safe_evidence.set_phase("call")


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_teardown(item):
    safe_evidence.set_phase("teardown")


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    phase_report(item, call, report)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    config = session.config
    directory = getattr(config, "_evidence_results_dir", None)
    if directory is not None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "phase_results.json").write_text(json.dumps({"run_token": config._evidence_run_token,
            "pytest_exit_code": int(exitstatus), "events": safe_evidence.PHASES}, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    if config.option.collectonly:
        return
    safe_evidence.restore_log_filter()
    safe_evidence.restore_console_filter()
    directory = getattr(config, "_evidence_results_dir", None)
    if directory is not None:
        safe_evidence.sanitize_artifacts(directory, [getattr(config.option, "xmlpath", None), config.getini("log_file")])


@pytest.fixture(scope="session")
@allure.title("定位本地被测环境配置")
def api_config_path(pytestconfig):
    path = Path(pytestconfig.getoption("--api-config"))
    return path if path.is_absolute() else PROJECT_ROOT / path


class RuntimeConfig(dict):
    def __repr__(self):
        return "<RuntimeConfig: 私有凭据不展示>"


@pytest.fixture(scope="session")
def config_loader():
    """本进程只缓存只读配置原稿；交给每条用例的都是深拷贝。"""
    cache = {}
    def read(path, require_credentials):
        key = (str(path), require_credentials)
        if key not in cache:
            cache[key] = load_config(path, require_credentials=require_credentials)
        return RuntimeConfig(deepcopy(cache[key]))
    return read


@pytest.fixture(scope="function")
@allure.title("读取本例配置副本")
def environment_config(yaml_case, api_config_path, pytestconfig, config_loader):
    path = api_config_path if yaml_case["_needs_login"] else PROJECT_ROOT / "data/config/environment.example.yaml"
    cfg = config_loader(path, yaml_case["_needs_login"])
    safe_evidence.register_sensitive(cfg)
    if yaml_case["_needs_login"]:
        mode = pytestconfig.getoption("--captcha-mode")
        cfg["_captcha_settings"] = validate_captcha_settings(cfg, mode)
        allure.dynamic.label("captcha_mode", mode)
    else:
        cfg["_captcha_settings"] = {"mode": "not_used", "max_attempts": 1}
    return cfg


@pytest.fixture(scope="function")
@allure.title("建立本例上下文，并在准备业务资源前登记统一收尾")
def case_runtime(yaml_case, environment_config, request):
    context = create_context(environment_config)
    context["_case"] = yaml_case
    context["_nodeid"] = request.node.nodeid
    directory = request.config._evidence_results_dir / "cases" / context["batch_tag"]
    directory.mkdir(parents=True, exist_ok=True)
    context["_evidence_dir"] = directory
    request.node._case_evidence_context = context
    request.node._case_evidence_dir = directory
    request.node._evidence_metadata["batch_tag"] = context["batch_tag"]
    allure.dynamic.label("batch_tag", context["batch_tag"])
    if yaml_case["_needs_login"]:
        context["admin_password"] = environment_config["admin_password"]
    for key in ("expected_business_code", "expected_owned_users"):
        if key in yaml_case.get("_scenario", {}):
            context[key] = yaml_case["_scenario"][key]
    def finish():
        with allure.step("回查本批账号清理、退出各身份会话并保存执行证据"):
            close_context(context)
    # 此时还没有登录或创建业务账号。后续任一fixture在yield前失败也会执行它。
    request.addfinalizer(finish)
    return context


@pytest.fixture(scope="function")
@allure.title("准备本例管理员身份")
def admin_client(case_runtime):
    prepare_admin(case_runtime)
    return current_admin_client(case_runtime)


@pytest.fixture(scope="function")
@allure.title("确认本例创建所需部门和查询角色")
def creation_ready(case_runtime, admin_client):
    prepare_creation_fields(case_runtime)
    return case_runtime


@pytest.fixture(scope="function")
@allure.title("提供本例账号工厂")
def user_factory(creation_ready):
    return UserFactory(creation_ready)


@pytest.fixture(scope="function")
@allure.title("准备本例专用查询用户")
def prepared_user(case_runtime, user_factory):
    user_factory.create()
    return case_runtime["new_user_id"]


@pytest.fixture(scope="function")
@allure.title("准备本例查询用户的独立会话")
def query_user_session(case_runtime, prepared_user):
    prepare_subject_session(case_runtime)
    return case_runtime


@pytest.fixture(scope="function")
@allure.title("准备本例维护用户及其原会话")
def maintainer_user_session(case_runtime, user_factory):
    user_factory.create(maintainer=True)
    prepare_subject_session(case_runtime, maintainer=True)
    return case_runtime


@pytest.fixture(scope="function")
@allure.title("执行本例声明的准备中断，核对补偿后提供独立验证身份")
def interrupted_preparation(case_runtime, user_factory):
    prepare_interrupted(case_runtime, user_factory)
    return case_runtime


@pytest.fixture(scope="function")
@allure.title("准备本例专属部门、角色、多账号和原会话")
def permission_resources(case_runtime, admin_client):
    from commons.permission_resources import PermissionResources
    resources = PermissionResources(case_runtime)
    # 在第一项资源创建前交给已登记的父级finalizer，覆盖准备部分成功后失败。
    case_runtime["_permission_resources"] = resources
    resources.prepare(case_runtime["_case"]["_permission_spec"])
    return resources


@pytest.fixture(scope="function")
@allure.title("交付本例所需的公共前置与独立上下文")
def case_context(yaml_case, case_runtime, request):
    profile = yaml_case["_preparation"]
    fixtures = {"none": None, "admin": "admin_client", "creation_ready": "creation_ready",
                "prepared_user": "prepared_user", "query_session": "query_user_session",
                "maintainer_session": "maintainer_user_session", "interrupted": "interrupted_preparation",
                "permission": "permission_resources"}
    case_runtime["_preparation"] = {"profile": profile, "status": "preparing"}
    try:
        if fixtures[profile]:
            request.getfixturevalue(fixtures[profile])
        if profile != "interrupted":
            case_runtime["_preparation"]["status"] = "ready"
    except BaseException as error:
        case_runtime["_setup_error_type"] = type(error).__name__
        case_runtime["_preparation"].update(status="failed", error_type=type(error).__name__)
        raise
    yield case_runtime
