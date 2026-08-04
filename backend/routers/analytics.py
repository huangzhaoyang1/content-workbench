"""数据分析接口：上传 → 分析 → 选题建议。"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from ..services import analytics

router = APIRouter(tags=["analytics"])

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB


def _summary(ds: dict) -> dict:
    """只返回给前端需要的元信息，不把整份 records 传回去（可能很大）。"""
    return {
        "dataset_id": ds["dataset_id"],
        "filename": ds.get("filename"),
        "row_count": ds.get("row_count"),
        "headers": ds.get("headers"),
        "mapping": ds.get("mapping"),
        "has_date": bool(ds.get("has_date")),
        "uploaded_at": ds.get("uploaded_at"),
        "is_sample": bool(ds.get("is_sample")),
        "preview": ds.get("records", [])[:5],
    }


@router.post("/analytics/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """上传 CSV/Excel 数据文件，解析后返回数据集摘要。"""
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB，请先裁剪后再上传")
    try:
        ds = analytics.parse_file(file.filename or "", content)
    except analytics.AnalyticsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败：{type(e).__name__}")
    return _summary(ds)


@router.post("/analytics/sample")
def load_sample() -> dict:
    """载入内置示例数据，方便没有导出文件时先看效果。"""
    ds = analytics.build_sample()
    return _summary(ds)


class AnalyzeReq(BaseModel):
    dataset_id: str | None = None
    time_range: str = "全部"


@router.post("/analytics/analyze")
def analyze(body: AnalyzeReq) -> dict:
    """分析数据集，返回概览 / 趋势 / 榜单。"""
    ds = analytics.get_dataset(body.dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="没有可分析的数据，请先上传文件或载入示例数据")
    try:
        return analytics.analyze(ds, body.time_range or "全部")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"分析失败：{type(e).__name__}")


@router.get("/analytics/suggestions")
def get_suggestions(dataset_id: str = Query("", description="数据集 ID，留空取最近一次")) -> dict:
    """基于数据生成 3-5 条选题方向建议。"""
    ds = analytics.get_dataset(dataset_id or None)
    if not ds:
        raise HTTPException(status_code=404, detail="没有可用数据，请先上传文件或载入示例数据")
    try:
        items = analytics.suggestions(ds)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"生成建议失败：{type(e).__name__}")
    return {"suggestions": items, "dataset_id": ds["dataset_id"]}


@router.delete("/analytics")
def clear() -> dict:
    """清空当前分析数据。"""
    analytics.clear()
    return {"ok": True}
