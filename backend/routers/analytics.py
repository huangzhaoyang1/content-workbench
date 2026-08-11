"""数据分析接口：上传 → 分析 → 选题建议。

两条数据入口并存：
- /analytics/upload：CSV / Excel 文件（原有能力，不动）
- /analytics/ocr-upload + /analytics/import：公众号后台截图 → 按 OCR 策略识别 → 确认导入
  OCR 策略由配置 ocr.mode 决定，默认本地 PaddleOCR：
  paddle_ocr（本地 PaddleOCR）/ tesseract（本地 Tesseract）/ baidu_ocr（百度智能云 OCR）/
  vision_model（云端视觉模型）。
"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator

from ..services.data import analytics, ocr_baidu, ocr_strategy, ocr_tesseract, vision

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
    except analytics.AnalyticsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败（{type(e).__name__}），请稍后重试")


@router.get("/analytics/suggestions")
def get_suggestions(dataset_id: str = Query("", description="数据集 ID，留空取最近一次")) -> dict:
    """基于数据生成 3-5 条选题方向建议。"""
    ds = analytics.get_dataset(dataset_id or None)
    if not ds:
        raise HTTPException(status_code=404, detail="没有可用数据，请先上传文件或载入示例数据")
    try:
        items = analytics.suggestions(ds)
    except analytics.AnalyticsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成建议失败（{type(e).__name__}），请稍后重试")
    return {"suggestions": items, "dataset_id": ds["dataset_id"]}


@router.delete("/analytics")
def clear() -> dict:
    """清空当前分析数据。"""
    analytics.clear()
    return {"ok": True}


class RecordDeleteReq(BaseModel):
    """删除单条数据记录。

    dataset_id 留空则作用于最近一次数据集（与 analyze 的默认行为一致）。
    title + date 唯一确定一条记录（与导入去重键保持一致）。
    """

    dataset_id: str | None = None
    title: str = Field(..., min_length=1, max_length=200)
    date: str | None = None


@router.delete("/analytics/record")
def delete_record(body: RecordDeleteReq) -> dict:
    """删除单条数据记录（按标题 + 日期匹配）。

    删除成功后返回更新后的数据集摘要，前端据此刷新概览 / 趋势 / 榜单。
    """
    try:
        ds = analytics.delete_record(body.dataset_id, body.title, body.date)
    except analytics.AnalyticsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败（{type(e).__name__}），请重试。")
    return _summary(ds)


# ==========================================================================
# 截图识别导入
# ==========================================================================
@router.get("/analytics/ocr-status")
def ocr_status() -> dict:
    """当前 OCR 策略是否可用。前端据此决定要不要提前提示，不发起真实调用。"""
    try:
        return ocr_strategy.status()
    except Exception:
        return {
            "configured": False,
            "model": "",
            "endpoint": "",
            "inherited": True,
            "hint": "读取 OCR 配置失败，请到「配置」页检查。",
            "mode": ocr_strategy.DEFAULT_MODE,
        }


class OcrDetectReq(BaseModel):
    """检测本地 Tesseract 是否可用。

    允许传入「用户刚在输入框里改、还没点保存」的路径，做到先测后存。
    留空则使用当前配置里的值。
    """

    tesseract_cmd: str = Field(default="", max_length=500)
    tessdata_dir: str = Field(default="", max_length=500)


@router.post("/analytics/ocr-detect")
def ocr_detect(body: OcrDetectReq) -> dict:
    """检测 Tesseract 可执行文件与中文语言包，返回可用性与安装指引。"""
    try:
        return ocr_tesseract.detect(body.tesseract_cmd, body.tessdata_dir)
    except Exception as e:  # 检测本身不该 500，失败也要给人话
        return {
            "ok": False,
            "cmd": (body.tesseract_cmd or "").strip(),
            "version": "",
            "languages": [],
            "has_chinese": False,
            "message": f"检测失败（{type(e).__name__}）。{ocr_tesseract.INSTALL_HINT}",
        }


class BaiduDetectReq(BaseModel):
    """检测百度 OCR 密钥是否可用。

    允许传入「用户刚在输入框里填、还没点保存」的密钥，做到先测后存。
    留空则使用当前配置里的值。
    """

    api_key: str = Field(default="", max_length=500)
    secret_key: str = Field(default="", max_length=500)


@router.post("/analytics/ocr-baidu-detect")
def ocr_baidu_detect(body: BaiduDetectReq) -> dict:
    """检测百度 OCR 的 API Key / Secret Key 是否能正常换取 access_token。"""
    try:
        return ocr_baidu.detect(body.api_key, body.secret_key)
    except Exception as e:  # 检测本身不该 500，失败也要给人话
        return {
            "ok": False,
            "has_key": bool((body.api_key or "").strip() and (body.secret_key or "").strip()),
            "message": f"检测失败（{type(e).__name__}）：{ocr_baidu.APPLY_HINT}",
        }


@router.post("/analytics/ocr-upload")
async def ocr_upload(file: UploadFile = File(...)) -> dict:
    """上传一张公众号后台截图，按当前 OCR 策略识别成结构化数据（不入库）。

    一次一张：前端按图片逐个调用，才能给每张图单独显示识别状态。
    走哪种策略由配置里的 ocr.mode 决定（默认本地 PaddleOCR，可切 Tesseract / 百度 OCR / 云端视觉模型）。
    """
    filename = file.filename or "截图.png"
    try:
        content = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail=f"读取「{filename}」失败，请重新上传。")

    if len(content) > vision.MAX_IMAGE_BYTES:
        mb = len(content) / 1024 / 1024
        raise HTTPException(
            status_code=413,
            detail=f"「{filename}」有 {mb:.1f}MB，超过 10MB 上限，请裁剪或压缩后重试。",
        )

    try:
        result = ocr_strategy.recognize(None, content, filename)
    except (vision.VisionError, ocr_strategy.OcrError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # 兜底：任何意外都不让前端拿到裸 500 堆栈
        raise HTTPException(
            status_code=500,
            detail=f"识别「{filename}」时出现异常（{type(e).__name__}），请稍后重试。",
        )
    return result


class ImportArticle(BaseModel):
    """一条待导入的文章数据（前端确认对话框里编辑后的结果）。"""

    title: str = Field(..., min_length=1, max_length=200)
    date: str | None = None
    reads: float | None = Field(default=None, ge=0, le=1e9)
    likes: float | None = Field(default=None, ge=0, le=1e9)
    shares: float | None = Field(default=None, ge=0, le=1e9)
    wow: float | None = Field(default=None, ge=0, le=1e9)
    collects: float | None = Field(default=None, ge=0, le=1e9)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("标题不能为空")
        return s


class ImportReq(BaseModel):
    articles: list[ImportArticle] = Field(..., min_length=1, max_length=500)


@router.post("/analytics/import")
def import_articles(body: ImportReq) -> dict:
    """把确认后的识别数据合并进当前数据集（标题+日期去重）。"""
    try:
        res = analytics.import_records([a.model_dump() for a in body.articles])
    except analytics.AnalyticsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败（{type(e).__name__}），请重试。")
    return {
        "imported": res["imported"],
        "skipped": res["skipped"],
        "duplicates": res["duplicates"],
        "dataset": _summary(res["dataset"]),
    }
