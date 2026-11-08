"""pytest阶段证据：同一nodeid分别记录setup/call/teardown，不虚增用例数量。"""

from pathlib import Path
import json
import traceback

import allure

from .config import PROJECT_ROOT
from .safe_evidence import META, PHASES, scrub, safe_text, set_case, set_phase


def prepare_item(item):
    case = getattr(getattr(item, "callspec", None), "params", {}).get("yaml_case", {})
    metadata = {"nodeid": item.nodeid, "case_id": case.get("_id", item.name),
                "source": case.get("_source"), "source_tcs": case.get("_source_tcs", []),
                "known_issue": case.get("_known_issue", ""),
                "kind": "assertion_copy" if case.get("_assertion_copy") else "business",
                "teaching_fault": case.get("_exercise", {}).get("phase") == "fault", "phase": "setup"}
    item._evidence_metadata = metadata
    set_case(metadata)


def category(report, error, case, context):
    if report.skipped:
        return "pending_requirement" if context.get("_business_verdict") == "pending_requirement" else "skipped"
    if not report.failed:
        return "phase_passed"
    name = type(error).__name__ if error else "UnknownError"
    if report.when == "teardown":
        return "cleanup"
    if name in {"ConnectionFailure", "RequestTimeout", "ConnectionError", "Timeout"}:
        return "network"
    if name in {"ResponseFormatError", "ExtractionError", "JSONDecodeError"}:
        return "parsing"
    if report.when == "setup" or name == "PreparationError":
        return "preparation"
    if case.get("_exercise", {}).get("phase") == "fault":
        return "teaching_assertion"
    if isinstance(error, AssertionError):
        return "known_product_expectation" if case.get("_known_issue") else "assertion"
    return "execution"


def phase_report(item, call, report):
    metadata = getattr(item, "_evidence_metadata", {"nodeid": item.nodeid, "case_id": item.name})
    case = getattr(getattr(item, "callspec", None), "params", {}).get("yaml_case", {})
    context = getattr(item, "_case_evidence_context", {})
    error = call.excinfo.value if call.excinfo else None
    message = safe_text(str(error)) if error is not None else ""
    location = None
    if error is not None and error.__traceback__:
        frame = traceback.extract_tb(error.__traceback__)[-1]
        path = Path(frame.filename)
        location = {"file": path.relative_to(PROJECT_ROOT).as_posix() if path.is_relative_to(PROJECT_ROOT) else path.name,
                    "line": frame.lineno, "function": frame.name}
    if isinstance(report.longrepr, tuple):
        report.longrepr = tuple(safe_text(x) if isinstance(x, str) else x for x in report.longrepr)
    elif report.longrepr:
        trace = safe_text(report.longreprtext)
        report.longrepr = (safe_text(call.excinfo.exconly()) + "\n" + trace) if call.excinfo else trace
    report.sections = [(name, safe_text(content)) for name, content in report.sections]
    record = {**metadata, "phase": report.when, "outcome": report.outcome, "duration": round(report.duration, 6),
              "category": category(report, error, case, context), "error_type": type(error).__name__ if error else None,
              "message": message, "location": location}
    PHASES.append(scrub(record))
    allure.attach(json.dumps(scrub(record), ensure_ascii=False, indent=2),
                  name=f"阶段结果：{report.when} / {report.outcome}", attachment_type=allure.attachment_type.JSON)
    if report.when == "teardown":
        directory = getattr(item, "_case_evidence_dir", None)
        if directory:
            summary_file = directory / "run_summary.json"
            summary = json.loads(summary_file.read_text(encoding="utf-8")) if summary_file.is_file() else {}
            phases = [row for row in PHASES if row["nodeid"] == item.nodeid]
            value = {"nodeid": item.nodeid, "case_id": metadata.get("case_id"),
                     "source": metadata.get("source"), "source_tcs": metadata.get("source_tcs", []),
                     "known_issue": metadata.get("known_issue"), "kind": metadata.get("kind"),
                     "batch_tag": summary.get("batch_tag"), "phases": phases,
                     "last_step": summary.get("last_step"), "last_assertion": summary.get("last_assertion"),
                     "input_evidence": [{k: v for k, v in row.items() if k != "password"} for row in summary.get("input_evidence", [])],
                     "checkpoints": summary.get("checkpoints", {}), "set_checks": summary.get("set_checks", []),
                     "cleanup_ok": summary.get("cleanup_ok"), "cleanup": summary.get("cleanup", []),
                     "resource_cleanup": summary.get("resource_cleanup", []), "restorations": summary.get("restorations", []),
                     "session_cleanup": summary.get("session_cleanup", []),
                     "http_evidence": "http.jsonl", "cleanup_evidence": "run_summary.json",
                     "pending_requirement": summary.get("pending_requirement")}
            mode = "--assertion-copy" if metadata.get("kind") == "assertion_copy" else "--business"
            value["reproduce"] = f'.\\.venv\\Scripts\\python.exe .\\main.py {mode} --case-id {metadata.get("case_id")} -v'
            value["current_report_evidence"] = "evidence/cases/" + str(summary.get("batch_tag"))
            value = scrub(value)
            (directory / "case_index.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            if any(row["outcome"] != "passed" for row in phases):
                allure.attach(json.dumps(value, ensure_ascii=False, indent=2), name="失败或待确认定位与证据链",
                              attachment_type=allure.attachment_type.JSON)
        set_case({})
