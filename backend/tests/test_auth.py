"""鉴权中间件测试。

通过环境变量在运行时切换鉴权开关（settings.auth_* 是实时读环境变量的 property），
无需重载模块即可验证：默认关、开启后无令牌拦截、带令牌放行、错误令牌拦截、
健康检查/状态接口豁免、开启但无令牌时返回 500、文档/OPTIONS 免鉴权。
"""
import os

# 默认确保关闭，避免污染其它用例
os.environ.pop("WORKBENCH_AUTH_ENABLED", None)
os.environ.pop("WORKBENCH_AUTH_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


def _set_auth(enabled: bool, token: str | None = None) -> None:
    if enabled:
        os.environ["WORKBENCH_AUTH_ENABLED"] = "true"
    else:
        os.environ.pop("WORKBENCH_AUTH_ENABLED", None)
    if token is None:
        os.environ.pop("WORKBENCH_AUTH_TOKEN", None)
    else:
        os.environ["WORKBENCH_AUTH_TOKEN"] = token


def _clear_auth() -> None:
    os.environ.pop("WORKBENCH_AUTH_ENABLED", None)
    os.environ.pop("WORKBENCH_AUTH_TOKEN", None)


def test_status_disabled_by_default():
    _clear_auth()
    with TestClient(app) as c:
        r = c.get("/api/auth/status")
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False
        assert body["token_set"] is False


def test_disabled_allows_requests():
    _clear_auth()
    with TestClient(app) as c:
        r = c.get("/api/topic/data-insight")
        assert r.status_code == 200


def test_enabled_blocks_without_token():
    _set_auth(True, "secret-123")
    try:
        with TestClient(app) as c:
            r = c.get("/api/topic/data-insight")
            assert r.status_code == 401
            assert r.json()["error"]["code"] == "unauthorized"

            # 带正确令牌放行
            ok = c.get(
                "/api/topic/data-insight",
                headers={"Authorization": "Bearer secret-123"},
            )
            assert ok.status_code == 200

            # 错误令牌拦截
            bad = c.get(
                "/api/topic/data-insight",
                headers={"Authorization": "Bearer wrong"},
            )
            assert bad.status_code == 401
    finally:
        _clear_auth()


def test_health_and_status_exempt():
    _set_auth(True, "secret-123")
    try:
        with TestClient(app) as c:
            # 健康检查免鉴权
            assert c.get("/api/health").status_code == 200
            # 状态接口免鉴权（前端据此决定是否登录）
            assert c.get("/api/auth/status").status_code == 200
            # 文档/根路径免鉴权
            assert c.get("/").status_code == 200
    finally:
        _clear_auth()


def test_enabled_without_token_returns_500():
    _set_auth(True, None)
    try:
        with TestClient(app) as c:
            # 开了鉴权但没配令牌：部署失误，立即返回 500 暴露问题，而非悄悄放行
            r = c.get("/api/topic/data-insight")
            assert r.status_code == 500
            assert r.json()["error"]["code"] == "auth_token_missing"
            assert "WORKBENCH_AUTH_TOKEN" in r.json()["detail"]
    finally:
        _clear_auth()


def test_docs_and_openapi_exempt():
    _set_auth(True, "secret-123")
    try:
        with TestClient(app) as c:
            # 交互式文档与 OpenAPI schema 免鉴权（否则无法排查/联调）
            assert c.get("/docs").status_code == 200
            assert c.get("/openapi.json").status_code == 200
            assert c.get("/redoc").status_code == 200
    finally:
        _clear_auth()


def test_options_preflight_exempt():
    _set_auth(True, "secret-123")
    try:
        with TestClient(app) as c:
            # CORS 预检请求免鉴权：不带任何令牌的 OPTIONS 不应被 auth 拦截返回 401。
            # （目标路由本身不支持 OPTIONS 时可能返回 405，但绝不能是 401。）
            r = c.options("/api/topic/data-insight")
            assert r.status_code != 401
            assert "WWW-Authenticate" not in r.headers
    finally:
        _clear_auth()
