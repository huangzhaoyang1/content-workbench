"""dissect 输出结构硬校验（validate.py）单测 + analyze 重试集成测试。

不依赖真实 LLM：analyze 的 _chat / _rewrite_call / _deepseek_cfg 全部打桩。
"""
import copy
import json

import pytest

from backend.services.content import dissect
from backend.services.content.validate import validate_dissect


def _valid_dissect() -> dict:
    """一份完整合法的拆解输出（字段名与 dissect.py 输出一致）。"""
    return {
        "basics": {"type_tags": ["干货"], "summary": "s", "account": "a"},
        "hook": {"technique": "悬念", "quote": "q"},
        "boom": {"core": "c"},
        "audience": {"who": "w"},
        "migration": {"expand": ["e"], "ending": "end"},
        "structure": ["s1", "s2"],
        "portable": ["p1"],
        "materials": {
            "views": [{"point": "p", "detail": "d"}],
            "cases": [{"what": "w", "detail": "d"}],
            "numbers": [{"value": "10万", "context": "c"}],
            "quotes": ["q1"],
            "methods": [{"name": "m", "usage": "u"}],
            "completeness": {"level": "full", "missing": [], "note": "完整"},
        },
    }


# ---------------------------------------------------------------------------
# 1) 完整合法 → 通过
# ---------------------------------------------------------------------------
def test_validate_full_valid_passes():
    ok, errs = validate_dissect(_valid_dissect())
    assert ok is True
    assert errs == []


# ---------------------------------------------------------------------------
# 2) level=thin 但 missing=[] → 失败，且信息指明缺失披露
# ---------------------------------------------------------------------------
def test_validate_thin_without_missing_fails():
    bad = _valid_dissect()
    bad["materials"]["completeness"] = {"level": "thin", "missing": [], "note": ""}
    ok, errs = validate_dissect(bad)
    assert ok is False
    assert any("未披露缺失项" in e for e in errs), errs


# ---------------------------------------------------------------------------
# 3) 五清单全空且 missing 为空 → 失败（空素材）
# ---------------------------------------------------------------------------
def test_validate_all_empty_fails():
    empty = _valid_dissect()
    for k in ("views", "cases", "numbers", "quotes", "methods"):
        empty["materials"][k] = []
    empty["materials"]["completeness"] = {"level": "full", "missing": [], "note": ""}
    ok, errs = validate_dissect(empty)
    assert ok is False
    assert any("全为空" in e for e in errs), errs


# ---------------------------------------------------------------------------
# 额外结构校验：必备字段缺失 / 类型错误 / level 非法
# ---------------------------------------------------------------------------
def test_validate_missing_required_field():
    bad = _valid_dissect()
    del bad["materials"]  # 缺 materials
    ok, errs = validate_dissect(bad)
    assert ok is False
    assert any("materials" in e for e in errs), errs


def test_validate_bad_type_on_list_field():
    bad = _valid_dissect()
    bad["structure"] = {"not": "a list"}  # 应为 list
    ok, errs = validate_dissect(bad)
    assert ok is False
    assert any("structure" in e for e in errs), errs


def test_validate_illegal_level():
    bad = _valid_dissect()
    bad["materials"]["completeness"]["level"] = "unknown"
    ok, errs = validate_dissect(bad)
    assert ok is False
    assert any("completeness" in e and "level" in e for e in errs), errs


# ---------------------------------------------------------------------------
# 集成：analyze 在拆解输出不合法时重试一次，第二次合法则成功
# ---------------------------------------------------------------------------
def _invalid_dissect_json() -> str:
    """第一段返回：thin + 未披露缺失 → 校验失败，触发重试。"""
    return json.dumps(
        {
            "basics": {},
            "hook": {},
            "boom": {},
            "audience": {},
            "migration": {},
            "structure": [],
            "portable": [],
            "materials": {
                "views": [],
                "cases": [],
                "numbers": [],
                "quotes": [],
                "methods": [],
                "completeness": {"level": "thin", "missing": [], "note": ""},
            },
        }
    )


def test_analyze_retries_on_invalid_then_succeeds(monkeypatch):
    calls = {"dissect": 0}

    def fake_chat(cfg, system, user, **kw):
        if system is dissect._DISSECT_SYSTEM:
            calls["dissect"] += 1
            if calls["dissect"] == 1:
                return _invalid_dissect_json()  # 第一次非法 → 触发重试
            return json.dumps(_valid_dissect())  # 第二次合法
        # 改写调用
        return json.dumps({"title": "t", "content": "c", "body": "b", "summary": "s", "tags": []})

    monkeypatch.setattr(dissect, "_deepseek_cfg", lambda: {"api_key": "x", "base_url": "http://x", "model": "m"})
    monkeypatch.setattr(dissect, "_chat", fake_chat)
    monkeypatch.setattr(
        dissect, "_rewrite_call", lambda *a, **k: {"title": "t", "content": "c", "body": "b", "summary": "s", "tags": []}
    )

    result = dissect.analyze(text="这是一段用于拆解校验测试的足够长文案。" * 6)
    assert "dissect" in result
    # 至少 1 次非法 + 1 次重试 = 2 次拆解调用
    assert calls["dissect"] >= 2


def test_analyze_gives_up_after_retry_fails(monkeypatch):
    def fake_chat(cfg, system, user, **kw):
        if system is dissect._DISSECT_SYSTEM:
            return _invalid_dissect_json()  # 两次都非法
        return json.dumps({"title": "t", "content": "c"})

    monkeypatch.setattr(dissect, "_deepseek_cfg", lambda: {"api_key": "x", "base_url": "http://x", "model": "m"})
    monkeypatch.setattr(dissect, "_chat", fake_chat)
    monkeypatch.setattr(
        dissect, "_rewrite_call", lambda *a, **k: {"title": "t", "content": "c"}
    )

    with pytest.raises(dissect.DissectError) as e:
        dissect.analyze(text="这是一段用于拆解校验测试的足够长文案。" * 6)
    assert "结构校验未通过" in str(e.value)
