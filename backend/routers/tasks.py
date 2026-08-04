"""历史任务接口：列表（筛选 + 分页）、详情、重新生成、打开本地目录。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services import pipeline
from ..services import queue as task_queue
from ..services import tasks

router = APIRouter(tags=["tasks"])


@router.get("/tasks")
def list_tasks(
    keyword: str = Query("", description="标题/主题关键词"),
    status: str = Query("全部", description="全部/成功/失败/进行中"),
    platform: str = Query("全部", description="全部/微信公众号/其他"),
    time_range: str = Query("全部", description="全部/近7天/近30天/近90天"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(0, ge=0, le=200, description="每页条数，0 表示不分页"),
) -> dict:
    """获取历史任务列表与统计概览。"""
    all_tasks, skipped = tasks.scan_issues()
    filtered = tasks.filter_tasks(all_tasks, keyword, status, platform, time_range)
    stats = tasks.build_stats(all_tasks)
    paged, pages = tasks.paginate(filtered, page, page_size)
    return {
        "tasks": paged,
        "stats": stats,
        "skipped": skipped,
        "total_filtered": len(filtered),
        "page": min(page, pages),
        "page_size": page_size,
        "pages": pages,
    }


@router.get("/tasks/{issue}")
def task_detail(issue: int) -> dict:
    """获取单期任务详情（含文章预览与封面 base64）。"""
    detail = tasks.get_task_detail(issue)
    if not detail:
        raise HTTPException(status_code=404, detail=f"第{issue}期不存在")
    return detail


class RegenerateReq(BaseModel):
    mode: str = "queue"     # queue=加入队列（默认，更安全）；now=立刻执行
    extra: str = ""


@router.post("/tasks/{issue}/regenerate")
def regenerate(issue: int, body: RegenerateReq | None = None) -> dict:
    """用同一选题重新生成一期。默认加入队列，mode=now 时直接启动流水线。"""
    body = body or RegenerateReq()
    detail = tasks.get_task_detail(issue)
    if not detail:
        raise HTTPException(status_code=404, detail=f"第{issue}期不存在")
    topic = detail.get("topic") or detail.get("title") or ""
    if not topic:
        raise HTTPException(status_code=422, detail="该期没有记录选题主题，无法重新生成")

    if body.mode == "now":
        try:
            res = pipeline.start(
                topic=topic, angle=detail.get("angle") or "", extra=body.extra or "",
                platform=detail.get("platform") or "wechat",
            )
        except pipeline.PipelineUnavailable as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        return {"mode": "now", **res}

    item = task_queue.add(
        topic=topic, angle=detail.get("angle") or "", extra=body.extra or "",
        platform=detail.get("platform") or "wechat", source="tasks",
    )
    return {"mode": "queue", "item": item, **task_queue.stats()}


@router.post("/tasks/{issue}/open-dir")
def open_dir(issue: int) -> dict:
    """在系统文件管理器中打开该期产出目录（仅本地使用）。"""
    ok, msg = tasks.open_issue_dir(issue)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "path": msg}
