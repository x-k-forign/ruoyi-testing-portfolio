"""执行 T9 的 pytest 用例并覆盖当前 Allure 报告。"""

import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def output_path(*parts):
    path = ROOT.joinpath(*parts)
    if path.resolve() != path:
        raise ValueError(f"运行产物目录不能重定向到其他位置：{path}")
    return path


def case_selector(value):
    if not re.fullmatch(r"TC-[A-Z][0-9]+-[0-9]+", value):
        raise argparse.ArgumentTypeError("用例编号格式如 TC-C01-01")
    return "test_" + value.lower().replace("-", "_")


def main():
    parser = argparse.ArgumentParser(description="运行 T9 UI 用例并覆盖 Allure 报告")
    parser.add_argument("--case", type=case_selector, action="append", help="按原用例编号筛选，可重复传入 --case")
    options = parser.parse_args()
    selection = ["-k", " or ".join(options.case)] if options.case else []
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv_python.is_file():
        print("缺少 T9 项目 .venv 的 Python。", file=sys.stderr)
        return 1

    allure = shutil.which("allure")
    if allure is None:
        print("PATH 中找不到 Allure CLI。", file=sys.stderr)
        return 1

    runtime = output_path(".local")
    results = output_path(".local", "allure-results")
    junit = output_path(".local", "junit.xml")
    report = output_path("report")
    runtime.mkdir(exist_ok=True)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", TEMP=str(runtime), TMP=str(runtime))

    test_status = subprocess.run(
        [
            str(venv_python), "-m", "pytest", "tests", "-v", "-s", "--tb=short", "-p", "no:cacheprovider",
            "--junitxml", str(junit), "--alluredir", str(results), "--clean-alluredir", "--allure-no-capture", *selection,
        ],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode
    report_status = subprocess.run(
        [allure, "generate", str(results), "--clean", "--output", str(report)],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode
    output_path(".local", "t9-exit-status.json").write_text(
        json.dumps({"pytest": test_status, "allure": report_status}), encoding="utf-8"
    )
    print(f"pytest 退出码 {test_status}，Allure 退出码 {report_status}。", flush=True)
    if report_status == 0:
        print(f"报告：{report / 'index.html'}", flush=True)
    return test_status or report_status


if __name__ == "__main__":
    raise SystemExit(main())
