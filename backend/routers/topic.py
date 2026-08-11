"""选题生成接口。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.system.config import load_config
from ..services.content import topic

router = APIRouter(tags=["topic"])


class TopicGenerateReq(BaseModel):
    hotspots: list[dict[str, Any]] = []
    data_insight: str | None = None
    data_suggestions: list[dict[str, Any]] = []


@router.get("/topic/data-insight")
def topic_data_insight() -> dict:
    """读历史数据，给出「3 个内容方向 + 3 种标题风格 + 建议」。

    没有数据时返回 available=False + reason，前端显示引导即可，不算错误。
    """
    return topic.data_insight()


@router.post("/topic/generate")
def topic_generate(body: TopicGenerateReq) -> dict:
    """生成候选选题（5 个基础 + 数据分析建议方向）。

    前端没传 data_insight / data_suggestions 时，服务端会自动读一次历史数据补上。
    """
    topics = topic.generate(
        load_config(),
        hotspots=body.hotspots,
        data_insight=body.data_insight,
        data_suggestions=body.data_suggestions,
    )
    return {"topics": topics}
