"""任务队列接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.system import queue as task_queue

router = APIRouter(tags=["queue"])


class QueueAddReq(BaseModel):
    topic: str = ""
    angle: str = ""
    extra: str = ""
    platform: str = "wechat"
    source: str = "manual"
    topic_id: str = ""  # 关联选题库条目 id（用于生产完成后翻转状态）
    review: bool = False  # 透传：是否走「待审核」而非直推微信
    # 批量加入（选题页/历史任务页一次带多条时用）
    items: list[dict] | None = None


@router.get("/queue")
def get_queue() -> dict:
    """队列状态 + 任务列表。"""
    return task_queue.snapshot()


@router.post("/queue/add")
def add_to_queue(body: QueueAddReq) -> dict:
    """添加任务到队列，支持单条或批量。"""
    if body.items:
        added = task_queue.add_many(body.items, body.source)
        if not added:
            raise HTTPException(status_code=422, detail="没有有效任务可加入（选题主题不能为空）")
        return {"added": len(added), "items": added, **task_queue.stats()}
    try:
        item = task_queue.add(
            body.topic, body.angle, body.extra, body.platform, body.source, body.topic_id,
            body.review,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"added": 1, "items": [item], **task_queue.stats()}


@router.post("/queue/start")
def start_queue() -> dict:
    """开始顺序执行队列中等待的任务。"""
    return task_queue.start()


@router.post("/queue/skip")
def skip_current() -> dict:
    """跳过当前正在执行的任务（标记为 skipped 并继续下一条）。"""
    res = task_queue.skip_current()
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("reason", "跳过失败"))
    return {"ok": True, "id": res.get("id"), **task_queue.stats()}


@router.delete("/queue/{item_id}")
def delete_item(item_id: str) -> dict:
    """删除单条队列任务（执行中的不允许删）。"""
    ok = task_queue.remove(item_id)
    if not ok:
        raise HTTPException(status_code=400, detail="任务不存在，或正在执行中无法删除")
    return {"ok": True, **task_queue.stats()}


@router.delete("/queue")
def clear_queue(only_finished: bool = False) -> dict:
    """清空队列。only_finished=true 时只清理已完成/失败的记录。"""
    removed = task_queue.clear(only_finished=only_finished)
    return {"removed": removed, **task_queue.stats()}
