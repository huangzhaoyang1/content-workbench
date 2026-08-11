"""抖音收藏同步接口。

    GET    /douyin-sync/state      首屏一次性数据（配置 + 统计 + 下次执行时间）
    GET    /douyin-sync/config     读取配置（cookie 不回传明文）
    POST   /douyin-sync/config     保存配置（含来源 / 频率 / cookie / 筛选条件）
    POST   /douyin-sync/run        立即跑一次（可带手动链接 urls）
    GET    /douyin-sync/records    爬取记录列表（支持状态/来源/关键词筛选）
    GET    /douyin-sync/records/{id}   单条记录详情
    PATCH  /douyin-sync/records/{id}   改状态 / 笔记 / 文案 / 标题
    DELETE /douyin-sync/records/{id}   删除单条
    POST   /douyin-sync/records/clear  清空（可选按状态）
    POST   /douyin-sync/import    把勾选的记录选入选题库
    GET    /douyin-sync/runs      运行历史
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.integration import douyin_sync

router = APIRouter(tags=["douyin-sync"])


@router.get("/douyin-sync/state")
def state() -> dict:
    """首屏一次性数据：配置 + 统计 + 下次执行时间 + 是否在跑。"""
    return douyin_sync.get_state()


@router.get("/douyin-sync/config")
def get_config() -> dict:
    return douyin_sync.get_config()


class RunReq(BaseModel):
    urls: list[str] = Field(default_factory=list, description="手动粘贴的抖音链接，留空则跑配置里的来源")


@router.post("/douyin-sync/run")
def run(body: RunReq) -> dict:
    """立即跑一次同步。"""
    try:
        return douyin_sync.run_sync(urls=body.urls or None, trigger="manual")
    except douyin_sync.SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/douyin-sync/config")
def save_config(body: dict[str, Any]) -> dict:
    """保存配置（来源 / 频率 / cookie / 筛选条件）。"""
    try:
        return douyin_sync.save_config(body or {})
    except douyin_sync.SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/douyin-sync/records")
def list_records(
    status: str = Query("", description="new / imported / ignored"),
    keyword: str = Query(""),
    source: str = Query("", description="来源名称，例如「我的收藏夹」"),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    return douyin_sync.list_records(status=status, keyword=keyword, limit=limit, source=source)


@router.get("/douyin-sync/records/{record_id}")
def get_record(record_id: str) -> dict:
    try:
        return douyin_sync.get_record(record_id)
    except douyin_sync.SyncError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/douyin-sync/records/{record_id}")
def update_record(record_id: str, body: dict[str, Any]) -> dict:
    try:
        return douyin_sync.update_record(record_id, **(body or {}))
    except douyin_sync.SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/douyin-sync/records/{record_id}")
def delete_record(record_id: str) -> dict:
    try:
        return douyin_sync.delete_record(record_id)
    except douyin_sync.SyncError as e:
        raise HTTPException(status_code=404, detail=str(e))


class ClearReq(BaseModel):
    status: str = Field("", description="留空=清空全部，否则只清该状态")


@router.post("/douyin-sync/records/clear")
def clear_records(body: ClearReq) -> dict:
    return douyin_sync.clear_records(status=body.status or "")


class ImportReq(BaseModel):
    ids: list[str] = Field(..., description="要选入选题库的记录 id 列表")
    priority: str = Field("中", description="高 / 中 / 低")


@router.post("/douyin-sync/import")
def import_to_topics(body: ImportReq) -> dict:
    try:
        return douyin_sync.import_to_topics(ids=body.ids, priority=body.priority)
    except douyin_sync.SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/douyin-sync/runs")
def list_runs(limit: int = Query(20, ge=1, le=30)) -> dict:
    return douyin_sync.list_runs(limit=limit)
