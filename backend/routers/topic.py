"""选题生成接口。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import load_config
from ..services import topic

router = APIRouter(tags=["topic"])


class TopicGenerateReq(BaseModel):
    hotspots: list[dict[str, Any]] = []
    data_insight: str | None = None
    data_suggestions: list[dict[str, Any]] = []


@router.post("/topic/generate")
def topic_generate(body: TopicGenerateReq) -> dict:
    """生成候选选题（5 个基础 + 可选数据分析建议方向）。"""
    topics = topic.generate(
        load_config(),
        hotspots=body.hotspots,
        data_insight=body.data_insight,
        data_suggestions=body.data_suggestions,
    )
    return {"topics": topics}
