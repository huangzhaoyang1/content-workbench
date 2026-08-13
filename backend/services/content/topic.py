"""选题生成逻辑。

两部分：
1. `generate()` —— 复用现有 Streamlit 工作台的模板生成算法，纯函数无外部依赖；
   现在会「自动」去读一次已落盘的公众号数据，把数据洞察融进选题，
   而不是等前端手动传 data_insight（前端传了就以前端为准）。
2. `data_insight()` —— 从历史数据里推导「下一篇该写什么」：
   3 个内容方向 + 3 种标题风格 + 几条可执行建议，供选题页顶部展示。
"""
from __future__ import annotations

import json
import re

from ..data import analytics
from ..system.llm_usage import call as llm_call
from ..prompts import load_topic

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


# ---------------------------------------------------------------------------
# 数据洞察：从历史数据推导「下一篇该怎么写」
# ---------------------------------------------------------------------------
_TITLE_STYLE_RULES: list[tuple[str, tuple[str, ...], str]] = [
    ("数字型", ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"),
     "标题里塞一个具体数字（3 个坑 / 7 天 / 1 小时），先给读者确定性。"),
    ("疑问型", ("吗", "？", "?", "为什么", "怎么", "如何", "该不该", "值不值"),
     "用一个读者心里正在想的问题当标题，正文第一段就把答案给了。"),
    ("干货型", ("教程", "指南", "清单", "步骤", "方法", "直接抄", "保姆", "手把手", "模板"),
     "标题直接标注可操作性（直接抄 / 保姆级 / 附模板），主打收藏价值。"),
    ("故事型", ("我", "第一次", "那天", "翻车", "踩坑", "复盘", "亲测", "实测"),
     "第一人称 + 具体事件，靠真实感而不是靠信息量吸引点击。"),
    ("反差型", ("原来", "居然", "别再", "误区", "错", "真相", "反常识", "不是", "白费"),
     "先否定一个大家默认正确的做法，制造认知冲突。"),
]


def _styles_of(title: str) -> list[str]:
    t = title or ""
    hits = []
    for name, keys, _tip in _TITLE_STYLE_RULES:
        if any(k in t for k in keys):
            hits.append(name)
    return hits


def _style_tip(name: str) -> str:
    for n, _k, tip in _TITLE_STYLE_RULES:
        if n == name:
            return tip
    return ""


def _title_style_ranking(records: list[dict]) -> list[dict]:
    """按标题风格聚合平均阅读，找出「哪种标题在这个号更吃得开」。"""
    valid = [r for r in records if r.get("title") and r.get("reads") is not None]
    if len(valid) < 3:
        return []
    overall = sum(r["reads"] for r in valid) / len(valid)
    buckets: dict[str, list[float]] = {}
    for r in valid:
        for s in _styles_of(r["title"]):
            buckets.setdefault(s, []).append(float(r["reads"]))

    out = []
    for name, vals in buckets.items():
        if len(vals) < 2:  # 单篇是噪声，不当规律
            continue
        avg = sum(vals) / len(vals)
        out.append({
            "name": name,
            "count": len(vals),
            "avg_reads": round(avg, 1),
            "lift": round(avg / overall, 2) if overall else None,
            "tip": _style_tip(name),
        })
    out.sort(key=lambda x: x["avg_reads"], reverse=True)
    return out[:3]


def _build_advice(analysis: dict, records: list[dict], styles: list[dict]) -> list[str]:
    ov = analysis["overview"]
    advice: list[str] = []

    avg = ov.get("avg_reads") or 0
    best = ov.get("max_reads") or 0
    if avg and best:
        ratio = best / avg
        if ratio >= 2:
            advice.append(
                f"头部文章 {int(best)} 阅读，是平均值 {avg} 的 {ratio:.1f} 倍 —— "
                "选题差异比更新频率重要得多，优先照着爆款题材再写一轮。"
            )
        elif ratio <= 1.3:
            advice.append(
                f"最高 {int(best)} 阅读、平均 {avg}，差距只有 {ratio:.1f} 倍，"
                "说明还没跑出爆款结构，下一篇建议大胆换一种标题风格试试。"
            )

    reads = sum(r["reads"] for r in records if r.get("reads")) or 0
    likes = sum(r["likes"] for r in records if r.get("likes")) or 0
    if reads:
        rate = likes / reads * 100
        if rate < 1:
            advice.append(
                f"整体在看率只有 {rate:.2f}%，读者读完没表态 —— "
                "正文中段补一个带态度的判断，结尾抛立场问题。"
            )
        else:
            advice.append(
                f"整体在看率 {rate:.2f}%，共鸣是这个号的强项，"
                "继续保留第一人称 + 真实情绪的写法。"
            )

    if styles:
        top = styles[0]
        lift = top.get("lift")
        if lift and lift >= 1.1:
            advice.append(
                f"「{top['name']}」标题平均 {top['avg_reads']} 阅读，"
                f"比大盘高 {int((lift - 1) * 100)}%（{top['count']} 篇样本），下一篇优先用这种起标题。"
            )

    if ov.get("total_articles", 0) < 5:
        advice.append(
            f"目前只有 {ov.get('total_articles', 0)} 篇数据，规律还不稳，"
            "先按固定节奏更到 10 篇以上，再回头做横向对比。"
        )

    return advice[:4]


def data_insight() -> dict:
    """读取已落盘的公众号数据，产出「3 方向 + 3 标题风格 + 建议」。

    没有数据时返回 available=False，前端据此显示引导，而不是报错。
    """
    try:
        ds = analytics.get_dataset(None)
    except Exception:
        ds = None
    if not ds or not ds.get("records"):
        return {
            "available": False,
            "reason": "还没有导入公众号数据。去「数据分析」页上传 CSV 或截图导入后，这里会自动给出选题方向。",
            "directions": [],
            "title_styles": [],
            "advice": [],
        }

    try:
        analysis = analytics.analyze(ds, "全部")
        sugg = analytics.suggestions(ds, analysis)
    except Exception as e:
        return {
            "available": False,
            "reason": f"数据分析失败：{type(e).__name__}: {e}",
            "directions": [],
            "title_styles": [],
            "advice": [],
        }

    records = ds.get("records") or []
    styles = _title_style_ranking(records)
    ov = analysis["overview"]

    return {
        "available": True,
        "reason": "",
        "dataset": {
            "filename": ds.get("filename"),
            "total_articles": ov.get("total_articles"),
            "avg_reads": ov.get("avg_reads"),
            "max_reads": ov.get("max_reads"),
        },
        "directions": sugg[:3],
        "title_styles": styles,
        "advice": _build_advice(analysis, records, styles),
        "summary": (
            f"基于 {ov.get('total_articles')} 篇历史数据（平均 {ov.get('avg_reads')} 阅读）"
            "推导出的下一篇写作方向"
        ),
    }


def _auto_context() -> tuple[str, list[dict]]:
    """选题生成时自动带上数据洞察，前端不用手动传。"""
    ins = data_insight()
    if not ins.get("available"):
        return "", []
    bits = []
    if ins.get("title_styles"):
        top = ins["title_styles"][0]
        bits.append(f"「{top['name']}」标题平均 {top['avg_reads']} 阅读，表现最好")
    if ins.get("advice"):
        bits.append(ins["advice"][0])
    return " ；".join(bits), list(ins.get("directions") or [])


# ---------------------------------------------------------------------------
# 选题生成
# ---------------------------------------------------------------------------
def _deepseek_cfg(cfg: dict) -> dict | None:
    """取 DeepSeek 子配置（base_url/api_key/model）；缺 key 返回 None。"""
    ds = (cfg.get("deepseek") or {}) if isinstance(cfg, dict) else {}
    api_key = (ds.get("api_key") or "").strip()
    if not api_key:
        return None
    return {
        "base_url": (ds.get("base_url") or "https://api.deepseek.com/v1").strip(),
        "api_key": api_key,
        "model": (ds.get("model") or "deepseek-chat").strip(),
    }


def _extract_json(text: str) -> dict:
    """从模型输出里抠出 JSON 对象，兼容围栏 / 前后废话 / 行尾多余逗号。"""
    s = (text or "").strip()
    if not s:
        raise ValueError("模型没有返回任何内容")
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", s, re.S)
    if fence:
        s = fence.group(1).strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start, end = s.find("{"), s.rfind("}")
    if start >= 0 and end > start:
        chunk = s[start : end + 1]
        for candidate in (chunk, re.sub(r",(\s*[}\]])", r"\1", chunk)):
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    raise ValueError("模型返回无法解析为 JSON")


def _generate_llm(
    cfg: dict,
    hotspots: list[dict],
    data_insight: str | None,
    data_suggestions: list[dict] | None,
) -> list[dict] | None:
    """调用 LLM 产出 5~8 个具体选题；任何失败返回 None（调用方回退模板）。"""
    dsc = _deepseek_cfg(cfg)
    if dsc is None:
        return None
    try:
        import requests  # 懒加载，与 dissect / hotspot / vision 保持一致

        pos = (cfg.get("positioning") or "").strip() or (cfg.get("account_name") or "你的账号")
        default_style = (
            (cfg.get("style") or "").strip() or "真实、有用、可跟；第一人称，像跟朋友聊天"
        )

        system = (
            load_topic()
            .replace("{positioning}", pos)
            .replace("{default_style}", default_style)
        )

        user_parts: list[str] = []
        if hotspots:
            hs = "\n".join(
                f"- 《{h.get('title', '')}》(来源:{h.get('source') or '未知来源'})"
                for h in hotspots
            )
            user_parts.append("【热点素材】\n" + hs)
        if data_insight:
            user_parts.append("【数据洞察】" + data_insight)
        if data_suggestions:
            ds = "\n".join(
                f"- {s.get('name', '')}：{s.get('evidence', '')}".rstrip("：")
                for s in data_suggestions
            )
            user_parts.append("【数据选题建议】\n" + ds)
        user_parts.append("请基于以上素材产出选题，严格按系统提示的 JSON 格式返回。")
        user = "\n\n".join(user_parts)

        payload = {
            "model": dsc["model"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.9,
            "max_tokens": 2000,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        r = llm_call(
            base_url=dsc["base_url"],
            api_key=dsc["api_key"],
            module="topic",
            payload=payload,
            timeout=120,
        )
        if r.status_code >= 400:
            return None
        data = r.json()
        text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        obj = _extract_json(text)
        raw = obj.get("topics") or []
        out: list[dict] = []
        for it in raw:
            if not isinstance(it, dict):
                continue
            t = (it.get("topic") or "").strip()
            # 过滤空泛的「方向 / 篇」类表述，只留具体标题
            if not t or len(t) < 6 or t.endswith("篇"):
                continue
            out.append({
                "topic": t,
                "angle": (it.get("angle") or "").strip(),
                "structure": (it.get("structure") or "").strip(),
                "background": (it.get("background") or "").strip(),
            })
        return out if out else None
    except Exception:
        return None


def _generate_template(
    pos: str,
    hotspots: list[dict],
    data_insight: str | None,
    data_suggestions: list[dict] | None,
) -> list[dict]:
    """纯模板兜底：无外部依赖、稳定，LLM 不可用或返回不达标时启用。"""
    theme_word = pos[:18] if pos else "你的账号"
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


def generate(
    cfg: dict,
    hotspots: list[dict] | None = None,
    data_insight: str | None = None,
    data_suggestions: list[dict] | None = None,
    auto_data: bool = True,
) -> list[dict]:
    """生成 5~8 个候选选题。

    优先调用 LLM 产出「具体、能直接当文章标题的选题」；LLM 不可用或返回不达标时，
    回退到纯模板逻辑（无外部依赖、稳定）。
    """
    pos = (cfg.get("positioning") or "").strip()
    hotspots = [h for h in (hotspots or []) if h.get("title")]

    if auto_data and not data_insight:
        auto_ins, auto_sugg = _auto_context()
        data_insight = data_insight or auto_ins
        data_suggestions = data_suggestions or auto_sugg

    llm_topics = _generate_llm(cfg, hotspots, data_insight, data_suggestions)
    if llm_topics:
        return llm_topics
    return _generate_template(pos, hotspots, data_insight, data_suggestions)
