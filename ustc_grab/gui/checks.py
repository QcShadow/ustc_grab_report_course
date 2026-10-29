"""Read-only checks used by the GUI: SMTP, platform session, report preview."""

import smtplib
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from ..client import USTCClient
from ..config import Config
from ..manager import CourseManager
from ..notification import Mailer


def _config(home: Path) -> Config:
    return Config(base_dir=home)


def _error(message: str) -> Dict[str, Any]:
    return {"ok": False, "error": message}


def _friendly_error(result: Any) -> str:
    text = str(result or "")
    lowered = text.lower()
    if "<html" in lowered or "<!doctype" in lowered or "登录" in text or "403" in text:
        return "平台返回了登录/错误页面，请检查 Cookie 是否过期"
    text = text.strip()
    return text[:200] if text else "未知错误"


def test_smtp(home: Path) -> Dict[str, Any]:
    try:
        config = _config(home)
        email = config.email_settings or {}
        smtp = email.get("smtp") or {}
        sender = email.get("sender")
        server = smtp.get("server")
        port = int(smtp.get("port", 465))
        auth_code = smtp.get("auth_code")
        if not sender or not server or not auth_code:
            return _error("邮件配置不完整")
        with smtplib.SMTP_SSL(server, port, timeout=20) as client:
            client.login(sender, auth_code)
        return {"ok": True, "message": f"SMTP 登录成功：{server}:{port}"}
    except smtplib.SMTPAuthenticationError as exc:
        return _error(f"SMTP 认证失败 [{exc.smtp_code}]，请检查授权码（不是登录密码）")
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}")


def send_test_email(home: Path) -> Dict[str, Any]:
    try:
        mailer = Mailer(_config(home))
        ok = mailer.send_test()
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}")
    if ok:
        return {"ok": True, "message": "测试邮件已发送，请检查收件箱"}
    return _error("发送失败，请检查 SMTP 配置")


def test_platform(home: Path) -> Dict[str, Any]:
    try:
        config = _config(home)
        client = USTCClient(config)
        ok, result = client.search_unselected_report()
        if not ok or not isinstance(result, dict):
            return _error(f"平台查询失败：{_friendly_error(result)}")
        box = (result.get("datas") or {}).get("wxbgbgdz", {})
        rows = box.get("rows") or []
        if not isinstance(rows, list):
            return _error("平台返回结构不符合预期，cookie 可能已过期")
        counter = Counter()
        for row in rows:
            counter[(row.get("YXDM"), row.get("YXDM_DISPLAY"))] += 1
        departments = [
            {"code": code, "name": name, "count": count}
            for (code, name), count in sorted(counter.items(), key=lambda item: -item[1])
        ]
        sample = [
            {
                "YXDM_DISPLAY": row.get("YXDM_DISPLAY"),
                "BGTMZW": row.get("BGTMZW"),
                "BGSJ": row.get("BGSJ"),
            }
            for row in rows[:5]
        ]
        return {
            "ok": True,
            "total_size": box.get("totalSize"),
            "page_size": box.get("pageSize"),
            "rows": len(rows),
            "departments": departments,
            "sample": sample,
        }
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}")


def _report_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "BGBM": row.get("BGBM", ""),
        "BGTMZW": row.get("BGTMZW", ""),
        "BGSJ": row.get("BGSJ", ""),
        "JZSJ": row.get("JZSJ", ""),
        "YXDM": row.get("YXDM", ""),
        "YXDM_DISPLAY": row.get("YXDM_DISPLAY", ""),
        "DD": row.get("DD", ""),
        "YXRS": row.get("YXRS", ""),
        "KXRS": row.get("KXRS", ""),
        "SFKXK": row.get("SFKXK", ""),
    }


def preview(home: Path) -> Dict[str, Any]:
    try:
        config = _config(home)
        manager = CourseManager(config)
        client = manager.client

        ok, result = client.search_unselected_report()
        if not ok or not isinstance(result, dict):
            return _error(f"平台查询失败：{_friendly_error(result)}")
        box = (result.get("datas") or {}).get("wxbgbgdz", {})
        rows = box.get("rows") or []
        if not isinstance(rows, list):
            return _error("平台返回结构不符合预期，cookie 可能已过期")

        eligible = manager.filter_reports(result)

        selected_rows: List[Dict[str, Any]] = []
        selected_error = None
        try:
            query = client._build_query_string(need_query_setting=False)
            ok_selected, selected_result = client._post(
                "search_selected_report", data=query, is_raw_data=True
            )
            if ok_selected and isinstance(selected_result, dict):
                selected_rows = (
                    (selected_result.get("datas") or {}).get("yxbgbgdz", {}).get("rows") or []
                )
            else:
                selected_error = str(selected_result)[:160]
        except Exception as exc:  # noqa: BLE001
            selected_error = f"{type(exc).__name__}: {exc}"

        selected_times = []
        for row in selected_rows:
            parsed = manager._parse_date(row.get("BGSJ"))
            if parsed:
                selected_times.append(parsed)

        window = config.conflict_window_minutes
        eligible_summary = []
        for row in eligible:
            item = _report_summary(row)
            parsed = manager._parse_date(row.get("BGSJ"))
            item["conflicts_selected"] = bool(
                parsed
                and any(abs(parsed - chosen).total_seconds() < window * 60 for chosen in selected_times)
            )
            eligible_summary.append(item)

        return {
            "ok": True,
            "total_size": box.get("totalSize"),
            "rows": len(rows),
            "eligible_count": len(eligible),
            "eligible": eligible_summary[:80],
            "selected": [_report_summary(row) for row in selected_rows],
            "selected_error": selected_error,
            "conflict_window_minutes": window,
        }
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}")
