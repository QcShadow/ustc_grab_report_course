#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""部署前自检。

默认只做本地配置检查；加上 --network 会向平台发一次只读查询验证 cookie，
加上 --smtp 会登录一次 SMTP 服务器（不会发送邮件）。

用法:
    ./venv/bin/python scripts/macos/preflight.py
    ./venv/bin/python scripts/macos/preflight.py --network --smtp
"""

import argparse
import smtplib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME = Path.home() / "Library/Application Support/USTC-Grab/report-course"
# 源码目录里可能没有 config.yml（运行时配置在 Application Support），自动回退
CONFIG_DIR = ROOT if (ROOT / "config.yml").exists() else DEFAULT_RUNTIME
sys.path.insert(0, str(ROOT))

from ustc_grab.client import USTCClient  # noqa: E402
from ustc_grab.config import Config  # noqa: E402

PLACEHOLDER_PARTS = ("xxxx", "xx@xx.com", "changeme", "your_")


def masked(value: str) -> str:
    value = str(value or "")
    if not value:
        return "(未填写)"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]} (长度 {len(value)})"


def is_placeholder(value: str) -> bool:
    text = str(value or "").strip().lower()
    return (not text) or any(part in text for part in PLACEHOLDER_PARTS)


def main() -> int:
    parser = argparse.ArgumentParser(description="USTC 抢报告脚本部署自检")
    parser.add_argument("--network", action="store_true", help="请求一次平台接口，验证 cookie 是否有效")
    parser.add_argument("--smtp", action="store_true", help="测试 SMTP 登录（不发送邮件）")
    args = parser.parse_args()

    print(f"项目目录: {ROOT}")
    print(f"配置目录: {CONFIG_DIR}")

    try:
        config = Config(base_dir=CONFIG_DIR)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 无法加载 config.yml: {exc}")
        return 1

    failures = []

    def check(label: str, value, required: bool = True, secret: bool = False) -> None:
        shown = masked(value) if secret and isinstance(value, str) else value
        if value is None or (isinstance(value, str) and not value.strip()):
            print(f"[FAIL] {label}: 未填写")
            if required:
                failures.append(label)
            return
        if isinstance(value, str) and is_placeholder(value):
            print(f"[FAIL] {label}: 仍是模板占位符 ({shown})")
            failures.append(label)
            return
        print(f"[ OK ] {label}: {shown}")

    email = config.email_settings or {}
    smtp = email.get("smtp") or {}

    print("\n-- 邮件通知 --")
    check("email.sender", email.get("sender"))
    check("email.receiver", email.get("receiver"))
    check("email.smtp.server", smtp.get("server"))
    port = smtp.get("port")
    if port in (None, ""):
        print("[FAIL] email.smtp.port: 未填写")
        failures.append("email.smtp.port")
    else:
        try:
            int(port)
            print(f"[ OK ] email.smtp.port: {port}")
        except (TypeError, ValueError):
            print(f"[FAIL] email.smtp.port: 不是数字 ({port})")
            failures.append("email.smtp.port")
    check("email.smtp.auth_code", smtp.get("auth_code"), secret=True)

    print("\n-- USTC 登录凭据 --")
    cookies = config.cookies or {}
    for key in ("GS_DBLOGIN_TOKEN", "GS_SESSIONID", "route", "_WEU"):
        check(f"cookies.{key}", cookies.get(key), secret=True)
    for key in ("EMAP_LANG", "THEME"):
        if cookies.get(key):
            print(f"[ OK ] cookies.{key}: {cookies.get(key)}（可选）")

    print("\n-- 保活课程（可选）--")
    bgbm = config.particular_course
    if bgbm and not is_placeholder(bgbm):
        print(f"[ OK ] particular_course.BGBM: {bgbm}")
    else:
        print("[INFO] 未配置保活课程；仅运行报告检测任务（_WEU 由缓存自动刷新）")

    print("\n-- 平台地址 --")
    if not config.base_url:
        print("[FAIL] base_url: 未配置")
        failures.append("base_url")
    else:
        print(f"[ OK ] base_url: {config.base_url}")
    missing_urls = {
        "search_unselected_report",
        "grab_courses",
        "withdraw_courses",
        "search_selected_report",
    } - set((config.urls or {}).keys())
    if missing_urls:
        print(f"[FAIL] urls 缺少: {', '.join(sorted(missing_urls))}")
        failures.append("urls")
    else:
        print("[ OK ] urls: 4 个选课接口齐全")

    if config.enable_grade_check:
        print("[INFO] enable_grade_check=true，成绩查询已开启")

    def ready(value) -> bool:
        return isinstance(value, str) and bool(value.strip()) and not is_placeholder(value)

    email_ready = (
        ready(email.get("sender"))
        and ready(email.get("receiver"))
        and ready(smtp.get("server"))
        and ready(smtp.get("auth_code"))
        and str(smtp.get("port", "")).strip().isdigit()
    )
    cookies_ready = all(
        ready(cookies.get(key)) for key in ("GS_DBLOGIN_TOKEN", "GS_SESSIONID", "route", "_WEU")
    )

    if args.network:
        if not cookies_ready:
            print("\n-- 平台只读查询 --\n[SKIP] cookie 未填写完整，跳过")
        else:
            print("\n-- 平台只读查询（验证 cookie）--")
            try:
                ok, result = USTCClient(config).search_unselected_report()
            except Exception as exc:  # noqa: BLE001
                print(f"[FAIL] 请求异常: {type(exc).__name__}: {exc}")
                failures.append("network")
            else:
                rows = None
                if ok and isinstance(result, dict):
                    rows = (result.get("datas") or {}).get("wxbgbgdz", {}).get("rows")
                if isinstance(rows, list):
                    print(f"[ OK ] cookie 有效，返回 {len(rows)} 条可查报告")
                    if len(rows) == 0:
                        print("[INFO] 当前没有检索到报告，可能是条件过窄或暂时没有名额")
                else:
                    text = str(result or "")[:200].replace("\n", " ")
                    print("[FAIL] 平台返回的不是预期数据，cookie 可能已过期或被重定向")
                    print(f"       响应片段: {text}")
                    failures.append("cookie/network")

    if args.smtp:
        if not email_ready:
            print("\n-- SMTP 登录测试 --\n[SKIP] 邮件配置未填写完整，跳过")
        else:
            print("\n-- SMTP 登录测试（不发信）--")
            sender = email.get("sender")
            auth_code = smtp.get("auth_code")
            server = smtp.get("server")
            try:
                with smtplib.SMTP_SSL(server, int(port), timeout=20) as smtp_client:
                    smtp_client.login(sender, auth_code)
                print(f"[ OK ] SMTP 登录成功: {server}:{port}")
            except smtplib.SMTPAuthenticationError as exc:
                print(f"[FAIL] SMTP 认证失败 [{exc.smtp_code}]，请检查 auth_code 是否为授权码（不是登录密码）")
                failures.append("smtp-auth")
            except Exception as exc:  # noqa: BLE001
                print(f"[FAIL] SMTP 连接失败: {type(exc).__name__}: {exc}")
                failures.append("smtp-connect")

    print("\n" + "=" * 50)
    if failures:
        print(f"自检未通过，共 {len(failures)} 项需要处理：")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("自检通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
