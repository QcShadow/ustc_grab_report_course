"""Lightweight GitHub version check for the local GUI.

This only detects releases; it never overwrites local code or configuration.
The result is cached for six hours so opening the GUI does not hammer GitHub.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

REPO = "QcShadow/ustc_grab_report_course"
RELEASES_URL = f"https://github.com/{REPO}/releases"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RAW_VERSION_URL = f"https://raw.githubusercontent.com/{REPO}/main/VERSION"
CACHE_TTL_SECONDS = 6 * 60 * 60
LOCAL_VERSION_PATH = Path(__file__).resolve().parents[2] / "VERSION"


def _normalize(value: str) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("v"):
        text = text[1:]
    match = re.search(r"\d+(?:\.\d+)*", text)
    return match.group(0) if match else "0.0.0"


def _version_tuple(value: str) -> Tuple[int, ...]:
    parts = [int(part) for part in re.findall(r"\d+", value)]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(latest: str, current: str) -> bool:
    return _version_tuple(latest) > _version_tuple(current)


def current_version() -> str:
    try:
        return _normalize(LOCAL_VERSION_PATH.read_text(encoding="utf-8"))
    except OSError:
        return "0.0.0"


def _fetch_latest() -> Tuple[str, str, str]:
    """Returns (version, url, notes). Falls back to raw VERSION if no release."""
    headers = {
        "User-Agent": "ustc-grab-report-gui/1.2",
        "Accept": "application/vnd.github+json",
    }
    try:
        response = requests.get(LATEST_RELEASE_API, headers=headers, timeout=6)
        if response.status_code == 200:
            data = response.json()
            tag = str(data.get("tag_name") or "")
            if tag:
                return (
                    _normalize(tag),
                    str(data.get("html_url") or RELEASES_URL),
                    str(data.get("body") or ""),
                )
    except requests.RequestException:
        pass

    try:
        response = requests.get(RAW_VERSION_URL, headers=headers, timeout=6)
        if response.status_code == 200:
            return _normalize(response.text), RELEASES_URL, ""
    except requests.RequestException:
        pass

    raise RuntimeError("无法连接 GitHub 检查更新")


def _cache_path(home: Path) -> Path:
    return Path(home) / "data" / "update_check.json"


def _read_cache(home: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(_cache_path(home).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(home: Path, latest: str, url: str, notes: str) -> None:
    path = _cache_path(home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "latest": latest,
                    "url": url,
                    "notes": notes,
                    "checked_at": time.time(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        path.chmod(0o600)
    except OSError:
        pass


def _result(
    current: str,
    latest: Optional[str],
    url: str,
    notes: str = "",
    cached: bool = False,
    error: str = "",
) -> Dict[str, Any]:
    return {
        "ok": True,
        "current": current,
        "latest": latest,
        "has_update": bool(latest and is_newer(latest, current)),
        "url": url or RELEASES_URL,
        "notes": notes,
        "cached": cached,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "error": error,
    }


def check_update(home: Path, force: bool = False) -> Dict[str, Any]:
    """Returns current/latest version info; network failures are non-fatal."""
    current = current_version()
    cache = _read_cache(home)
    now = time.time()

    if not force and cache:
        age = now - float(cache.get("checked_at") or 0)
        if 0 <= age < CACHE_TTL_SECONDS:
            latest = _normalize(str(cache.get("latest") or ""))
            return _result(
                current,
                latest,
                str(cache.get("url") or RELEASES_URL),
                str(cache.get("notes") or ""),
                cached=True,
            )

    try:
        latest, url, notes = _fetch_latest()
        _write_cache(home, latest, url, notes)
        return _result(current, latest, url, notes)
    except Exception as exc:  # noqa: BLE001
        if cache:
            latest = _normalize(str(cache.get("latest") or ""))
            return _result(
                current,
                latest,
                str(cache.get("url") or RELEASES_URL),
                str(cache.get("notes") or ""),
                cached=True,
                error=f"{type(exc).__name__}: {exc}",
            )
        return _result(current, None, RELEASES_URL, error=f"{type(exc).__name__}: {exc}")
