"""三大内容方向的日更轮换（学 / 用 / 赚，3 天一轮）。

日期 → 方向用「自公元 1 年的天数 mod 3」硬映射：
    toordinal() % 3 == 0 → 学
    toordinal() % 3 == 1 → 用
    toordinal() % 3 == 2 → 赚

保证前后端、每一天都拿到一致的方向；只依赖标准库。
"""
from __future__ import annotations

from datetime import date

# 三大方向 + 每方向说明（与 prompts/topic/system.md 保持一致）
DIRECTION_ORDER = ["学", "用", "赚"]
DIRECTION_DESC = {
    "学": "AI 学习方法 / 认知 / 踩坑复盘（怎么学 AI）",
    "用": "AI 工具 / 实操 / 教程 / 提效流程（AI 能干什么）",
    "赚": "AI 副业 / 变现 / 省钱 / 涨粉复盘（怎么靠 AI 赚钱）",
}


def today_direction(today: date | None = None) -> str:
    """今天该出哪个方向的选题（3 天一轮，固定映射）。"""
    t = today or date.today()
    return DIRECTION_ORDER[t.toordinal() % len(DIRECTION_ORDER)]


def direction_by_date(d: date) -> str:
    return today_direction(d)


def next_directions(days: int = 3, today: date | None = None) -> list[tuple[str, str]]:
    """未来 N 天每天对应的方向，用于前端展示排期。"""
    t = today or date.today()
    out = []
    for i in range(max(1, days)):
        d = t.fromordinal(t.toordinal() + i)
        out.append((d.isoformat(), today_direction(d)))
    return out
