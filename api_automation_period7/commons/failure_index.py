"""当前运行的失败/待确认索引；不创建reports历史目录，不增加另一种网页报告。"""

from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import shutil

from .safe_evidence import scrub, sanitize_artifacts
from .stage import CURRENT_STAGE


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_current_evidence(root, *, results_dir, junit_path, pytest_exit_code, environment,
                           run_label=None, run_token=None, assertion_copy=False, started_at=None):
    root, results = Path(root), Path(results_dir)
    phase_file = results / "phase_results.json"
    phases = read_json(phase_file).get("events", []) if phase_file.is_file() else []
    records = []
    for path in sorted(results.glob("*-result.json")):
        raw = read_json(path)
        labels = {x["name"]: x["value"] for x in raw.get("labels", [])}
        if run_token and labels.get("run_token") != run_token:
            raise ValueError("当前结果不属于本次运行，停止生成失败索引")
        tag = labels.get("batch_tag")
        directory = results / "cases" / str(tag)
        summary_path, index_path = directory / "run_summary.json", directory / "case_index.json"
        summary = read_json(summary_path) if summary_path.is_file() else {}
        index = read_json(index_path) if index_path.is_file() else {}
        nodeid = index.get("nodeid") or summary.get("nodeid")
        if nodeid is None:
            nodeid = next((event["nodeid"] for event in phases if event.get("source") == labels.get("case_source")), None)
        events = [event for event in phases if event["nodeid"] == nodeid]
        case_id = summary.get("case_id") or index.get("case_id") or labels.get("case_id")
        mode = "--assertion-copy" if assertion_copy else "--business"
        reproduce = f'.\\.venv\\Scripts\\python.exe .\\main.py {mode} --case-id {case_id} -v' if case_id else None
        record = {"case_id": case_id, "nodeid": nodeid, "name": raw["name"], "status": raw["status"],
                  "business_verdict": summary.get("business_verdict"), "kind": labels.get("case_kind"),
                  "source": labels.get("case_source"), "source_tcs": summary.get("source_tcs", []),
                  "known_issue": summary.get("known_issue", ""), "batch_tag": tag,
                  "phase_events": events, "last_step": summary.get("last_step"),
                  "expected_actual": summary.get("last_assertion", {}),
                  "input_evidence": index.get("input_evidence", []), "checkpoint_comparisons": index.get("checkpoints", {}),
                  "message": raw.get("statusDetails", {}).get("message", ""),
                  "cleanup_ok": summary.get("cleanup_ok"),
                  "case_index": f"cases/{tag}/case_index.json" if index_path.is_file() else None,
                  "http_evidence": f"cases/{tag}/http.jsonl" if (directory / "http.jsonl").is_file() else None,
                  "cleanup_evidence": f"cases/{tag}/run_summary.json" if summary_path.is_file() else None,
                  "reproduce": reproduce,
                  "evidence_limitations": ["本条证据来自接口及客户端回查；未为本次运行另采数据库SQL或服务端日志",
                                           "运行摘要缺失时不能声称资源已确认清理"] if not summary else
                                          ["当前证据为客户端请求与接口回查；需要额外服务端日志或SQL时另行限定对象与时间补证"]}
        historical = {"BUG-T3-002": ["functional_testing_period3/docs/T3_缺陷记录.md"],
                      "BUG-T3-003": ["database_testing_period5/docs/T5.5_执行说明.md"],
                      "BUG-T3-004": ["linux_testing_period6/docs/T6.4_执行记录.md"]}
        record["historical_correlations"] = {"scope": "仅历史关联，不冒记为本次新采集的SQL或服务端日志",
                                             "documents_relative_to_Ruo_Yi": historical.get(record["known_issue"], [])}
        records.append(scrub(record))
    failures = [r for r in records if r["status"] in {"failed", "broken"}]
    pending = [r for r in records if r["business_verdict"] == "pending_requirement"]
    current = {"evidence_schema": "T78_whitelist_v1", "stage": CURRENT_STAGE, "run_label": run_label, "run_token": run_token,
               "kind": "assertion_copy" if assertion_copy else "business", "started_at": started_at,
               "finished_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
               "pytest_exit_code": int(pytest_exit_code), "allure_exit_code": None,
               "case_count": len(records), "parameter_instances": len(records),
               "unique_original_tc_count": len({tc for record in records for tc in record["source_tcs"]}),
               "counts": dict(Counter(r["status"] for r in records)),
               "phase_event_counts": dict(Counter(p["phase"] for p in phases)),
               "failed_phase_events": sum(p["outcome"] == "failed" for p in phases),
               "pending_requirement_cases": len(pending),
               "http_requests": sum(len((results / r["http_evidence"]).read_text(encoding="utf-8").splitlines()) for r in records if r["http_evidence"]),
               "assertion_count": None, "assertion_count_note": "未对所有内嵌断言计数，不把请求数或阶段事件数作为断言数",
               "all_cleanup_ok": bool(records) and all(r["cleanup_ok"] is True for r in records),
               "results": records}
    paths = [root / name for name in ["main.py", "conftest.py", "pytest.ini", "requirements.txt", "requirements.lock.txt"]]
    for name in ["commons", "data", "tests"]:
        paths += [p for p in (root / name).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                  and not p.resolve().is_relative_to(results.resolve())
                  and p.suffix in {".py", ".json", ".yaml", ".yml", ".ini", ".txt"}]
    manifest = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for name, value in [("current_run.json", current), ("failure_index.json", {"failures": failures, "pending_requirements": pending}),
                        ("environment_info.json", environment), ("source_manifest.json", manifest)]:
        (results / name).write_text(json.dumps(scrub(value), ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def publish_evidence(results, report):
    """给Allure网页配套当前JSON证据文件，不另生成HTML/历史报告。"""
    results, target = Path(results), Path(report) / "evidence"
    target.mkdir(exist_ok=True)
    for name in ["current_run.json", "failure_index.json", "environment_info.json", "phase_results.json", "source_manifest.json"]:
        if (results / name).is_file():
            shutil.copy2(results / name, target / name)
    if (results / "cases").is_dir():
        shutil.copytree(results / "cases", target / "cases", dirs_exist_ok=True)
