"""HTTP 摘要脱敏后再写入日志和 Allure，不输出真实凭据和验证码图片。"""

import json
import logging
from pathlib import Path
import shutil
import subprocess
import allure
from types import SimpleNamespace
from .safe_evidence import scrub, record_http as record_safe_http

SENSITIVE = {"password", "admin_password", "new_password", "token", "authorization",
             "cookie", "set-cookie", "uuid", "captcha_uuid", "captcha_code", "captcha_answer",
             "redis_password", "img", "secret"}


def redact(value, *, request=False):
    if request and isinstance(value, dict):
        value = {key: "***" if str(key).lower() == "code" else item for key, item in value.items()}
    return scrub(value)


def record_http(method, path, options, response, *, input_evidence=None):
    """保留旧调用签名；主客户端已统一记录，这里同样只输出白名单摘要。"""
    client = SimpleNamespace(evidence_context=None, events=[], actor="未绑定调用方")
    return record_safe_http(client, method, path, options, response, input_evidence=input_evidence)


def generate_business_report(project_root, *, assertion_copy=False, results_dir=None, report_dir=None):
    """总调度调用的 Allure 转换：只读取业务结果，不执行任何用例。"""
    root = Path(project_root).resolve()
    results = Path(results_dir) if results_dir else root / "data/temps"
    report = Path(report_dir) if report_dir else root / "report"
    if not results.resolve().is_relative_to(root) or not report.resolve().is_relative_to(root):
        raise ValueError("Allure结果和报告目录必须位于当前项目")
    results.mkdir(exist_ok=True)
    records = []
    for path in results.glob("*-result.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        source = next((label["value"] for label in value.get("labels", [])
                       if label["name"] == "case_source"), "")
        if not value.get("fullName", "").endswith("#test_yaml_case") or not source.startswith("tests/"):
            raise ValueError("data/temps混入非YAML业务结果，停止生成混合报告")
        if source.startswith("tests/断言失败副本测试/") != assertion_copy:
            raise ValueError("当前data/temps与所选模式不符；请重新执行该模式，不能把旧结果伪装为另一类报告")
        policy = next((entry["value"] for entry in value.get("labels", []) if entry["name"] == "evidence_policy"), None)
        if policy != "T78_whitelist_v1":
            raise ValueError("旧结果未按当前白名单策略取证，请重新执行用例后生成报告")
        records.append(value)
    executable = shutil.which("allure")
    fallback = Path(r"E:\software\allure-2.46.1\bin\allure.bat")
    if executable is None and fallback.is_file():
        executable = str(fallback)
    if executable is None:
        raise RuntimeError("未找到 Allure 命令行工具，请核对 PATH")
    title = "若依断言失败副本练习报告" if assertion_copy else "若依业务用例执行报告"
    if not records:
        title += "（尚未执行）"
    # 只记录真实存在的结果条数，不创建伪造的通过或跳过用例。
    state = "Execution records present" if records else "Not executed"
    captcha_modes = sorted({label["value"] for value in records for label in value.get("labels", [])
                            if label["name"] == "captcha_mode"})
    captcha_observed = sorted({label["value"] for value in records for label in value.get("labels", [])
                               if label["name"] == "captcha_enabled"})
    stages = sorted({label["value"] for value in records for label in value.get("labels", [])
                     if label["name"] == "test_stage"})
    (results / "environment.properties").write_text(
        f"Business.execution={state}\nBusiness.result.count={len(records)}\n"
        f"Business.stage={','.join(stages) or 'not_recorded'}\n"
        f"Captcha.mode={','.join(captcha_modes) or 'not_recorded'}\n"
        f"Captcha.observed.enabled={','.join(captcha_observed) or 'not_recorded'}\n", encoding="ascii")
    info = results / "environment_info.json"
    if info.is_file():
        environment = json.loads(info.read_text(encoding="utf-8"))
        versions = {"Python.version": environment.get("python"),
                    "Requests.version": environment.get("packages", {}).get("requests"),
                    "pytest.version": environment.get("packages", {}).get("pytest"),
                    "Target.environment": environment.get("target_environment"),
                    "Backend.source.commit": environment.get("backend", {}).get("source_commit"),
                    "Frontend.source.commit": environment.get("frontend", {}).get("source_commit"),
                    "Backend.deployed.commit": "not_verified", "Frontend.deployed.commit": "not_verified"}
        with (results / "environment.properties").open("a", encoding="ascii") as stream:
            for key, value in versions.items():
                stream.write(key + "=" + str(value or "not_verified") + "\n")
    try:
        result = subprocess.run(
            [executable, "generate", str(results), "-o", str(report), "--clean",
             "--lang", "zh", "--name", title], cwd=root, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Allure转换未完成，原始业务结果仍保留在data/temps") from None
    if result.returncode == 0:
        current = results / "current_run.json"
        if current.is_file():
            value = json.loads(current.read_text(encoding="utf-8"))
            value["allure_exit_code"] = result.returncode
            current.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        from .failure_index import publish_evidence
        publish_evidence(results, report)
    return result.returncode
