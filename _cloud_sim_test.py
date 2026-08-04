"""云端环境模拟测试：不依赖本地 scripts/，只用环境变量注入密钥。

模拟 Render 上的情况，验证：
1. 服务能起来（相对导入、启动钩子都正常）
2. /api/health 返回 200，且 degraded 不影响存活
3. 密钥来自环境变量而不是磁盘文件
4. save_config 不会把环境变量里的密钥写进磁盘
5. CORS 对 Vercel 域名放行、对陌生域名拒绝
6. 流水线在无脚本环境下返回 503 人话提示，而不是 500 崩溃
"""
import os
import tempfile

TMP_DATA = tempfile.mkdtemp(prefix="cw_data_")
os.environ.update(
    {
        "RENDER": "1",
        "WORKBENCH_DATA_DIR": TMP_DATA,
        "STREAMLIT_PROJECT_ROOT": os.path.join(TMP_DATA, "no_such_project"),
        "DEEPSEEK_API_KEY": "sk-test-deepseek-from-env",
        "SERPAPI_KEY": "serpapi-test-from-env",
        "WX_APPID": "wx_test_appid",
        "WX_SECRET": "wx_test_secret",
        "FRONTEND_URL": "https://content-workbench.vercel.app",
        "DAILY_LIMIT": "33",
    }
)

import json  # noqa: E402
import pathlib  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


with TestClient(app) as c:
    print("\n[1] 健康检查")
    r = c.get("/api/health")
    check("HTTP 200", r.status_code == 200, str(r.status_code))
    body = r.json()
    check("cloud=True", body.get("cloud") is True, json.dumps(body, ensure_ascii=False))
    check("scripts_available=False（云端预期）", body.get("scripts_available") is False)
    check(
        "密钥来自环境变量",
        set(body.get("env_keys", []))
        == {"deepseek.api_key", "search_api.api_key", "wechat.appid", "wechat.secret"},
        str(body.get("env_keys")),
    )

    print("\n[2] 配置读取：环境变量覆盖生效")
    cfg = c.get("/api/config").json()
    check("deepseek key 来自 env", cfg["deepseek"]["api_key"] == "sk-test-deepseek-from-env")
    check("serpapi key 来自 env", cfg["search_api"]["api_key"] == "serpapi-test-from-env")
    check("daily_limit 来自 env", cfg["daily_limit"] == 33, str(cfg.get("daily_limit")))

    print("\n[3] 配置保存：环境变量密钥不落盘")
    cfg["account_name"] = "云端保存测试账号"
    r = c.put("/api/config", json={"config": cfg})
    check("保存返回 2xx", r.status_code < 300, str(r.status_code) + " " + r.text[:120])
    disk = json.loads(
        (pathlib.Path(TMP_DATA) / "workbench_config.json").read_text(encoding="utf-8")
    )
    check("磁盘上 deepseek key 为空", disk["deepseek"]["api_key"] == "")
    check("磁盘上 serpapi key 为空", disk["search_api"]["api_key"] == "")
    check("磁盘上微信 secret 为空", disk["wechat"]["secret"] == "")
    check("普通字段正常落盘", disk["account_name"] == "云端保存测试账号", disk.get("account_name", ""))
    check("重新读取仍能拿到 env 密钥", c.get("/api/config").json()["deepseek"]["api_key"]
          == "sk-test-deepseek-from-env")

    print("\n[4] CORS 白名单")
    r = c.options(
        "/api/health",
        headers={
            "Origin": "https://content-workbench.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    check("放行正式前端域名", r.headers.get("access-control-allow-origin") is not None,
          str(r.headers.get("access-control-allow-origin")))
    r = c.options(
        "/api/health",
        headers={
            "Origin": "https://cw-git-preview-abc.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    check("放行 Vercel 预览域名", r.headers.get("access-control-allow-origin") is not None)
    r = c.options(
        "/api/health",
        headers={"Origin": "http://localhost:3002", "Access-Control-Request-Method": "GET"},
    )
    check("放行本机任意端口", r.headers.get("access-control-allow-origin") is not None)
    r = c.options(
        "/api/health",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"},
    )
    check("拒绝陌生域名", r.headers.get("access-control-allow-origin") is None,
          str(r.headers.get("access-control-allow-origin")))

    print("\n[5] 流水线降级")
    r = c.get("/api/pipeline/availability")
    check("availability 返回 200", r.status_code == 200)
    check("available=False", r.json().get("available") is False)
    check("给出人话原因", len(r.json().get("reason", "")) > 10, r.json().get("reason", "")[:60])
    r = c.post("/api/pipeline/start", json={"topic": "测试选题"})
    check("启动返回 503 而不是 500", r.status_code == 503, str(r.status_code))
    check("错误信息可读", "云端" in r.json().get("detail", ""), r.json().get("detail", "")[:60])

    print("\n[6] 热点搜索（无真 key 时走 mock，不应报错）")
    r = c.post("/api/hotspot/search", json={"keywords": ["AI 副业"], "time_range": "近7天", "limit": 5})
    check("HTTP 200", r.status_code == 200, str(r.status_code)[:200])
    if r.status_code == 200:
        data = r.json()
        check("返回条目非空", len(data.get("items", [])) > 0, f"origin={data.get('origin')}")

print("\n" + "=" * 50)
print("失败项：" + (", ".join(fails) if fails else "无，全部通过"))
print("=" * 50)
