"""后端接口冒烟测试。

用法（在 content-workbench 根目录）：
    python smoke_test.py              # 只跑不花钱的接口
    python smoke_test.py --paid       # 额外真实调用 SerpAPI / DeepSeek 校验 Key

覆盖：健康检查、配置读写、CORS、热点额度、队列增删、定时任务增删改、
历史任务、数据分析、错误码边界。所有写操作都会自还原，不会留下脏数据，
也不会触发烧钱的流水线执行（/api/queue/start、/api/pipeline/start 真跑）。
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"

_passed = 0
_failed: list[str] = []


def req(method: str, path: str, body=None, headers=None, timeout=90):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        r.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {}), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200], dict(e.headers)
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}", {}


def check(label: str, cond: bool, extra: str = "") -> None:
    global _passed
    if cond:
        _passed += 1
        print(f"  OK  {label}{(' | ' + extra) if extra else ''}")
    else:
        _failed.append(label)
        print(f"  !!  {label}{(' | ' + extra) if extra else ''}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paid", action="store_true", help="额外真实调用 SerpAPI/DeepSeek")
    args = ap.parse_args()

    print("\n[1] 健康检查与配置")
    s, h, _ = req("GET", "/api/health")
    check("GET /api/health", s == 200, f"version={h.get('version') if isinstance(h, dict) else h}")
    s, cfg, _ = req("GET", "/api/config")
    check("GET /api/config", s == 200)
    if not isinstance(cfg, dict):
        print("配置读取失败，后续用例无法继续")
        return 1
    check("SerpAPI Key 已配置", bool(cfg.get("search_api", {}).get("api_key")))
    check("DeepSeek Key 已配置", bool(cfg.get("deepseek", {}).get("api_key")))
    check("project_root 已配置", bool(cfg.get("project_root")), cfg.get("project_root", ""))

    print("\n[2] 配置写入（写入 -> 还原）")
    orig = cfg.get("account_name")
    cfg["account_name"] = f"{orig}_SMOKE"
    s, saved, _ = req("PUT", "/api/config", {"config": cfg})
    check("PUT /api/config 写入", s == 200 and isinstance(saved, dict)
          and saved.get("account_name") == f"{orig}_SMOKE")
    cfg["account_name"] = orig
    s, back, _ = req("PUT", "/api/config", {"config": cfg})
    check("PUT /api/config 还原", s == 200 and isinstance(back, dict)
          and back.get("account_name") == orig)
    check("还原后 Key 未丢失", isinstance(back, dict)
          and bool(back.get("search_api", {}).get("api_key"))
          and bool(back.get("deepseek", {}).get("api_key")))

    print("\n[3] CORS（前端端口可能顺延到 3001/3002）")
    for origin in ("http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3002"):
        _, _, hdr = req("GET", "/api/health", headers={"Origin": origin})
        allow = hdr.get("access-control-allow-origin") or hdr.get("Access-Control-Allow-Origin")
        check(f"允许来源 {origin}", allow == origin, f"allow-origin={allow}")

    print("\n[4] 搜索额度")
    s, q, _ = req("GET", "/api/hotspot/quota")
    check("GET /api/hotspot/quota", s == 200,
          f"{q.get('used')}/{q.get('limit')} 剩余 {q.get('remaining')}" if isinstance(q, dict) else str(q))

    print("\n[5] 任务队列（新增 -> 批量 -> 删除，自还原）")
    s, q0, _ = req("GET", "/api/queue")
    n0 = len(q0.get("items") or []) if isinstance(q0, dict) else -1
    check("GET /api/queue", s == 200, f"现有 {n0} 条")
    s, one, _ = req("POST", "/api/queue/add", {"topic": "__smoke__", "source": "manual"})
    ids = [i["id"] for i in one.get("items", [])] if isinstance(one, dict) else []
    check("POST /api/queue/add 单条", s == 200 and len(ids) == 1)
    s, many, _ = req("POST", "/api/queue/add",
                     {"items": [{"topic": "__smokeA__"}, {"topic": "__smokeB__"}], "source": "topic"})
    if isinstance(many, dict):
        ids += [i["id"] for i in many.get("items", [])]
    check("POST /api/queue/add 批量", s == 200 and isinstance(many, dict) and many.get("added") == 2)
    s, _, _ = req("POST", "/api/queue/add", {"topic": "   "})
    check("空主题应 422", s == 422, f"实际 {s}")
    for i in ids:
        req("DELETE", f"/api/queue/{i}")
    s, q1, _ = req("GET", "/api/queue")
    n1 = len(q1.get("items") or []) if isinstance(q1, dict) else -2
    check("队列已还原", n1 == n0, f"{n0} -> {n1}")

    print("\n[6] 定时任务（每日/每周 next_run 计算）")
    s, job, _ = req("POST", "/api/schedule",
                    {"name": "__smoke__", "topic": "冒烟", "frequency": "daily",
                     "time": "23:59", "enabled": True})
    jid = job.get("id") if isinstance(job, dict) else None
    check("POST /api/schedule", s == 200 and bool(jid),
          f"next_run={job.get('next_run') if isinstance(job, dict) else ''}")
    if jid:
        s, off, _ = req("PUT", f"/api/schedule/{jid}", {"enabled": False})
        check("禁用后 next_run 置空", s == 200 and isinstance(off, dict) and off.get("next_run") is None)
        s, wk, _ = req("PUT", f"/api/schedule/{jid}",
                       {"enabled": True, "frequency": "weekly", "weekday": 2, "time": "08:30"})
        check("改为每周任务", s == 200 and isinstance(wk, dict) and bool(wk.get("next_run")),
              f"next_run={wk.get('next_run') if isinstance(wk, dict) else ''}")
        s, _, _ = req("DELETE", f"/api/schedule/{jid}")
        check("DELETE /api/schedule/{id}", s == 200)
    s, _, _ = req("POST", "/api/schedule", {"name": "x", "frequency": "cron", "cron": "乱写的"})
    check("非法 cron 应 422", s == 422, f"实际 {s}")

    print("\n[7] 历史任务")
    s, lst, _ = req("GET", "/api/tasks?page=1&page_size=5")
    cnt = len(lst.get("tasks") or []) if isinstance(lst, dict) else -1
    check("GET /api/tasks", s == 200 and cnt > 0,
          f"返回 {cnt} 条 / 共 {lst.get('total_filtered') if isinstance(lst, dict) else '?'} 条")
    if isinstance(lst, dict) and lst.get("tasks"):
        issue = lst["tasks"][0]["issue"]
        s, d, _ = req("GET", f"/api/tasks/{issue}")
        check(f"GET /api/tasks/{issue}", s == 200 and isinstance(d, dict) and bool(d.get("title")))
    s, _, _ = req("GET", "/api/tasks/99999")
    check("不存在的期号应 404", s == 404)

    print("\n[8] 数据分析")
    s, ds, _ = req("POST", "/api/analytics/sample")
    did = ds.get("dataset_id") if isinstance(ds, dict) else None
    check("POST /api/analytics/sample", s == 200 and bool(did))
    s, an, _ = req("POST", "/api/analytics/analyze", {"dataset_id": did, "time_range": "全部"})
    check("POST /api/analytics/analyze", s == 200 and isinstance(an, dict) and bool(an.get("mapping")))
    s, sg, _ = req("GET", f"/api/analytics/suggestions?dataset_id={did}")
    check("GET /api/analytics/suggestions", s == 200,
          f"{len(sg.get('suggestions') or []) if isinstance(sg, dict) else '?'} 条建议")

    print("\n[9] 错误码边界")
    s, _, _ = req("POST", "/api/pipeline/start", {"topic": ""})
    check("空 topic 启动流水线应 422", s == 422, f"实际 {s}")
    s, _, _ = req("GET", "/api/pipeline/status/notexist")
    check("查不存在任务应 404", s == 404, f"实际 {s}")

    if args.paid:
        print("\n[10] 真实第三方调用（会计费）")
        s, t, _ = req("POST", "/api/config/test",
                      {"search_api": cfg.get("search_api", {}), "deepseek": cfg.get("deepseek", {})})
        check("POST /api/config/test", s == 200)
        if isinstance(t, dict):
            check("SerpAPI 连通", bool(t.get("serpapi", {}).get("ok")), t.get("serpapi", {}).get("message", ""))
            check("DeepSeek 连通", bool(t.get("deepseek", {}).get("ok")), t.get("deepseek", {}).get("message", ""))
        s, tp, _ = req("POST", "/api/topic/generate", {
            "hotspots": [{"title": "AI 副业实操", "snippet": "用智能体承接内容外包",
                          "link": "https://example.com"}],
            "data_insight": "", "data_suggestions": [],
        }, timeout=120)
        tops = tp.get("topics") or [] if isinstance(tp, dict) else []
        check("POST /api/topic/generate", s == 200 and len(tops) > 0, f"生成 {len(tops)} 条")
        s, hs, _ = req("POST", "/api/hotspot/search",
                       {"keywords": ["AI 副业"], "time_range": "近7天", "limit": 5}, timeout=120)
        check("POST /api/hotspot/search", s == 200,
              f"origin={hs.get('origin') if isinstance(hs, dict) else hs}")

    total = _passed + len(_failed)
    print(f"\n{'=' * 52}")
    print(f"通过 {_passed}/{total}")
    if _failed:
        print("失败用例：")
        for f in _failed:
            print("  -", f)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
