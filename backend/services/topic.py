"""选题生成逻辑（复用现有 Streamlit 工作台的模板生成算法，纯函数无外部依赖）。"""
from __future__ import annotations

# 5 个固定切入角度
_ANGLES = [
    ("真实踩坑", "以我第一次实操翻车的真实经历切入,讲清楚踩了哪些坑、怎么填。"),
    ("小白拆解", "抛开术语,用大白话把一个概念/工具拆到普通人能听懂。"),
    ("实操日记", "记录我用它完成一件具体小事的全过程,步骤可照抄。"),
    ("对比复盘", "把两个常被拿来比的方案摆一起,说清楚普通人该怎么选。"),
    ("阶段总结", "跑到某个节点回头看,沉淀几条真心话和避坑清单。"),
]

# 与角度一一对应的建议文章结构
_STRUCTURES = [
    "痛点开场 → 场景还原 → 分步做法 → 一句心得",
    "故事引入 → 方法拆解 → 行动清单",
    "结论先行 → 论据支撑 → 实操步骤 → 避坑提示",
    "对比呈现 → 优劣分析 → 我的选择 → 适用人群",
    "时间线回顾 → 关键转折 → 沉淀方法 → 下一步",
]


def _short_title(title: str, limit: int = 24) -> str:
    """把长热点标题裁成干净短语：优先在标点处断句，避免拦腰截断。"""
    t = (title or "").strip()
    if len(t) <= limit:
        return t
    for sep in ("：", ":", ",", "，", "、", "|", "·", " "):
        head = t.split(sep)[0].strip()
        if 8 <= len(head) <= limit:
            return head
    return t[:limit].rstrip("，,、:：·| ") + "…"


def generate(
    cfg: dict,
    hotspots: list[dict] | None = None,
    data_insight: str | None = None,
    data_suggestions: list[dict] | None = None,
) -> list[dict]:
    """基于账号定位/文风生成 5 个候选选题（纯模板，稳定无外部依赖）。

    hotspots / data_insight / data_suggestions 均为可选：
    全部为空时行为与原来完全一致；传入时把热点标题、数据洞察融入选题。
    """
    pos = (cfg.get("positioning") or "").strip()
    theme_word = pos[:18] if pos else (cfg.get("account_name") or "你的账号")
    hotspots = [h for h in (hotspots or []) if h.get("title")]
    topics: list[dict] = []
    for i, (fa, fd) in enumerate(_ANGLES):
        item = {
            "topic": f"{theme_word}：{fa}篇",
            "angle": fd,
            "structure": _STRUCTURES[i],
            "background": "",
        }
        if hotspots:
            h = hotspots[i % len(hotspots)]
            head = _short_title(h["title"])
            item["topic"] = f"{head}：{fa}篇"
            item["angle"] = f"{fd} 结合热点《{h['title']}》(来源:{h.get('source') or '未知来源'})展开。"
            item["background"] = f"{h['title']} · {h.get('source') or ''} · {h.get('url') or ''}".strip(" ·")
        if data_insight:
            item["background"] = (item["background"] + " | 数据洞察:" + data_insight).strip(" |")
        topics.append(item)

    # 数据分析建议作为额外候选方向追加（不影响前 5 个基础选题）
    for s in (data_suggestions or []):
        topics.append({
            "topic": s.get("name", "数据选题建议"),
            "angle": s.get("angle", ""),
            "structure": "数据结论 → 选题方向 → 实操建议",
            "background": s.get("evidence", ""),
        })
    return topics
