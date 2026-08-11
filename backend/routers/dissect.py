"""抖音爆款拆解接口。

    POST   /douyin-dissect/fetch        链接 → 结构化抓取结果（只抓不拆，供预览编辑）
    POST   /douyin-dissect/analyze      链接或文案 → 拆解分析 + 三种角度的公众号改写
    POST   /douyin-dissect/rewrite-one  只重新生成某一个角度的文章
    GET    /douyin-dissect/angles       三个改写角度的定义
    POST   /douyin-dissect/save-topic   把改写结果存进选题库
    GET    /douyin-dissect/topics       选题库列表（支持分类/优先级/状态筛选）
    PATCH  /douyin-dissect/topics/{id}  编辑选题
    DELETE /douyin-dissect/topics/{id}  删除选题
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.content import dissect
from ..services.system import queue as task_queue

router = APIRouter(tags=["dissect"])


class FetchReq(BaseModel):
    url: str = Field("", description="抖音分享链接 / 短链 / 带口令的整段分享文本")


@router.post("/douyin-dissect/fetch")
def fetch(body: FetchReq) -> dict:
    """只抓取不拆解：返回视频标题、口播文案、描述、作者、发布时间、点赞/评论/收藏数。

    抓不到的字段会出现在 source.missing 里，前端据此提示用户手动补。
    """
    try:
        return dissect.fetch_preview(body.url or "")
    except dissect.DissectError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


class AnalyzeReq(BaseModel):
    url: str = Field("", description="抖音分享链接，与 text 二选一")
    text: str = Field("", description="抖音视频文案 / 口播稿，优先于 url")
    meta: dict[str, Any] | None = Field(
        None, description="上一步 /fetch 拿到的 source 结构，用户改过文案时用来保留视频元信息"
    )


@router.post("/douyin-dissect/analyze")
def analyze(body: AnalyzeReq) -> dict:
    """拆解一条抖音视频，并改写成三篇不同角度的公众号文章。

    text 与 url 二选一，两个都给时以 text 为准（手动粘贴的文案最完整）。
    一次拆解 + 三次并行改写，通常 60-180 秒。
    """
    try:
        return dissect.analyze(url=body.url or "", text=body.text or "", meta=body.meta)
    except dissect.DissectError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


class RewriteOneReq(BaseModel):
    angle_key: str = Field(..., description="pitfall / howto / insight")
    raw_text: str = Field(..., description="原始口播文案，与首次拆解时保持一致")
    dissect: dict[str, Any] | None = Field(
        None, description="上一次的拆解结果；不传则重新拆一遍（更慢）"
    )


@router.post("/douyin-dissect/rewrite-one")
def rewrite_one(body: RewriteOneReq) -> dict:
    """只重新生成某一个角度的文章，复用已有拆解结果，通常 30-90 秒。"""
    try:
        return dissect.rewrite_one(
            angle_key=body.angle_key,
            raw_text=body.raw_text,
            dissect_data=body.dissect,
        )
    except dissect.DissectError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.get("/douyin-dissect/angles")
def angles() -> dict:
    """三个改写角度的定义，前端用来渲染标题卡片。"""
    return {
        "items": [
            {"key": a["key"], "label": a["label"], "desc": a["desc"], "words": a["words"]}
            for a in dissect.REWRITE_ANGLES
        ]
    }


class SaveTopicReq(BaseModel):
    title: str
    content: str = ""
    theme: str = ""
    category: str = ""
    priority: str = ""
    status: str = ""
    angle_key: str = ""
    tags: list[str] | None = None


@router.post("/douyin-dissect/save-topic")
def save_topic(body: SaveTopicReq) -> dict:
    """把选中的标题 + 改写正文存进选题库（按标题去重）。"""
    try:
        return dissect.save_topic(
            title=body.title,
            content=body.content,
            theme=body.theme,
            source="dissect",
            category=body.category,
            priority=body.priority,
            status=body.status,
            angle_key=body.angle_key,
            tags=body.tags,
        )
    except dissect.DissectError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.get("/douyin-dissect/topics")
def list_topics(
    limit: int = Query(50, ge=1, le=200),
    category: str = Query("", description="踩坑类/干货类/复盘类/工具类/其他"),
    priority: str = Query("", description="高/中/低"),
    status: str = Query("", description="待生产/生产中/已完成"),
    keyword: str = Query(""),
    tag: str = Query("", description="按标签过滤"),
) -> dict:
    """选题库列表。高优先级排前面，支持分类 / 优先级 / 状态 / 关键词 / 标签筛选。"""
    return dissect.list_topics(
        limit=limit,
        category=category,
        priority=priority,
        status=status,
        keyword=keyword,
        tag=tag,
    )


@router.get("/douyin-dissect/topics/tags")
def list_topic_tags() -> dict:
    """选题库里出现过的全部标签。"""
    return dissect.list_tags()


@router.get("/douyin-dissect/topics/trash")
def list_topic_trash() -> dict:
    """回收站里的选题。"""
    return dissect.list_trash()


class TopicIdReq(BaseModel):
    id: str = ""


@router.post("/douyin-dissect/topics/restore")
def restore_topic(body: TopicIdReq) -> dict:
    """从回收站恢复一条选题。"""
    try:
        return dissect.restore_topic(body.id)
    except dissect.DissectError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.post("/douyin-dissect/topics/purge")
def purge_topic(body: TopicIdReq) -> dict:
    """从回收站彻底删除一条选题（不可恢复）。"""
    try:
        return dissect.purge_topic(body.id)
    except dissect.DissectError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.post("/douyin-dissect/topics/empty-trash")
def empty_trash() -> dict:
    """清空回收站。"""
    return dissect.empty_trash()


class UpdateTopicReq(BaseModel):
    title: str | None = None
    content: str | None = None
    theme: str | None = None
    category: str | None = None
    priority: str | None = None
    status: str | None = None
    tags: list[str] | None = None


@router.patch("/douyin-dissect/topics/{topic_id}")
def update_topic(topic_id: str, body: UpdateTopicReq) -> dict:
    """局部更新一条选题，只传要改的字段。"""
    try:
        return dissect.update_topic(topic_id, **body.model_dump(exclude_none=True))
    except dissect.DissectError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.delete("/douyin-dissect/topics/{topic_id}")
def delete_topic(topic_id: str) -> dict:
    """删除一条选题。"""
    try:
        return dissect.delete_topic(topic_id)
    except dissect.DissectError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


class BatchDeleteTopicsReq(BaseModel):
    ids: list[str] = []


@router.post("/douyin-dissect/topics/batch-delete")
def batch_delete_topics(body: BatchDeleteTopicsReq) -> dict:
    """批量删除选题（跳过不存在的 id，不抛错）。"""
    try:
        return dissect.delete_topics(body.ids)
    except dissect.DissectError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


class BatchProduceTopicsReq(BaseModel):
    ids: list[str] = []


@router.post("/douyin-dissect/topics/batch-produce")
def batch_produce_topics(body: BatchProduceTopicsReq) -> dict:
    """批量把选题送进队列（带 topic_id 联动，source=topic）。"""
    added: list[dict] = []
    skipped: list[str] = []
    for tid in body.ids or []:
        item = dissect.get_topic(tid)
        if not item:
            skipped.append(tid)
            continue
        try:
            q = task_queue.add(
                topic=item["title"],
                angle="" if item.get("category") == "其他" else (item.get("category") or ""),
                extra=item.get("content", ""),
                platform="wechat",
                source="topic",
                topic_id=item["id"],
            )
            added.append(q)
        except Exception:
            skipped.append(tid)
    return {
        "added": len(added),
        "items": added,
        "skipped": skipped,
        **task_queue.stats(),
    }


class RestoreVersionReq(BaseModel):
    version_id: str = ""


@router.get("/douyin-dissect/topics/{topic_id}/versions")
def topic_versions(topic_id: str) -> dict:
    """某选题的版本历史列表（元数据，不含完整正文）。"""
    return dissect.list_topic_versions(topic_id)


@router.get("/douyin-dissect/topics/{topic_id}/versions/{version_id}")
def topic_version_detail(topic_id: str, version_id: str) -> dict:
    """取某条历史版本的完整内容。"""
    v = dissect.get_topic_version(topic_id, version_id)
    if not v:
        raise HTTPException(status_code=404, detail="找不到这个历史版本")
    return {"topic_id": topic_id, "version": v}


@router.post("/douyin-dissect/topics/{topic_id}/restore-version")
def topic_restore_version(topic_id: str, body: RestoreVersionReq) -> dict:
    """回退到某个历史版本（当前内容会先自动存档）。"""
    try:
        return dissect.restore_topic_version(topic_id, body.version_id)
    except dissect.DissectError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
