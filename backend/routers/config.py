"""配置管理接口：读取 / 更新 / 测试连接。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import ConfigWriteError, load_config, save_config
from ..services import hotspot

router = APIRouter(tags=["config"])


class ConfigUpdate(BaseModel):
    config: dict[str, Any]


class ConnectionTestReq(BaseModel):
    search_api: dict[str, Any] = {}
    deepseek: dict[str, Any] = {}


@router.get("/config")
def get_config() -> dict:
    """获取全部配置（复用现有 workbench_config.json 结构）。"""
    return load_config()


@router.put("/config")
def put_config(body: ConfigUpdate) -> dict:
    """更新配置并落盘。落盘失败时返回可读原因，而不是笼统的 500。"""
    try:
        return save_config(body.config)
    except ConfigWriteError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/config/test")
def test_connection(body: ConnectionTestReq) -> dict:
    """测试 SerpAPI 与 DeepSeek 连通性（用请求体里的 Key，不落地）。"""
    sa = body.search_api or {}
    ds = body.deepseek or {}
    serpapi_ok, serpapi_msg = (False, "未填写 API Key")
    if sa.get("api_key"):
        serpapi_ok, serpapi_msg = hotspot._probe_serpapi(sa["api_key"])
    deepseek_ok, deepseek_msg = (False, "未填写 API Key")
    if ds.get("api_key"):
        deepseek_ok, deepseek_msg = hotspot._probe_deepseek(ds)
    return {
        "serpapi": {"ok": serpapi_ok, "message": serpapi_msg},
        "deepseek": {"ok": deepseek_ok, "message": deepseek_msg},
    }
