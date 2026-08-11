"""统一错误处理测试。

验证两点：
1) 路由把业务异常转成 HTTPException 后，http_exc_handler 输出干净的中文 JSON
   （ok:false / detail / error.code），而不是泛化的「服务端异常」；
2) 新增的全局 DissectError/TasksError 兜底处理器同样输出该格式。
"""
import asyncio
import json

from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.main import app, dissect_exc_handler, tasks_exc_handler
from backend.services.content.dissect import DissectError
from backend.services.data.tasks import TasksError


def test_http_404_task_returns_friendly_json():
    with TestClient(app) as client:
        r = client.delete("/api/tasks/999999")
        assert r.status_code == 404
        body = r.json()
        assert body["ok"] is False
        assert "不存在" in body["detail"]
        assert body["error"]["code"] == "http_404"


def test_http_404_topic_returns_friendly_json():
    with TestClient(app) as client:
        r = client.patch("/api/douyin-dissect/topics/ghost", json={"content": "x"})
        assert r.status_code == 404
        assert r.json()["ok"] is False


def test_dissect_global_handler_format():
    async def _run():
        req = Request({"type": "http", "method": "GET", "path": "/x", "headers": []})
        return await dissect_exc_handler(req, DissectError("自定义错误", 400))

    resp = asyncio.run(_run())
    assert resp.status_code == 400
    body = json.loads(resp.body)
    assert body["ok"] is False
    assert body["detail"] == "自定义错误"
    assert body["error"]["code"] == "business_error"


def test_tasks_global_handler_format():
    async def _run():
        req = Request({"type": "http", "method": "GET", "path": "/x", "headers": []})
        return await tasks_exc_handler(req, TasksError("任务错误", 409))

    resp = asyncio.run(_run())
    assert resp.status_code == 409
    body = json.loads(resp.body)
    assert body["detail"] == "任务错误"
    assert body["error"]["code"] == "business_error"
