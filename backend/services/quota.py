"""每日搜索额度管理（防止真实 API 超额扣费）。

额度按自然日重置，仅统计真实搜索次数；状态持久化在 backend/data/quota.json。
"""
from __future__ import annotations

import json
from datetime import date

from ..config import DATA_DIR

# 统一走 config.DATA_DIR，跟其余持久化文件保持一致，
# 这样 WORKBENCH_DATA_DIR 环境变量能一次性改掉所有数据落盘位置。
QUOTA_PATH = DATA_DIR / "quota.json"


def _read() -> dict:
    try:
        return json.loads(QUOTA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(d: dict) -> None:
    try:
        QUOTA_PATH.parent.mkdir(parents=True, exist_ok=True)
        QUOTA_PATH.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def quota_ok(limit: int) -> bool:
    """今日是否还有额度。"""
    d = _read()
    today = date.today().isoformat()
    if d.get("date") != today:
        return True
    return int(d.get("count", 0)) < int(limit or 50)


def quota_inc(n: int) -> None:
    """累加到今日已用额度。"""
    d = _read()
    today = date.today().isoformat()
    if d.get("date") != today:
        d = {"date": today, "count": 0}
    d["count"] = int(d.get("count", 0)) + max(0, n)
    _write(d)


def quota_status(limit: int) -> dict:
    """今日额度概览，供前端展示「今日已用 X/Y」。"""
    d = _read()
    today = date.today().isoformat()
    used = int(d.get("count", 0)) if d.get("date") == today else 0
    limit = int(limit or 50)
    return {
        "date": today,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "exhausted": used >= limit,
    }


def quota_reset() -> dict:
    """把今日已用额度清零（解除本地保护，之后的搜索会真实调用 API）。"""
    _write({"date": date.today().isoformat(), "count": 0})
    return {"date": date.today().isoformat(), "used": 0}
