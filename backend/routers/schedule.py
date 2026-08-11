"""定时任务接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.system import schedule

router = APIRouter(tags=["schedule"])


class ScheduleReq(BaseModel):
    name: str = ""
    topic: str = ""
    angle: str = ""
    extra: str = ""
    platform: str = "wechat"
    frequency: str = "daily"       # daily / weekly / cron
    time: str = "09:00"            # HH:MM
    weekday: int = 0               # 0=周一 … 6=周日（frequency=weekly 时生效）
    cron: str = ""                 # frequency=cron 时生效，标准 5 字段
    enabled: bool = True


class ToggleReq(BaseModel):
    enabled: bool


@router.get("/schedule")
def list_schedules() -> dict:
    """定时任务列表。"""
    return {"jobs": schedule.list_jobs()}


@router.post("/schedule")
def create_schedule(body: ScheduleReq) -> dict:
    """新增定时任务。"""
    try:
        return schedule.create(body.model_dump())
    except schedule.ScheduleError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/schedule/{job_id}")
def update_schedule(job_id: str, body: dict) -> dict:
    """更新定时任务。只传 {enabled: bool} 时表示单纯启用/禁用。"""
    try:
        job = schedule.update(job_id, body or {})
    except schedule.ScheduleError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return job


@router.delete("/schedule/{job_id}")
def delete_schedule(job_id: str) -> dict:
    """删除定时任务。"""
    if not schedule.delete(job_id):
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return {"ok": True}
