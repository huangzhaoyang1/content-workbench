"""OCR 识别策略模式：把「截图 → 结构化文章数据」抽象成可插拔的策略。

四种策略并存：
- vision_model：云端视觉大模型（依赖 vision 服务，需配 VL 端点）
- paddle_ocr  ：本地 PaddleOCR 出文字 + DeepSeek 整理成 JSON
- tesseract   ：本地 Tesseract 出文字 + DeepSeek 整理成 JSON
                （独立 C++ 程序，与 Python 版本无关，高版本 Python 下最稳）
- baidu_ocr   ：百度智能云 OCR（通用文字识别·高精度版）出文字 + DeepSeek 整理
                （纯云端、中文准确率高、每天 1000 次免费额度，无需本地安装）

后端 /api/analytics/ocr-upload 不再关心用哪种方式，只调用本模块的
recognize() / status()，由当前配置里的 ocr.mode 决定走哪条路。
新增一种 OCR 方式，只要实现一个策略类并注册进 _STRATEGIES 即可。
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from ..system.config import load_config
from . import vision

log = logging.getLogger("workbench.ocr")

MODE_PADDLE = "paddle_ocr"
MODE_VISION = "vision_model"
MODE_TESSERACT = "tesseract"
MODE_BAIDU = "baidu_ocr"
DEFAULT_MODE = MODE_PADDLE


class OcrError(Exception):
    """识别过程中的可预期错误，路由层转成 4xx，message 直接展示给用户。"""


@runtime_checkable
class OcrStrategy(Protocol):
    mode: str

    def recognize(self, content: bytes, filename: str) -> dict: ...

    def status(self) -> dict: ...


class VisionModelStrategy:
    """云端视觉模型策略：直接复用现有 vision 服务。"""

    mode = MODE_VISION

    def recognize(self, content: bytes, filename: str) -> dict:
        return vision.recognize(content, filename)

    def status(self) -> dict:
        st = vision.status()
        st["mode"] = self.mode
        return st


class PaddleOcrStrategy:
    """本地 PaddleOCR 策略：OCR 出文字 + DeepSeek 整理。"""

    mode = MODE_PADDLE

    def recognize(self, content: bytes, filename: str) -> dict:
        from . import ocr_paddle

        return ocr_paddle.recognize(content, filename)

    def status(self) -> dict:
        from . import ocr_paddle

        st = ocr_paddle.status()
        st["mode"] = self.mode
        return st


class TesseractStrategy:
    """本地 Tesseract 策略：OCR 出文字 + DeepSeek 整理。

    Tesseract 是独立安装的 C++ 程序，不受 Python 版本影响，
    PaddleOCR 装不上时用这个最省事。
    """

    mode = MODE_TESSERACT

    def recognize(self, content: bytes, filename: str) -> dict:
        from . import ocr_tesseract

        return ocr_tesseract.recognize(content, filename)

    def status(self) -> dict:
        from . import ocr_tesseract

        st = ocr_tesseract.status()
        st["mode"] = self.mode
        return st


class BaiduOcrStrategy:
    """百度智能云 OCR 策略：OCR 出文字 + DeepSeek 整理。

    纯云端调用，中文准确率高、国内速度快，每天 1000 次免费额度，
    不需要在本地装任何程序，也不受 Python 版本影响。
    """

    mode = MODE_BAIDU

    def recognize(self, content: bytes, filename: str) -> dict:
        from . import ocr_baidu

        return ocr_baidu.recognize(content, filename)

    def status(self) -> dict:
        from . import ocr_baidu

        st = ocr_baidu.status()
        st["mode"] = self.mode
        return st


# 策略注册表：新增 OCR 方式只需在此注册一个 OcrStrategy 实现
_STRATEGIES: dict[str, type[OcrStrategy]] = {
    MODE_PADDLE: PaddleOcrStrategy,
    MODE_TESSERACT: TesseractStrategy,
    MODE_BAIDU: BaiduOcrStrategy,
    MODE_VISION: VisionModelStrategy,
}


def available_modes() -> list[str]:
    """所有已注册的 OCR 方式（前端下拉与校验用）。"""
    return list(_STRATEGIES)


def resolve_mode(mode: str | None = None) -> str:
    """把传入的 / 配置的 mode 归一化成合法策略名，非法值回落到默认。"""
    cfg = load_config()
    m = (mode or "").strip() or (cfg.get("ocr") or {}).get("mode") or DEFAULT_MODE
    return m if m in _STRATEGIES else DEFAULT_MODE


def get_strategy(mode: str | None = None) -> OcrStrategy:
    return _STRATEGIES[resolve_mode(mode)]()


def recognize(mode: str | None, content: bytes, filename: str) -> dict:
    """按策略识别一张截图，返回 {articles, summary, confidence, note, model}。"""
    return get_strategy(mode).recognize(content, filename)


def status(mode: str | None = None) -> dict:
    """按策略返回可用性探测（前端决定要不要提前提示）。"""
    return get_strategy(mode).status()
