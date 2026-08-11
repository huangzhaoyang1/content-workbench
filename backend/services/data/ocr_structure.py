"""OCR 文字 → 结构化 JSON：本地 OCR 引擎共用的 DeepSeek 整理层。

PaddleOCR / Tesseract 这类本地引擎只负责「认字」，认不出「标题 / 阅读量 / 在看」
这种表头-数值关系。所以统一走两步：

    本地 OCR 出文字（按行、列用 Tab 分隔）→ DeepSeek(deepseek-chat) → 结构化 JSON

这一层被所有本地 OCR 驱动共享，engine 名称参数化，避免每加一种引擎就抄一遍
提示词和错误处理。云端视觉模型（vision.py）是端到端的，不走这里。
"""
from __future__ import annotations

import logging
import re

from ..system.config import load_config
from . import vision
from .ocr_strategy import OcrError

log = logging.getLogger("workbench.ocr_structure")

_TIMEOUT = 90


# --------------------------------------------------------------------------
# 提示词
# --------------------------------------------------------------------------
_STRUCTURE_SYSTEM = (
    "你是一个严谨的数据提取助手，专门把微信公众号后台截图经本地 OCR 提取出的文字，"
    "整理成结构化 JSON。你只输出 JSON，不输出任何解释、前言、Markdown 代码围栏或多余文字。"
)

_STRUCTURE_USER = """下面是一张微信公众号后台截图，经本地 OCR（{engine}）识别出的文字。
文字已按「行」整理，同一行的不同单元格用制表符（Tab）分隔，尽量保留了表格的列结构。

请从中提取结构化数据，严格按以下 JSON 结构输出（只输出 JSON 本身）：
{{
  "articles": [
    {{
      "title": "文章标题原文",
      "date": "YYYY-MM-DD",
      "reads": 1234,
      "likes": 12,
      "wow": 8,
      "shares": 20,
      "collects": 5
    }}
  ],
  "summary": {{
    "followers_delta": 0,
    "new_followers": 0,
    "lost_followers": 0,
    "total_reads": 0,
    "date_range": ""
  }},
  "confidence": "high",
  "note": ""
}}

字段要求：
1. articles：每一篇文章一条，按截图从上到下的顺序排列。
2. title：抄写标题原文，不要改写、不要翻译、不要补全省略号以外的内容。
3. date：发布日期统一转成 YYYY-MM-DD；截图里只有「月-日」时用截图中出现的年份；
   完全没有年份就填 null，不要瞎猜。没有日期列就填 null。
4. reads=阅读量/阅读人数，likes=在看数，wow=点赞数，shares=分享/转发数，collects=收藏数。
5. 数字必须是纯整数，不要带逗号、不要带「次」「人」等单位；
   截图里写「1.2万」要换算成 12000。某个字段截图里没有就填 null，绝对不要编造。
6. summary：只有整体数据/概览类截图才填，followers_delta 是净增关注（可为负数）；
   文章列表截图里没有这些信息就全部填 null。
7. confidence：图片文字清晰、能确认所有数字填 "high"；部分模糊或 OCR 明显错字填 "low"，
   并在 note 里用中文说明哪里看不清。
8. OCR 可能把相似字认错（如「0/O」「1/l」「读/续」），根据上下文合理纠正明显的错别字，
   但数字不要猜，认不准就填 null 并在 note 里说明。
9. 如果这段文字根本不是公众号后台数据，返回 {{"articles": [], "summary": {{}}, "confidence": "low", "note": "不是公众号后台数据"}}。

OCR 文字内容如下：
```
{text}
```

再次强调：只输出 JSON，不要输出 ```json 围栏，不要输出任何解释。"""


# --------------------------------------------------------------------------
# DeepSeek 调用
# --------------------------------------------------------------------------
def deepseek_cfg() -> dict:
    """取 deepseek 段配置（用于把 OCR 文字整理成 JSON）。"""
    cfg = load_config()
    ds = cfg.get("deepseek") or {}
    return {
        "base_url": (ds.get("base_url") or "https://api.deepseek.com/v1").strip(),
        "api_key": (ds.get("api_key") or "").strip(),
        "model": (ds.get("model") or "deepseek-chat").strip(),
    }


def _host(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1) if m else (url or "")


def _call_deepseek(cfg: dict, ocr_text: str, engine: str) -> str:
    import requests  # 懒加载，和 hotspot.py / vision.py 保持一致

    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": _STRUCTURE_SYSTEM},
            {
                "role": "user",
                "content": _STRUCTURE_USER.format(engine=engine, text=ocr_text),
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
        raise OcrError("DeepSeek 整理数据超时（超过 90 秒），请稍后重试。") from e
    except requests.exceptions.RequestException as e:
        raise OcrError(
            f"连不上 DeepSeek（{_host(cfg['base_url'])}）：{type(e).__name__}，"
            "请检查网络和「配置」页里的 DeepSeek Key。"
        ) from e

    if r.status_code >= 400:
        raise OcrError(_deepseek_error(r.status_code, r.text, cfg))

    try:
        data = r.json()
    except ValueError as e:
        raise OcrError("DeepSeek 返回的不是合法 JSON 响应，请稍后重试。") from e

    choices = data.get("choices") or []
    if not choices:
        raise OcrError("DeepSeek 没有返回整理结果，请稍后重试。")
    msg = choices[0].get("message") or {}
    text = msg.get("content")
    if isinstance(text, list):
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    if not text:
        raise OcrError("DeepSeek 返回内容为空，请换一张更清晰的截图重试。")
    return str(text)


def _deepseek_error(status: int, body: str, cfg: dict) -> str:
    snippet = (body or "")[:300]
    low = snippet.lower()
    if status in (401, 403):
        return f"DeepSeek 鉴权失败（{status}）。请到「配置」页检查 DeepSeek API Key 是否正确或已过期。"
    if status == 429:
        return "DeepSeek 调用过于频繁或额度用尽（429），请稍后再试或检查余额。"
    if status in (400, 404, 422) and any(
        k in low for k in ("model", "not found", "not exist", "unsupported", "invalid_request")
    ):
        return (
            f"DeepSeek 不支持模型「{cfg['model']}」。"
            "本地 OCR 的结构化默认用 deepseek-chat，请在「配置 → DeepSeek」里把模型改成 deepseek-chat。"
        )
    if status >= 500:
        return f"DeepSeek 服务端异常（{status}），请稍后重试。"
    return f"DeepSeek 调用失败（{status}）：{snippet or '无附加信息'}"


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def structure(ocr_text: str, filename: str, engine: str) -> dict:
    """把 OCR 出来的文字交给 DeepSeek 整理成 {articles, summary, confidence, note}。

    engine 只用于提示词与结果里的 model 标注（如 "PaddleOCR" / "Tesseract OCR"）。
    """
    cfg = deepseek_cfg()
    if not cfg["api_key"]:
        raise OcrError(
            f"{engine} 已识别出文字，但把文字整理成数据需要 DeepSeek（deepseek-chat）密钥。"
            "请到「配置 → DeepSeek」填写 API Key 后重试；或改用「云端视觉模型」方式。"
        )
    raw = _call_deepseek(cfg, ocr_text, engine)
    # 复用视觉模型的脏 JSON 清洗与字段归一化，避免两套逻辑
    data = vision._extract_json(raw)
    result = vision._normalize(data)
    if not result["articles"]:
        reason = result["note"] or "OCR 文字里没有可识别的文章数据"
        raise OcrError(
            f"没能整理出文章数据：{reason}。"
            "请确认上传的是公众号后台「内容分析 / 单篇文章数据」列表截图，且文字清晰。"
        )
    result["model"] = f"{engine} + {cfg['model']}"
    result["filename"] = filename
    return result
