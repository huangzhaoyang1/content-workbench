"""热点搜索接口。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.system.config import load_config
from ..services.integration import hotspot
from ..services.system import quota

router = APIRouter(tags=["hotspot"])


class HotspotSearchReq(BaseModel):
    keywords: list[str] = []
    time_range: str = "近7天"   # 近1天 / 近7天 / 近30天
    limit: int = 15


@router.post("/hotspot/search")
def hotspot_search(body: HotspotSearchReq) -> dict:
    """搜索热点，返回 {items, origin, insight}。"""
    return hotspot.search(load_config(), "\n".join(body.keywords), body.time_range, body.limit)


@router.get("/hotspot/quota")
def get_quota() -> dict:
    """今日搜索额度用量（前端展示「今日已用 X/Y」，用满后搜索会回退示例数据）。"""
    return quota.quota_status(load_config().get("daily_limit", 50))


@router.post("/hotspot/quota/reset")
def reset_quota() -> dict:
    """手动清零今日额度。注意：解除保护后，后续搜索会真实调用 SerpAPI 并计费。"""
    quota.quota_reset()
    return quota.quota_status(load_config().get("daily_limit", 50))
