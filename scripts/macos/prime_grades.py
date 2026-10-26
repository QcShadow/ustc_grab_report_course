#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""首次开启成绩查询前预热：把当前已有成绩的 WID 写入 data/grades.json。

这样第一次正式运行不会把历史成绩全部当成“新成绩”各发一封邮件。
不会发送任何邮件。

用法:
    ./venv/bin/python scripts/macos/prime_grades.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME = Path.home() / "Library/Application Support/USTC-Grab/report-course"
CONFIG_DIR = ROOT if (ROOT / "config.yml").exists() else DEFAULT_RUNTIME
sys.path.insert(0, str(ROOT))

from ustc_grab.client import USTCClient  # noqa: E402
from ustc_grab.config import Config  # noqa: E402


def main() -> int:
    config = Config(base_dir=CONFIG_DIR)
    if not config.enable_grade_check:
        print("enable_grade_check 未开启，无需预热。")
        return 0

    print("查询当前成绩（只读）...")
    ok, response = USTCClient(config).get_grades()
    if not ok or not isinstance(response, dict):
        print("[FAIL] 查询失败，cookie 可能无效。")
        print(f"       响应片段: {str(response)[:200]}")
        return 1

    rows = (response.get("datas") or {}).get("xscjcx", {}).get("rows")
    if not isinstance(rows, list):
        print("[FAIL] 返回结构不符合预期，cookie 可能已过期。")
        print(f"       响应片段: {str(response)[:200]}")
        return 1

    wids = [row.get("WID") for row in rows if row.get("WID")]
    existing = []
    if config.grades_file.exists():
        try:
            existing = json.loads(config.grades_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []
    if not isinstance(existing, list):
        existing = []

    merged = sorted(set(map(str, existing)) | set(map(str, wids)))
    config.grades_file.write_text(
        json.dumps(merged, ensure_ascii=False, indent=4), encoding="utf-8"
    )
    print(f"[ OK ] 已记录 {len(wids)} 门现有成绩，之后只会通知新增成绩。")
    print(f"       缓存文件: {config.grades_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
