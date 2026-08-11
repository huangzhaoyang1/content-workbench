"""本地 OCR 驱动：PaddleOCR 识别截图文字，再由 DeepSeek 整理成结构化 JSON。

整体链路：
    截图 → PaddleOCR 出文字（按表格行结构重排）→ DeepSeek(deepseek-chat)
         → 归一化成 {articles, summary, confidence, note}

为什么是「OCR + LLM 两步」而不是端到端：
- PaddleOCR 只认字、不认「标题 / 阅读量 / 在看」这种表头-数值关系，直接让它吐 JSON 很不稳定；
- 把表格结构整理成 JSON 交给 DeepSeek 最稳，而且 deepseek-chat 本来就有 key，
  不用再额外配一个视觉模型，用户零配置就能用。

关于依赖与首次运行：
- PaddleOCR / PaddlePaddle 已写进 requirements.txt，安装后才有本地识别能力；
- 第一次真正识别时会自动下载检测+识别模型（几百 MB），需要联网；下完之后纯本地、可离线。
- 模块被 import 时不触发任何下载，下载只发生在第一次 recognize()。
"""
from __future__ import annotations

import logging
import threading

from . import ocr_structure, vision
from .ocr_strategy import OcrError

log = logging.getLogger("workbench.ocr_paddle")

# 结果里标注的引擎名，同时会写进 DeepSeek 提示词
ENGINE_NAME = "PaddleOCR"

# 懒加载的单例引擎；首次 recognize 时才真正 import paddleocr 并下载模型
_ENGINE = None
_ENGINE_LOCK = threading.Lock()
_MODEL_WARMING = False  # 下模型期间置位，便于给用户更准的提示


# --------------------------------------------------------------------------
# 引擎（懒加载）
# --------------------------------------------------------------------------
def _get_engine():
    """返回 PaddleOCR 单例；首次调用时 import 并触发模型下载。"""
    global _ENGINE, _MODEL_WARMING
    if _ENGINE is not None:
        return _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is not None:
            return _ENGINE
        try:
            from paddleocr import PaddleOCR
        except Exception as e:  # 多半是没装 paddleocr / paddlepaddle
            raise OcrError(
                "本地 OCR 引擎 PaddleOCR 尚未安装。请在后端环境执行 "
                "`pip install -r backend/requirements.txt` 安装后重启服务，"
                "再用「本地 PaddleOCR」方式识别。"
            ) from e
        _MODEL_WARMING = True
        try:
            engine = PaddleOCR(
                use_angle_cls=True,
                lang="ch",
                show_log=False,
                use_gpu=False,
                det_db_box_thresh=0.3,
                rec_batch_num=6,
            )
        finally:
            _MODEL_WARMING = False
        _ENGINE = engine
        return _ENGINE


# --------------------------------------------------------------------------
# 文字 → 表格行结构重排（纯函数，可单测）
# --------------------------------------------------------------------------
def _rebuild_rows(raw_lines: list) -> str:
    """把 PaddleOCR 的识别结果重排成「一行一记录、列用 Tab 分隔」的纯文本。

    PaddleOCR 返回结构是 [ [ [ [x1,y1],[x2,y2],[x3,y3],[x4,y4] ], (text, score) ], ... ]。
    公众号后台是规整表格：按文字框的 y 坐标聚类成「行」，行内按 x 从左到右排序，
    单元格用 Tab 连接，能很好地还原「标题 / 阅读量 / 在看 …」的列关系。
    """
    cells: list[tuple[float, float, float, float, str]] = []
    for line in raw_lines or []:
        if not line:
            continue
        box = line[0]
        pair = line[1]
        text = pair[0] if isinstance(pair, (list, tuple)) else pair
        if not text or not str(text).strip():
            continue
        try:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
        except Exception:
            continue
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        cells.append((x0, y0, x1, y1, str(text).strip()))

    if not cells:
        return ""

    # 行高中位数作为行聚类阈值（同一行的框 y 差距应小于约 0.6 个行高）
    heights = sorted((c[3] - c[1]) for c in cells)
    med_h = heights[len(heights) // 2] if heights else 10
    row_th = max(8.0, med_h * 0.6)

    cells.sort(key=lambda c: (c[1], c[0]))
    rows: list[list[tuple[float, float, float, float, str]]] = []
    cur: list = []
    cur_y: float | None = None
    for c in cells:
        y0 = c[1]
        if cur_y is None or abs(y0 - cur_y) <= row_th:
            cur.append(c)
            cur_y = cur_y if cur_y is not None else y0
        else:
            rows.append(cur)
            cur = [c]
            cur_y = y0
    if cur:
        rows.append(cur)

    return "\n".join("\t".join(c[4] for c in r) for r in rows)


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def status() -> dict:
    """给前端的可用性探测：本地 OCR 只要装了 paddleocr 就一直可用。"""
    try:
        import paddleocr  # noqa: F401 仅做可用性探测，不触发模型下载
    except Exception:
        installed = False
    else:
        installed = True
    return {
        "configured": installed,
        "model": "PaddleOCR",
        "endpoint": "本地",
        "inherited": False,
        "hint": "" if installed else "本地 OCR 引擎 PaddleOCR 尚未安装，无法使用「本地 PaddleOCR」方式。",
        "mode": "paddle_ocr",
        "note": "首次识别会自动下载模型（几百 MB），请保持联网；之后可离线使用。",
    }


def recognize(content: bytes, filename: str = "") -> dict:
    """识别一张截图：本地 OCR 出文字 → DeepSeek 整理成结构化数据。"""
    # 沿用视觉模型的三重图片校验（大小 / 扩展名 / magic bytes）
    vision.validate_image(filename, content)

    engine = _get_engine()
    try:
        from io import BytesIO

        from PIL import Image
        import numpy as np
    except Exception as e:
        raise OcrError(
            f"本地 OCR 依赖缺失（PIL/numpy）：{type(e).__name__}。请重装后端依赖后重试。"
        ) from e

    try:
        img = Image.open(BytesIO(content)).convert("RGB")
        arr = np.array(img)
    except Exception as e:
        raise OcrError(f"「{filename or '图片'}」无法作为图片打开：{type(e).__name__}。") from e

    try:
        raw = engine.ocr(arr, cls=True)
    except Exception as e:
        raise OcrError(
            f"PaddleOCR 识别失败（{type(e).__name__}）。请换一张清晰、未被遮挡的截图重试。"
        ) from e

    lines = raw[0] if raw and isinstance(raw, list) else []
    text = _rebuild_rows(lines)
    if not text.strip():
        raise OcrError(
            f"从「{filename or '这张图'}」没有识别到任何文字。"
            "请确认是清晰、未被弹窗遮挡的公众号后台截图。"
        )

    log.info("PaddleOCR 提取文字 %d 行，交给 DeepSeek 整理", text.count("\n") + 1)
    # 结构化走共享层（与 Tesseract 驱动同一套提示词与错误处理）
    return ocr_structure.structure(text, filename, ENGINE_NAME)
