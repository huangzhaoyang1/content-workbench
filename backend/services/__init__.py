"""后端服务层包。

按功能模块分子包：

- ``content``     ：内容生产（拆解 / 选题 / 流水线 / 质量评分）
- ``data``        ：数据与识别（分析 / 历史任务 / OCR / 视觉模型）
- ``system``      ：系统（配置 / 配额 / 定时任务 / 任务队列）
- ``integration`` ：第三方集成（热点素材 / 抖音同步）

为平滑过渡，这里把子模块重新导出，旧写法 ``from backend.services import X``
仍可用；新代码请直接使用子包路径，例如
``from backend.services.data import analytics``。
"""
from .content import dissect, pipeline, quality, topic
from .data import (
    analytics,
    ocr_baidu,
    ocr_paddle,
    ocr_strategy,
    ocr_structure,
    ocr_tesseract,
    tasks,
    vision,
)
from .integration import douyin_sync, hotspot
from .system import config, quota, queue, schedule

__all__ = [
    "dissect", "pipeline", "quality", "topic",
    "analytics", "ocr_baidu", "ocr_paddle", "ocr_strategy", "ocr_structure",
    "ocr_tesseract", "tasks", "vision",
    "douyin_sync", "hotspot",
    "config", "quota", "queue", "schedule",
]
