"""质量评分「红色加粗」口径回归：同时识别 HTML 红字与 Markdown 粗体。

背景：模型实际产出用 Markdown `**...**` 粗体，旧评分器只数 HTML `<font color=red>`，
导致真实稿的「红色加粗」普遍漏计（如 E2E 稿 md_bold=7、html_red=0，旧口径 red=0）。
本次修复：red = html_red + md_bold，仍按 4-8 区间判分；md_bold 排除代码围栏内误计。
"""

import re

import pytest

from services.content.quality import score_article, _strip_code_fences


def _format(content: str) -> float:
    """取四维里「格式达标」的分数。"""
    r = score_article(content)
    return next(d["score"] for d in r["dimensions"] if d["key"] == "format")


def _tips(content: str) -> list[str]:
    r = score_article(content)
    return [t for t in r["advice"] if "[格式达标]" in t]


# ----- 组 1：Markdown 粗体被计入；无 HTML 红字时 red = md_bold -----
def test_md_bold_counted_without_html_red():
    content = (
        "正文开头。\n\n"
        "## 😀 小节一\n\n"
        "这是 **关键结论一**，注意它。\n\n"
        "## 🚀 小节二\n\n"
        "再来 **关键结论二** 和 **关键结论三**。\n\n"
        "> **金句引用也带粗体。**\n"
    )
    # 0 个 HTML 红字，3 个 Markdown 粗体 -> red = 3
    r = score_article(content)
    assert r["block"] is False  # 仅格式特征，无违禁词
    # 3 落在 [4,8) 之下，_band(3,4,8,6) = 6*3/4 = 4.5
    fmt = _format(content)
    assert fmt >= 4.5, f"应包含粗体贡献的 4.5 分，实得 {fmt}"


# ----- 组 2：HTML 红字仍被计入（向后兼容） -----
def test_html_red_still_counted():
    content = (
        "## 😀 标题\n\n"
        '<font color="red">重点红字一</font> 文字。\n\n'
        '<font color=red>重点红字二</font> 文字。\n\n'
        "普通段落。\n"
    )
    # 2 个 HTML 红字，0 个 md 粗体 -> red = 2
    r = score_article(content)
    assert r["block"] is False
    fmt = _format(content)
    # red=2 -> _band(2,4,8,6)=3.0；emoji 标题 1 个 -> _band(1,3,5,6)=2.0
    assert fmt >= 5.0, f"HTML 红字应贡献分数，实得 {fmt}"


# ----- 组 3：HTML + Markdown 合计 -----
def test_combined_html_and_md():
    content = (
        "## 😀 标题\n\n"
        '<font color="red">红字一处</font>\n\n'
        "这是 **粗体一处**，还有 **粗体二处**。\n"
    )
    # red = 1(html) + 2(md) = 3
    r = score_article(content)
    assert r["block"] is False
    fmt = _format(content)
    assert fmt >= 4.5, f"合计 red=3 应贡献 4.5 分，实得 {fmt}"


# ----- 组 4：代码围栏内的 **...** 不计入 -----
def test_code_fence_md_bold_excluded():
    content = (
        "## 😀 标题\n\n"
        "正文重点 **这里算粗体**。\n\n"
        "```python\n"
        "# 示例代码里的 **这个不算** 也不该被算\n"
        "x = **not_bold**\n"
        "```\n"
    )
    # 代码围栏内 2 处 ** 应被剥离；仅正文 1 处计入 -> md_bold=1
    body = _strip_code_fences(content)
    md_in_code = len(re.findall(r"\*\*(.+?)\*\*", body))
    assert md_in_code == 1, f"代码围栏内粗体应被排除，实得 {md_in_code}"
    r = score_article(content)
    assert r["block"] is False


# ----- 组 5：落在 4-8 区间给满分（band 上限） -----
def test_bold_in_band_gives_full():
    bolds = "\n\n".join(f"这是 **重点{i}**。" for i in range(5))  # 5 处粗体
    content = "## 😀 标题\n\n" + bolds + "\n"
    # red = 5 落在 [4,8]，该 band 满分 6.0
    r = score_article(content)
    fmt = _format(content)
    # 仅格式维度里 red band = 6.0（其它特征可能 0）；断言 ≥6.0 即说明 band 满分
    assert fmt >= 6.0, f"red=5 应拿满 6.0 的 band，实得 {fmt}"


# ----- 组 6：real-ish 文章（含 7 处 md 粗体、0 html）格式分显著提升 -----
def test_real_article_md_bold_boosts_format():
    content = (
        "## 😀 先说结论\n\n"
        "说白了，这次的进化是 **模型自己跟自己玩**。\n\n"
        "核心流程让 AI 反复做三件事：**自己出题、自己答题、自己打分**。\n\n"
        "> **说白了，以前是请了个家教，现在是养了个会自学的孩子。**\n\n"
        "## 🤔 这跟你有啥关系\n\n"
        "**这就是那套流程的民间版**，不追求一步到位。\n\n"
        "重点在于你把这个开关打开。**以后每一次使用，都是一次微小的进化。**\n\n"
        "> **工具谁都有，差距在你怎么喂它。**\n\n"
        "## 💭 说句心里话\n\n"
        "真正值钱的，是 **你愿不愿意花心思去调教它**。\n"
    )
    # 计数：7 处 md 粗体（含 2 处在引用块内）、0 html -> red=7 -> band 满分 6.0
    r = score_article(content)
    fmt = _format(content)
    assert fmt >= 6.0, f"7 处粗体应拿满 6.0 band，实得 {fmt}"
    tips = _tips(content)
    # 修复后不应再提示「红色加粗只有 0 处」
    assert not any("红色加粗只有 0" in t for t in tips), "修复后不应再误报红色加粗为 0"
