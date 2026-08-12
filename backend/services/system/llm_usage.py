"""统一的 LLM（DeepSeek / 视觉模型）调用入口与用量记录。

所有聊天补全请求都从这里的 call() 走 requests.post，自动把每次调用的
{time, module, model, prompt_tokens, completion_tokens, cost_est, duration_ms}
追加到 backend/data/llm_usage.jsonl，供 GET /api/analytics/llm-cost 汇总。

设计要点：
- 不替代各调用点自己的「鉴权失败 / 超时 / 模型不支持」等业务错误文案，
  只负责「发请求 + 量时间 + 记用量」，正常返回 requests.Response，异常原样抛出。
- 成本估算是量级参考（合并缓存命中/未命中等复杂计费为单一定价），不是精确账单。
- 记用量失败时绝不拖垮主流程（发文/拆解比记账重要）。
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

from ..system.config import DATA_DIR, load_config

USAGE_PATH = DATA_DIR / "llm_usage.jsonl"
_lock = threading.Lock()  # 多路由并发写同一份 jsonl 时串行化，避免行交错
_MILLION = 1_000_000.0    # 价格单位：元 / 每百万 token


def _price_for(model: str) -> tuple[float, float]:
    """返回 (input_price, output_price)，单位 元/百万token。

    按模型名查配置表 llm_pricing，查不到用 default；配置缺失则退回内置兜底价。
    """
    try:
        pricing = load_config().get("llm_pricing") or {}
    except Exception:
        pricing = {}
    if not pricing:
        return 1.0, 4.0
    spec = pricing.get(model) or pricing.get("default") or {}
    return float(spec.get("input", 1.0)), float(spec.get("output", 4.0))


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _record(
    module: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_est: float,
    duration_ms: float,
) -> None:
    row = {
        "time": _now_iso(),
        "module": module,
        "model": model,
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "cost_est": round(float(cost_est), 6),
        "duration_ms": round(float(duration_ms), 1),
    }
    line = json.dumps(row, ensure_ascii=False)
    try:
        with _lock:
            USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with USAGE_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
    except Exception:
        # 用量记录失败绝不抛异常拖垮主流程
        pass


def call(
    *,
    base_url: str,
    api_key: str,
    module: str,
    payload: dict,
    timeout: int = 60,
):
    """统一的 /chat/completions 调用入口。

    payload 由各调用点按自身业务拼好（model / messages / temperature / ...）。
    本函数只负责：发请求、量耗时、成功后解析 usage 记一笔到 llm_usage.jsonl。
    返回 requests.Response，调用方继续做「状态码判断 + 取 content」等原有逻辑。
    超时 / 网络异常原样抛出，由调用方的 except 分支处理（文案不变）。

    注意：仅在 HTTP < 400 的成功响应里记用量——错误响应 DeepSeek 不返回 usage。
    """
    model = (payload.get("model") or "unknown").strip() or "unknown"
    url = (base_url or "").rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    t0 = time.perf_counter()
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    duration_ms = (time.perf_counter() - t0) * 1000.0

    if r.status_code < 400:
        try:
            data = r.json()
            usage = data.get("usage") or {}
            pt = int(usage.get("prompt_tokens") or 0)
            ct = int(usage.get("completion_tokens") or 0)
            input_p, output_p = _price_for(model)
            cost = (pt * input_p + ct * output_p) / _MILLION
            _record(module, model, pt, ct, cost, duration_ms)
        except Exception:
            # 解析 usage 失败也不影响主流程
            pass
    return r
