"""Known USTC graduate-school department codes used by the report search."""

from typing import Dict, List, Optional

KNOWN_DEPARTMENTS: List[Dict[str, str]] = [
    {"code": "229", "name": "人工智能与数据科学学院"},
    {"code": "011", "name": "计算机科学与技术学院"},
    {"code": "210", "name": "信息科学技术学院"},
    {"code": "010", "name": "自动化系"},
    {"code": "006", "name": "电子工程与信息科学系"},
    {"code": "225", "name": "软件学院"},
    {"code": "A13", "name": "软件学院合肥"},
    {"code": "221", "name": "网络空间安全学院"},
    {"code": "219", "name": "微电子学院"},
    {"code": "023", "name": "电子科学与技术系"},
    {"code": "201", "name": "研究生院"},
    {"code": "226", "name": "苏州研究生院"},
    {"code": "A14", "name": "软件学院苏州"},
    {"code": "A15", "name": "纳米学院"},
    {"code": "175", "name": "长春应用化学研究所"},
    {"code": "168", "name": "合肥物质研究院"},
    {"code": "178", "name": "广州能源研究所"},
    {"code": "207", "name": "生命科学学院"},
    {"code": "916", "name": "生物医学工程学院"},
    {"code": "216", "name": "公共管理学院"},
    {"code": "218", "name": "先进技术研究院"},
    {"code": "231", "name": "国家同步辐射实验室"},
    {"code": "001", "name": "数学学院"},
    {"code": "009", "name": "精密机械与精密仪器系"},
    {"code": "013", "name": "热科学和能源工程系"},
    {"code": "304", "name": "网络信息中心"},
]

DEFAULT_PRIORITY = [
    "229",
    "011",
    "210",
    "010",
    "006",
    "225",
    "A13",
    "221",
    "219",
]

_BY_CODE = {item["code"]: item["name"] for item in KNOWN_DEPARTMENTS}


def name_for(code: str) -> str:
    return _BY_CODE.get(str(code), str(code))


def all_departments() -> List[Dict[str, str]]:
    return [dict(item) for item in KNOWN_DEPARTMENTS]


def find(code: str) -> Optional[Dict[str, str]]:
    for item in KNOWN_DEPARTMENTS:
        if item["code"] == code:
            return dict(item)
    return None
