"""Platform service adapters: launchd on macOS, Task Scheduler on Windows."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import REPO_ROOT, logs_dir

MAC_LABEL = "com.ustc.grab.report"
MAC_KEEPALIVE = "com.ustc.grab.keepalive"
WIN_TASK = "USTC-Grab-Report"
WIN_KEEPALIVE = "USTC-Grab-Keepalive"


def _run(command, timeout: int = 60, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _truncate(text: str, limit: int = 8000) -> str:
    text = text or ""
    return text if len(text) <= limit else text[-limit:]


def _uid() -> int:
    return os.getuid()


def service_status(home: Path) -> Dict[str, Any]:
    if sys.platform == "darwin":
        return _mac_status()
    if os.name == "nt":
        return _windows_status()
    return {
        "supported": False,
        "installed": False,
        "loaded": False,
        "running": False,
        "platform": sys.platform,
        "message": "当前平台暂不支持自动注册定时任务，可手动运行 python main.py。",
    }


def _mac_status() -> Dict[str, Any]:
    plist = Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"
    result = {
        "supported": True,
        "installed": plist.exists(),
        "loaded": False,
        "running": False,
        "last_exit": None,
        "runs": None,
        "interval": None,
        "label": MAC_LABEL,
        "detail": "",
    }
    if not plist.exists():
        return result

    try:
        interval = _run(["plutil", "-extract", "StartInterval", "raw", "-o", "-", str(plist)], 10)
        if interval.returncode == 0:
            result["interval"] = int(interval.stdout.strip())
    except Exception:
        pass

    try:
        proc = _run(["launchctl", "print", f"gui/{_uid()}/{MAC_LABEL}"], 15)
    except Exception as exc:  # noqa: BLE001
        result["detail"] = f"{type(exc).__name__}: {exc}"
        return result

    if proc.returncode != 0:
        result["detail"] = (proc.stderr or proc.stdout or "").strip()[:500]
        return result

    result["loaded"] = True
    output = proc.stdout
    result["running"] = "state = running" in output
    match = re.search(r"last exit code = (-?\d+)", output)
    if match:
        result["last_exit"] = int(match.group(1))
    match = re.search(r"runs = (\d+)", output)
    if match:
        result["runs"] = int(match.group(1))
    return result


def _windows_powershell() -> Optional[str]:
    return shutil.which("powershell") or shutil.which("pwsh")


def _windows_status() -> Dict[str, Any]:
    result = {
        "supported": True,
        "installed": False,
        "loaded": False,
        "running": False,
        "last_exit": None,
        "runs": None,
        "interval": None,
        "label": WIN_TASK,
        "detail": "",
    }
    powershell = _windows_powershell()
    if not powershell:
        result["supported"] = False
        result["message"] = "找不到 PowerShell"
        return result

    script = (
        "$t = Get-ScheduledTask -TaskName '" + WIN_TASK + "' -ErrorAction SilentlyContinue; "
        "if (-not $t) { Write-Output 'NOT_FOUND'; exit }; "
        "$i = Get-ScheduledTaskInfo -TaskName '" + WIN_TASK + "'; "
        "Write-Output ('STATE={0};LAST={1};RESULT={2};NEXT={3}' -f $t.State,$i.LastRunTime,$i.LastTaskResult,$i.NextRunTime)"
    )
    try:
        proc = _run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], 30)
    except Exception as exc:  # noqa: BLE001
        result["detail"] = f"{type(exc).__name__}: {exc}"
        return result

    output = (proc.stdout or "").strip()
    if "NOT_FOUND" in output or proc.returncode != 0:
        result["detail"] = _truncate(proc.stderr or output, 500)
        return result

    result["installed"] = True
    result["loaded"] = True
    fields = {}
    for part in output.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key.strip()] = value.strip()
    result["running"] = fields.get("STATE") == "Running"
    result["last_run"] = fields.get("LAST")
    result["next_run"] = fields.get("NEXT")
    try:
        result["last_exit"] = int(fields.get("RESULT", ""))
    except (TypeError, ValueError):
        pass
    return result


def install_service(home: Path, interval_seconds: int, keepalive: bool) -> Dict[str, Any]:
    if sys.platform == "darwin":
        script = REPO_ROOT / "scripts" / "macos" / "install_launchd.sh"
        if not script.exists():
            return {"ok": False, "error": f"找不到安装脚本: {script}"}
        env = os.environ.copy()
        env["USTC_GRAB_HOME"] = str(home)
        env["START_INTERVAL"] = str(max(30, int(interval_seconds)))
        env["ENABLE_KEEPALIVE"] = "1" if keepalive else "0"
        try:
            proc = _run(["bash", str(script)], timeout=900, env=env)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "安装超时（依赖下载可能过慢）"}
        output = _truncate((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else ""))
        return {"ok": proc.returncode == 0, "output": output, "returncode": proc.returncode}

    if os.name == "nt":
        script = REPO_ROOT / "scripts" / "windows" / "install_task.ps1"
        if not script.exists():
            return {"ok": False, "error": f"找不到安装脚本: {script}"}
        powershell = _windows_powershell()
        if not powershell:
            return {"ok": False, "error": "找不到 PowerShell"}
        minutes = max(1, int(round(int(interval_seconds) / 60)))
        command = [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Root",
            str(home),
            "-IntervalMinutes",
            str(minutes),
        ]
        if keepalive:
            command.append("-EnableKeepalive")
        try:
            proc = _run(command, timeout=300)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "安装超时"}
        output = _truncate((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else ""))
        return {"ok": proc.returncode == 0, "output": output, "returncode": proc.returncode}

    return {"ok": False, "error": "当前平台暂不支持自动注册定时任务"}


def start_service(home: Path) -> Dict[str, Any]:
    if sys.platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"
        if not plist.exists():
            return {"ok": False, "error": "服务尚未安装"}
        try:
            check = _run(["launchctl", "print", f"gui/{_uid()}/{MAC_LABEL}"], 15)
            if check.returncode != 0:
                boot = _run(["launchctl", "bootstrap", f"gui/{_uid()}", str(plist)], 30)
                if boot.returncode != 0:
                    return {"ok": False, "error": _truncate(boot.stderr or boot.stdout, 1000)}
            proc = _run(["launchctl", "kickstart", "-k", f"gui/{_uid()}/{MAC_LABEL}"], 30)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": proc.returncode == 0, "output": _truncate(proc.stderr or proc.stdout)}

    if os.name == "nt":
        try:
            proc = _run(["schtasks", "/Run", "/TN", WIN_TASK], 30)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": proc.returncode == 0, "output": _truncate(proc.stdout + proc.stderr)}

    return {"ok": False, "error": "当前平台暂不支持"}


def stop_service(home: Path) -> Dict[str, Any]:
    if sys.platform == "darwin":
        try:
            proc = _run(["launchctl", "bootout", f"gui/{_uid()}/{MAC_LABEL}"], 30)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": proc.returncode == 0, "output": _truncate(proc.stderr or proc.stdout)}

    if os.name == "nt":
        try:
            proc = _run(["schtasks", "/End", "/TN", WIN_TASK], 30)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": proc.returncode == 0, "output": _truncate(proc.stdout + proc.stderr)}

    return {"ok": False, "error": "当前平台暂不支持"}


def uninstall_service(home: Path) -> Dict[str, Any]:
    if sys.platform == "darwin":
        script = REPO_ROOT / "scripts" / "macos" / "uninstall_launchd.sh"
        if not script.exists():
            return {"ok": False, "error": f"找不到卸载脚本: {script}"}
        env = os.environ.copy()
        env["USTC_GRAB_HOME"] = str(home)
        try:
            proc = _run(["bash", str(script)], 120, env=env)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": proc.returncode == 0, "output": _truncate(proc.stdout + proc.stderr)}

    if os.name == "nt":
        script = REPO_ROOT / "scripts" / "windows" / "uninstall_task.ps1"
        powershell = _windows_powershell()
        if not script.exists() or not powershell:
            return {"ok": False, "error": "找不到卸载脚本或 PowerShell"}
        try:
            proc = _run(
                [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Root", str(home)],
                120,
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": proc.returncode == 0, "output": _truncate(proc.stdout + proc.stderr)}

    return {"ok": False, "error": "当前平台暂不支持"}


def tail_log(home: Path, lines: int = 300) -> Dict[str, Any]:
    path = logs_dir(home) / "main.log"
    if not path.exists():
        return {"path": str(path), "lines": [], "text": ""}
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 256 * 1024))
            data = handle.read()
    except OSError as exc:
        return {"path": str(path), "lines": [], "text": f"读取日志失败: {exc}"}
    text = data.decode("utf-8", errors="replace")
    lines_list = text.splitlines()[-max(1, min(lines, 2000)):]
    return {"path": str(path), "lines": lines_list, "text": "\n".join(lines_list)}
