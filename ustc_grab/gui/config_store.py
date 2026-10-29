"""Persistence helpers for the GUI: config.yml, exclude.json, validation."""

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .departments import all_departments, name_for
from .paths import REPO_ROOT, config_path, data_dir, ensure_home_dir

SECRET_COOKIES = ("GS_DBLOGIN_TOKEN", "GS_SESSIONID", "_WEU", "route")
OPTIONAL_COOKIES = ("EMAP_LANG", "THEME")
PLACEHOLDER_PARTS = ("xxxx", "xx@xx.com", "changeme", "your_")


def ensure_home(home: Path) -> None:
    ensure_home_dir(home)
    cfg = config_path(home)
    if not cfg.exists():
        template = REPO_ROOT / "templates" / "config.template.yml"
        shutil.copyfile(template, cfg)
        try:
            os.chmod(cfg, 0o600)
        except OSError:
            pass
    exclude = data_dir(home) / "exclude.json"
    if not exclude.exists():
        exclude.write_text('{\n  "EXCLUDE_BGBM": []\n}\n', encoding="utf-8")


def load_config(home: Path) -> Dict[str, Any]:
    ensure_home(home)
    path = config_path(home)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("config.yml 不是有效的 YAML 对象")
    return raw


def save_config(home: Path, data: Dict[str, Any]) -> None:
    ensure_home(home)
    path = config_path(home)
    if path.exists():
        backup = path.with_name("config.yml.bak")
        shutil.copyfile(path, backup)
        try:
            os.chmod(backup, 0o600)
        except OSError:
            pass

    header = (
        "# USTC Grab Report Course configuration\n"
        "# 由 GUI 保存；包含平台 cookie 与 SMTP 授权码，请勿提交到 Git。\n"
    )
    text = header + yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        indent=2,
    )
    tmp = path.with_name("config.yml.tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def load_exclude(home: Path) -> List[str]:
    ensure_home(home)
    path = data_dir(home) / "exclude.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, dict):
        return []
    items = raw.get("EXCLUDE_BGBM") or []
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def save_exclude(home: Path, items: List[str]) -> None:
    ensure_home(home)
    cleaned: List[str] = []
    for item in items or []:
        text = str(item).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    path = data_dir(home) / "exclude.json"
    tmp = path.with_name("exclude.json.tmp")
    tmp.write_text(
        json.dumps({"EXCLUDE_BGBM": cleaned}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _is_placeholder(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return (not text) or any(part in text for part in PLACEHOLDER_PARTS)


def _secret_status(value: Any) -> Dict[str, Any]:
    text = str(value or "")
    return {"set": bool(text) and not _is_placeholder(text), "length": len(text)}


def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _ensure_dict(data: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        value = {}
        data[key] = value
    return value


def _departments_from_data(data: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = data.get("data_raw") or {}
    query = raw.get("querySetting") or []
    for item in query:
        if not isinstance(item, dict) or item.get("name") != "YXDM":
            continue
        codes = [part.strip() for part in str(item.get("value", "")).split(",") if part.strip()]
        names = [part.strip() for part in str(item.get("value_display", "")).split(",") if part.strip()]
        result = []
        for index, code in enumerate(codes):
            name = names[index] if index < len(names) and names[index] else name_for(code)
            result.append({"code": code, "name": name})
        return result
    return []


def _set_departments(data: Dict[str, Any], departments: Any) -> None:
    if not isinstance(departments, list) or not departments:
        raise ValueError("至少保留一个院系")

    cleaned: List[Dict[str, str]] = []
    seen = set()
    for item in departments:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        name = str(item.get("name", "")).strip() or name_for(code)
        cleaned.append({"code": code, "name": name})
    if not cleaned:
        raise ValueError("至少保留一个有效院系")

    raw = _ensure_dict(data, "data_raw")
    query = raw.get("querySetting")
    if not isinstance(query, list):
        query = []
        raw["querySetting"] = query

    yxdm = None
    for item in query:
        if isinstance(item, dict) and item.get("name") == "YXDM":
            yxdm = item
            break
    if yxdm is None:
        yxdm = {
            "name": "YXDM",
            "caption": "院系",
            "linkOpt": "AND",
            "builderList": "cbl_m_List",
            "builder": "m_value_equal",
        }
        query.insert(0, yxdm)

    yxdm["value"] = ",".join(item["code"] for item in cleaned)
    yxdm["value_display"] = ",".join(item["name"] for item in cleaned)


def public_state(home: Path) -> Dict[str, Any]:
    data = load_config(home)
    email = data.get("email") if isinstance(data.get("email"), dict) else {}
    smtp = email.get("smtp") if isinstance(email.get("smtp"), dict) else {}
    cookies = data.get("cookies") if isinstance(data.get("cookies"), dict) else {}
    particular = data.get("particular_course") if isinstance(data.get("particular_course"), dict) else {}
    raw = data.get("data_raw") if isinstance(data.get("data_raw"), dict) else {}
    bgbm = str(particular.get("BGBM", ""))
    if _is_placeholder(bgbm):
        bgbm = ""

    return {
        "home": str(home),
        "config_path": str(config_path(home)),
        "platform": _platform(),
        "email": {
            "sender": str(email.get("sender", "")),
            "receiver": str(email.get("receiver", "")),
            "server": str(smtp.get("server", "")),
            "port": smtp.get("port", 465),
        },
        "secrets": {
            "auth_code": _secret_status(smtp.get("auth_code")),
            **{key: _secret_status(cookies.get(key)) for key in SECRET_COOKIES},
        },
        "optional_cookies": {
            key: str(cookies.get(key, "")) for key in OPTIONAL_COOKIES
        },
        "departments": _departments_from_data(data),
        "known_departments": all_departments(),
        "particular_bgbm": bgbm,
        "enable_grade_check": bool(data.get("enable_grade_check", False)),
        "max_grabs_per_cycle": _as_int(data.get("max_grabs_per_cycle", 1), 1, 1, 20),
        "conflict_window_minutes": _as_int(data.get("conflict_window_minutes", 120), 120, 0, 1440),
        "schedule_interval_seconds": _as_int(data.get("schedule_interval_seconds", 120), 120, 30, 86400),
        "enable_keepalive": bool(data.get("enable_keepalive", False)),
        "page_size": _as_int(raw.get("pageSize", 999), 999, 1, 999),
        "exclude": load_exclude(home),
    }


def _platform() -> str:
    from .paths import platform_label

    return platform_label()


def validate_data(data: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    email = data.get("email") if isinstance(data.get("email"), dict) else {}
    smtp = email.get("smtp") if isinstance(email.get("smtp"), dict) else {}
    cookies = data.get("cookies") if isinstance(data.get("cookies"), dict) else {}
    particular = data.get("particular_course") if isinstance(data.get("particular_course"), dict) else {}

    sender = str(email.get("sender", "")).strip()
    receiver = str(email.get("receiver", "")).strip()
    if _is_placeholder(sender) or "@" not in sender:
        errors.append("发件邮箱未填写或格式不正确")
    if _is_placeholder(receiver) or "@" not in receiver:
        errors.append("收件邮箱未填写或格式不正确")
    if _is_placeholder(smtp.get("server")):
        errors.append("SMTP 服务器未填写")
    try:
        port = int(smtp.get("port", 465))
        if not (1 <= port <= 65535):
            raise ValueError
    except (TypeError, ValueError):
        errors.append("SMTP 端口不是有效数字")
    if _is_placeholder(smtp.get("auth_code")):
        errors.append("SMTP 授权码未填写（不是邮箱登录密码）")

    for key in SECRET_COOKIES:
        value = cookies.get(key)
        if _is_placeholder(value):
            errors.append(f"Cookie {key} 未填写")

    departments = _departments_from_data(data)
    if not departments:
        errors.append("至少选择一个院系")

    if data.get("enable_keepalive"):
        bgbm = str(particular.get("BGBM", "")).strip()
        if _is_placeholder(bgbm):
            errors.append("启用保活任务时必须填写 particular_course.BGBM")

    if _is_placeholder(data.get("base_url")):
        errors.append("base_url 未配置")
    if not isinstance(data.get("urls"), dict) or not data["urls"]:
        errors.append("urls 未配置")

    return errors


def apply_payload(home: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = load_config(home)
    email = _ensure_dict(data, "email")
    smtp = _ensure_dict(email, "smtp")
    cookies = _ensure_dict(data, "cookies")

    incoming_email = payload.get("email") if isinstance(payload.get("email"), dict) else {}
    for key in ("sender", "receiver"):
        if key in incoming_email:
            email[key] = str(incoming_email.get(key, "")).strip()
    if "server" in incoming_email:
        smtp["server"] = str(incoming_email.get("server", "")).strip()
    if "port" in incoming_email:
        try:
            smtp["port"] = int(incoming_email.get("port"))
        except (TypeError, ValueError):
            smtp["port"] = incoming_email.get("port")
    auth_code = incoming_email.get("auth_code")
    if auth_code and str(auth_code) not in ("__KEEP__", "********"):
        smtp["auth_code"] = str(auth_code).strip()

    incoming_cookies = payload.get("cookies") if isinstance(payload.get("cookies"), dict) else {}
    for key in SECRET_COOKIES:
        value = incoming_cookies.get(key)
        if value == "__CLEAR__":
            cookies.pop(key, None)
        elif value and str(value) not in ("__KEEP__", "********"):
            cookies[key] = str(value).strip()
    for key in OPTIONAL_COOKIES:
        if key in incoming_cookies:
            value = str(incoming_cookies.get(key, "")).strip()
            if value:
                cookies[key] = value
            else:
                cookies.pop(key, None)

    if "departments" in payload:
        _set_departments(data, payload.get("departments"))

    particular = _ensure_dict(data, "particular_course")
    if "particular_bgbm" in payload:
        bgbm = str(payload.get("particular_bgbm", "")).strip()
        if bgbm and not _is_placeholder(bgbm):
            particular["BGBM"] = bgbm
        else:
            particular.pop("BGBM", None)

    if "enable_grade_check" in payload:
        data["enable_grade_check"] = bool(payload.get("enable_grade_check"))
    if "enable_keepalive" in payload:
        data["enable_keepalive"] = bool(payload.get("enable_keepalive"))
    if "max_grabs_per_cycle" in payload:
        data["max_grabs_per_cycle"] = _as_int(payload.get("max_grabs_per_cycle"), 1, 1, 20)
    if "conflict_window_minutes" in payload:
        data["conflict_window_minutes"] = _as_int(
            payload.get("conflict_window_minutes"), 120, 0, 1440
        )
    if "schedule_interval_seconds" in payload:
        data["schedule_interval_seconds"] = _as_int(
            payload.get("schedule_interval_seconds"), 120, 30, 86400
        )
    if "page_size" in payload:
        raw = _ensure_dict(data, "data_raw")
        raw["pageSize"] = _as_int(payload.get("page_size"), 999, 1, 999)

    errors = validate_data(data)
    if errors:
        raise ValueError("；".join(errors))

    save_config(home, data)
    if "exclude" in payload:
        items = payload.get("exclude")
        if not isinstance(items, list):
            items = []
        save_exclude(home, items)
    return public_state(home)
