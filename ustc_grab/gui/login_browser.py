"""Dedicated browser login window with local CDP cookie capture.

This module never reads the user's normal browser profile. It launches Chrome
or Edge with a separate ``--user-data-dir`` under the app data directory, lets
the user log in manually, then reads the cookies from that dedicated profile
through the browser's local DevTools protocol.

The login window is intentionally visible and manual: no account password is
stored, and CAS / two-factor prompts remain under the user's control.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:  # optional at import time; a clear error is shown if missing
    import websocket  # type: ignore
except ImportError:  # pragma: no cover - exercised only on incomplete installs
    websocket = None  # type: ignore

from ..client import USTCClient
from ..config import Config
from .config_store import load_config, save_config

LOGIN_URL = "https://yjs1.ustc.edu.cn/gsapp/sys/yjsemaphome/portal/index.do?forceCas=1"
COOKIE_NAMES = ("GS_DBLOGIN_TOKEN", "GS_SESSIONID", "_WEU", "route")
PROFILE_DIR = "browser-profile"
LOGIN_TIMEOUT = 300
DEVTOOLS_TIMEOUT = 30


def find_browser() -> Optional[Path]:
    """Returns an installed Chromium-based browser, or None."""
    candidates = []
    if sys.platform == "darwin":
        candidates.extend(
            [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            ]
        )
    elif os.name == "nt":
        roots = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        for root in roots:
            if not root:
                continue
            base = Path(root)
            candidates.extend(
                [
                    base / "Google/Chrome/Application/chrome.exe",
                    base / "Microsoft/Edge/Application/msedge.exe",
                    base / "BraveSoftware/Brave-Browser/Application/brave.exe",
                ]
            )
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))

    for path in candidates:
        if path.exists():
            return path

    for name in ("chrome", "google-chrome", "chromium", "msedge", "microsoft-edge", "brave"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


class BrowserLoginManager:
    """Runs one visible login session at a time."""

    def __init__(self, home: Path):
        self.home = Path(home)
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._cancel = threading.Event()
        self._state: Dict[str, Any] = {"status": "idle", "message": "未启动"}

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def start(self) -> Dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return dict(self._state)
            browser = find_browser()
            if browser is None:
                self._state = {
                    "status": "error",
                    "message": "未找到 Chrome 或 Edge，请安装后重试，或继续手动粘贴 Cookie。",
                }
                return dict(self._state)
            self._cancel.clear()
            self._state = {
                "status": "opening",
                "message": "正在打开独立登录窗口…",
                "browser": browser.name,
            }
            self._thread = threading.Thread(target=self._run, args=(browser,), daemon=True)
            self._thread.start()
            return dict(self._state)

    def cancel(self) -> Dict[str, Any]:
        self._cancel.set()
        with self._lock:
            proc = self._proc
            self._state = {"status": "cancelled", "message": "已取消登录"}
        self._close_browser(proc)
        return self.status()

    def shutdown(self) -> None:
        self._cancel.set()
        with self._lock:
            proc = self._proc
        self._close_browser(proc)

    # ---------- worker ----------
    def _set(self, status: str, message: str, **extra: Any) -> None:
        with self._lock:
            self._state = {"status": status, "message": message, **extra}

    def _run(self, browser: Path) -> None:
        proc: Optional[subprocess.Popen] = None
        try:
            profile = self._prepare_profile()
            active_port = profile / "DevToolsActivePort"
            try:
                active_port.unlink()
            except OSError:
                pass

            args = [
                str(browser),
                "--user-data-dir=" + str(profile),
                "--remote-debugging-port=0",
                "--remote-debugging-address=127.0.0.1",
                "--remote-allow-origins=*",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-sync",
                "--disable-background-mode",
                "--new-window",
                LOGIN_URL,
            ]
            popen_kwargs = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True
            proc = subprocess.Popen(args, **popen_kwargs)
            with self._lock:
                self._proc = proc

            ws_url = self._wait_for_devtools(active_port, proc)
            self._set("waiting", "请在独立登录窗口中完成登录…")

            deadline = time.time() + LOGIN_TIMEOUT
            while time.time() < deadline:
                if self._cancel.is_set():
                    self._set("cancelled", "已取消登录")
                    return
                if proc.poll() is not None:
                    self._set("closed", "登录窗口已关闭")
                    return
                try:
                    cookies = self._read_cookies(ws_url)
                except Exception:
                    cookies = {}

                if cookies.get("GS_SESSIONID"):
                    self._set("validating", "已获取 Cookie，正在验证…")
                    if self._validate(cookies):
                        self._save(cookies)
                        self._set("success", "登录已更新，Cookie 已保存")
                        return
                time.sleep(2)

            self._set("timeout", "登录超时，请重新打开登录窗口。")
        except Exception as exc:  # noqa: BLE001
            if self._cancel.is_set():
                self._set("cancelled", "已取消登录")
            else:
                self._set("error", "登录窗口失败：" + str(exc))
        finally:
            self._close_browser(proc)
            with self._lock:
                self._proc = None

    def _prepare_profile(self) -> Path:
        profile = self.home / PROFILE_DIR
        profile.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(profile, 0o700)
        except OSError:
            pass
        return profile

    @staticmethod
    def _wait_for_devtools(active_port: Path, proc: subprocess.Popen) -> str:
        deadline = time.time() + DEVTOOLS_TIMEOUT
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("浏览器已退出")
            if active_port.exists():
                try:
                    lines = active_port.read_text(encoding="utf-8").splitlines()
                except OSError:
                    lines = []
                if len(lines) >= 2 and lines[0].strip().isdigit():
                    return "ws://127.0.0.1:" + lines[0].strip() + lines[1].strip()
            time.sleep(0.25)
        raise RuntimeError("浏览器启动超时")

    @staticmethod
    def _read_cookies(ws_url: str) -> Dict[str, str]:
        if websocket is None:
            raise RuntimeError("缺少 websocket-client 依赖")
        try:
            ws = websocket.create_connection(ws_url, timeout=5, origin="http://127.0.0.1")
        except Exception:
            ws = websocket.create_connection(ws_url, timeout=5, suppress_origin=True)

        try:
            ws.send(json.dumps({"id": 1, "method": "Storage.getCookies", "params": {}}))
            deadline = time.time() + 5
            while time.time() < deadline:
                raw = ws.recv()
                if not raw:
                    continue
                message = json.loads(raw)
                if message.get("id") != 1:
                    continue
                if "error" in message:
                    raise RuntimeError("读取浏览器 Cookie 失败")
                found: Dict[str, str] = {}
                for item in (message.get("result") or {}).get("cookies", []):
                    name = item.get("name")
                    domain = str(item.get("domain", ""))
                    if name in COOKIE_NAMES and "ustc.edu.cn" in domain:
                        found[str(name)] = str(item.get("value", ""))
                return found
            raise RuntimeError("读取浏览器 Cookie 超时")
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def _validate(self, cookies: Dict[str, str]) -> bool:
        cfg = Config(base_dir=self.home)
        merged = dict(cfg.cookies)
        merged.update(cookies)
        cfg._data["cookies"] = merged

        cache = self.home / "data" / "weu_cache.json"
        try:
            cache.unlink()
        except OSError:
            pass

        client = USTCClient(cfg)
        query = client._build_query_string(need_query_setting=False)
        ok, data = client._post("search_selected_report", data=query, is_raw_data=True)
        if not ok or not isinstance(data, dict):
            return False
        datas = data.get("datas")
        return isinstance(datas, dict) and isinstance(datas.get("yxbgbgdz"), dict)

    def _save(self, cookies: Dict[str, str]) -> None:
        data = load_config(self.home)
        current = data.setdefault("cookies", {})
        if not isinstance(current, dict):
            current = {}
            data["cookies"] = current
        for name, value in cookies.items():
            if name in COOKIE_NAMES and value:
                current[name] = value
        save_config(self.home, data)

        for path in (
            self.home / "data" / "search_fail_msg.txt",
            self.home / "data" / "weu_cache.json",
        ):
            try:
                path.unlink()
            except OSError:
                pass

    @staticmethod
    def _close_browser(proc: Optional[subprocess.Popen]) -> None:
        if proc is None or proc.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                return
            except Exception:
                pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
