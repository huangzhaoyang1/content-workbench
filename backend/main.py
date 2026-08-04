"""FastAPI 应用入口。

AI 内容运营工作台后端：复用现有 Python 流水线脚本，
为前端 Next.js 提供 REST API。

启动方式（在 content-workbench 根目录）：
    uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .routers import analytics
from .routers import config as config_router
from .routers import health, hotspot, pipeline
from .routers import queue as queue_router
from .routers import schedule as schedule_router
from .routers import tasks, topic
from .services import schedule as schedule_service

log = logging.getLogger("workbench")

# ---------------------------------------------------------------------------
# CORS 白名单
# 本机：Next.js 默认 3000，端口被占用会顺延到 3001/3002…，写死单端口会导致
#       浏览器拦截、页面所有请求失败，所以放开 localhost 任意端口。
# 线上：由环境变量 FRONTEND_URL 指定（支持英文逗号分隔多个域名）。
#       Vercel 每次 preview 部署域名都会变，默认额外放行 *.vercel.app，
#       不需要的话设 ALLOW_VERCEL_PREVIEWS=0 关掉。
# ---------------------------------------------------------------------------
_LOCALHOST_REGEX = r"http://(localhost|127\.0\.0\.1)(:\d+)?"
_VERCEL_REGEX = r"https://[a-z0-9][a-z0-9-]*\.vercel\.app"


def _allowed_origins() -> list[str]:
    raw = os.getenv("FRONTEND_URL", "")
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


def _origin_regex() -> str:
    parts = [_LOCALHOST_REGEX]
    if os.getenv("ALLOW_VERCEL_PREVIEWS", "1") not in ("0", "false", "False"):
        parts.append(_VERCEL_REGEX)
    custom = os.getenv("ALLOWED_ORIGIN_REGEX", "").strip()
    if custom:
        parts.append(custom)
    return r"^(" + "|".join(parts) + r")$"


ALLOWED_ORIGINS = _allowed_origins()
ALLOWED_ORIGIN_REGEX = _origin_regex()

app = FastAPI(
    title="AI 内容运营工作台 API",
    version="0.3.0",
    description=(
        "复用现有 Python 流水线脚本的后端服务。"
        "核心闭环：热点 → 选题 → 流水线 → 结果；"
        "扩展能力：数据分析、任务队列、定时任务。"
    ),
)

# CORS：allow_origins（精确白名单）与 allow_origin_regex（本机 + preview 域名）同时生效
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
log.info("CORS 白名单=%s regex=%s", ALLOWED_ORIGINS, ALLOWED_ORIGIN_REGEX)


# ---------------------------------------------------------------------------
# 统一错误格式
# 保留 detail 字段（前端 api.ts 依赖它，向后兼容），额外补 ok/code/error。
# ---------------------------------------------------------------------------
def _error_body(status: int, message: str, code: str = "") -> dict:
    return {
        "ok": False,
        "detail": message,
        "error": {"code": code or f"http_{status}", "message": message},
    }


@app.exception_handler(StarletteHTTPException)
async def http_exc_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.status_code, detail),
    )


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errs = exc.errors()
    if errs:
        first = errs[0]
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        msg = f"参数校验失败：{loc or '请求体'} {first.get('msg', '')}".strip()
    else:
        msg = "参数校验失败"
    return JSONResponse(status_code=422, content=_error_body(422, msg, "validation_error"))


@app.exception_handler(Exception)
async def unhandled_exc_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=_error_body(500, f"服务端异常：{type(exc).__name__}", "internal_error"),
    )


# 所有业务路由挂在 /api 前缀下
app.include_router(health.router, prefix="/api")
app.include_router(config_router.router, prefix="/api")
app.include_router(hotspot.router, prefix="/api")
app.include_router(topic.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(queue_router.router, prefix="/api")
app.include_router(schedule_router.router, prefix="/api")


@app.on_event("startup")
def _on_startup() -> None:
    """恢复定时任务并拉起调度线程。"""
    try:
        schedule_service.startup()
    except Exception:
        log.exception("定时任务调度启动失败")


@app.on_event("shutdown")
def _on_shutdown() -> None:
    try:
        schedule_service.shutdown()
    except Exception:
        pass


@app.get("/")
def root() -> dict:
    return {"service": "ai-content-workbench", "docs": "/docs", "api_prefix": "/api"}
