"""Cross-platform paths and runtime-home detection for the GUI."""

import os
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]


def platform_label() -> str:
    if sys.platform == "darwin":
        return "macOS"
    if os.name == "nt":
        return "Windows"
    return sys.platform


def mac_runtime() -> Path:
    return Path.home() / "Library" / "Application Support" / "USTC-Grab" / "report-course"


def default_home() -> Path:
    """Where config.yml / data / logs live.

    macOS always uses Application Support because launchd cannot read ~/Desktop
    (TCC). Windows and Linux run from the cloned repository, so the project
    directory is the home.
    """
    if sys.platform == "darwin":
        return mac_runtime()
    return REPO_ROOT


def resolve_home(value: Optional[str] = None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    env = os.environ.get("USTC_GRAB_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return default_home()


def config_path(home: Path) -> Path:
    return home / "config.yml"


def data_dir(home: Path) -> Path:
    return home / "data"


def logs_dir(home: Path) -> Path:
    return home / "logs"


def web_dir() -> Path:
    return Path(__file__).resolve().parent / "web"


def ensure_home_dir(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    data_dir(home).mkdir(parents=True, exist_ok=True)
    logs_dir(home).mkdir(parents=True, exist_ok=True)
