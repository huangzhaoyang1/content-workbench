"""内容质量四阶标准 + 自动打分。

两个用途：
1. `QUALITY_SPEC` —— 注入到所有写作类 prompt（抖音改写、流水线写作），
   把「什么叫好文章」写死成可执行的检查项，而不是让模型自由发挥。
2. `score_article()` —— 文章生成后本地打分，不再多花一次模型调用。
   打分全部基于可数的硬特征（红色加粗几处、数字几个、金句几句…），
   因为「让模型给自己打分」永远是 8 分以上，没有参考价值。

四个维度各 25 分，总分 100：
    格式达标 / 内容有料 / 情绪共鸣 / 传播属性
其中「内容有料」是重点，扣分最狠——空泛和正确的废话直接扣到底。
"""
from __future__ import annotations

import emoji
import re
from typing import Any

# ---------------------------------------------------------------------------
# 一、写进 prompt 的四阶标准
# ---------------------------------------------------------------------------
from ..prompts import load_quality_styles
from ..system.config import load_config

_QUALITY = load_quality_styles()
QUALITY_SPEC = _QUALITY["QUALITY_SPEC"]
QUALITY_SELF_CHECK = _QUALITY["QUALITY_SELF_CHECK"]


# ---------------------------------------------------------------------------
# 二、自动打分
# ---------------------------------------------------------------------------
# 「正确的废话」黑名单，命中一条扣 3 分（内容有料维度）
_FLUFF = [
    "随着人工智能的发展", "随着AI的发展", "随着 AI 的发展",
    "随着技术的进步",
    "在这个日新月异的时代", "在这个数字化时代", "在这个时代", "在当今社会",
    "众所周知", "不言而喻", "毋庸置疑",
    "月入过万", "轻松躺赚", "一键搞定", "零基础也能",
    "让我们一起来看看", "接下来为大家介绍",
    "人工智能技术正在深刻改变", "赋能", "助力",
    "打造", "构建", "引领", "驱动",
    "这条视频", "这个视频", "抖音上", "有位博主说",  # 搬运痕迹
    "内容为王", "贵在坚持", "坚持不懈",
    "适合自己的才是最好的",
    "综上所述", "总而言之",
    "不断学习", "希望对你有帮助",
]

# 正则模式：覆盖变体/组合式的 AI 腔、套话、搬运痕迹，命中一条扣 2 分
_FLUFF_PATTERNS = [
    re.compile(r"随着.{0,6}(AI|人工智能|技术).{0,6}(发展|进步|崛起|革新)"),
    re.compile(r"(深度|深刻).{0,3}(改变|影响|重塑|变革)"),
    re.compile(r"(赋能|助力|驱动).{0,6}(未来|发展|转型)"),
    re.compile(r"让我们(一起|来)?.{0,6}(探索|了解|学习|看看)"),
]

# 具体性信号词：出现说明作者在讲实际发生的事，而不是在讲道理
_CONCRETE = (
    "我试了",
    "我踩",
    "我卡",
    "我以为",
    "结果",
    "第一次",
    "那天",
    "当时",
    "后来",
    "实测",
    "报错",
    "失败",
    "改了",
    "花了",
)

_EMOTION = ("我", "其实", "说实话", "坦白讲", "有点", "崩溃", "松了口气", "尴尬", "焦虑", "爽")

_IDENTITY = ("如果你也", "如果你正在", "写给", "同类", "跟我一样", "你是不是也")


# ---------------------------------------------------------------------------
# 三、违禁词合规扫描（命中任意词即标记 BLOCK）
# ---------------------------------------------------------------------------
# 广告法极限词：仅用「极限程度复合词」做子串匹配，不再用单字「最」「第一」。
#
# 为什么改（由 11 篇校准稿暴露）：旧表含单字「最」，会把「最近 / 最重要 /
# 最直观 / 最值得」这类非极限表述误判为违禁，导致大量误 BLOCK；单字「第一」
# 又会把「第一步 / 第一周 / 第一次 / 第一名」等序数、枚举用法误拦。
#
# 改法（方案 A，更稳）：枚举真实极限复合词——
#   1) 最 + 程度形容词（最大/最高/最佳/最便宜…），自然放过「最近/最直观」；
#      只收语义上确属「绝对化」的（先进/便宜/低/大/高/佳/好/强/优/完美），
#      不收时间/趋势义易误伤的（最新/最热/最快/最全/最省）；
#   2) 第一 + 极限名词（第一品牌/全网第一/销量第一/排名第一…），自然放过
#      「第一步/第一条」等序数；
#   3) 顶级 / 极致 / 唯一 / 国家级 / 世界级 等其他绝对化用语。
# 平台敏感词、用户自定义词逻辑保持不动。
_FORBIDDEN_AD_LAW = [
    # 最 + 程度形容词（极限用法；「最近/最新/最直观/最值得」等不在表内，自然放过）
    "最先进", "最便宜", "最低价", "最低", "最大", "最高", "最佳", "最好", "最强",
    "最优", "最完美",
    # 顶级 / 极致类
    "顶级", "极品", "极致", "顶尖", "顶配", "至尊", "王中之王",
    # 第一 + 极限名词（「第一步/第一条/第一名」等序数不在表内，自然放过）
    "第一品牌", "全网第一", "销量第一", "排名第一", "全国第一", "行业第一",
    "品类第一", "第一选择",
    # 唯一 / 绝对类
    "唯一", "独家", "首发", "首选", "绝无仅有", "史无前例", "空前绝后", "独一无二",
    "万能", "百分百", "100%", "绝对",
    # 国家级 / 世界级 / 品牌地位
    "国家级", "世界级", "全国首家", "王牌", "领导者", "领先品牌", "永久",
]

# 平台敏感词：约 20 条占位，抖音/公众号导流、诱导类表达（可按平台调整）。
_FORBIDDEN_PLATFORM = [
    "微信", "加微信", "微信号", "私聊", "私信我", "免费领", "扫码", "二维码",
    "红包", "转发朋友圈", "点赞关注", "关注公众号", "点击链接", "下载APP",
    "限时免费", "内部资料", "机密", "加群", "福利", "秒杀",
]

# (固定两类) + 用户自定义类（从配置读）。分类顺序即命中返回顺序。
_FORBIDDEN_CATEGORIES = (
    ("广告法极限词", _FORBIDDEN_AD_LAW),
    ("平台敏感词", _FORBIDDEN_PLATFORM),
)


def _load_custom_forbidden_words() -> list[str]:
    """从 data/workbench_config.json 读 custom_forbidden_words（默认空）。"""
    try:
        cfg = load_config()
        raw = cfg.get("custom_forbidden_words") or []
    except Exception:
        raw = []
    out: list[str] = []
    seen: set[str] = set()
    for w in raw:
        if not isinstance(w, str):
            continue
        w = w.strip()
        if w and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _check_forbidden_words(content: str) -> list[dict]:
    """扫描内容中的违禁词，返回命中列表 [{word, category, line}, ...]。

    line 为命中的正文行号（1 起），方便前端/用户定位修改。
    命中任意词即视为合规风险，调用方据此把评分标记 BLOCK。
    匹配方式：子串包含（与 _FLUFF 一致），大小写敏感、按原文匹配。
    """
    content = content or ""
    hits: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    lines = content.splitlines()

    def _first_line(word: str) -> int | None:
        for i, ln in enumerate(lines, 1):
            if word in ln:
                return i
        return None

    for category, words in _FORBIDDEN_CATEGORIES:
        for w in words:
            if not w:
                continue
            line_no = _first_line(w)
            if line_no is not None and (w, category) not in seen_pairs:
                seen_pairs.add((w, category))
                hits.append({"word": w, "category": category, "line": line_no})
    for w in _load_custom_forbidden_words():
        line_no = _first_line(w)
        if line_no is not None and (w, "用户自定义词") not in seen_pairs:
            seen_pairs.add((w, "用户自定义词"))
            hits.append({"word": w, "category": "用户自定义词", "line": line_no})
    return hits


def _strip_code_fences(content: str) -> str:
    """去掉 ``` 围栏代码块，避免内部的 `**...**` 被误算成粗体。

    仅用于 Markdown 粗体计数（HTML 红字本身不会写在代码围栏里，不受影响）。
    """
    return re.sub(r"```.*?```", "", content, flags=re.S)


def _paragraphs(content: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", content or "") if p.strip()]


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _band(n: int, lo: int, hi: int, full: float) -> float:
    """落在 [lo, hi] 给满分；不足按比例给分；超出适度惩罚（滥用同样是问题）。"""
    if n <= 0:
        return 0.0
    if n < lo:
        return round(full * n / lo, 1)
    if n <= hi:
        return full
    over = n - hi
    return round(max(full * 0.5, full - over * (full / max(hi, 1)) * 0.5), 1)


def _score_format(content: str) -> tuple[float, list[str]]:
    tips: list[str] = []
    headings = re.findall(r"^\s{0,3}#{2,3}\s+(.+)$", content, re.M)
    emoji_headings = [h for h in headings if emoji.emoji_count(h) > 0]
    # 红色加粗计数：HTML 红字 <font color=red> 与 Markdown 粗体 **...** 合计。
    # Markdown 粗体在代码围栏内不算（避免示例里的 **x** 被误计）。
    body_no_code = _strip_code_fences(content)
    html_red = len(re.findall(r'<font\s+color=["\']?red', content, re.I))
    md_bold = len(re.findall(r"\*\*(.+?)\*\*", body_no_code))
    red = html_red + md_bold
    quotes = len(re.findall(r"^\s{0,3}>\s+\S", content, re.M))
    lists = len(re.findall(r"^\s{0,3}(?:[-*+]\s+|\d+[.、)]\s+)\S", content, re.M))

    paras = _paragraphs(content)
    body = [p for p in paras if not p.lstrip().startswith(("#", ">", "-", "*"))]
    long_paras = [p for p in body if len(p) > 120]
    long_ratio = len(long_paras) / len(body) if body else 0

    s = 0.0
    s += _band(len(emoji_headings), 3, 5, 6)
    s += _band(red, 4, 8, 6)
    s += _band(quotes, 2, 3, 5)
    s += _band(lists, 3, 30, 3)
    s += round(5 * (1 - _clip(long_ratio * 2, 0, 1)), 1)

    if len(emoji_headings) < 3:
        tips.append(f"带 emoji 的小标题只有 {len(emoji_headings)} 个，建议 3-5 个")
    if red < 4:
        tips.append(f"红色加粗只有 {red} 处，建议 4-8 处")
    elif red > 8:
        tips.append(f"红色加粗 {red} 处偏多，每屏最多一处才醒目")
    if quotes < 2:
        tips.append("金句引用块少于 2 处，挑 2-3 句单独用 > 拎出来")
    if long_ratio > 0.25:
        tips.append(f"有 {len(long_paras)} 段超过 120 字，手机上会劝退，拆短一些")
    return round(_clip(s, 0, 25), 1), tips


def _score_substance(content: str) -> tuple[float, list[str]]:
    tips: list[str] = []
    # 数字信号：带单位/时间/百分比的数字，比裸数字更能说明是真实数据
    numbers = re.findall(
        r"\d+(?:\.\d+)?\s*(?:%|％|块|元|万|千|个|次|天|周|月|年|分钟|小时|秒|字|篇|条|人|倍|版|步|轮)",
        content,
    )
    bare_numbers = re.findall(r"(?<![\w])\d{1,6}(?![\w])", content)
    steps = len(re.findall(r"^\s{0,3}\d+[.、)]\s+\S", content, re.M))
    concrete = sum(1 for k in _CONCRETE if k in content)
    fluff_hits = [k for k in _FLUFF if k in content]
    pattern_hits = sum(1 for p in _FLUFF_PATTERNS if p.search(content))

    s = 0.0
    s += _band(len(numbers), 5, 40, 9)          # 带单位数字：最能体现「有料」
    s += _band(len(bare_numbers), 6, 60, 3)
    s += _band(steps, 3, 30, 5)                 # 可复用方法
    s += _band(concrete, 4, 20, 8)              # 具体细节
    s -= 3 * len(fluff_hits)                    # 正确的废话（固定短语），扣到底
    s -= 2 * pattern_hits                       # AI 腔/套话模式变体，每命中一条扣 2 分

    if len(numbers) < 5:
        tips.append(f"带单位的具体数据只有 {len(numbers)} 处，至少补到 5 处（时长/字数/次数/金额）")
    if concrete < 4:
        tips.append("缺少「我试了 / 我卡在 / 结果」这类第一手细节，读起来像在讲道理")
    if steps < 3:
        tips.append("没有可照抄的步骤清单，补一段有序列表")
    if fluff_hits:
        tips.append("出现正确的废话：" + "、".join(fluff_hits[:4]) + "，删掉换成具体的事")
    if pattern_hits:
        tips.append("还有 AI 腔/套话模式（如「随着…发展」「深刻改变」「赋能未来」「让我们看看」），删掉换成具体的事")
    return round(_clip(s, 0, 25), 1), tips


def _score_emotion(content: str) -> tuple[float, list[str]]:
    tips: list[str] = []
    head = content[:260]
    tail = content[-320:]
    first_person = content.count("我")
    emo = sum(1 for k in _EMOTION if k in content)
    has_scene_open = bool(re.search(r"(那天|上周|昨天|前几天|凌晨|我以为|我一开始|第一次)", head))
    ends_question = "？" in tail or "?" in tail

    s = 0.0
    s += _band(first_person, 12, 120, 8)
    s += _band(emo, 4, 20, 6)
    s += 6 if has_scene_open else 0
    s += 5 if ends_question else 0

    if not has_scene_open:
        tips.append("开头不是具体场景切入，换成「那天我…」这种真实片段")
    if not ends_question:
        tips.append("结尾没有开放式提问，补一句问读者处境的话")
    if first_person < 12:
        tips.append("第一人称密度偏低，人设会糊掉")
    return round(_clip(s, 0, 25), 1), tips


def _score_spread(content: str) -> tuple[float, list[str]]:
    tips: list[str] = []
    quote_lines = re.findall(r"^\s{0,3}>\s+(.+)$", content, re.M)
    punchy = [q for q in quote_lines if 8 <= len(q.strip()) <= 45]
    headings = re.findall(r"^\s{0,3}#{2,3}\s+(.+)$", content, re.M)
    listicle = sum(1 for h in headings if re.search(r"\d+\s*(?:个|步|条|类|种|点|招)", h))
    listicle += len(re.findall(r"\d+\s*(?:个信号|步搞定|类人|个坑|条建议)", content))
    identity = sum(1 for k in _IDENTITY if k in content)

    s = 0.0
    s += _band(len(punchy), 2, 5, 10)
    s += _band(listicle, 1, 6, 8)
    s += _band(identity, 1, 4, 7)

    if len(punchy) < 2:
        tips.append("缺少能单独截图转发的短金句（8-45 字，用 > 单独成段）")
    if listicle < 1:
        tips.append("没有清单体表达，加一个「3 个信号 / 5 步」这样的标题")
    if identity < 1:
        tips.append("缺少身份认同句，补一句「如果你也是…这篇写给你」")
    return round(_clip(s, 0, 25), 1), tips


def _grade(total: float) -> str:
    if total >= 85:
        return "优秀"
    if total >= 70:
        return "合格"
    if total >= 55:
        return "待打磨"
    return "不合格"


# ---------------------------------------------------------------------------
# 四、质量门槛（决策支持，不是自动裁决）
# ---------------------------------------------------------------------------
# 阈值 v1（2026-08-11）：基于 11 篇真实稿校准。坏稿(#1=26.2 残稿/#3=24.1 无标题)
# 与好稿(#2=43.5/#4=58.2) 之间清晰分界在 30。随语料积累再校准。
QUALITY_THRESHOLD = 30


def meets_threshold(quality: dict | None) -> bool | None:
    """判断一次产出是否达到发布质量门槛（总分 >= QUALITY_THRESHOLD）。

    返回 None 表示尚未评分（quality 为空）——这时不应据此做任何自动裁决，
    只是「没有可用分数」；返回 True/False 才是明确的达标判定。
    注意：本函数只提供决策支持，最终闸门始终是人（确认发布 / 放弃）。
    """
    if not quality:
        return None
    return bool(quality.get("total", 0) >= QUALITY_THRESHOLD)


def score_article(content: str, *, titles: Any = None) -> dict:
    """对一篇 Markdown 文章做四维打分。纯本地计算，不调模型。"""
    content = content or ""
    forbidden = _check_forbidden_words(content)
    blocked = bool(forbidden)
    fmt, t1 = _score_format(content)
    sub, t2 = _score_substance(content)
    emo, t3 = _score_emotion(content)
    spr, t4 = _score_spread(content)
    total = round(fmt + sub + emo + spr, 1)

    # 建议按「哪一维最低」排序，先给最该改的
    buckets = [
        ("内容有料", sub, t2),
        ("格式达标", fmt, t1),
        ("情绪共鸣", emo, t3),
        ("传播属性", spr, t4),
    ]
    buckets.sort(key=lambda b: b[1])
    advice: list[str] = []
    for name, _score, tips in buckets:
        for tip in tips:
            advice.append(f"[{name}] {tip}")
    if blocked:
        # 违禁词带行号，方便用户定位修改
        parts: list[str] = []
        for h in forbidden[:6]:
            loc = f"第{h['line']}行" if h.get("line") else ""
            parts.append(f"{h['word']}（{loc}）" if loc else h["word"])
        more = f" 等共 {len(forbidden)} 处" if len(forbidden) > 6 else ""
        advice.insert(
            0,
            f"[合规] 命中违禁词：{'、'.join(parts)}{more}，已标记 BLOCK，请修改后重新生成",
        )

    return {
        "total": total,
        "grade": "BLOCK" if blocked else _grade(total),
        "block": blocked,
        "forbidden_words": forbidden,
        "dimensions": [
            {"key": "format", "label": "格式达标", "score": fmt, "full": 25},
            {"key": "substance", "label": "内容有料", "score": sub, "full": 25},
            {"key": "emotion", "label": "情绪共鸣", "score": emo, "full": 25},
            {"key": "spread", "label": "传播属性", "score": spr, "full": 25},
        ],
        "weakest": buckets[0][0],
        "advice": advice[:8],
    }
