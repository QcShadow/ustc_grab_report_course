import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from .config import Config
from .client import USTCClient
from .notification import Mailer

class CourseManager:
    """
    Manages the core business logic: searching, filtering, grabbing, and withdrawing courses.
    """
    def __init__(self, config: Config):
        self.config = config
        self.client = USTCClient(config)
        self.mailer = Mailer(config)

    def _parse_date(self, date_str: str) -> datetime:
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                return datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None

    def _load_exclude_list(self) -> List[str]:
        if not self.config.exclude_file.exists():
            return []
        try:
            with open(self.config.exclude_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("EXCLUDE_BGBM", [])
        except (json.JSONDecodeError, KeyError):
            return []

    def withdraw_exclude_courses(self) -> bool:
        """
        Checks currently selected courses against the exclude list and withdraws them if found.
        """
        # Search selected courses
        # Note: We need to implement search_selected_report in client
        # It uses query string with need_query_setting=False
        query_string = self.client._build_query_string(need_query_setting=False)
        success, response = self.client._post("search_selected_report", data=query_string, is_raw_data=True)
        
        if not success:
            return False

        try:
            selected_rows = response['datas']['yxbgbgdz']['rows']
        except (KeyError, TypeError):
            print("Error: Unexpected data structure in selected courses response.")
            return False

        exclude_list = self._load_exclude_list()
        
        print(f"Selected courses: {[item.get('BGTMZW') for item in selected_rows]}")

        for exclude_bgbm in exclude_list:
            for course in selected_rows:
                if exclude_bgbm == course.get('BGBM'):
                    print(f"Found excluded course selected: {exclude_bgbm} - {course.get('BGTMZW')}")
                    if self.client.withdraw_course(exclude_bgbm):
                        self.mailer.send_withdraw_success(course)
        return True

    def filter_reports(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Filters reports based on date, availability, and exclude list.
        """
        try:
            rows = data["datas"]["wxbgbgdz"]["rows"]
        except (KeyError, TypeError):
            print("Error: Unexpected data structure in unselected reports response.")
            return []

        today = datetime.now()
        filtered_rows = []
        exclude_list = self._load_exclude_list()
        allowed_departments = set(self.config.department_codes)

        for item in rows:
            bgsj_str = item.get("BGSJ")
            jzsj_str = item.get("JZSJ")
            yxrs_str = item.get("YXRS")
            kxrs = item.get("KXRS")
            bgbm = item.get("BGBM")
            bgtmzw = item.get("BGTMZW")

            # 0. Department whitelist (also enforced server-side)
            if allowed_departments and item.get("YXDM") not in allowed_departments:
                continue

            # 1. Date check
            bgsj_dt = self._parse_date(bgsj_str)
            jzsj_dt = self._parse_date(jzsj_str)
            
            if not bgsj_dt or bgsj_dt <= today:
                continue
            if not jzsj_dt or jzsj_dt <= today:
                continue

            # 2. Capacity check
            try:
                yxrs_int = int(yxrs_str) if yxrs_str is not None else 0
            except (ValueError, TypeError):
                continue

            if not isinstance(kxrs, int):
                try:
                    kxrs = int(kxrs)
                except (ValueError, TypeError):
                    continue
            
            if kxrs <= yxrs_int:
                continue

            # 3. Exclude list check
            if bgbm in exclude_list:
                print(f"Skipping excluded course: {bgbm} - {bgtmzw}")
                continue

            filtered_rows.append(item)

        # Department priority order comes from data_raw.querySetting.
        # Within one department, the nearest registration deadline goes first.
        priority = {
            code: index for index, code in enumerate(self.config.department_codes)
        }
        filtered_rows.sort(
            key=lambda row: (
                priority.get(row.get("YXDM"), len(priority)),
                self._parse_date(row.get("JZSJ")) or datetime.max,
                self._parse_date(row.get("BGSJ")) or datetime.max,
            )
        )

        return filtered_rows

    def search_and_write(self) -> Tuple[bool, Any]:
        """
        Searches, filters, and writes results to COURSE_FILE.
        Returns: (has_useful_courses, raw_search_result)
        """
        print("Searching for unselected reports...")
        success, result = self.client.search_unselected_report()
        
        if not success:
            print("Search failed.")
            return False, result

        # Write Raw result for debugging (as per original logic printing result)
        # But we mostly care about filtering
        
        filtered = self.filter_reports(result)
        
        # Write to file
        with open(self.config.course_file, 'w', encoding='utf-8') as f:
            json.dump(filtered, f, ensure_ascii=False, indent=4)
            
        print(f"Filter complete. Kept {len(filtered)} courses.")
        return filtered, result

    def _attempt_grab(self, course: Dict[str, Any]) -> bool:
        """Helper to grab a single course and notify."""
        bgbm = course.get("BGBM")
        bgtmzw = course.get("BGTMZW")
        print(f"Attempting to grab: {bgtmzw} ({bgbm})")
        
        if self.client.grab_course(bgbm):
            self.mailer.send_success(course)
            return True
        return False

    def grab_loop(self, courses: List[Dict[str, Any]]):
        """
        Tries to select courses sequentially.

        To avoid selecting a whole batch of reports at once, only
        `max_grabs_per_cycle` courses may succeed per cycle, and at most
        three courses are attempted.
        """
        if not courses:
            print("No courses available to grab.")
            return

        limit = self.config.max_grabs_per_cycle
        max_attempts = max(limit * 3, 3)
        selected = 0
        attempts = 0
        select_window = timedelta(minutes=self.config.conflict_window_minutes)
        selected_times = []

        print(f"Starting grab: {len(courses)} candidates, limit {limit}/cycle...")
        for course in courses:
            if selected >= limit or attempts >= max_attempts:
                break

            # Do not select two reports whose start times overlap.
            bgsj_dt = self._parse_date(course.get("BGSJ"))
            if bgsj_dt and any(
                abs(bgsj_dt - chosen) < select_window for chosen in selected_times
            ):
                print(f"Skipping time-conflicting course: {course.get('BGTMZW')}")
                continue

            attempts += 1
            if self._attempt_grab(course):
                selected += 1
                if bgsj_dt:
                    selected_times.append(bgsj_dt)

        if selected:
            print(f"Selected {selected} course(s) this cycle; the rest will be handled next cycle.")
        else:
            print("No course selected this cycle.")

    def _load_known_grades(self) -> List[str]:
        """Loads list of WIDs for already notified grades."""
        if not self.config.grades_file.exists():
            return []
        try:
            with open(self.config.grades_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
            return []
            
    def _save_known_grades(self, wids: List[str]):
        """Saves list of known WIDs."""
        with open(self.config.grades_file, 'w', encoding='utf-8') as f:
            json.dump(wids, f, ensure_ascii=False, indent=4)

    def check_grades_routine(self):
        """Checks for new grades and notifies."""
        print("Checking for new grades...")
        success, response = self.client.get_grades()
        
        if not success:
            # Silent fail for grades to not disrupt main loop, or print error
            print(f"Grade check failed: {response}")
            return

        try:
            rows = response.get('datas', {}).get('xscjcx', {}).get('rows', [])
            if not rows:
                print("No grade data found.")
                return
        except AttributeError:
            print("Unexpected grade data structure.")
            return

        known_wids = self._load_known_grades()
        if not isinstance(known_wids, list):
             known_wids = []
             
        new_wids = []
        has_new = False
        
        for row in rows:
            wid = row.get("WID")
            if not wid:
                continue
                
            if wid not in known_wids:
                print(f"New grade found: {row.get('KCMC')}")
                self.mailer.send_grade_notification(row)
                known_wids.append(wid)
                has_new = True
        
        if has_new:
            self._save_known_grades(known_wids)
            print("Grade list updated.")
        else:
            print("No new grades.")

    @staticmethod
    def _is_session_error(post_result: Any) -> bool:
        """Detects an expired session / rejected token from a search result."""
        if isinstance(post_result, dict):
            return str(post_result.get("code", "0")) not in ("0", "200")
        if isinstance(post_result, str):
            return any(
                hint in post_result
                for hint in ("登录", "超时", "403", "Client Error", "Forbidden")
            )
        return False

    def _notify_session_failure_once(self, detail: str) -> None:
        """Sends the cookie-expired email at most once until the session recovers."""
        marker = self.config.search_fail_msg_file
        try:
            if marker.exists() and marker.read_text(encoding="utf-8").strip():
                print("Session error already notified; skipping duplicate email.")
                return
            marker.write_text("cookie_expired\n", encoding="utf-8")
        except OSError as exc:
            print(f"Warning: cannot write failure marker: {exc}")
        self.mailer.send_fail(detail)

    def _clear_session_failure(self) -> None:
        """Resets the failure marker after a successful search."""
        marker = self.config.search_fail_msg_file
        try:
            if marker.exists() and marker.read_text(encoding="utf-8").strip():
                marker.write_text("", encoding="utf-8")
        except OSError:
            pass

    def run_cycle(self):
        """
        Main execution cycle: Withdraw Excluded -> Search -> Grab -> Check Grades.
        """
        # 0. Check Grades (Run first or last, doesn't matter much)
        if self.config.enable_grade_check:
            self.check_grades_routine()

        # 1. Withdraw exclude courses
        self.withdraw_exclude_courses()

        # 2. Search
        courses, post_result = self.search_and_write()

        # Session expired: notify once, keep the marker until a search succeeds.
        if self._is_session_error(post_result):
            self._notify_session_failure_once(str(post_result)[:500])
            return
        self._clear_session_failure()

        if not courses:
            return

        # 3. Grab (at most max_grabs_per_cycle successful selections)
        self.grab_loop(courses)

    def keep_alive_routine(self):
        """
        Routine for main_update_weu.py
        """
        print("Starting Keep-Alive Routine...")
        # 1. Withdraw particular course
        pc_bgbm = self.config.particular_course
        if not pc_bgbm:
            print("No particular course configured for keep-alive.")
            return

        print("Withdrawing particular course for keep-alive...")
        self.client.withdraw_course(pc_bgbm)
        
        print(f"Waiting {self.config.interval} seconds...")
        for i in range(self.config.interval):
            # print(f"Wait {self.config.interval - i}...")
            time.sleep(1)
            
        print("Grabbing particular course back...")
        self.client.grab_course(pc_bgbm)
