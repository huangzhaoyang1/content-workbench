"""拆解结果（dissect）输出结构硬校验。

作为「硬结构闸门」在 LLM 输出解析为 dict 之后、归一化（_normalize_dissect）
之前调用：

- 必备字段齐全、类型正确；
- 五清单（views / cases / numbers / quotes / methods）必须为 list；
- completeness.level 必须合法（full / partial / thin）；
- 缺失披露：声明非 full 时必须披露 missing 列表；
- 空素材：五清单全空且未声明缺失 → 视为没有抠到任何有效素材。

字段名与 dissect.py 的归一化输出保持一致（basics / materials / hook /
structure / boom / audience / portable / migration），前端解析逻辑不变。
校验不通过时由调用方（dissect.analyze）把错误说明回灌给模型重试一次。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class Completeness(BaseModel):
    """素材完整度自述（来自模型自身声明，未经过本地规则复核）。"""

    level: Literal["full", "partial", "thin"]
    missing: list[str] = Field(default_factory=list)
    note: str = ""


class Materials(BaseModel):
    """核心素材清单：五个列表 + 完整度自述。

    仅校验「五个清单是 list」这一硬约束，内部元素结构（如 views 的
    point/detail）交给归一化层处理，避免对模型输出过约束。
    """

    views: list[Any] = Field(default_factory=list)
    cases: list[Any] = Field(default_factory=list)
    numbers: list[Any] = Field(default_factory=list)
    quotes: list[Any] = Field(default_factory=list)
    methods: list[Any] = Field(default_factory=list)
    completeness: Completeness


class DissectResult(BaseModel):
    """拆解结果顶层结构，字段名与 dissect.py 输出一一对应。

    basics / hook / boom / audience / migration 为对象；
    structure / portable 为列表；materials 为核心素材清单。
    """

    basics: dict[str, Any] = Field(default_factory=dict)
    hook: dict[str, Any] = Field(default_factory=dict)
    boom: dict[str, Any] = Field(default_factory=dict)
    audience: dict[str, Any] = Field(default_factory=dict)
    migration: dict[str, Any] = Field(default_factory=dict)
    structure: list[Any] = Field(default_factory=list)
    portable: list[Any] = Field(default_factory=list)
    materials: Materials


def validate_dissect(parsed: dict) -> tuple[bool, list[str]]:
    """校验拆解结果结构，返回 (是否通过, 错误说明列表)。

    通过条件：结构合法、缺失披露自洽（声明非 full 必须披露 missing）、
    且至少存在有效素材（五清单非空 或 声明了缺失项）。

    不通过时错误信息由调用方回灌给模型，作为重试的补充提示。
    """
    errors: list[str] = []

    if not isinstance(parsed, dict):
        return False, ["拆解结果不是 JSON 对象（dict），无法结构化校验。"]

    # 1) 结构 / 类型校验：必备字段齐全、五清单为 list、level 合法
    try:
        model = DissectResult.model_validate(parsed)
    except ValidationError as e:
        seen: set[str] = set()
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "<root>"
            msg = f"字段「{loc}」校验失败：{err['msg']}"
            if msg not in seen:
                seen.add(msg)
                errors.append(msg)
        return False, errors

    # 2) 缺失披露校验（enforce_missing）
    comp = model.materials.completeness
    if comp.level != "full" and not comp.missing:
        errors.append(
            "声明非 full（level=%s）但未披露缺失项：completeness.missing 不能为空，"
            "请列出具体没抓到的素材类型（如「没有抠到具体数字」）。" % comp.level
        )

    # 3) 空素材校验：五清单全空且未声明任何缺失 → 视为无有效素材
    mats = model.materials
    has_any = bool(
        mats.views or mats.cases or mats.numbers or mats.quotes or mats.methods
    )
    if not has_any and not comp.missing:
        errors.append(
            "素材五清单（views/cases/numbers/quotes/methods）全为空且未声明缺失项，"
            "视为没有抠到任何有效素材，请重新拆解或补充完整文案。"
        )

    return (len(errors) == 0, errors)
