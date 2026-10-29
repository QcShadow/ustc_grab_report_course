import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any, Optional, List

class Config:
    """
    Configuration manager for the USTC Grab application.
    Loads settings from .env and config.yml.
    """
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(os.getcwd())
        self._load_env()
        self._load_config_yml()
        self._init_paths()
        
    def _load_env(self):
        load_dotenv()
        
    def _init_paths(self):
        self.course_file = self.base_dir / os.getenv("COURSE_FILE", "data/courses.json")
        self.response_file = self.base_dir / os.getenv("RESPONSE_FILE", "data/response.json")
        self.exclude_file = self.base_dir / os.getenv("EXCLUDE_FILE", "data/exclude.json")
        self.grades_file = self.base_dir / os.getenv("GRADES_FILE", "data/grades.json")
        self.search_fail_msg_file = self.base_dir / "data/search_fail_msg.txt"
        
    def _load_config_yml(self):
        self.config_path = self.base_dir / "config.yml"
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
            
        with open(self.config_path, "r", encoding="utf-8") as f:
            self._data: Dict[str, Any] = yaml.safe_load(f) or {}

    @property
    def email_settings(self) -> Dict[str, Any]:
        return self._data.get("email", {})

    @property
    def cookies(self) -> Dict[str, str]:
        raw_cookies = self._data.get("cookies", {})
        if not isinstance(raw_cookies, dict):
            return {}
        # Robustness: Filter out non-string values (e.g. if user mis-indents settings into cookies)
        return {k: v for k, v in raw_cookies.items() if isinstance(v, str)}
    
    @property
    def headers(self) -> Dict[str, str]:
        return self._data.get("headers", {})

    @property
    def app_specific_headers(self) -> Dict[str, Dict[str, str]]:
        """
        Returns app-specific headers (e.g. referer) from config.
        Structure: {'xsbg': {'referer': ...}, 'wdcj': {'referer': ...}}
        """
        return self._data.get("app_specific_headers", {})

    @property
    def base_url(self) -> str:
        return self._data.get("base_url", "")

    @property
    def urls(self) -> Dict[str, str]:
        """Returns full URLs constructed from base_url."""
        paths = self._data.get("urls", {})
        # Support absolute URLs for different apps (e.g. wdcjapp vs xsbgglappustc)
        return {
            k: v if v.startswith("http") else f"{self.base_url.rstrip('/')}/{v.lstrip('/')}"
            for k, v in paths.items()
        }

    @property
    def timeout(self) -> int:
        return self._data.get("timeout", 10)

    @property
    def particular_course(self) -> Optional[str]:
        pc = self._data.get("particular_course", {})
        return pc.get("BGBM") if pc else None

    @property
    def interval(self) -> int:
        return self._data.get("interval", 20)

    @property
    def max_grabs_per_cycle(self) -> int:
        """How many courses may be selected per cycle. Default 1."""
        try:
            value = int(self._data.get("max_grabs_per_cycle", 1))
        except (TypeError, ValueError):
            return 1
        return max(1, value)

    @property
    def department_codes(self) -> List[str]:
        """Department codes in priority order, taken from data_raw.querySetting."""
        for item in self.data_raw.get("querySetting", []) or []:
            if item.get("name") == "YXDM":
                raw = str(item.get("value", ""))
                return [code.strip() for code in raw.split(",") if code.strip()]
        return []

    @property
    def conflict_window_minutes(self) -> int:
        """Two reports starting within this many minutes are treated as conflicting."""
        try:
            value = int(self._data.get("conflict_window_minutes", 120))
        except (TypeError, ValueError):
            return 120
        return max(0, value)

    @property
    def schedule_interval_seconds(self) -> int:
        """How often the scheduler runs a detection cycle. Default 120 seconds."""
        try:
            value = int(self._data.get("schedule_interval_seconds", 120))
        except (TypeError, ValueError):
            return 120
        return max(30, min(value, 86400))

    @property
    def enable_keepalive(self) -> bool:
        return bool(self._data.get("enable_keepalive", False))

    @property
    def page_size(self) -> int:
        try:
            value = int(self.data_raw.get("pageSize", 999))
        except (TypeError, ValueError):
            return 999
        return max(1, min(value, 999))

    @property
    def enable_grade_check(self) -> bool:
        """Returns whether grade checking is enabled. Default False."""
        return self._data.get("enable_grade_check", False)

    @property
    def data_raw(self) -> Dict[str, Any]:
        return self._data.get("data_raw", {})

    @property
    def grade_data(self) -> Dict[str, Any]:
        return self._data.get("grade_data", {})
    
    def update_weu_cookie(self, new_weu: str):
        """Updates the _WEU cookie in the config file."""
        # Update in-memory
        if "cookies" not in self._data or self._data["cookies"] is None:
            self._data["cookies"] = {}
        self._data["cookies"]["_WEU"] = new_weu
        
        # Write to file
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(
                self._data,
                f,
                allow_unicode=True,
                default_flow_style=False,
                indent=2,
                sort_keys=False
            )
