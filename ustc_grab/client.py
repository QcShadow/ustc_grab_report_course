import json
import requests
import re
from urllib.parse import quote
from typing import Dict, Any, Tuple, Optional
from .config import Config

class USTCClient:
    """
    HTTP Client for interacting with USTC Graduate School system.

    Note: the platform issues a different `_WEU` cookie per application
    (xsbgglappustc for course selection, wdcjapp for grades), and a `_WEU`
    obtained from one application is rejected with HTTP 403 by another.

    To keep the request rate identical to the original project, each
    application's `_WEU` is cached in `data/weu_cache.json` and only
    refreshed (by loading the application index page) when the platform
    answers 403.
    """
    def __init__(self, config: Config):
        self.config = config
        self._app_cookies: Dict[str, Dict[str, str]] = {}
        self._weu_cache: Dict[str, str] = self._load_weu_cache()

    @staticmethod
    def _app_for(url_key: str) -> str:
        return "wdcj" if url_key == "check_grade" else "xsbg"

    def _weu_cache_path(self):
        return self.config.base_dir / "data" / "weu_cache.json"

    def _load_weu_cache(self) -> Dict[str, str]:
        try:
            raw = json.loads(self._weu_cache_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {k: v for k, v in raw.items() if isinstance(v, str) and v}

    def _save_weu_cache(self) -> None:
        path = self._weu_cache_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(
                json.dumps(self._weu_cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.chmod(0o600)
            tmp.replace(path)
        except OSError as exc:
            print(f"Warning: cannot save _WEU cache: {exc}")

    @staticmethod
    def _extract_weu(response: requests.Response) -> Optional[str]:
        match = re.search(r"_WEU=([^;]+)", response.headers.get("Set-Cookie", ""))
        return match.group(1) if match else None

    def _get_app_cookies(self, app: str, force_refresh: bool = False) -> Dict[str, str]:
        """Returns cookies carrying this application's own `_WEU`."""
        if not force_refresh and app in self._app_cookies:
            return self._app_cookies[app]

        base = dict(self.config.cookies)
        if not force_refresh:
            cached = self._weu_cache.get(app)
            # Valid tokens are base64-ish, so their length is a multiple of 4.
            if cached and len(cached) % 4 == 0:
                cookies = dict(base)
                cookies["_WEU"] = cached
                self._app_cookies[app] = cookies
                return cookies

        referer = (self.config.app_specific_headers.get(app) or {}).get("referer")
        if referer:
            warm_headers = self.config.headers.copy()
            warm_headers["referer"] = referer

            # Try the configured _WEU first, then other applications' cached
            # tokens. The index page usually issues a fresh, app-scoped token
            # even when the presented token belongs to another application.
            candidates = []
            seen = set()
            token_pool = [base.get("_WEU")]
            token_pool += [v for k, v in self._weu_cache.items() if k != app]
            for token in token_pool:
                if token and token not in seen:
                    seen.add(token)
                    candidate = dict(base)
                    candidate["_WEU"] = token
                    candidates.append(candidate)
            candidates.append(dict(base))

            for candidate in candidates:
                try:
                    response = requests.get(
                        referer,
                        headers=warm_headers,
                        cookies=candidate,
                        timeout=self.config.timeout,
                    )
                except requests.RequestException as exc:
                    print(f"Warm-up failed for {app}: {exc}")
                    continue

                candidate.update(response.cookies.get_dict())
                if self._extract_weu(response):
                    self._remember_weu(app, response, candidate)
                    self._app_cookies[app] = candidate
                    return candidate
                if response.status_code != 200:
                    print(f"Warm-up warning: {app} index returned HTTP {response.status_code}")

        self._app_cookies[app] = base
        return base

    def _remember_weu(self, app: str, response: requests.Response, cookies: Dict[str, str]) -> None:
        """Copies a rotated `_WEU` from Set-Cookie into the cookies and cache."""
        value = self._extract_weu(response)
        if not value:
            return
        cookies["_WEU"] = value
        if self._weu_cache.get(app) != value:
            self._weu_cache[app] = value
            self._save_weu_cache()

    @staticmethod
    def _token_rejected(response: requests.Response) -> bool:
        """True when the response looks like a rejected/expired session."""
        if response.status_code == 403:
            return True
        if response.status_code != 200:
            return False
        try:
            data = response.json()
        except ValueError:
            return True  # HTML login page instead of JSON
        if not isinstance(data, dict):
            return False
        msg = str(data.get("msg", "")).lower()
        return any(hint in msg for hint in ("multiple of 4", "token", "登录", "超时", "_weu"))

    def _build_query_string(self, need_query_setting: bool) ->  str:
        """Constructs the complex query string required by the API."""
        params = []
        data_raw = self.config.data_raw
        
        for key, value in data_raw.items():
            if key != 'querySetting':
                encoded_value = quote(str(value))
                params.append(f"{key}={encoded_value}")
            elif need_query_setting:
                # querySetting is a list/object that needs JSON dumps then Quote
                query_json = json.dumps(value, ensure_ascii=False)
                encoded_query = quote(query_json)
                params.append(f"querySetting={encoded_query}")
                
        return "&".join(params)

    def _build_grade_query_string(self) -> str:
        """Constructs specific query string for grades."""
        params = []
        grade_data = self.config.grade_data
        
        for key, value in grade_data.items():
            if key == 'querySetting':
                # querySetting is an empty list as per user payload
                query_json = json.dumps(value, ensure_ascii=False)
                encoded_query = quote(query_json)
                params.append(f"querySetting={encoded_query}")
            else:
                encoded_value = quote(str(value))
                params.append(f"{key}={encoded_value}")
                
        return "&".join(params)

    def _post(self, url_key: str, data: Any = None, is_raw_data: bool = False, headers: Optional[Dict[str, str]] = None) -> Tuple[bool, Any]:
        """
        Generic POST request handler.
        :param url_key: The key in config.urls to fetch the URL.
        :param data: The data payload (dict or string).
        :param is_raw_data: If True, data is sent as-is.
        :param headers: Optional headers to merge/override global config headers.
        """
        target_url = self.config.urls.get(url_key)
        if not target_url:
            return False, f"URL key '{url_key}' not found in configuration."

        # Each application needs its own _WEU; warm it up on first use.
        app = self._app_for(url_key)
        cookies = self._get_app_cookies(app)

        # Merge headers: start with global, override with specific
        request_headers = self.config.headers.copy()
        if headers:
            request_headers.update(headers)

        def send(cookie_jar: Dict[str, str]) -> requests.Response:
            return requests.post(
                target_url,
                headers=request_headers,
                cookies=cookie_jar,
                data=data,
                timeout=self.config.timeout,
            )

        try:
            response = send(cookies)
            if self._token_rejected(response):
                print(f"Session rejected by {app}, refreshing _WEU and retrying once...")
                cookies = self._get_app_cookies(app, force_refresh=True)
                response = send(cookies)

            cookies.update(response.cookies.get_dict())
            self._remember_weu(app, response, cookies)
            
            # For debugging/logging
            # print(f"Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"HTTP Error: {response.status_code}")
                return False, response.text

            try:
                # Try parsing as JSON
                json_data = response.json()
                return True, json_data
            except json.JSONDecodeError:
                return False, response.text
                
        except requests.RequestException as e:
            print(f"Request Exception: {e}")
            return False, str(e)

    def search_unselected_report(self) -> Tuple[bool, Any]:
        """Searches for unselected reports (courses)."""
        query_string = self._build_query_string(need_query_setting=True)
        headers = self.config.app_specific_headers.get('xsbg')
        return self._post("search_unselected_report", data=query_string, is_raw_data=True, headers=headers)

    def grab_course(self, bgbm: str) -> bool:
        """Attempts to grab a specific course by BGBM."""
        payload = {
            "data": json.dumps({"BGBM": bgbm}, ensure_ascii=False)
        }
        headers = self.config.app_specific_headers.get('xsbg')
        success, result = self._post("grab_courses", data=payload, headers=headers)
        
        if success and isinstance(result, dict):
            print(f"Grab result: {result}")
            return result.get("code") == "0" and result.get("msg") == "成功"
        return False

    def withdraw_course(self, bgbm: str) -> bool:
        """Attempts to withdraw from a specific course by BGBM."""
        payload = {
            "data": json.dumps({"BGBM": bgbm}, ensure_ascii=False)
        }
        headers = self.config.app_specific_headers.get('xsbg')
        success, result = self._post("withdraw_courses", data=payload, headers=headers)
        
        if success and isinstance(result, dict):
            print(f"Withdraw result: {result}")
            return result.get("code") == "0" and result.get("msg") == "成功"
        return False

    def get_grades(self) -> Tuple[bool, Any]:
        """Fetches grade data."""
        query_string = self._build_grade_query_string()
        headers = self.config.app_specific_headers.get('wdcj')
        return self._post("check_grade", data=query_string, is_raw_data=True, headers=headers)
