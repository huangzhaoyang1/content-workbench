"""健康检查与联调测试接口。

注意：早期版本里的 /config 与 /pipeline/run 端点已移除：
- /config 与 config.py 的 GET /api/config 路径冲突，会抢先匹配导致配置页拿不到完整配置；
  配置读写请统一走 config.py 的 /api/config。
- /pipeline/run 调用了 service 层不存在的 pipeline.run_pipeline 且 Settings 无 raw 属性，
  流水线启动/状态请统一走 pipeline.py 的 /api/pipeline/start 与 /api/pipeline/status/{task_id}。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.system.config import env_managed_fields, settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    scripts_dir: str
    scripts_available: bool
    cloud: bool = False
    env_keys: list[str] = []      # 由环境变量托管的密钥字段（只回字段名，不回值）


class EchoRequest(BaseModel):
    message: str


class EchoResponse(BaseModel):
    echo: str
    received_at: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """健康检查：验证后端存活、脚本目录可达性、密钥注入情况。

    云端部署时没有本地脚本目录属于预期状态，status 返回 degraded 但服务正常，
    Render 的健康检查只看 HTTP 200，不会因此判定失败。
    """
    scripts_available = settings.scripts_dir.exists()
    return HealthResponse(
        status="ok" if scripts_available else "degraded",
        version="0.3.0",
        scripts_dir=str(settings.scripts_dir),
        scripts_available=scripts_available,
        cloud=settings.is_cloud,
        env_keys=sorted(env_managed_fields()),
    )


@router.post("/test/echo", response_model=EchoResponse)
def echo(req: EchoRequest) -> EchoResponse:
    """联调测试接口：原样回显消息并返回服务端时间。"""
    return EchoResponse(
        echo=req.message,
        received_at=datetime.now().isoformat(timespec="seconds"),
    )
