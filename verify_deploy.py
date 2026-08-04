"""部署后线上验收脚本。

用法：
    python verify_deploy.py <后端地址> [前端地址]

例：
    python verify_deploy.py https://content-workbench-backend.onrender.com \
        https://content-workbench.vercel.app

只做只读探测（唯一的写操作是把配置改回原值），不会破坏线上数据。
Render 免费实例休眠时首次请求会很慢，脚本会自动等待唤醒。
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request

TIMEOUT = 90
results: list[tuple[bool, str, str]] = []


def log(ok: bool, name: str, extra: str = "") -> None:
    results.append((ok, name, extra))
    mark = "[ OK ]" if ok else "[FAIL]"
    print(f"  {mark} {name}" + (f"  -> {extra}" if extra else ""), flush=True)


def http(url: str, method: str = "GET", body: dict | None = None,
         headers: dict | None = None, timeout: int = TIMEOUT):
    """返回 (status, headers, parsed_body_or_text)。失败返回 (0, {}, 错误串)。"""
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", "User-Agent": "verify-deploy/1.0"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, dict(r.headers), json.loads(raw)
            except json.JSONDecodeError:
                return r.status, dict(r.headers), raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, dict(e.headers), json.loads(raw)
        except json.JSONDecodeError:
            return e.code, dict(e.headers), raw
    except Exception as e:  # 网络层失败
        return 0, {}, f"{type(e).__name__}: {e}"


def wake_up(api: str) -> bool:
    """唤醒可能在休眠的免费实例，最多等约 3 分钟。"""
    print("\n[0] 唤醒后端（免费实例休眠后首次访问较慢，请耐心等）")
    for i in range(1, 4):
        t0 = time.time()
        status, _, _ = http(f"{api}/api/health")
        cost = time.time() - t0
        if status == 200:
            log(True, f"后端已响应（第 {i} 次尝试，耗时 {cost:.1f}s）")
            return True
        print(f"       第 {i} 次未通（status={status}，耗时 {cost:.1f}s），10 秒后重试…", flush=True)
        time.sleep(10)
    log(False, "后端始终无响应，请检查 Render 服务状态与启动命令")
    return False


def check_frontend_api_base(web: str, api: str, html: str) -> None:
    """确认前端构建产物里真的写入了后端地址。

    NEXT_PUBLIC_* 是构建时内联到 JS chunk 里的，不会出现在首页 HTML，
    所以要顺着 <script src> 把 chunk 抓下来找。
    """
    host = api.split("//", 1)[-1].rstrip("/")
    chunks = re.findall(r'src="(/_next/static/[^"]+\.js)"', html)
    # 去重保序，最多查 12 个，避免大项目拖太久
    seen: list[str] = []
    for c in chunks:
        if c not in seen:
            seen.append(c)
    if not seen:
        log(False, "未在前端页面里找到 JS 资源，无法校验后端地址")
        return
    for path in seen[:12]:
        status, _, text = http(f"{web}{path}", timeout=30)
        if status == 200 and isinstance(text, str) and host in text:
            log(True, "前端构建产物已内联正确的后端地址", host)
            return
        if status == 200 and isinstance(text, str) and "localhost:8000" in text:
            log(False, "前端仍指向 localhost:8000",
                "NEXT_PUBLIC_API_URL 没配，或配完没重新 Deploy")
            return
    log(False, "未在前端产物中找到后端地址",
        "检查 Vercel 的 NEXT_PUBLIC_API_URL，改完必须重新 Deploy 才生效")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    api = sys.argv[1].rstrip("/")
    web = sys.argv[2].rstrip("/") if len(sys.argv) > 2 else ""

    print("=" * 62)
    print(f"后端：{api}")
    print(f"前端：{web or '（未提供，跳过前端检查）'}")
    print("=" * 62)

    if not wake_up(api):
        summary()
        return 1

    # ---------------- 1. 健康检查 ----------------
    print("\n[1] 后端健康检查")
    status, _, body = http(f"{api}/api/health")
    log(status == 200, "GET /api/health 返回 200", str(status))
    if isinstance(body, dict):
        log(body.get("version") is not None, "返回版本号", str(body.get("version")))
        log(body.get("cloud") is True, "识别为云端环境", f"cloud={body.get('cloud')}")
        env_keys = body.get("env_keys") or []
        log("deepseek.api_key" in env_keys,
            "DEEPSEEK_API_KEY 已注入", str(env_keys))
        if "search_api.api_key" not in env_keys:
            print("       提示：未检测到 SERPAPI_KEY，热点搜索会走示例数据（不影响部署成功）")

    # ---------------- 2. CORS ----------------
    print("\n[2] CORS 白名单")
    if web:
        status, hdrs, _ = http(
            f"{api}/api/health", method="OPTIONS",
            headers={"Origin": web, "Access-Control-Request-Method": "GET"},
        )
        allow = hdrs.get("access-control-allow-origin") or hdrs.get(
            "Access-Control-Allow-Origin")
        log(bool(allow), "后端放行前端域名",
            allow or "缺少 Access-Control-Allow-Origin，请检查 Render 的 FRONTEND_URL")
    else:
        print("       跳过（未提供前端地址）")

    # ---------------- 3. 前端可访问 ----------------
    print("\n[3] 前端可访问")
    if web:
        status, _, text = http(web)
        log(status == 200, "前端首页返回 200", str(status))
        if status == 200 and isinstance(text, str):
            check_frontend_api_base(web, api, text)
    else:
        print("       跳过（未提供前端地址）")

    # ---------------- 4. 热点搜索 ----------------
    print("\n[4] 热点搜索")
    status, _, body = http(
        f"{api}/api/hotspot/search",
        method="POST",
        body={"keywords": ["AI 副业"], "time_range": "近7天", "limit": 5},
    )
    log(status == 200, "POST /api/hotspot/search 返回 200", str(status))
    if isinstance(body, dict):
        items = body.get("items") or []
        log(len(items) > 0, "返回热点条目", f"{len(items)} 条，来源：{body.get('origin')}")

    # ---------------- 5. 选题生成 ----------------
    print("\n[5] 选题生成")
    status, _, body = http(
        f"{api}/api/topic/generate",
        method="POST",
        body={"hotspots": [{"title": "AI 副业调研：多数人卡在没有交付物",
                            "summary": "报告指出能变现的人把能力固化成了标准流程。"}]},
    )
    ok = status == 200
    log(ok, "POST /api/topic/generate 返回 200", str(status) if ok else str(body)[:120])
    if ok and isinstance(body, dict):
        topics = body.get("topics") or []
        log(len(topics) > 0, "返回选题", f"{len(topics)} 条")

    # ---------------- 6. 流水线降级 ----------------
    print("\n[6] 流水线（云端应为友好降级，不是崩溃）")
    status, _, body = http(f"{api}/api/pipeline/availability")
    log(status == 200, "GET /api/pipeline/availability 返回 200", str(status))
    if isinstance(body, dict) and body.get("available") is False:
        log(True, "已正确识别为不可用并给出原因", str(body.get("reason"))[:70])
    elif isinstance(body, dict) and body.get("available") is True:
        log(True, "流水线可用（后端跑在有脚本的机器上）")
    status, _, body = http(f"{api}/api/pipeline/start", method="POST",
                           body={"topic": "部署验收测试"})
    log(status in (200, 503), "启动流水线未返回 5xx 崩溃", f"status={status}")
    if status == 503 and isinstance(body, dict):
        log(True, "返回可读提示", str(body.get("detail"))[:70])

    # ---------------- 7. 配置读写 ----------------
    print("\n[7] 配置读写")
    status, _, cfg = http(f"{api}/api/config")
    log(status == 200 and isinstance(cfg, dict), "GET /api/config 返回 200", str(status))
    if status == 200 and isinstance(cfg, dict):
        original = cfg.get("account_name", "")
        probe = f"{original}_verify"
        cfg["account_name"] = probe
        s2, _, _ = http(f"{api}/api/config", method="PUT", body={"config": cfg})
        log(s2 == 200, "PUT /api/config 保存成功", str(s2))
        _, _, back = http(f"{api}/api/config")
        log(isinstance(back, dict) and back.get("account_name") == probe,
            "保存后能读回新值")
        # 还原，避免污染线上配置
        if isinstance(back, dict):
            back["account_name"] = original
            http(f"{api}/api/config", method="PUT", body={"config": back})
            print(f"       已还原 account_name 为「{original}」")

    return summary()


def summary() -> int:
    print("\n" + "=" * 62)
    bad = [n for ok, n, _ in results if not ok]
    total = len(results)
    if bad:
        print(f"结果：{total - len(bad)}/{total} 通过，以下项目未通过：")
        for n in bad:
            print(f"  - {n}")
        print("\n对照《部署手册.md》第 5 节排查。最常见的两个原因：")
        print("  1) Render 的 FRONTEND_URL 没填或带了结尾斜杠 → CORS 失败")
        print("  2) Vercel 改了 NEXT_PUBLIC_API_URL 但没重新 Deploy → 前端仍指向旧地址")
        print("=" * 62)
        return 1
    print(f"结果：{total}/{total} 全部通过，部署成功。")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
