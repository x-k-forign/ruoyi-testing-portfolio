"""总调度：解析运行参数、筛选 YAML、启动 pytest、生成 Allure 并汇总退出码。"""

import argparse
import configparser
import json
from pathlib import Path
import os
import shlex
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from commons.case_catalog import discover_cases
from commons.report_utils import generate_business_report
from commons.environment_evidence import capture_environment
from commons.failure_index import write_current_evidence
from commons.safe_evidence import sanitize_artifacts

ROOT = Path(__file__).resolve().parent


def configured_assertion_copy():
    """与pytest.ini/PYTEST_ADDOPTS中的副本开关保持一致，避免执行模式与报告模式不符。"""
    config = configparser.ConfigParser(interpolation=None)
    config.read(ROOT / "pytest.ini", encoding="utf-8-sig")
    arguments = shlex.split(config.get("pytest", "addopts", fallback=""))
    arguments += shlex.split(os.environ.get("PYTEST_ADDOPTS", ""))
    return "--assertion-copy" in arguments


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="只查看 YAML 业务用例清单，不发送请求")
    mode.add_argument("--collect-only", action="store_true", help="只收集用例，不发送请求")
    mode.add_argument("--report-only", action="store_true", help="只转换已有业务结果，不重跑用例")
    parser.add_argument("--group", action="append", default=[], help="指定 tests 下的业务分组，可重复指定")
    parser.add_argument("--api-config", help="指定本地私有 JSON/YAML 环境配置")
    suite = parser.add_mutually_exclusive_group()
    suite.add_argument("--assertion-copy", action="store_true", default=configured_assertion_copy(),
                        help="运行断言失败副本，同样生成report；下次运行覆盖当前网页")
    suite.add_argument("--business", action="store_true", help="明确运行正式40条，覆盖预设的副本模式")
    parser.add_argument("--run-label", help="本次运行标签，用于当前证据定位，不改变业务预期")
    parser.add_argument("--captcha-mode", choices=("redis", "manual"), default="redis", help="默认Redis自动取验证码，可显式选择manual人工输入")
    parser.add_argument("--no-report", action="store_true", help="测试结束后不转换 Allure 网页")
    parser.add_argument("-m", dest="mark", help="按 YAML 的 mark 筛选")
    parser.add_argument("-k", dest="keyword", help="按 pytest 用例 ID 筛选")
    parser.add_argument("--case-id", action="append", default=[], help="精确选择实例ID，可重复指定")
    detail = parser.add_mutually_exclusive_group()
    detail.add_argument("-q", action="store_true", help="简洁输出")
    detail.add_argument("-v", action="store_true", help="详细输出")
    parser.add_argument("-s", action="store_true", help="兼容 pytest 参数，实际执行默认允许人工输入")
    options = parser.parse_args(argv)
    if options.business:
        options.assertion_copy = False

    # 总调度负责固定运行目录，避免日志、结果被写到其他目录。
    os.chdir(ROOT)
    if options.list:
        cases = discover_cases(options.group, assertion_copy=options.assertion_copy)
        if options.case_id:
            if set(options.case_id) - {case["_id"] for case in cases}:
                parser.error("--case-id未匹配当前模式，请先查看完整--list")
            cases = [case for case in cases if case["_id"] in options.case_id]
        for case in cases:
            print(f"[{case['_group']}] {case['name']}\n  {case['_source']}")
            print(f"  原TC：{'、'.join(case['_source_tcs']) or '前置资料检查'}；用例ID：{case['_id']}")
        print(f"共 {len(cases)} 条业务 YAML；本次未执行。")
        return 0
    if options.report_only:
        return generate_business_report(ROOT, assertion_copy=options.assertion_copy)

    # 真正执行 YAML 的函数在 tests/test_yaml_case.py，不放在 main 中。
    arguments = [str(ROOT / "tests" / "test_yaml_case.py")]
    if options.assertion_copy:
        arguments.append("--assertion-copy")
    else:
        arguments.append("--business")
    arguments.extend(["--captcha-mode", options.captcha_mode])
    for group in options.group:
        arguments.extend(["--group", group])
    if options.api_config:
        arguments.extend(["--api-config", options.api_config])
    if options.mark:
        arguments.extend(["-m", options.mark])
    if options.keyword:
        arguments.extend(["-k", options.keyword])
    for case_id in options.case_id:
        arguments.extend(["--case-id", case_id])
    if options.q:
        arguments.append("-q")
    elif options.v:
        arguments.append("-v")
    if options.collect_only:
        # 只收集不清理原temps，也不覆盖实际运行日志或报告。
        arguments.extend(["--collect-only", "-o", "addopts=-ra --tb=short --strict-markers",
                          "-o", "log_file=NUL", "-o", "result_log_enable=0", "-p", "no:cacheprovider"])
    else:
        (ROOT / ".local").mkdir(exist_ok=True)
        # manual模式仍允许输入；Redis模式无需人工。只收集时不覆盖实际执行记录。
        junit = ROOT / ".local" / ("last_assertion_copy_pytest.xml" if options.assertion_copy else "last_business_pytest.xml")
        arguments.extend(["-s", "--junitxml=" + str(junit)])
        if options.assertion_copy:
            arguments.extend(["-o", "log_file=logs/pytest_assertion_copy.log"])
    run_token = uuid.uuid4().hex
    started_at = datetime.now(timezone(timedelta(hours=8))).isoformat()
    if not options.collect_only:
        arguments.extend(["--run-token", run_token])
    selection = {"groups": options.group, "mark": options.mark, "keyword": options.keyword,
                 "case_ids": options.case_id, "captcha_mode": options.captcha_mode,
                 "kind": "assertion_copy" if options.assertion_copy else "business"}
    environment = capture_environment(ROOT, selection) if not options.collect_only else None
    code = int(pytest.main(arguments))
    if options.collect_only:
        return code
    results = ROOT / "data/temps"
    report = ROOT / "report"
    sanitize_artifacts(results, [junit, ROOT / "logs" / ("pytest_assertion_copy.log" if options.assertion_copy else "pytest.log")])
    current = write_current_evidence(ROOT, results_dir=results, junit_path=junit, pytest_exit_code=code,
                                    environment=environment, run_label=options.run_label, run_token=run_token,
                                    assertion_copy=options.assertion_copy, started_at=started_at)
    report_code = None
    if not options.no_report and any(results.glob("*-result.json")):
        try:
            report_code = generate_business_report(ROOT, assertion_copy=options.assertion_copy)
        except Exception as error:
            report_code = 2
            print("Allure生成未完成：" + type(error).__name__ + "；当前原始结果仍在data/temps。", flush=True)
    current["allure_exit_code"] = report_code
    (results / "current_run.json").write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"当前结果：{len(current['results'])}条；失败索引：data/temps/failure_index.json；无reports历史归档。", flush=True)
    # 报告转换成功不能掩盖业务用例失败；转换失败同样返回非零。
    return code if code else (report_code or 0)


if __name__ == "__main__":
    raise SystemExit(main())
