"""FastAPI 应用入口。

AI 内容运营工作台后端：复用现有 Python 流水线脚本，
为前端 Next.js 提供 REST API。

启动方式（在 content-workbench 根目录）：
    uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import hmac
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .routers import analytics
from .routers import config as config_router
from .routers import dissect
from .routers import douyin_sync as douyin_sync_router
from .routers import health, hotspot, pipeline
from .routers import queue as queue_router
from .routers import schedule as schedule_router
from .routers import tasks, topic
from .services.content.dissect import DissectError
from .services.data.tasks import TasksError
from .services.integration import douyin_sync as douyin_sync_service
from .services.integration.douyin_sync import SyncError
from .services.system import schedule as schedule_service
from .services.system.config import settings

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动恢复定时任务并拉起调度线程，关闭时清理。"""
    # —— 启动逻辑（yield 之前）——
    try:
        schedule_service.startup()
    except Exception:
        log.exception("定时任务调度启动失败")
    try:
        douyin_sync_service.startup()
    except Exception:
        log.exception("抖音收藏同步调度启动失败")
    yield
    # —— 关闭逻辑（yield 之后）——
    try:
        schedule_service.shutdown()
    except Exception:
        pass
    try:
        douyin_sync_service.shutdown()
    except Exception:
        pass


app = FastAPI(
    title="AI 内容运营工作台 API",
    version="0.3.0",
    description=(
        "复用现有 Python 流水线脚本的后端服务。"
        "核心闭环：热点 → 选题 → 流水线 → 结果；"
        "扩展能力：数据分析、任务队列、定时任务。"
    ),
    lifespan=lifespan,
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
# 访问鉴权中间件（部署时开启，本地默认关）
# ---------------------------------------------------------------------------
# 豁免清单：健康检查、API 文档、OpenAPI schema、根路径、鉴权状态接口、
# CORS 预检（OPTIONS）。其余 /api/* 请求必须带 `Authorization: Bearer <token>`，
# 否则返回 401。鉴权状态接口本身必须免鉴权，否则前端无法先查询是否开启登录。
_AUTH_EXEMPT_PREFIXES = ("/docs", "/redoc", "/openapi.json")
_AUTH_EXEMPT_EXACT = {"/", "/health", "/api/auth/status"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not settings.auth_enabled:
        return await call_next(request)

    path = request.url.path
    if (
        request.method == "OPTIONS"
        or path in _AUTH_EXEMPT_EXACT
        or path.startswith("/api/health")
        or any(path.startswith(p) or path == p for p in _AUTH_EXEMPT_PREFIXES)
    ):
        return await call_next(request)

    token = settings.auth_token
    if not token:
        # 开了鉴权却没配令牌：部署失误，立即报错而非悄悄放行，避免裸奔。
        log.error("鉴权已开启但未配置 WORKBENCH_AUTH_TOKEN")
        return JSONResponse(
            status_code=500,
            content=_error_body(
                500, "鉴权已开启但未配置令牌，请设置 WORKBENCH_AUTH_TOKEN", "auth_token_missing"
            ),
        )

    auth_header = request.headers.get("Authorization", "")
    # 仅允许 Authorization: Bearer <token> header，禁止 URL 查询参数传令牌
    # （避免令牌出现在服务器访问日志 / 浏览器历史 / Referer 中被窃取）。
    # 使用 hmac.compare_digest 做常量时间比对，防时序攻击。
    expected = f"Bearer {token}"
    if hmac.compare_digest(auth_header, expected):
        return await call_next(request)

    log.info("鉴权失败 path=%s", path)
    return JSONResponse(
        status_code=401,
        content=_error_body(401, "需要有效访问令牌，请先登录", "unauthorized"),
        headers={"WWW-Authenticate": f'Bearer realm="{settings.auth_realm}"'},
    )


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
    import traceback
    tb = traceback.format_exc()
    log.exception("未处理异常 %s %s", request.method, request.url.path)
    # 把最近 5 行堆栈附到 detail（仅服务端异常，不暴露给线上正常用户；本地调试很有用）
    tb_tail = "\n".join(tb.strip().splitlines()[-8:])
    detail = f"服务端异常：{type(exc).__name__}: {exc}\n\n{tb_tail}"
    return JSONResponse(
        status_code=500,
        content=_error_body(500, detail, "internal_error"),
    )


# 业务异常：把 service 层抛出的中文提示原样返回给前端，而不是落到 500 泛化提示。
@app.exception_handler(DissectError)
async def dissect_exc_handler(_: Request, exc: DissectError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.status_code, exc.message, "business_error"),
    )


@app.exception_handler(TasksError)
async def tasks_exc_handler(_: Request, exc: TasksError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.status_code, exc.message, "business_error"),
    )


# 抖音收藏同步业务异常。SyncError 是 RuntimeError 子类、本身没有 status_code/message
# 属性，故用 hasattr 兜底到 400 + str(exc)，避免出现泛化的 500「服务端异常」。
@app.exception_handler(SyncError)
async def sync_exc_handler(_: Request, exc: SyncError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code if hasattr(exc, "status_code") else 400,
        content=_error_body(
            exc.status_code if hasattr(exc, "status_code") else 400,
            exc.message if hasattr(exc, "message") else str(exc),
            "business_error",
        ),
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
app.include_router(dissect.router, prefix="/api")
app.include_router(douyin_sync_router.router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {"service": "ai-content-workbench", "docs": "/docs", "api_prefix": "/api"}


@app.get("/api/auth/status")
def auth_status() -> dict:
    """告知前端当前是否开启鉴权、是否已配置令牌。

    前端据此决定要不要弹出登录框、以及把令牌存到 localStorage 后自动附带。
    """
    return {
        "enabled": settings.auth_enabled,
        "token_set": bool(settings.auth_token),
        "realm": settings.auth_realm,
    }
