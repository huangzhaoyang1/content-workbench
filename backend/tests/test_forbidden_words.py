"""广告法极限词 / 平台敏感词匹配精度回归测试（6 组语义，9 条用例）。

背景：11 篇真实校准稿暴露旧表用单字「最」「第一」做子串匹配，会把
「最近/最直观」「第一步/第一周」等非极限表述误判 BLOCK。修复后改为
枚举「极限程度复合词」，本文件把这 6 组语义固化成回归用例，防止回退。

只测 score_article 的合规扫描分支（block / forbidden_words），不依赖模型。
"""
import pytest

from backend.services.content.quality import QUALITY_THRESHOLD, meets_threshold, score_article


def _words(content: str) -> list[str]:
    return [h["word"] for h in score_article(content)["forbidden_words"]]


# ----- 组 1：时间词「最近」不应误 BLOCK -----
def test_recent_phrase_not_blocked():
    r = score_article("最近一周我用了三个工具，效率提升不少。")
    assert r["block"] is False
    assert r["forbidden_words"] == []


# ----- 组 2：极限复合词「最便宜」应 BLOCK -----
def test_cheapest_blocked():
    content = "这是全网最便宜的价格，错过再等一年。"
    r = score_article(content)
    assert r["block"] is True
    assert "最便宜" in _words(content)


# ----- 组 3：极限复合词「第一品牌」应 BLOCK -----
def test_first_brand_blocked():
    content = "我们立志做行业第一品牌。"
    r = score_article(content)
    assert r["block"] is True
    assert "第一品牌" in _words(content)


# ----- 组 4：序数/枚举「第一X」应豁免，不 BLOCK -----
def test_ordinal_exempt_not_blocked():
    content = "第一步先注册，第一次登录会送券；第一点要注意，第一条规则别违反。"
    r = score_article(content)
    assert r["block"] is False
    assert r["forbidden_words"] == []


# ----- 组 5：真极限词 最大/最高/最佳 各一条，均应 BLOCK -----
def test_max_blocked():
    content = "这是最大的一次版本更新。"
    r = score_article(content)
    assert r["block"] is True
    assert "最大" in _words(content)


def test_highest_blocked():
    content = "建议把画质调到最高配置。"
    r = score_article(content)
    assert r["block"] is True
    assert "最高" in _words(content)


def test_best_blocked():
    content = "它提供了最佳的综合方案。"
    r = score_article(content)
    assert r["block"] is True
    assert "最佳" in _words(content)


# ----- 组 6：平台敏感词 二维码/机密 应 BLOCK -----
def test_qrcode_blocked():
    content = "扫码加我微信，详情见下方二维码。"
    r = score_article(content)
    assert r["block"] is True
    assert "二维码" in _words(content)


def test_secret_blocked():
    content = "这份内部资料属于机密，请勿外传。"
    r = score_article(content)
    assert r["block"] is True
    assert "机密" in _words(content)


# ----- 阈值 + 决策支持函数（质量闭环配套，顺带固化）-----
def test_threshold_is_30():
    assert QUALITY_THRESHOLD == 30


def test_meets_threshold_boundaries():
    assert meets_threshold({"total": 43.5}) is True
    assert meets_threshold({"total": 26.2}) is False
    assert meets_threshold(None) is None
