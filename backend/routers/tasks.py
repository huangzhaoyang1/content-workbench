"""历史任务接口：列表（筛选 + 分页）、详情、重新生成、打开本地目录。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services.content import pipeline
from ..services.system import queue as task_queue
from ..services.data import tasks

router = APIRouter(tags=["tasks"])


@router.get("/tasks")
def list_tasks(
    keyword: str = Query("", description="标题/主题关键词"),
    status: str = Query("全部", description="全部/成功/失败/运行中/等待中"),
    platform: str = Query("全部", description="全部/微信公众号/小红书/抖音/其他"),
    time_range: str = Query("全部", description="全部/近7天/近30天/本月/上月"),
    tag: str = Query("", description="按标签过滤（留空=不限）"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(0, ge=0, le=200, description="每页条数，0 表示不分页"),
) -> dict:
    """获取历史任务列表与统计概览。"""
    all_tasks, skipped = tasks.scan_issues()
    filtered = tasks.filter_tasks(all_tasks, keyword, status, platform, time_range, tag)
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


@router.get("/tasks/tags")
def task_tags() -> dict:
    """返回所有任务标签（去重，按出现次数降序），供筛选下拉使用。"""
    return {"tags": tasks.list_task_tags()}


@router.get("/tasks/trash")
def task_trash() -> dict:
    """回收站里的历史任务。"""
    return tasks.list_trash_tasks()


class TaskIssueReq(BaseModel):
    issue: int = 0


@router.post("/tasks/restore")
def restore_task(body: TaskIssueReq) -> dict:
    """从回收站恢复某期任务。"""
    try:
        return tasks.restore_task(body.issue)
    except tasks.TasksError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/tasks/purge")
def purge_task(body: TaskIssueReq) -> dict:
    """从回收站彻底删除某期任务（不可恢复）。"""
    try:
        return tasks.purge_task(body.issue)
    except tasks.TasksError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/tasks/empty-trash")
def empty_trash() -> dict:
    """清空回收站。"""
    return tasks.empty_task_trash()


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


@router.delete("/tasks/{issue}")
def delete_task(issue: int) -> dict:
    """删除某期历史任务 → 移入回收站（连同整期产出目录，可恢复）。"""
    try:
        return tasks.delete_task(issue)
    except tasks.TasksError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


class SetTaskTagsReq(BaseModel):
    tags: list[str] = []


@router.patch("/tasks/{issue}/tags")
def set_tags(issue: int, body: SetTaskTagsReq) -> dict:
    """给某期任务设置标签（覆盖式；空列表即清空）。"""
    try:
        tags = tasks.set_task_tags(issue, body.tags)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "issue": issue, "tags": tags}


class BatchDeleteTasksReq(BaseModel):
    issues: list[int] = []


@router.post("/tasks/batch-delete")
def batch_delete_tasks(body: BatchDeleteTasksReq) -> dict:
    """批量删除历史任务（连同整期产出目录），跳过不存在的期号。"""
    removed: list[int] = []
    skipped: list[int] = []
    for issue in body.issues or []:
        try:
            tasks.delete_task(issue)
            removed.append(issue)
        except (tasks.TasksError, ValueError, TypeError):
            skipped.append(issue)
        except Exception:
            skipped.append(issue)
    return {"ok": True, "removed": removed, "skipped": skipped}
