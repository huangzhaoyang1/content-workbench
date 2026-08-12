"""用户偏好：读写 backend/data/preferences.json。

供流水线 start() 作为默认值（可被显式参数覆盖），以及配置页展示 / 维护。

设计要点：
- 复用 config.py 的 atomic_write_json 做原子写（同盘 os.replace + 指数退避重试），
  保证写一半崩溃或文件被占用时不会损坏 / 截断。
- 「密钥剥离」模式与 config.py 保持一致：本文件当前不含任何密钥字段，
  _SECRET_FIELD_NAMES 为空集，密钥剥离是防御性空操作；若将来加入敏感字段，
  只需往该集合里加名字即可一键启用，无需改写入逻辑。
- DEFAULT_PREFS 提供出厂默认值；load_preferences() 做字段回退 + 类型归一
  （列表字段去空 / 去重 / 保序），保证缺字段、旧文件、脏数据都不会让下游崩。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from ..system.config import DATA_DIR, atomic_write_json

PREFS_PATH = DATA_DIR / "preferences.json"
_LOCK = threading.Lock()

# 出厂默认值。start() 在未显式传参时回退到这里；
# default_platform 与现有 start() 的 "wechat" 默认值对齐，保证行为一致。
DEFAULT_PREFS = {
    "default_platform": "wechat",   # 默认平台：wechat / douyin / xiaohongshu / ...
    "style_key": "",                # 常用风格 key（对应 prompts 里的风格档位）
    "word_count": "",               # 字数偏好（纯文本，如 "800-1200" / "短" / "1500"）
    "domains": [],                  # 常用领域（如 ["AI", "职场", "副业"]）
    "forbidden_topics": [],         # 禁写话题（命中时选题 / 流水线提示规避）
}

# 密钥类字段名（本文件暂无；保留为与 config.py 一致的防御性结构）。
_SECRET_FIELD_NAMES = frozenset()


def _normalize(prefs: object) -> dict:
    """字段回退 + 类型归一，保证下游拿到的结构稳定、可预测。

    - 未知字段丢弃；缺字段补默认值。
    - 字符串字段：转 str、去首尾空白；default_platform 为空时回退到 wechat。
    - 列表字段：非列表先包成列表；逐元素转 str、去空、去重、保序。
    """
    out: dict = dict(DEFAULT_PREFS)
    if isinstance(prefs, dict):
        for k, v in prefs.items():
            if k in DEFAULT_PREFS:
                out[k] = v

    out["default_platform"] = (str(out.get("default_platform") or "")).strip() or DEFAULT_PREFS["default_platform"]
    out["style_key"] = (str(out.get("style_key") or "")).strip()
    out["word_count"] = (str(out.get("word_count") or "")).strip()

    for key in ("domains", "forbidden_topics"):
        raw = out.get(key)
        if not isinstance(raw, list):
            raw = [raw] if raw else []
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in raw:
            s = (str(item or "")).strip()
            if s and s not in seen:
                seen.add(s)
                cleaned.append(s)
        out[key] = cleaned

    return out


def load_preferences() -> dict:
    """读取偏好；文件缺失 / 损坏 / 非字典时返回 DEFAULT_PREFS（不抛异常）。"""
    try:
        if PREFS_PATH.exists():
            with _LOCK:
                data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
            return _normalize(data)
    except Exception:
        pass
    return dict(DEFAULT_PREFS)


def save_preferences(prefs: object) -> dict:
    """原子写入偏好，返回归一化后的完整偏好（供接口直接返回）。

    非密钥文件，沿用 config.py 的 atomic_write_json；密钥剥离逻辑本文件为空操作，
    但保留与 config.py 一致的代码形态（将来加敏感字段可一键启用）。
    """
    normalized = _normalize(prefs)
    # 密钥剥离（当前无密钥字段，保留为与 config.py 一致的防御性结构）
    for name in _SECRET_FIELD_NAMES:
        if name in normalized:
            normalized[name] = ""
    with _LOCK:
        atomic_write_json(PREFS_PATH, normalized)
    return normalized
