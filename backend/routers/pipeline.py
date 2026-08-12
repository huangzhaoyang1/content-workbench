"""流水线调度接口：启动 + 查询状态（实时日志）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.content import pipeline

router = APIRouter(tags=["pipeline"])


class PipelineStartReq(BaseModel):
    topic: str
    angle: str = ""
    extra: str = ""
    references: str = ""   # 热点素材链接，英文逗号分隔
    platform: str = ""     # 留空 → 回退到用户偏好 default_platform
    review: bool = False   # True=存为待审核(不推送)，审核后再发布
    style_key: str = ""    # 留空 → 回退到偏好
    word_count: str = ""   # 留空 → 回退到偏好
    domains: list[str] | None = None      # 留空 → 回退到偏好
    forbidden_topics: list[str] | None = None  # 留空 → 回退到偏好
    auto_refs: bool = True                 # True=用 topic 检索历史素材补充进 references


class PipelineIssueReq(BaseModel):
    issue: int
    cover_label: str = ""   # 封面期号标识；非空时覆盖默认「第N期」（合集场景由用户手动指定）


@router.get("/pipeline/availability")
def pipeline_availability() -> dict:
    """流水线是否可用（云端没有本地脚本时返回 available=false + 原因说明）。"""
    return pipeline.availability()


@router.post("/pipeline/start")
def pipeline_start(body: PipelineStartReq) -> dict:
    """启动流水线，返回 {task_id, issue}。review=True 时存为待审核不推送。"""
    if not body.topic or not body.topic.strip():
        raise HTTPException(status_code=422, detail="topic 不能为空")
    try:
        return pipeline.start(
            topic=body.topic.strip(),
            angle=body.angle,
            extra=body.extra,
            references=body.references,
            platform=body.platform,
            review=body.review,
            style_key=body.style_key,
            word_count=body.word_count,
            domains=body.domains,
            forbidden_topics=body.forbidden_topics,
            auto_supplement_refs=body.auto_refs,
        )
    except pipeline.PipelineUnavailable as e:
        # 503：环境缺脚本导致功能不可用，不是代码 bug，前端直接展示这句话
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.post("/pipeline/publish")
def pipeline_publish(body: PipelineIssueReq) -> dict:
    """把已存为「待审核」的某期推送到公众号，返回 {task_id, issue}。"""
    try:
        return pipeline.publish(body.issue, cover_label=body.cover_label)
    except pipeline.PipelineUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.post("/pipeline/discard")
def pipeline_discard(body: PipelineIssueReq) -> dict:
    """把「待审核」的某期标记为放弃（只改本地状态，不调微信）。"""
    return pipeline.discard(body.issue)


@router.get("/pipeline/status/{task_id}")
def pipeline_status(task_id: str) -> dict:
    """查询任务状态与实时日志。"""
    task = pipeline.get_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task
