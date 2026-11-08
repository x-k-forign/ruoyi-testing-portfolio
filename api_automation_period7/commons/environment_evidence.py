"""环境版本只读取证；源码提交与实际运行产物分开说明，不导出进程完整命令或私有配置。"""

from datetime import datetime, timezone, timedelta
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import platform
import shutil
import subprocess


def git_info(path):
    git = shutil.which("git")
    fallback = Path(r"E:\software\Git\cmd\git.exe")
    git = git or (str(fallback) if fallback.is_file() else None)
    if not git or not path.is_dir():
        return {"status": "not_verified", "reason": "源码目录或Git不可用"}
    def run(arguments):
        result = subprocess.run([git, "-C", str(path), *arguments], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=10, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    commit = run(["rev-parse", "HEAD"])
    dirty = run(["status", "--porcelain", "--untracked-files=no"])
    return {"status": "source_observed" if commit else "not_verified", "source_commit": commit,
            "tracked_dirty_file_count": len(dirty.splitlines()) if dirty is not None else None,
            "deployment_commit_verified": False,
            "scope": "仅源码仓库；不把Git HEAD或工作区状态冒充实际运行版本"}


def process_observation():
    script = r'''
$observations=@();
foreach ($port in @(8080,5173)) {
 $connection=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1;
 if ($connection) {
  $process=Get-CimInstance Win32_Process -Filter ("ProcessId="+$connection.OwningProcess);
  $match=[regex]::Match($process.CommandLine,'-jar\s+(?:"([^"]+)"|(\S+))');
  $jarPath=$null; if ($match.Success) { $jarPath=if($match.Groups[1].Success){$match.Groups[1].Value}else{$match.Groups[2].Value} };
  $observations += [pscustomobject]@{port=$port;pid=$connection.OwningProcess;process_name=$process.Name;jar_path=$jarPath;command_line_exported=$false};
 }
}
ConvertTo-Json -InputObject @($observations) -Compress
'''
    try:
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            return {"status": "not_verified", "reason": "未找到PowerShell"}
        result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                                timeout=15, check=False)
        if result.returncode:
            return {"status": "not_verified", "reason": "监听进程读取未完成"}
        return {"status": "observed", "listeners": json.loads(result.stdout.decode("utf-8-sig"))}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"status": "not_verified", "reason": "监听进程证据不可得"}


def capture_environment(root, selection):
    root = Path(root)
    packages = {}
    for name in ["requests", "pytest", "allure-pytest", "PyYAML", "responses-validator", "jsonpath", "lxml", "redis"]:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "not_installed"
    sources = root.parent / "sources"
    observation = process_observation()
    backend = git_info(sources / "backend")
    frontend = git_info(sources / "frontend")
    for listener in observation.get("listeners", []):
        if listener["port"] == 8080 and listener.get("jar_path"):
            path = Path(listener["jar_path"])
            backend["running_jar_filename"] = path.name
            if path.is_absolute() and path.is_file():
                backend["running_command_artifact"] = {"filename": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "scope": "监听进程命令所指向的当前磁盘JAR摘要；未反推部署Git提交"}
                try:
                    with ZipFile(path) as jar:
                        if "META-INF/MANIFEST.MF" in jar.namelist():
                            text = jar.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
                            backend["manifest_versions"] = {line.split(": ", 1)[0]: line.split(": ", 1)[1]
                                for line in text.splitlines() if ": " in line and line.split(": ", 1)[0] in
                                {"Implementation-Version", "Spring-Boot-Version", "Build-Jdk-Spec"}}
                except (OSError, ValueError):
                    pass
            else:
                backend["running_artifact_status"] = "relative_jar_path_not_resolved"
                backend["artifact_limitation"] = "启动参数使用相对JAR名，未把候选target文件摘要当成实际运行字节码"
            listener["jar_path"] = path.name  # 公开信息只保留文件名，不导出完整进程参数。
    return {"observed_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "target_environment": "shared_local_8080", "base_url": "http://127.0.0.1:8080",
            "python": platform.python_version(), "packages": packages, "selection": selection,
            "backend": backend, "frontend": frontend, "runtime_observation": observation,
            "authentication": {"captcha_enabled_required": True, "mode": selection.get("captcha_mode"),
                               "redis_scope": "只读本次uuid对应答案；不导出连接凭据"},
            "limitations": ["源码提交和当前运行产物分别记录，部署提交未核实时明确保留未核实",
                            "前端开发服务运行时未建立提交到已服务资源的完整映射"]}
