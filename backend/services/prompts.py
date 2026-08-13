"""提示词加载器。

所有硬编码提示词现已集中维护在 ``backend/prompts/`` 下：

    prompts/
        dissect/system.md     # 拆解相关提示词（分节存放）
        dissect/params.json   # REWRITE_ANGLES（三种改写角度的参数）
        hotspot/system.md     # 热点洞察提示词（用 .replace 渲染）
        ocr-shared/system.md  # 视觉 / OCR 共用：数据提取系统提示词
        ocr-shared/user.md    # 视觉 / OCR 共用：参数化用户提示词（用 .replace 渲染）
        quality/styles.json   # 内容质量四阶标准 + 自检收尾

``*.md`` 多提示词文件用如下分节标记隔开，本模块按标记切分还原：

    [[[PROMPT:NAME]]]
    <提示词正文>

这样 service 层只需 ``from ..prompts import load_dissect`` 等，拿到的字符串
与迁移前源码里硬编码的字面量逐字一致（见 _archive_junk/_baseline.json，迁移审计基线，已从 prompts/ 移出，与生成脚本的回环校验）。
"""
from __future__ import annotations

import json
import os
import re

_PROMPTS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prompts")
)

_SECTION_RE = re.compile(r"^\[\[\[PROMPT:(.+?)\]\]\]$", re.M)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _parse_sections(text: str) -> dict:
    """按 [[[PROMPT:NAME]]] 标记切分多提示词文件，返回 {name: 正文}。"""
    result: dict = {}
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        s = m.end()
        if text[s:s + 1] == "\n":
            s += 1
        if i + 1 < len(matches):
            ns = matches[i + 1].start()
            # 分节之间只有一个 "\n" 分隔符，去掉它避免正文多出一个尾部换行。
            e = ns - 1 if text[ns - 1:ns] == "\n" else ns
        else:
            e = len(text)
        result[name] = text[s:e]
    return result


def load_dissect() -> dict:
    """返回拆解相关提示词 dict：键为 _DISSECT_SYSTEM / _DISSECT_USER /
    _REWRITE_SYSTEM / _REWRITE_USER / _REWRITE_FEW_SHOT。

    （默认文风 _DEFAULT_STYLE 已迁移到 dissect/params.json 的 default_style 字段，
    由 load_dissect_default_style() 提供，不再从此处返回。）
    """
    return _parse_sections(_read(os.path.join(_PROMPTS_DIR, "dissect", "system.md")))


# 兜底默认值：仅在 prompts/dissect/params.json 缺失 default_style 字段时生效，正常由单一真相源驱动。
_DEFAULT_STYLE_LITERAL = "真实、有用、可跟；第一人称，像跟朋友聊天"


def _load_dissect_params() -> dict:
    """读取 dissect/params.json 全量参数（含 angles 与 default_style）。"""
    with open(os.path.join(_PROMPTS_DIR, "dissect", "params.json"), encoding="utf-8") as f:
        return json.load(f)


def load_dissect_angles() -> list:
    """返回 REWRITE_ANGLES 列表（三种改写角度的完整定义）。"""
    return _load_dissect_params()["angles"]


def load_dissect_default_style() -> str:
    """返回默认文风（单一真相源：dissect/params.json 的 default_style 字段）。

    文件缺失或字段缺失时回退到原硬编码字面量，保证无参时行为一致。
    """
    try:
        return _load_dissect_params().get("default_style") or _DEFAULT_STYLE_LITERAL
    except (OSError, ValueError):
        return _DEFAULT_STYLE_LITERAL


def load_hotspot() -> str:
    """返回热点洞察提示词模板（含 {titles} / {data_source} 占位符）。

    调用方用 str.replace 渲染（模板内含 JSON 示例的字面 { }，不能用 .format）。
    """
    return _read(os.path.join(_PROMPTS_DIR, "hotspot", "system.md"))


def load_topic() -> str:
    """返回选题生成系统提示词（含 {positioning} / {default_style} 占位符）。

    调用方用 str.replace 渲染；提示词内已写明 JSON 输出 schema，要求模型产出
    具体、能直接当公众号文章标题的「选题」而非空泛的角度方向。
    """
    return _read(os.path.join(_PROMPTS_DIR, "topic", "system.md"))


def load_quality_styles() -> dict:
    """返回 {"QUALITY_SPEC": ..., "QUALITY_SELF_CHECK": ...}。"""
    with open(os.path.join(_PROMPTS_DIR, "quality", "styles.json"), encoding="utf-8") as f:
        return json.load(f)


def load_ocr_shared() -> dict:
    """返回视觉 / OCR 共用的提示词 {"system": ..., "user": ...}。

    user.md 是参数化模板，含 {input_desc}/{ocr_detail}/{mode_rule}/{input_block}
    占位符，以及调用时才替换的 {image}(视觉) / {engine},{text}(OCR)。调用方用
    str.replace 渲染（模板内含 JSON 示例的字面 { }，不能用 .format）。
    """
    return {
        "system": _read(os.path.join(_PROMPTS_DIR, "ocr-shared", "system.md")),
        "user": _read(os.path.join(_PROMPTS_DIR, "ocr-shared", "user.md")),
    }
