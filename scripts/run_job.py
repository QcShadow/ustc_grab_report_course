#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-platform single-run entry point used by schedulers.

Usage:
    python scripts/run_job.py main
    python scripts/run_job.py keepalive
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB = sys.argv[1] if len(sys.argv) > 1 else "main"
SCRIPTS = {"main": "main.py", "keepalive": "main_update_weu.py"}
LOG_DIR = ROOT / "logs"
MAX_LOG_BYTES = 5 * 1024 * 1024


def _log_path(job: str) -> Path:
    return LOG_DIR / f"{job}.log"


def _lock_path(job: str) -> Path:
    return LOG_DIR / f"{job}.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _acquire_lock(job: str) -> bool:
    lock = _lock_path(job)
    for _ in range(2):
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
            os.close(fd)
            return True
        except FileExistsError:
            try:
                content = lock.read_text(encoding="utf-8").strip()
                pid = int(content.split()[0]) if content else 0
                age = time.time() - lock.stat().st_mtime
            except (OSError, ValueError):
                pid, age = 0, 999999
            if age > 3600 or not _pid_alive(pid):
                try:
                    lock.unlink()
                except OSError:
                    pass
                continue
            return False
    return False


def _rotate(log: Path) -> None:
    try:
        if log.exists() and log.stat().st_size > MAX_LOG_BYTES:
            log.write_text("", encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    if JOB not in SCRIPTS:
        print(f"用法: {sys.argv[0]} main|keepalive", file=sys.stderr)
        return 64

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = _log_path(JOB)
    _rotate(log)

    if not _acquire_lock(JOB):
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 跳过：上一轮 {JOB} 仍在运行\n")
        return 0

    script = ROOT / SCRIPTS[JOB]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONWARNINGS"] = "ignore"
    env["PYTHONIOENCODING"] = "utf-8"

    started = time.strftime("%Y-%m-%d %H:%M:%S")
    exit_code = 1
    try:
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"[{started}] ===== 开始 {SCRIPTS[JOB]} (pid {os.getpid()}) =====\n")
            handle.flush()
            try:
                proc = subprocess.run(
                    [sys.executable, str(script)],
                    cwd=str(ROOT),
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
                exit_code = proc.returncode
            except Exception as exc:  # noqa: BLE001
                handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 运行失败: {type(exc).__name__}: {exc}\n")
                exit_code = 1
            handle.write(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ===== 结束 {SCRIPTS[JOB]} (exit {exit_code}) =====\n"
            )
    finally:
        try:
            _lock_path(JOB).unlink()
        except OSError:
            pass
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
