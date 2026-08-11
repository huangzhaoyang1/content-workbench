"""公众号后台截图识别：调用视觉大模型把截图转成结构化文章数据。

为什么不把模型写死成 deepseek-vl：
- DeepSeek 官方 API（api.deepseek.com）目前只提供 deepseek-chat / deepseek-reasoner，
  没有开放视觉模型；deepseek-vl2 是开源权重，要走第三方托管（硅基流动等）或自建。
- 所以这里按「OpenAI 兼容 chat/completions + 可配置端点」实现：默认复用 deepseek 的
  key / base_url，也可以在配置里给 vision 单独指一个视觉端点。换成 qwen-vl、glm-4v、
  自建 deepseek-vl2 都不用改代码，只改配置。

设计要点：
- 只依赖 requests（懒加载），与 hotspot.py 保持一致，不引入新的重依赖。
- 输入验证前置：大小、扩展名、magic bytes 三重校验，坏图不发给模型白花钱。
- 模型返回的 JSON 可能带 ```json 围栏或前后废话，统一做鲁棒抽取。
- 所有异常收敛成 VisionError，路由层直接把 message 给用户看（都是人话）。
"""
from __future__ import annotations

import base64
import json
import logging
import re

from ..system.config import load_config

log = logging.getLogger("workbench.vision")

# 单张图上限 10MB，和 CSV 上传保持一致
MAX_IMAGE_BYTES = 10 * 1024 * 1024
# 太小的图基本是坏文件或占位图，直接拦掉
MIN_IMAGE_BYTES = 1024

ALLOWED_EXTENSIONS = (".png", ".jpg", ".jpeg")

# (魔数, mime)：只认 PNG / JPEG，避免改后缀绕过校验
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)

_DEFAULT_MODEL = "deepseek-vl2"
_TIMEOUT = 90  # 视觉推理慢，给足时间；超时了给出「裁剪重试」引导
_MAX_ARTICLES = 60  # 单张截图最多接受的条数，防止模型幻觉刷屏


class VisionError(Exception):
    """识别过程中的可预期错误，路由层转成 4xx，message 直接展示给用户。"""


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------
def resolve_config() -> dict:
    """取视觉模型配置：vision 段优先，缺什么就用 deepseek 段兜底。"""
    cfg = load_config()
    ds = cfg.get("deepseek") or {}
    vs = cfg.get("vision") or {}
    base_url = (vs.get("base_url") or "").strip() or (ds.get("base_url") or "").strip()
    api_key = (vs.get("api_key") or "").strip() or (ds.get("api_key") or "").strip()
    model = (vs.get("model") or "").strip() or _DEFAULT_MODEL
    return {
        "base_url": base_url or "https://api.deepseek.com/v1",
        "api_key": api_key,
        "model": model,
        # 是否用的是 vision 段自己的端点（前端提示文案要区分）
        "inherited": not (vs.get("base_url") or "").strip(),
    }


def status() -> dict:
    """给前端的可用性探测结果，不发起真实请求。"""
    c = resolve_config()
    configured = bool(c["api_key"])
    host = _host(c["base_url"])
    hint = ""
    if not configured:
        hint = "还没有配置 API Key。到「配置 → DeepSeek / 视觉模型」填一个支持视觉的模型 Key 就能用。"
    elif "api.deepseek.com" in host:
        hint = (
            "当前视觉端点指向 DeepSeek 官方 API，而官方 API 暂未开放视觉模型，识别会失败。"
            "请在「配置 → DeepSeek / 视觉模型」里把视觉 Base URL 换成支持 VL 的服务"
            "（如硅基流动 https://api.siliconflow.cn/v1 + deepseek-ai/deepseek-vl2）。"
        )
    return {
        "configured": configured,
        "model": c["model"],
        "endpoint": host,
        "inherited": c["inherited"],
        "hint": hint,
    }


def _host(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1) if m else (url or "")


# --------------------------------------------------------------------------
# 输入校验
# --------------------------------------------------------------------------
def validate_image(filename: str, content: bytes) -> str:
    """校验图片并返回 mime；不合法时抛 VisionError（message 已是人话）。"""
    name = (filename or "").strip()
    if not content:
        raise VisionError(f"「{name or '图片'}」是空文件，请重新选择截图。")
    if len(content) < MIN_IMAGE_BYTES:
        raise VisionError(f"「{name or '图片'}」体积过小，可能不是有效截图，请重新上传。")
    if len(content) > MAX_IMAGE_BYTES:
        mb = len(content) / 1024 / 1024
        raise VisionError(
            f"「{name or '图片'}」有 {mb:.1f}MB，超过 10MB 上限。"
            "可以先裁掉截图上下无关区域，或另存为 JPG 再上传。"
        )
    lower = name.lower()
    if lower and not lower.endswith(ALLOWED_EXTENSIONS):
        raise VisionError(f"只支持 png / jpg / jpeg 格式，「{name}」不在其中。")
    for magic, mime in _MAGIC:
        if content.startswith(magic):
            return mime
    raise VisionError(
        f"「{name or '图片'}」不是有效的 PNG / JPEG 图片（文件内容与格式不符），请重新截图后上传。"
    )


# --------------------------------------------------------------------------
# 提示词
# --------------------------------------------------------------------------
_SYSTEM_PROMPT = (
    "你是一个严谨的数据提取助手，专门从微信公众号后台截图中提取运营数据。"
    "你只输出 JSON，不输出任何解释、前言、Markdown 代码围栏或多余文字。"
)

_USER_PROMPT = """请识别这张微信公众号后台截图，把里面的数据提取成 JSON。

严格按以下结构输出（只输出 JSON 本身）：
{
  "articles": [
    {
      "title": "文章标题原文",
      "date": "YYYY-MM-DD",
      "reads": 1234,
      "likes": 12,
      "wow": 8,
      "shares": 20,
      "collects": 5
    }
  ],
  "summary": {
    "followers_delta": 0,
    "new_followers": 0,
    "lost_followers": 0,
    "total_reads": 0,
    "date_range": ""
  },
  "confidence": "high",
  "note": ""
}

字段说明与硬性要求：
1. articles：截图里每一篇文章一条，按截图从上到下的顺序排列。
2. title：抄写标题原文，不要改写、不要翻译、不要补全省略号以外的内容。
3. date：发布日期，统一转成 YYYY-MM-DD。截图里只有「月-日」时，用截图中出现的年份；
   完全没有年份就填 null，不要瞎猜。没有日期列就填 null。
4. reads=阅读量/阅读人数，likes=在看数，wow=点赞数，shares=分享/转发数，collects=收藏数。
5. 数字必须是纯数字（整数），不要带逗号、不要带「次」「人」等单位。
   截图里写「1.2万」要换算成 12000。某个字段截图里没有就填 null，绝对不要编造。
6. summary：只有整体数据/概览类截图才填，followers_delta 是净增关注（可为负数）；
   文章列表截图里没有这些信息就全部填 null。
7. confidence：图片清晰、能确认所有数字填 "high"；部分模糊或有遮挡填 "low"，
   并在 note 里用中文说明哪里看不清。
8. 如果这张图根本不是公众号后台数据截图，返回 {"articles": [], "summary": {}, "confidence": "low", "note": "不是公众号后台数据截图"}。

再次强调：只输出 JSON，不要输出 ```json 围栏，不要输出任何解释。"""


# --------------------------------------------------------------------------
# 调用
# --------------------------------------------------------------------------
def _extract_json(text: str) -> dict:
    """从模型输出里抠出 JSON 对象。兼容围栏、前后废话、单引号等常见脏输出。"""
    s = (text or "").strip()
    if not s:
        raise VisionError("视觉模型没有返回任何内容，请重试。")
    # 去掉 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", s, re.S)
    if fence:
        s = fence.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # 兜底：抓第一个 { 到最后一个 }
    start, end = s.find("{"), s.rfind("}")
    if start >= 0 and end > start:
        chunk = s[start : end + 1]
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            # 再兜底：去掉行尾多余逗号
            cleaned = re.sub(r",(\s*[}\]])", r"\1", chunk)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass
    log.warning("视觉模型返回无法解析的内容：%s", s[:500])
    raise VisionError(
        "识别结果格式异常（模型没有按 JSON 返回）。"
        "换一张更清晰、只包含数据表格区域的截图重试通常就能解决。"
    )


def _call_api(cfg: dict, mime: str, content: bytes) -> str:
    import requests  # 懒加载，和 hotspot.py 保持一致

    b64 = base64.b64encode(content).decode("ascii")
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _USER_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            },
        ],
        "temperature": 0.0,
        "max_tokens": 4000,
        "stream": False,
    }
    try:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=_TIMEOUT,
        )
    except requests.exceptions.Timeout as e:
        raise VisionError(
            f"识别超时（超过 {_TIMEOUT} 秒）。图片过大或服务繁忙，"
            "建议裁剪截图只保留数据区域后重试。"
        ) from e
    except requests.exceptions.RequestException as e:
        raise VisionError(
            f"连不上视觉模型服务（{_host(cfg['base_url'])}）：{type(e).__name__}。"
            "请检查网络和「配置」页里的 Base URL。"
        ) from e

    if r.status_code >= 400:
        raise VisionError(_http_error_message(r.status_code, r.text, cfg))

    try:
        data = r.json()
    except ValueError as e:
        raise VisionError("视觉模型返回的不是合法 JSON 响应，请稍后重试。") from e

    choices = data.get("choices") or []
    if not choices:
        raise VisionError("视觉模型没有返回识别结果，请稍后重试。")
    msg = choices[0].get("message") or {}
    text = msg.get("content")
    if isinstance(text, list):
        # 少数网关会把 content 拆成分段结构
        text = "".join(
            part.get("text", "") for part in text if isinstance(part, dict)
        )
    if not text:
        raise VisionError("视觉模型返回内容为空，请换一张更清晰的截图重试。")
    return str(text)


def _http_error_message(status: int, body: str, cfg: dict) -> str:
    """把上游 HTTP 错误翻译成用户能照着做的一句话。"""
    snippet = (body or "")[:300]
    low = snippet.lower()
    model, host = cfg["model"], _host(cfg["base_url"])

    if status in (401, 403):
        return f"视觉模型鉴权失败（{status}）。请到「配置」页检查 API Key 是否正确、是否已过期。"
    if status == 429:
        return "视觉模型调用过于频繁或额度用尽（429），请稍后再试，或检查服务商的余额。"
    if status in (400, 404, 422) and any(
        k in low for k in ("model", "not found", "not exist", "unsupported", "invalid_request")
    ):
        return (
            f"端点 {host} 不支持模型「{model}」。"
            "注意：DeepSeek 官方 API 暂未开放视觉模型，"
            "请到「配置 → DeepSeek / 视觉模型」把视觉 Base URL 指向支持 VL 的服务，例如："
            "硅基流动 https://api.siliconflow.cn/v1 + deepseek-ai/deepseek-vl2、"
            "阿里云 qwen-vl-max、智谱 glm-4v。"
        )
    if status >= 500:
        return f"视觉模型服务端异常（{status}），这是对方服务的问题，请稍后重试。"
    return f"视觉模型调用失败（{status}）：{snippet or '无附加信息'}"


# --------------------------------------------------------------------------
# 结果归一化
# --------------------------------------------------------------------------
def _clean_number(v) -> float | None:
    """把模型返回的数字字段清洗成非负数值；不可用返回 None。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        s = str(v).strip().replace(",", "").replace("，", "")
        if not s or s.lower() in ("null", "none", "n/a", "-", "—", "无"):
            return None
        mult = 1.0
        if s.endswith(("万", "w", "W")):
            mult, s = 10000.0, s[:-1]
        s = re.sub(r"[^\d.\-]", "", s)
        if not s or s in ("-", ".", "-."):
            return None
        try:
            n = float(s) * mult
        except ValueError:
            return None
    if n < 0:
        return None
    if n > 1e9:  # 明显是幻觉，丢弃比留着更安全
        return None
    return round(n)


def _clean_signed_number(v) -> float | None:
    """净增关注这类允许为负的字段。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        s = str(v).strip().replace(",", "").replace("，", "")
        if not s or s.lower() in ("null", "none", "n/a", "-", "—", "无"):
            return None
        mult = 1.0
        if s.endswith(("万", "w", "W")):
            mult, s = 10000.0, s[:-1]
        s = re.sub(r"[^\d.\-+]", "", s).replace("+", "")
        try:
            n = float(s) * mult
        except ValueError:
            return None
    if abs(n) > 1e9:
        return None
    return round(n)


def _normalize(data: dict) -> dict:
    """把模型原始 JSON 归一化成前端可直接渲染的结构。"""
    from .analytics import to_date  # 复用已有的日期归一化，避免两套逻辑

    raw_articles = data.get("articles")
    if not isinstance(raw_articles, list):
        raw_articles = []

    articles: list[dict] = []
    for item in raw_articles[:_MAX_ARTICLES]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        reads = _clean_number(item.get("reads"))
        likes = _clean_number(item.get("likes"))
        wow = _clean_number(item.get("wow") or item.get("thumbs_up"))
        shares = _clean_number(item.get("shares"))
        collects = _clean_number(item.get("collects") or item.get("favorites"))
        # 只有标题、一个数都没有 → 多半是识别噪声，丢掉
        if reads is None and likes is None and shares is None and wow is None:
            continue
        articles.append(
            {
                "title": title[:200],
                "date": to_date(item.get("date")),
                "reads": reads,
                "likes": likes,
                "wow": wow,
                "shares": shares,
                "collects": collects,
            }
        )

    raw_summary = data.get("summary")
    raw_summary = raw_summary if isinstance(raw_summary, dict) else {}
    summary = {
        "followers_delta": _clean_signed_number(
            raw_summary.get("followers_delta") or raw_summary.get("net_followers")
        ),
        "new_followers": _clean_number(raw_summary.get("new_followers")),
        "lost_followers": _clean_number(raw_summary.get("lost_followers")),
        "total_reads": _clean_number(raw_summary.get("total_reads")),
        "date_range": str(raw_summary.get("date_range") or "").strip()[:60] or None,
    }

    confidence = str(data.get("confidence") or "").strip().lower()
    if confidence not in ("high", "low", "medium"):
        confidence = "high" if articles else "low"
    note = str(data.get("note") or "").strip()[:200]

    return {
        "articles": articles,
        "summary": summary,
        "confidence": confidence,
        "note": note,
    }


def recognize(content: bytes, filename: str = "") -> dict:
    """识别一张截图，返回 {articles, summary, confidence, note, model}。"""
    cfg = resolve_config()
    if not cfg["api_key"]:
        raise VisionError(
            "还没有配置视觉模型的 API Key。请到「配置 → DeepSeek / 视觉模型」"
            "填写一个支持视觉的模型（如硅基流动 deepseek-ai/deepseek-vl2）后再试。"
        )
    mime = validate_image(filename, content)
    text = _call_api(cfg, mime, content)
    result = _normalize(_extract_json(text))

    if not result["articles"]:
        reason = result["note"] or "截图里没有找到可识别的文章数据"
        raise VisionError(
            f"没能从「{filename or '这张图'}」识别出文章数据：{reason}。"
            "请确认上传的是公众号后台「内容分析 / 单篇文章数据」列表截图，"
            "并保证文字清晰、没有被弹窗遮挡。"
        )

    result["model"] = cfg["model"]
    result["filename"] = filename
    return result
