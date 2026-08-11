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
QUALITY_SPEC = """【内容质量四阶标准 —— 四阶全部达标才算合格，缺一阶就是废稿】

▍第一阶 · 格式达标（决定读者愿不愿意往下滑）
1. 小标题用 `## emoji 小标题` 形式，全文 3-5 个，emoji 不重复。
2. 关键结论、反常识的点、要读者记住的话，用 `<font color="red">**红色加粗**</font>`
   包起来，全文 4-8 处；每屏最多一处，滥用就不值钱了。
3. 金句用 Markdown 引用块 `> ` 单独成段，全文 2-3 处。
4. 段落必须短：每段最多 3 行手机屏（60-80 字），长句一律拆成短句。
5. 能列表就列表：步骤用有序列表，并列要点用 `- `。

▍第二阶 · 内容有料（决定读者读完有没有「学到了」）★★★ 最重要，优先满足这一阶
1. 全文至少 3 个「具体细节 / 真实数据 / 可复用方法」，三类都要出现：
   · 具体细节 —— 写「我在第 3 步卡了 40 分钟」，不写「过程有点曲折」；
   · 真实数据 —— 写「从 800 字压到 320 字，阅读完成率翻倍」，不写「效果提升明显」；
   · 可复用方法 —— 读者能照着抄的步骤、话术、参数、判断清单。
2. 至少 1 个反常识观点，并且给出成立的理由，不能只抛结论。
3. 每一个结论后面必须跟一个场景、一个数字或一个动作，三选一，不许裸奔。
4. 以下表达出现即判定不合格，一句都不许写：
   「随着 AI 的发展」「在这个时代」「内容为王」「贵在坚持」
   「适合自己的才是最好的」「总之」「综上所述」「不断学习不断进步」
   以及任何没有主语、没有数字、换个话题也成立的万能句。
5. 自检方法：删掉这句话，文章信息量是否减少？不减少就删掉它。

▍第三阶 · 情绪共鸣（决定读者会不会记住你这个人）
1. 开头用一个具体场景或一次真实失败切入，禁止总起句、禁止背景铺垫。
2. 全文要有情绪曲线：困惑 → 折腾 → 转折 → 松口气，不要从头到尾一个调。
3. 人设保持一致：非技术出身、正在试错、承认不确定，不装专家。
4. 结尾一个开放式提问，问的是读者当下的真实处境，不是「你学会了吗」。

▍第四阶 · 传播属性（决定读者愿不愿意转发）
1. 至少 2 句能被单独截图发朋友圈的金句：短、有反差、脱离上下文也成立。
2. 至少 1 处清单体表达，例如「3 个信号」「5 步」「两类人」。
3. 至少 1 处身份认同表述，例如「如果你也是……那这篇就是写给你的」。
"""

# 改写/写作 prompt 里统一附加的自检收尾
QUALITY_SELF_CHECK = """【交稿前自检（不通过就重写，不要交半成品）】
- 数一遍：具体数字/时间/金额出现了几处？少于 5 处就回去补。
- 数一遍：红色加粗几处？引用块几处？emoji 小标题几个？不在区间内就调整。
- 通读一遍：有没有一句话删掉之后信息量不变？有就删掉。
- 问自己：读者读完能立刻做的那一件事是什么？说不出来就说明第二阶没达标。
"""

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
    red = len(re.findall(r'<font\s+color=["\']?red', content, re.I))
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


def score_article(content: str, *, titles: Any = None) -> dict:
    """对一篇 Markdown 文章做四维打分。纯本地计算，不调模型。"""
    content = content or ""
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

    return {
        "total": total,
        "grade": _grade(total),
        "dimensions": [
            {"key": "format", "label": "格式达标", "score": fmt, "full": 25},
            {"key": "substance", "label": "内容有料", "score": sub, "full": 25},
            {"key": "emotion", "label": "情绪共鸣", "score": emo, "full": 25},
            {"key": "spread", "label": "传播属性", "score": spr, "full": 25},
        ],
        "weakest": buckets[0][0],
        "advice": advice[:8],
    }
