"""Small local web GUI for configuring and operating the grabber.

The server binds to 127.0.0.1, uses a random per-session token cookie, and
only serves the bundled static files. No third-party web framework is needed.
"""

import argparse
import json
import mimetypes
import os
import secrets
import sys
import threading
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from . import checks
from .config_store import (
    apply_payload,
    ensure_home,
    load_config,
    public_state,
)
from .paths import ensure_home_dir, platform_label, resolve_home, web_dir
from .service import (
    install_service,
    service_status,
    start_service,
    stop_service,
    tail_log,
    uninstall_service,
)

MAX_BODY = 1024 * 1024


class GuiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, home: Path, token: str):
        self.home = home
        self.token = token
        super().__init__(address, handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "USTC-Grab-GUI/1.0"
    protocol_version = "HTTP/1.1"

    # ---------- helpers ----------
    @property
    def home(self) -> Path:
        return self.server.home  # type: ignore[attr-defined]

    @property
    def token(self) -> str:
        return self.server.token  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        print("[gui] " + (fmt % args))

    def _cookies(self) -> SimpleCookie:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            pass
        return cookie

    def _authorized(self) -> bool:
        header = self.headers.get("X-GUI-Token", "")
        if header and secrets.compare_digest(header, self.token):
            return True
        cookie = self._cookies()
        if "gui_token" in cookie and secrets.compare_digest(cookie["gui_token"].value, self.token):
            return True
        return False

    def _send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(data, "application/json; charset=utf-8", status)

    def _send_error_json(self, message: str, status: int = 400) -> None:
        self._send_json({"ok": False, "error": message}, status)

    def _read_json(self) -> Dict[str, Any]:
        length = self.headers.get("Content-Length")
        if not length:
            return {}
        try:
            size = int(length)
        except ValueError:
            raise ValueError("无效的 Content-Length")
        if size > MAX_BODY:
            raise ValueError("请求体过大")
        raw = self.rfile.read(size)
        if not raw:
            return {}
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return value

    def _serve_index(self) -> None:
        index = web_dir() / "index.html"
        if not index.exists():
            self._send_error_json("GUI 静态文件缺失", 500)
            return
        self._send_bytes(index.read_bytes(), "text/html; charset=utf-8")

    def _serve_static(self, path: str) -> None:
        relative = unquote(path).lstrip("/")
        root = web_dir().resolve()
        target = (root / relative).resolve()
        if target != root and root not in target.parents:
            self._send_error_json("Not Found", 404)
            return
        if not target.is_file():
            self._send_error_json("Not Found", 404)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in (
            "application/javascript",
            "application/json",
        ):
            content_type += "; charset=utf-8"
        self._send_bytes(target.read_bytes(), content_type)

    def _redirect_with_cookie(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        tab = (query.get("tab") or [""])[0]
        location = "/"
        if tab in ("overview", "config", "preview", "service"):
            location = "/?tab=" + tab
        self.send_response(302)
        self.send_header(
            "Set-Cookie",
            "gui_token=" + self.token + "; HttpOnly; SameSite=Strict; Path=/",
        )
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------- GET ----------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            query = parse_qs(parsed.query)
            candidate = (query.get("token") or [""])[0]
            if candidate and secrets.compare_digest(candidate, self.token):
                self._redirect_with_cookie()
                return
            if not self._authorized():
                self._send_bytes(
                    "<html><body style='font-family:sans-serif;padding:40px'>"
                    "<h2>需要访问令牌</h2><p>请使用启动 GUI 时终端里打印的带 token 的地址。</p>"
                    "</body></html>".encode("utf-8"),
                    "text/html; charset=utf-8",
                    403,
                )
                return
            self._serve_index()
            return

        if path == "/api/state":
            if not self._authorized():
                self._send_error_json("未授权", 401)
                return
            try:
                state = public_state(self.home)
                state["ok"] = True
                state["service"] = service_status(self.home)
                self._send_json(state)
            except Exception as exc:  # noqa: BLE001
                self._send_error_json(f"{type(exc).__name__}: {exc}", 500)
            return

        if path == "/api/logs":
            if not self._authorized():
                self._send_error_json("未授权", 401)
                return
            query = parse_qs(parsed.query)
            try:
                lines = int((query.get("lines") or ["300"])[0])
            except ValueError:
                lines = 300
            self._send_json({"ok": True, **tail_log(self.home, lines)})
            return

        if path.startswith("/api/"):
            self._send_error_json("Not Found", 404)
            return

        if path == "/favicon.ico":
            self._send_bytes(b"", "image/x-icon", 204)
            return

        if not self._authorized():
            self._send_error_json("未授权", 401)
            return
        self._serve_static(path)

    # ---------- POST ----------
    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._send_error_json("未授权", 401)
            return

        path = urlparse(self.path).path
        try:
            payload = self._read_json()
        except Exception as exc:  # noqa: BLE001
            self._send_error_json(str(exc), 400)
            return

        try:
            if path == "/api/config":
                state = apply_payload(self.home, payload)
                state["ok"] = True
                state["service"] = service_status(self.home)
                self._send_json(state)
                return

            if path == "/api/test/smtp":
                self._send_json(checks.test_smtp(self.home))
                return

            if path == "/api/test/email":
                self._send_json(checks.send_test_email(self.home))
                return

            if path == "/api/test/platform":
                self._send_json(checks.test_platform(self.home))
                return

            if path == "/api/preview":
                self._send_json(checks.preview(self.home))
                return

            if path == "/api/service/install":
                config = load_config(self.home)
                interval = int(payload.get("interval_seconds") or config.get("schedule_interval_seconds", 120))
                keepalive = payload.get("keepalive")
                if keepalive is None:
                    keepalive = bool(config.get("enable_keepalive", False))
                result = install_service(self.home, interval, bool(keepalive))
                result["service"] = service_status(self.home)
                self._send_json(result)
                return

            if path == "/api/service/start":
                result = start_service(self.home)
                result["service"] = service_status(self.home)
                self._send_json(result)
                return

            if path == "/api/service/stop":
                result = stop_service(self.home)
                result["service"] = service_status(self.home)
                self._send_json(result)
                return

            if path == "/api/service/uninstall":
                result = uninstall_service(self.home)
                result["service"] = service_status(self.home)
                self._send_json(result)
                return

            if path == "/api/shutdown":
                self._send_json({"ok": True, "message": "GUI 已停止"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return

            self._send_error_json("Not Found", 404)
        except ValueError as exc:
            self._send_error_json(str(exc), 400)
        except Exception as exc:  # noqa: BLE001
            self._send_error_json(f"{type(exc).__name__}: {exc}", 500)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="USTC 报告助手图形界面")
    parser.add_argument("--home", help="配置与数据目录（默认 macOS Application Support / 项目目录）")
    parser.add_argument("--port", type=int, default=0, help="监听端口，0 表示随机端口")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--token", help="固定访问令牌（仅测试用）")
    args = parser.parse_args(argv)

    home = resolve_home(args.home)
    ensure_home_dir(home)
    ensure_home(home)

    token = args.token or secrets.token_urlsafe(24)
    server = GuiServer(("127.0.0.1", args.port), Handler, home, token)
    url = f"http://127.0.0.1:{server.server_port}/?token={token}"

    print("=" * 60)
    print("USTC 报告助手 GUI")
    print(f"平台: {platform_label()}")
    print(f"配置目录: {home}")
    print(f"访问地址: {url}")
    print("按 Ctrl+C 停止")
    print("=" * 60)
    sys.stdout.flush()

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止 GUI...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
