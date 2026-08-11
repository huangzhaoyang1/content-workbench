"""抖音爆款拆解 → 公众号改写。

核心链路：
    抖音链接/文案 → （可选）抓取文案 → DeepSeek 拆解分析（含核心素材清单）
                  → DeepSeek 并行改写三篇（踩坑经历 / 干货总结 / 认知升级）

调用是刻意拆开的：
- 拆解要「像内容运营专家一样分析」，温度低、结构化 JSON，重点是**把原文里的
  案例、数字、金句、逻辑链、工具一条条抠出来**，形成「核心素材清单」；
- 改写要「像扬本人一样写文章」，温度略高、长文本输出，且**必须消费上面那份素材清单**。
一次调用同时干这两件事，长度会互相挤压，改写质量掉得很明显。

三篇改写不是「一篇换三个标题」：每个角度有各自的骨架、各自的主料、
各自的禁区（见 REWRITE_ANGLES），三次调用并行发出，总耗时约等于单篇。

抖音抓文案属于尽力而为：官方页面有反爬，抓不到时抛友好错误，
抓到但明显不完整时也会显式警告，引导用户切到「手动粘贴」。
"""
from __future__ import annotations

import concurrent.futures as _futures
import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ..system.config import DATA_DIR, load_config
from .quality import QUALITY_SELF_CHECK, QUALITY_SPEC, score_article

log = logging.getLogger("workbench.dissect")

# 拆解偏分析、输出短；改写要出整篇文章，给足时间和 token
_DISSECT_TIMEOUT = 150
_REWRITE_TIMEOUT = 300

TOPIC_DB_PATH = DATA_DIR / "topic_library.db"             # 选题库（SQLite）
_TOPIC_VERSION_MAX = 30                                    # 每个选题最多保留的版本数
_DB_LOCK = threading.Lock()                               # 串行化所有 DB 读写，避免并发写损坏

# 选题类型标签白名单（前端按标签上色，不允许模型自由发挥）
TYPE_TAGS = ("反常识", "痛点", "干货", "故事", "经验")


class DissectError(RuntimeError):
    """拆解链路的业务异常，由路由层或统一异常处理器转成 4xx 友好提示。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------------------
# DeepSeek 调用
# ---------------------------------------------------------------------------
def _deepseek_cfg() -> dict:
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


def _api_error(status: int, body: str, cfg: dict) -> str:
    snippet = (body or "")[:300]
    low = snippet.lower()
    if status in (401, 403):
        return f"DeepSeek 鉴权失败（{status}）。请到「系统配置」页检查 DeepSeek API Key 是否正确或已过期。"
    if status == 429:
        return "DeepSeek 调用过于频繁或额度用尽（429），请稍后再试或检查账户余额。"
    if status in (400, 404, 422) and any(
        k in low for k in ("model", "not found", "not exist", "unsupported", "invalid_request")
    ):
        return (
            f"DeepSeek 不支持模型「{cfg['model']}」。"
            "爆款拆解建议用 deepseek-chat，请到「系统配置 → DeepSeek」调整。"
        )
    if status >= 500:
        return f"DeepSeek 服务端异常（{status}），请稍后重试。"
    return f"DeepSeek 调用失败（{status}）：{snippet or '无附加信息'}"


def _chat(
    cfg: dict,
    system: str,
    user: str,
    *,
    temperature: float,
    max_tokens: int,
    timeout: int,
    json_mode: bool = True,
) -> str:
    """调用 DeepSeek chat/completions，返回纯文本内容。"""
    import requests  # 懒加载，与 hotspot.py / vision.py 保持一致

    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except requests.exceptions.Timeout as e:
        raise DissectError(
            f"DeepSeek 处理超时（超过 {timeout} 秒）。文案越长越慢，可以删掉无关部分后重试。"
        ) from e
    except requests.exceptions.RequestException as e:
        raise DissectError(
            f"连不上 DeepSeek（{_host(cfg['base_url'])}）：{type(e).__name__}，"
            "请检查网络和「系统配置」页里的 DeepSeek Key。"
        ) from e

    if r.status_code >= 400:
        raise DissectError(_api_error(r.status_code, r.text, cfg))

    try:
        data = r.json()
    except ValueError as e:
        raise DissectError("DeepSeek 返回的不是合法 JSON 响应，请稍后重试。") from e

    choices = data.get("choices") or []
    if not choices:
        raise DissectError("DeepSeek 没有返回内容，请稍后重试。")
    msg = choices[0].get("message") or {}
    text = msg.get("content")
    if isinstance(text, list):
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    if not text or not str(text).strip():
        raise DissectError("DeepSeek 返回内容为空，请稍后重试。")
    return str(text)


def _extract_json(text: str) -> dict:
    """从模型输出里抠出 JSON 对象，兼容围栏 / 前后废话 / 行尾多余逗号。"""
    s = (text or "").strip()
    if not s:
        raise DissectError("模型没有返回任何内容，请重试。")
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", s, re.S)
    if fence:
        s = fence.group(1).strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start, end = s.find("{"), s.rfind("}")
    if start >= 0 and end > start:
        chunk = s[start : end + 1]
        for candidate in (chunk, re.sub(r",(\s*[}\]])", r"\1", chunk)):
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    log.warning("拆解结果无法解析为 JSON：%s", s[:500])
    raise DissectError("模型返回格式异常（没有按 JSON 输出），换个说法或稍后重试通常就能解决。")


# ---------------------------------------------------------------------------
# 抖音链接 → 文案（尽力而为）
# ---------------------------------------------------------------------------
_UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
_UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_MANUAL_HINT = (
    "抖音对网页抓取限制很严，链接解析经常拿不到完整文案。"
    "建议切到「手动粘贴」页签：在抖音 App 里点视频右下角「…」→「复制链接」旁边的字幕/文案，"
    "或直接把口播内容打出来粘进来，拆解质量反而更高。"
)

# 链接抓取通常只能拿到标题/简介（几十字），拆不出案例和数据。
# 低于这个字数就明确告诉用户「内容不完整」，而不是让他拿着一份空拆解发懵。
_INCOMPLETE_THRESHOLD = 200
_INCOMPLETE_WARN = (
    "⚠️ 抓取到的内容不完整（只拿到 {n} 字，大概率是标题/简介，不是完整口播文案）。"
    "这种情况下拆不出具体案例和数据，改写出来的文章会很空。"
    "强烈建议改用「手动粘贴」：把视频完整文案贴进来重跑一次。"
)


# 结构化字段的中文名：抓不到时逐条告诉用户缺什么，而不是笼统说「抓取失败」
_FIELD_LABELS = {
    "text": "完整口播文案",
    "title": "视频标题",
    "desc": "视频描述",
    "author": "作者昵称",
    "create_time": "发布时间",
    "stats": "点赞/评论/收藏数",
    "duration_sec": "视频时长",
}

_NOISE = ("抖音-记录美好生活", "验证", "你访问的页面", "Verification", "系统繁忙", "抖音短视频")


def extract_url(raw: str) -> str:
    """从抖音分享口令里抠出真正的链接（分享文本里混着大量提示语）。"""
    m = re.search(r"https?://[^\s\u4e00-\u9fff，。！？、）)]+", raw or "")
    return m.group(0).rstrip("/") if m else ""


def _unescape_unicode(s: str) -> str:
    """把页面里 \\uXXXX 形式的转义还原成中文。"""
    try:
        return json.loads(f'"{s}"')
    except Exception:
        return s


def _aweme_id(url: str) -> str:
    """从各种形态的抖音链接里抠出视频 id（短链要先跟随重定向再调用）。"""
    for pat in (
        r"/video/(\d{6,})",
        r"/share/video/(\d{6,})",
        r"/note/(\d{6,})",
        r"[?&]modal_id=(\d{6,})",
        r"[?&]aweme_id=(\d{6,})",
    ):
        m = re.search(pat, url or "")
        if m:
            return m.group(1)
    return ""


def _fmt_ts(ts: Any) -> str:
    """抖音的 create_time 是秒级时间戳，转成人能看懂的字符串。"""
    n = _int(ts)
    if not n:
        return ""
    if n > 10**12:  # 偶尔会给毫秒
        n //= 1000
    if n < 946684800:  # 2000-01-01 之前的一律当脏数据
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(n))
    except Exception:
        return ""


def _dig_item(obj: Any, depth: int = 0) -> dict | None:
    """在任意嵌套 JSON 里递归找出「视频条目」——带 desc 且带统计/作者/id 的那个 dict。"""
    if depth > 10:
        return None
    if isinstance(obj, dict):
        if isinstance(obj.get("desc"), str) and obj.get("desc").strip() and (
            isinstance(obj.get("statistics"), dict)
            or isinstance(obj.get("author"), dict)
            or obj.get("aweme_id")
        ):
            return obj
        for v in obj.values():
            if (hit := _dig_item(v, depth + 1)) is not None:
                return hit
    elif isinstance(obj, list):
        for v in obj[:60]:
            if (hit := _dig_item(v, depth + 1)) is not None:
                return hit
    return None


def _parse_embedded_json(html: str) -> tuple[dict | None, str]:
    """解析页面内嵌的结构化数据，返回 (视频条目, 命中的策略名)。

    抖音前后换过好几种注水方式，这里按可靠性依次尝试，全部失败才回落到正则。
    """
    # 1) 新版分享页：window._ROUTER_DATA = {...}
    for pat in (
        r"window\._ROUTER_DATA\s*=\s*(\{.+?\})\s*;?\s*</script>",
        r"_ROUTER_DATA\s*=\s*(\{.+?\})\s*;\s*\n",
    ):
        m = re.search(pat, html, re.S)
        if m:
            try:
                if (hit := _dig_item(json.loads(m.group(1)))) is not None:
                    return hit, "router_data"
            except Exception:
                pass

    # 2) 老版 SSR：<script id="RENDER_DATA">urlencoded json</script>
    m = re.search(r'id="RENDER_DATA"[^>]*>([^<]+)<', html)
    if m:
        try:
            from urllib.parse import unquote

            if (hit := _dig_item(json.loads(unquote(m.group(1))))) is not None:
                return hit, "render_data"
        except Exception:
            pass

    # 3) 兜底：整页里所有 {...} 块逐个试（只试看起来像 aweme 的）
    for m in re.finditer(r'\{"aweme_?[Ii]d".{200,20000}?\}\s*[,\]\}]', html, re.S):
        chunk = m.group(0).rstrip(",]}")
        try:
            if (hit := _dig_item(json.loads(chunk))) is not None:
                return hit, "inline_json"
        except Exception:
            continue
    return None, ""


def _regex_texts(html: str) -> list[str]:
    """结构化解析全挂时的最后手段：正则扒可读文本。"""
    out: list[str] = []
    for pattern in (
        r'"desc"\s*:\s*"((?:[^"\\]|\\.)*)"',
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
        r"<title[^>]*>(.*?)</title>",
    ):
        for m in re.finditer(pattern, html, re.S | re.I):
            val = re.sub(r"\s+", " ", _unescape_unicode(m.group(1)).strip())
            if val and val not in out:
                out.append(val)
        if out:
            break
    return [c for c in out if len(c) >= 8 and not any(n in c for n in _NOISE)]


def _http_get(url: str, *, mobile: bool = True, timeout: int = 15):
    import requests  # 懒加载

    headers = {
        "User-Agent": _UA_MOBILE if mobile else _UA_DESKTOP,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.douyin.com/",
    }
    return requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)


def fetch_douyin(raw_url: str) -> dict:
    """从抖音链接尽力抓取**结构化**视频信息。

    返回 dict，字段固定，抓不到的给空值并记进 missing，绝不静默编造：
        video_id / title / desc / text / author / create_time / duration_sec
        stats{digg,comment,collect,share} / cover / source_url
        complete / missing / note / strategy

    只有在「一个字都没抓到」时才抛 DissectError，其余情况一律返回部分结果，
    交给用户在前端补齐——这比直接失败有用得多。
    """
    import requests  # 懒加载

    url = extract_url(raw_url)
    if not url:
        raise DissectError("没识别出链接。请粘贴完整的抖音分享链接（含 http），或改用「手动粘贴」。")
    if "douyin.com" not in url and "iesdouyin.com" not in url:
        raise DissectError(f"这不像抖音链接：{url}。目前只支持抖音，其他平台请用「手动粘贴」。")

    try:
        r = _http_get(url)
    except requests.exceptions.Timeout as e:
        raise DissectError(f"抓取抖音页面超时。{_MANUAL_HINT}") from e
    except requests.exceptions.RequestException as e:
        raise DissectError(f"抓取抖音页面失败（{type(e).__name__}）。{_MANUAL_HINT}") from e

    final_url = str(r.url)
    html = r.text or ""
    item, strategy = _parse_embedded_json(html)

    # 短链页面常常只有跳转脚本，拿到 id 后换分享页再试一次
    vid = _aweme_id(final_url) or _aweme_id(url)
    if item is None and vid:
        for alt in (
            f"https://www.iesdouyin.com/share/video/{vid}/",
            f"https://www.douyin.com/video/{vid}",
        ):
            try:
                r2 = _http_get(alt)
            except requests.exceptions.RequestException:
                continue
            item, strategy = _parse_embedded_json(r2.text or "")
            if item is not None:
                html, final_url = r2.text or "", str(r2.url)
                break

    # ---------- 组装结构化结果 ----------
    desc = title = author = create_time = cover = ""
    duration_sec: int | None = None
    stats = {"digg": None, "comment": None, "collect": None, "share": None}

    if item is not None:
        desc = re.sub(r"\s+", " ", _s(item.get("desc"), 4000)).strip()
        vid = _s(item.get("aweme_id"), 40) or vid
        create_time = _fmt_ts(item.get("create_time"))
        if isinstance(item.get("author"), dict):
            author = _s(item["author"].get("nickname"), 60)
        st = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
        stats = {
            "digg": _int(st.get("digg_count")),
            "comment": _int(st.get("comment_count")),
            "collect": _int(st.get("collect_count")),
            "share": _int(st.get("share_count")),
        }
        video = item.get("video") if isinstance(item.get("video"), dict) else {}
        if (ms := _int(video.get("duration"))) :
            duration_sec = round(ms / 1000) if ms > 1000 else ms
        cov = video.get("cover") or video.get("origin_cover") or {}
        if isinstance(cov, dict):
            cover = _s((cov.get("url_list") or [""])[0], 500)

    # 正则兜底补 desc / title
    fallback = _regex_texts(html)
    if not desc and fallback:
        desc = max(fallback, key=len)
        strategy = strategy or "regex"
    if fallback:
        title = fallback[0][:80]
    if not title and desc:
        # 没有独立标题时，用描述第一句当标题
        title = re.split(r"[。！？\n#]", desc)[0][:80] or desc[:80]

    # 去掉描述尾部的话题标签，正文更干净（标签另存）
    hashtags = re.findall(r"#([^\s#]{1,20})", desc)
    text = re.sub(r"#[^\s#]{1,20}", "", desc).strip()

    if not (text or title):
        raise DissectError(
            f"没能从这个链接里读到任何视频信息（抖音返回的是验证页或空页面）。{_MANUAL_HINT}"
        )

    missing = [
        _FIELD_LABELS[k]
        for k, v in (
            ("title", title),
            ("desc", desc),
            ("author", author),
            ("create_time", create_time),
            ("stats", any(v is not None for v in stats.values())),
            ("duration_sec", duration_sec),
        )
        if not v
    ]
    complete = len(text) >= _INCOMPLETE_THRESHOLD
    if not complete:
        missing.insert(0, _FIELD_LABELS["text"])

    note = (
        "已抓到视频描述。抖音网页端不提供口播字幕，如果下面的文案不是完整口播稿，"
        "建议手动补全后再拆解，出来的文章会具体得多。"
        if complete
        else _INCOMPLETE_WARN.format(n=len(text))
    )

    return {
        "video_id": vid,
        "title": title,
        "desc": desc,
        "text": text or title,
        "author": author,
        "create_time": create_time,
        "duration_sec": duration_sec,
        "stats": stats,
        "hashtags": hashtags[:12],
        "cover": cover,
        "source_url": final_url,
        "complete": complete,
        "missing": missing,
        "note": note,
        "strategy": strategy or "regex",
    }


def fetch_douyin_text(raw_url: str) -> dict:
    """兼容旧调用方：只要 {text, title, source_url, complete, note}。"""
    return fetch_douyin(raw_url)


# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------
_DISSECT_SYSTEM = (
    "你是一名做了 8 年短视频和公众号的内容运营专家，尤其擅长拆解知识科普类爆款视频，"
    "并判断哪些要素能迁移到图文平台。\n"
    "你干活分两步，缺一不可：\n"
    "第一步是**素材提取**——像做庭审记录一样，把原文里所有具体案例、具体数字、"
    "原话金句、论证步骤、提到的工具方法，一条条抠出来，逐字引用，不许概括、不许美化、"
    "更不许编造原文没有的东西；原文确实没有的类别就留空数组并说明。\n"
    "第二步才是**分析判断**，而且每一条结论都要能指回第一步抠出来的某条素材。\n"
    "禁止「内容优质」「贴近用户」「引发共鸣」这类换个视频也成立的正确的废话。\n"
    "你只输出 JSON，不输出任何解释、前言或 Markdown 围栏。"
)

_DISSECT_USER = """下面是一条抖音知识科普类视频的文案（口播稿/字幕）。请像给同事做内部复盘一样把它拆透。

严格按以下 JSON 结构输出（只输出 JSON 本身）：
{{
  "basics": {{
    "title": "给这条视频起一个概括性的标题（20 字内）",
    "summary": "用 2-3 句话讲清楚这条视频到底说了什么",
    "duration_sec": 60,
    "word_count": 0,
    "type_tags": ["反常识"],
    "topic": "一句话概括这条视频的选题方向"
  }},
  "materials": {{
    "views": [
      {{"point": "原文抛出的一个具体观点/分论点/核心判断（哪怕是很小的观点也要单列）", "detail": "支撑这个观点的原文依据：可引用的原话，或它出现的位置/上下文"}}
    ],
    "cases": [
      {{"what": "原文里的一个具体案例/故事/真实经历，用原文说法概括", "detail": "这个案例里的关键细节：谁、做了什么、结果如何（尽量引用原话）"}}
    ],
    "numbers": [
      {{"value": "原文出现的具体数字，含单位，如「3 个月」「800 块」「涨了 5 倍」", "context": "这个数字在原文里是用来说明什么的"}}
    ],
    "quotes": ["原文里的金句/反常识断言/爆点句，逐字抄原话，不要改写"],
    "logic_chain": ["论证第 1 步：作者先说了什么", "第 2 步：由此推出什么", "第 3 步：最后落到什么结论"],
    "methods": [
      {{"name": "原文提到的工具/方法/步骤/操作建议名", "usage": "原文里说的具体用法、步骤、参数或操作建议"}}
    ],
    "completeness": {{
      "level": "full",
      "missing": ["这段文案里缺失的素材类型，如：没有任何具体数字"],
      "note": "一句话说明这份素材够不够支撑写一篇有料的公众号文章"
    }}
  }},
  "hook": {{
    "quote": "原文里前 3 秒/前 3 句的原话，直接抄，不要改写",
    "technique": "用到的钩子手法，如：反常识断言 / 痛点提问 / 利益点前置 / 悬念倒叙 / 身份代入",
    "why": "为什么这个钩子能在 3 秒内拦住人，讲清楚心理机制（2-3 句）",
    "score": 8
  }},
  "structure": [
    {{
      "stage": "起",
      "seconds": "0-5s",
      "label": "这一段在干什么（6 字内）",
      "content": "这一段的原文要点",
      "role": "它在整条视频里承担的作用"
    }}
  ],
  "boom": {{
    "core": "一句话说清这条为什么能火",
    "reasons": ["具体原因1（要能对应到文案里的手法）", "具体原因2", "具体原因3"],
    "emotion": "戳中的情绪或爽点，如：认知被刷新 / 焦虑被命名 / 省钱省时间 / 找到同类"
  }},
  "audience": {{
    "who": "主要打动的人群画像，要具体到身份+处境",
    "pain": "这群人当下最真实的痛点",
    "scene": "他们大概在什么场景下刷到并转发这条"
  }},
  "portable": [
    {{"point": "可以直接搬到公众号的东西", "how": "具体怎么搬，落到动作上"}}
  ],
  "migration": {{
    "titles": ["公众号标题备选1", "备选2", "备选3"],
    "opening": "公众号开头应该怎么改才抓得住人（讲清楚改法，不是写好的开头）",
    "expand": ["视频里一带而过、公众号可以展开写的点1", "点2", "点3"],
    "ending": "结尾怎么引导互动/关注，给具体做法"
  }}
}}

【materials 是这次拆解最重要的字段，优先把它做扎实，规则如下】
M0. materials 的五个清单（views 观点 / cases 案例 / numbers 数据 / quotes 金句 / methods 方法）
    是这次拆解最核心的交付物，目标是「信息无损」：原文里出现的观点、案例、数字、金句、方法，
    只要出现了就不要漏。宁可多列几条，也不要替我总结掉。
M1. views / cases / numbers / quotes / methods 里的内容**必须来自原文**，尽量逐字引用。
    宁可少写一条，也不许编造原文没有的东西——编造会直接毒化后续改写。
M2. views 收所有观点：核心观点、分论点、小判断，哪怕是很小的观点也要单列出来，
    不要只列大标题，拆到能单独成句的小观点；detail 写支撑它的原文原话或上下文。
M3. numbers 要把原文里出现的每一个数字都收进来：时间、金额、次数、比例、
    时长、人数、版本号都算。原文一个数字都没有，就返回空数组，
    并在 completeness.missing 里写「全文无任何具体数字」。
M4. quotes 只收「脱离上下文也成立、能单独截图」的句子，3-8 条；
    普通陈述句不要收。禁止改写，逐字抄。
M5. logic_chain 要还原作者的完整论证路径，3-6 步，
    每一步写清楚「说了什么 → 因此推出什么」，不要只列小标题。
M6. methods 收所有被点名的工具、平台、方法论、话术模板、操作步骤、操作建议。
    原文只提名字没说用法，usage 就写「原文未展开」。
M7. completeness.level 只能是 "full"（观点+案例+数字+金句+方法 五类里至少 4 类各有 1 条）、
    "partial"（只抠到 2-3 类）、"thin"（几乎抠不出具体素材，多半只拿到了标题或简介）。
    判断要诚实，thin 就写 thin——我需要据此决定要不要重新粘贴完整文案。

字段要求：
1. type_tags 只能从 ["反常识", "痛点", "干货", "故事", "经验"] 里选，可多选，最多 3 个。
2. duration_sec 按中文口播每分钟约 300 字估算，取整数秒；word_count 填文案实际字数。
3. structure 按「起承转合」的实际段落拆，2-6 段，段数以文案真实结构为准，不要硬凑四段。
   seconds 按字数比例估算，格式如 "0-8s"。
4. hook.score 是 1-10 的钩子强度打分，8 分以上要说得出过硬理由。
5. reasons / expand / portable 每条都要具体到「这条文案里的哪句话、哪个手法」，
   出现「内容有价值」「符合用户需求」这类空话视为不合格。
6. migration.titles 三个标题风格要拉开：一个日记体、一个数字体、一个反差体，都控制在 22 字内。
7. 如果这段文字根本不是视频文案（例如是一段代码、一堆链接或乱码），
   返回 {{"error": "这段内容不像视频文案，请粘贴抖音口播稿或字幕"}}。

视频文案如下：
```
{text}
```

再次强调：只输出 JSON，不要输出 ```json 围栏，不要输出任何解释。"""


# 「扬」的典型文风示例：给改写模型做 few-shot，模仿具体语感和节奏。
# 后续可从历史文章中随机抽取，这里先硬编码三篇好文的代表性片段。
_REWRITE_FEW_SHOT = """【示例1 · 踩坑叙事】
昨天试了一下用 AI 写小红书文案，结果翻车了。
不是 AI 写得不好——是太好了，好到一看就是 AI 写的。
后来我改了个思路：先让 AI 出框架，再自己往里填大白话，效果反而好了。

【示例2 · 干货总结】
搞了两周，终于摸清了 AI 写公众号的套路。
核心就一句话：别让 AI 自由发挥，给它框死结构。
我现在固定用「场景切入→踩坑过程→改法→小结」四段式，每篇省一半时间。

【示例3 · 认知升级】
之前一直觉得学 AI 就是学工具——Prompt 怎么写、Midjourney 怎么画。
上周跟一个做了 3 年自媒体的朋友聊完，才发现方向反了。
工具随时会更新，但「怎么用内容解决一个具体问题」这个能力不会过时。"""

# 账号默认文风（与 _shared_ctx 里的兜底一致），用于判断是否追加自定义 style 补充。
_DEFAULT_STYLE = "真实、有用、可跟；第一人称，像跟朋友聊天"


def _build_few_shot(style: str) -> str:
    """组装 few-shot 示例；若账号配置了非默认的自定义文风，作为补充追加。"""
    few_shot = _REWRITE_FEW_SHOT
    if style and style != _DEFAULT_STYLE:
        few_shot = f"{few_shot}\n\n（再补充一下你的文风设定：{style}）"
    return few_shot


_REWRITE_SYSTEM = """你是「{account}」这个公众号的主理人本人，笔名扬。

你的人设：一个正在用 AI 搞副业的普通人，非技术出身，每天记录真实的学习过程。
你不是专家，也不装专家——你的可信度来自「我真的试过、我真的踩过坑」。

写作铁律：
1. 第一人称「我」，像跟朋友在微信里聊天，可以有口语、有停顿、有自嘲。
2. 不许写「随着人工智能的发展」「在这个时代」这种 AI 腔开场。
3. 不许过度承诺（「月入过万」「轻松躺赚」「一键搞定」这类词直接禁用）。
4. 有观点就明说，不确定就承认不确定，比假装全懂更可信。
5. 每个结论后面必须跟一个具体的场景、数字或动作，读者要能照着做。

以下是你（扬）过去写过的几段文字，感受一下语感和节奏：
{few_shot_examples}

本次你只负责写**一种角度**的文章：{angle_label}。
{angle_persona}

你只输出 JSON，不输出任何解释、前言或 Markdown 围栏。"""


# ---------------------------------------------------------------------------
# 三种改写角度：骨架 / 主料 / 禁区 各不相同，避免「一篇文章换三个标题」
# ---------------------------------------------------------------------------
REWRITE_ANGLES: list[dict[str, str]] = [
    {
        "key": "pitfall",
        "label": "踩坑经历",
        "desc": "第一人称故事，讲一次具体的失败和它的转折",
        "persona": (
            "这一篇你要当一个刚从坑里爬出来的人在讲故事，不是老师。"
            "全程按时间线推进，允许啰嗦、允许自嘲、允许承认当时很蠢。"
        ),
        "skeleton": """【本篇骨架（必须按这个顺序写，不许改成说明书结构）】
1. 开场直接落在一个具体的失败现场：那天几点、我在干什么、哪一步炸了。
   不要总起句，不要背景介绍，第一句话就是场景。
2. 我当时是怎么想的——把那个错误认知原原本本写出来（这是全文最值钱的部分）。
3. 撞墙过程：2-3 个具体节点，每个节点都要有动作 + 结果 + 当时的心理活动。
4. 转折点：是哪一句话/哪一个发现让我意识到搞错了方向。
5. 现在我怎么做：把改法写成 3-5 条，但语气仍然是「我现在都这么干」而不是「你应该」。
6. 结尾对着还在坑里的人说一句话 + 一个开放式提问。""",
        "primary": "cases、numbers、views（案例、数字、观点是主料，必须大量用）",
        "secondary": "quotes 可以穿插引用，methods 只在讲改法时点到",
        "forbidden": (
            "禁止写成分点说明书；禁止一上来给方法论；"
            "禁止出现「三个步骤」「五个方法」这类干货体标题；禁止讲抽象的底层逻辑。"
        ),
        "title_style": "日记体 / 自曝体，带具体时间或数字，例如「我在 XX 上浪费了 3 天，就因为搞错了这一步」",
        "words": "1400-1800",
        "temp": "0.85",
    },
    {
        "key": "howto",
        "label": "干货总结",
        "desc": "方法清单，读者能直接照抄执行",
        "persona": (
            "这一篇你要当一个把流程整理清楚的实操者，句子短、动词多、不抒情。"
            "读者读完应该能立刻打开电脑照着做。"
        ),
        "skeleton": """【本篇骨架（必须按这个顺序写，不许写成故事）】
1. 开篇一句话给结论：这套方法解决什么问题、能省多少时间/多少步。要带数字。
2. 适用前提：什么情况下用得上，什么情况下别用（把不适用的情况也写出来，更可信）。
3. 主体是 3-5 个步骤，每一步固定三小块：
   · 具体做什么（动词开头，能操作）
   · 怎么判断这一步做对了（给一个可观察的标志）
   · 常见错法（大多数人在这一步会怎么做错）
4. 一张自查清单：用无序列表列出 4-6 条，读者可以对着打勾。
5. 结尾给「今天就能做的第一步」，只要一个动作，5 分钟内能完成 + 开放式提问。""",
        "primary": "methods、logic_chain（工具方法和步骤是主料，必须逐条落地）",
        "secondary": "numbers 用来当参数和标准，cases 只能压缩成一句话举例",
        "forbidden": (
            "禁止长篇故事；禁止情绪铺垫；禁止「我那天……」式开场；"
            "禁止讲哲学和认知，只讲怎么做。"
        ),
        "title_style": "数字体 / 清单体，例如「AI 写文案的 5 步流程，我把踩过的坑都标出来了」",
        "words": "1200-1600",
        "temp": "0.7",
    },
    {
        "key": "insight",
        "label": "认知升级",
        "desc": "观点文，拆底层逻辑，给一个新的思考模型",
        "persona": (
            "这一篇你要当一个想明白了某件事、忍不住要跟朋友掰扯清楚的人。"
            "有立场、敢下判断，但每个判断都要给理由，不能只喊口号。"
        ),
        "skeleton": """【本篇骨架（必须按这个顺序写，不许写成教程也不许写成流水账）】
1. 先原样摆出大多数人的默认认知：「大家普遍觉得 X」，写得越具体越好。
2. 指出它哪里错了——这是本篇的反常识核心，必须尖锐、必须给出判断。
3. 底层机制：为什么会形成这个误解？拆到原因层，2-3 层往下追问。
   这一段是全篇密度最高的地方，要有推理链条，不能只给结论。
4. 换一个模型看这件事：给读者一个可以复用的思考框架（起个好记的名字）。
5. 这个认知具体改变了我的哪一个决策——必须落到一件真实的、具体的小事上，带数字。
6. 结尾一句能被记住的话 + 开放式提问。""",
        "primary": "views、quotes、logic_chain（观点/金句/论证链是主料，要把作者的推理往下再推一层）",
        "secondary": "cases 用作论据，numbers 用来给判断加砝码，methods 基本不提",
        "forbidden": (
            "禁止把主体写成操作步骤；禁止流水账叙事；"
            "禁止只抛观点不给理由；禁止和另外两篇共用同一个开头场景。"
        ),
        "title_style": "反差体 / 观点体，例如「大部分人学 AI 的方向从一开始就反了」",
        "words": "1300-1700",
        "temp": "0.8",
    },
]

ANGLE_KEYS = tuple(a["key"] for a in REWRITE_ANGLES)


_REWRITE_USER = """把下面这条抖音爆款视频，改写成一篇发在「{account}」上的公众号文章。

这不是翻译，是**内容迁移**：原视频已经验证过选题能火，你要做的是把它的核心观点和爆点，
用公众号的节奏重新讲一遍，并且补上视频里没空展开的细节。

⚠️ 本次只写一种角度：**{angle_label}**（{angle_desc}）。
同一条视频我会另外用其他角度各写一篇，所以这一篇必须**只做这个角度**，
不许为了完整而把其他角度的内容也塞进来。

【原视频文案】
```
{text}
```

【核心素材清单 —— 这是本次改写的硬性原料，必须用上】
▸ 核心观点（改写时必须在正文里有所体现，尤其 insight 角度）：
{m_views}
▸ 具体案例/故事：
{m_cases}
▸ 具体数字/时间点：
{m_numbers}
▸ 金句/反常识观点：
{m_quotes}
▸ 论证逻辑链：
{m_logic}
▸ 工具/方法/步骤：
{m_methods}
▸ 素材完整度：{m_completeness}

素材使用规则（违反即不合格）：
- 本篇的主料是：{angle_primary}
- 辅料是：{angle_secondary}
- 清单里的**数字必须原样出现在正文里**，一个都不许含糊成「很多」「不少」「大幅」。
- 清单里的案例要展开写成有画面的段落，不能只提一句名字。
- 观点清单里每条核心观点都要在正文里有所体现（用作论点或判断依据），不许整条丢弃不提。
- 方法清单（工具/步骤）若是本篇主料，要逐条落地写进正文，标明怎么做。
- 如果某类素材是空的，不许编造，改为写「我自己准备怎么试」并明确标注这是我的计划。
- 在 materials_used 字段里如实列出你实际用到了清单中的哪几条。

【差异化硬约束】你正在为同一条视频写三个不同角度中的第 {angle_index}/3 篇。
三篇之间必须满足：
  - 开头场景不能相同（如果第一篇用了'学 XX 的时候'，这篇就换'刷到一条消息'或'朋友问我'）
  - 核心案例不能重复（第一篇用了案例 A，这篇用案例 B 或 C）
  - 金句最多共用一句
  - 结尾提问方向不能相同
如果做不到差异化，宁可降低素材使用率，也不要写出跟其他角度雷同的文章。

【已完成的爆款拆解（据此保留爆点）】
- 选题类型：{tags}
- 钩子手法：{hook_tech}｜钩子原话：{hook_quote}
- 爆点核心：{boom_core}
- 目标人群：{audience}
- 可展开的点：{expand}
- 结尾引导建议：{ending}

【账号信息】
- 名称：{account}
- 内容定位：{positioning}
- 文风要求：{style}

{angle_skeleton}

【本篇禁区】
{angle_forbidden}

严格按以下 JSON 结构输出（只输出 JSON 本身）：
{{
  "titles": ["标题备选1", "标题备选2", "标题备选3"],
  "theme": "主题分类，从 [AI工具, AI副业, 学习方法, 行业观察, 个人成长] 里选一个",
  "digest": "公众号摘要，一句话，60 字以内",
  "content": "完整的公众号正文，Markdown 格式",
  "word_count": 0,
  "changes": ["相比原视频做的关键改动1", "改动2", "改动3"],
  "materials_used": ["实际用到的素材清单条目，逐条写清楚用在哪一段"]
}}

【标题要求】
- 三个标题都要贴合本篇角度：{angle_title_style}
- 都控制在 22 字以内，不做标题党，但必须有具体信息量（数字 / 反差 / 场景三选一）。

{quality_spec}

【本篇额外硬指标】
- 全文 {angle_words} 字。
- 开头 2-3 句可以自我介绍式切入（例如「嗨，我是扬。」），但紧接着必须按本篇骨架第 1 步走。
- 不要出现「这条视频」「抖音上」「有位博主」这种暴露搬运痕迹的表述，要写得像你自己的思考。
- content 字段里不要包含文章大标题（标题单独放 titles 里），直接从正文开始。

{quality_check}

再次强调：只输出 JSON，不要输出 ```json 围栏。content 字段里的换行用 \\n 转义。"""


# ---------------------------------------------------------------------------
# 结果归一化
# ---------------------------------------------------------------------------
def _s(val: Any, limit: int = 2000) -> str:
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        val = "；".join(str(v) for v in val)
    return str(val).strip()[:limit]


def _slist(val: Any, limit: int = 12) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        return [val.strip()] if val.strip() else []
    if isinstance(val, (list, tuple)):
        out = [_s(v, 500) for v in val]
        return [o for o in out if o][:limit]
    return []


def _int(val: Any) -> int | None:
    try:
        if isinstance(val, bool):
            return None
        if isinstance(val, (int, float)):
            return int(val)
        digits = re.sub(r"[^\d]", "", str(val))
        return int(digits) if digits else None
    except Exception:
        return None


_COMPLETENESS_LEVELS = ("full", "partial", "thin")


def _pairs(raw: Any, k1: str, k2: str, *, limit: int = 12, l1: int = 300, l2: int = 600) -> list[dict]:
    """把 [{k1, k2}] 或 ["纯字符串"] 统一成 [{k1, k2}]。"""
    out: list[dict] = []
    for item in (raw or [])[:limit]:
        if isinstance(item, dict):
            a, b = _s(item.get(k1), l1), _s(item.get(k2), l2)
        else:
            a, b = _s(item, l1), ""
        if a:
            out.append({k1: a, k2: b})
    return out


def _normalize_materials(raw: Any, raw_text: str) -> dict:
    """核心素材清单归一化，并在模型偷懒时用本地规则兜底判断完整度。"""
    src = raw if isinstance(raw, dict) else {}
    views = _pairs(src.get("views"), "point", "detail", limit=15, l1=300, l2=600)
    cases = _pairs(src.get("cases"), "what", "detail", limit=8)
    numbers = _pairs(src.get("numbers"), "value", "context", limit=20, l1=80, l2=300)
    quotes = _slist(src.get("quotes"), 10)
    logic = _slist(src.get("logic_chain"), 8)
    # methods 替代旧版 tools；模型若仍输出 tools 也兼容
    methods = _pairs(src.get("methods") or src.get("tools"), "name", "usage", limit=12, l1=80, l2=400)

    comp = src.get("completeness") if isinstance(src.get("completeness"), dict) else {}
    level = _s(comp.get("level"), 20).lower()
    missing = _slist(comp.get("missing"), 6)
    note = _s(comp.get("note"), 300)

    # 模型给的 level 不可全信：用实际抠出来的条目数复核一遍，取更保守的那个
    filled = sum(1 for x in (views, cases, numbers, quotes, methods) if x)
    computed = "full" if filled >= 4 else ("partial" if filled >= 2 else "thin")
    if level not in _COMPLETENESS_LEVELS:
        level = computed
    elif _COMPLETENESS_LEVELS.index(computed) > _COMPLETENESS_LEVELS.index(level):
        level = computed  # thin > partial > full，取更差的

    if not missing:
        for name, bucket in (
            ("核心观点", views),
            ("具体案例", cases),
            ("具体数字", numbers),
            ("金句", quotes),
            ("方法步骤", methods),
        ):
            if not bucket:
                missing.append(f"没有抠到{name}")
    if not note:
        note = {
            "full": "素材齐全，足够支撑三篇有细节的文章。",
            "partial": "素材有缺口，改写时部分段落会偏空，建议补充完整口播文案。",
            "thin": "几乎没有可用素材，多半只拿到了标题或简介，强烈建议手动粘贴完整文案后重跑。",
        }[level]

    return {
        "views": views,
        "cases": cases,
        "numbers": numbers,
        "quotes": quotes,
        "logic_chain": logic,
        "methods": methods,
        "completeness": {"level": level, "missing": missing[:6], "note": note},
        "counts": {
            "views": len(views),
            "cases": len(cases),
            "numbers": len(numbers),
            "quotes": len(quotes),
            "logic_chain": len(logic),
            "methods": len(methods),
        },
    }


def _fmt_materials(materials: dict) -> dict[str, str]:
    """把素材清单渲染成喂给改写模型的文本块。"""

    def block(lines: list[str]) -> str:
        return "\n".join(f"  {i}. {ln}" for i, ln in enumerate(lines, 1)) if lines else "  （原文没有，不许编造）"

    return {
        "m_views": block([f"{v['point']}｜依据：{v['detail'] or '原文未展开'}" for v in materials["views"]]),
        "m_cases": block([f"{c['what']}｜细节：{c['detail'] or '原文未展开'}" for c in materials["cases"]]),
        "m_numbers": block([f"{n['value']}｜用来说明：{n['context'] or '原文未说明'}" for n in materials["numbers"]]),
        "m_quotes": block(materials["quotes"]),
        "m_logic": block(materials["logic_chain"]),
        "m_methods": block([f"{t['name']}｜用法：{t['usage'] or '原文未展开'}" for t in materials["methods"]]),
        "m_completeness": (
            f"{materials['completeness']['level']} —— {materials['completeness']['note']}"
        ),
    }


def _normalize_dissect(data: dict, raw_text: str) -> dict:
    if data.get("error"):
        raise DissectError(_s(data["error"], 200))

    basics = data.get("basics") or {}
    hook = data.get("hook") or {}
    boom = data.get("boom") or {}
    audience = data.get("audience") or {}
    migration = data.get("migration") or {}

    tags = [t for t in _slist(basics.get("type_tags"), 3) if t in TYPE_TAGS]
    word_count = _int(basics.get("word_count")) or len(raw_text)
    duration = _int(basics.get("duration_sec")) or max(5, round(word_count / 5))

    structure: list[dict] = []
    for seg in (data.get("structure") or [])[:8]:
        if not isinstance(seg, dict):
            continue
        structure.append(
            {
                "stage": _s(seg.get("stage"), 10) or "段",
                "seconds": _s(seg.get("seconds"), 20),
                "label": _s(seg.get("label"), 30),
                "content": _s(seg.get("content"), 600),
                "role": _s(seg.get("role"), 300),
            }
        )

    portable: list[dict] = []
    for p in (data.get("portable") or [])[:8]:
        if isinstance(p, dict):
            point, how = _s(p.get("point"), 200), _s(p.get("how"), 400)
        else:
            point, how = _s(p, 200), ""
        if point:
            portable.append({"point": point, "how": how})

    score = _int(hook.get("score"))
    return {
        "basics": {
            "title": _s(basics.get("title"), 60) or "未命名视频",
            "summary": _s(basics.get("summary"), 600),
            "topic": _s(basics.get("topic"), 200),
            "duration_sec": duration,
            "word_count": word_count,
            "type_tags": tags or ["干货"],
        },
        "hook": {
            "quote": _s(hook.get("quote"), 400),
            "technique": _s(hook.get("technique"), 100),
            "why": _s(hook.get("why"), 600),
            "score": min(10, max(1, score)) if score else None,
        },
        "structure": structure,
        "boom": {
            "core": _s(boom.get("core"), 300),
            "reasons": _slist(boom.get("reasons"), 6),
            "emotion": _s(boom.get("emotion"), 100),
        },
        "audience": {
            "who": _s(audience.get("who"), 300),
            "pain": _s(audience.get("pain"), 300),
            "scene": _s(audience.get("scene"), 300),
        },
        "portable": portable,
        "migration": {
            "titles": _slist(migration.get("titles"), 3),
            "opening": _s(migration.get("opening"), 600),
            "expand": _slist(migration.get("expand"), 6),
            "ending": _s(migration.get("ending"), 600),
        },
        "materials": _normalize_materials(data.get("materials"), raw_text),
    }


_THEMES = ("AI工具", "AI副业", "学习方法", "行业观察", "个人成长")


def _normalize_rewrite(data: dict, angle: dict | None = None) -> dict:
    content = _s(data.get("content"), 40000)
    if not content:
        raise DissectError("改写结果为空，请重试。文案太短时模型容易放弃，建议补充更完整的口播内容。")
    titles = _slist(data.get("titles"), 3)
    theme = _s(data.get("theme"), 20)
    out = {
        "angle_key": (angle or {}).get("key", ""),
        "angle_label": (angle or {}).get("label", ""),
        "angle_desc": (angle or {}).get("desc", ""),
        "titles": titles or ["（模型没给标题，请手动补一个）"],
        "theme": theme if theme in _THEMES else "AI副业",
        "digest": _s(data.get("digest"), 200),
        "content": content,
        "word_count": _int(data.get("word_count")) or len(content),
        "changes": _slist(data.get("changes"), 6),
        "materials_used": _slist(data.get("materials_used"), 12),
    }
    # 校验 materials_used：声称使用的素材关键词是否真的出现在正文中
    if out.get("materials_used") and out.get("content"):
        content_lower = out["content"].lower()
        verified = []
        for item in out["materials_used"]:
            # 取素材中的关键词（按中文标点/括号/空白切分，并去掉首尾引号，取长度>=2 的词）
            raw_kw = re.split(r"[，。、；：（）\s]+", item)
            keywords = [w.strip().strip("\"'“”‘’（）") for w in raw_kw]
            keywords = [w for w in keywords if len(w) >= 2]
            # 如果素材中至少有一个关键词出现在正文中，视为真实使用
            if keywords and any(kw.lower() in content_lower for kw in keywords[:3]):
                verified.append(item)
            elif not keywords:
                verified.append(item)  # 无法提取关键词的短素材，保留
        out["materials_used"] = verified
    # 本地打分，不额外消耗模型调用
    out["quality"] = score_article(content, titles=out["titles"])
    return out


# ---------------------------------------------------------------------------
# 对外主入口
# ---------------------------------------------------------------------------
_BLANK_STATS = {"digg": None, "comment": None, "collect": None, "share": None}


def blank_source() -> dict[str, Any]:
    """统一的 source 结构：抓不到的字段也保留 key，前端不用到处判空。"""
    return {
        "origin": "manual",
        "url": "",
        "note": "",
        "complete": True,
        "video_id": "",
        "title": "",
        "desc": "",
        "author": "",
        "create_time": "",
        "duration_sec": None,
        "stats": dict(_BLANK_STATS),
        "hashtags": [],
        "cover": "",
        "missing": [],
        "strategy": "manual",
    }


def source_from_fetch(fetched: dict) -> dict[str, Any]:
    """fetch_douyin() 的结果 → source 结构。"""
    src = blank_source()
    stats = fetched.get("stats") if isinstance(fetched.get("stats"), dict) else {}
    src.update(
        {
            "origin": "url",
            "url": fetched.get("source_url") or "",
            "note": fetched.get("note") or "",
            "complete": bool(fetched.get("complete", False)),
            "video_id": fetched.get("video_id") or "",
            "title": fetched.get("title") or "",
            "desc": fetched.get("desc") or "",
            "author": fetched.get("author") or "",
            "create_time": fetched.get("create_time") or "",
            "duration_sec": fetched.get("duration_sec"),
            "stats": {k: stats.get(k) for k in _BLANK_STATS},
            "hashtags": list(fetched.get("hashtags") or [])[:12],
            "cover": fetched.get("cover") or "",
            "missing": list(fetched.get("missing") or [])[:12],
            "strategy": fetched.get("strategy") or "regex",
        }
    )
    return src


def _merge_meta(source: dict[str, Any], meta: Any) -> dict[str, Any]:
    """把前端「抓取预览」阶段拿到的结构化信息合并回来（用户改过文案时仍保留视频元信息）。"""
    if not isinstance(meta, dict):
        return source
    for key in (
        "video_id",
        "title",
        "desc",
        "author",
        "create_time",
        "duration_sec",
        "cover",
        "strategy",
    ):
        val = meta.get(key)
        if val not in (None, "", []):
            source[key] = val
    if isinstance(meta.get("stats"), dict):
        source["stats"] = {k: meta["stats"].get(k) for k in _BLANK_STATS}
    if meta.get("hashtags"):
        source["hashtags"] = list(meta["hashtags"])[:12]
    if meta.get("missing"):
        source["missing"] = list(meta["missing"])[:12]
    if meta.get("url") and not source.get("url"):
        source["url"] = meta["url"]
    return source


def fetch_preview(url: str) -> dict:
    """只抓取不拆解：给前端做「抓取结果预览 / 编辑」用。"""
    if not (url or "").strip():
        raise DissectError("请先填一个抖音分享链接。")
    fetched = fetch_douyin(url)
    source = source_from_fetch(fetched)
    text = fetched.get("text") or ""
    hints: list[str] = []
    if fetched.get("missing"):
        hints.append("没抓到：" + "、".join(fetched["missing"][:6]))
    if len(text) < 200:
        hints.append(
            f"只抓到 {len(text)} 个字，多半是简介而不是完整口播稿。"
            "建议打开视频、开字幕手动复制完整文案后粘贴到下面的框里再拆解。"
        )
    return {
        "text": text,
        "source": source,
        "hints": hints,
        "note": fetched.get("note") or "",
        "complete": bool(fetched.get("complete", False)),
    }


def _shared_ctx(dissect_data: dict, raw: str) -> tuple[str, dict]:
    """组装喂给改写模型的公共上下文（拆解 + 素材 + 账号定位）。"""
    account_cfg = load_config()
    account = account_cfg.get("account_name") or "扬的AI学习日记"
    shared = {
        "account": account,
        "positioning": account_cfg.get("positioning") or "非技术小白跟扬一起学 AI、一起搞副业",
        "style": account_cfg.get("style") or "真实、有用、可跟；第一人称，像跟朋友聊天",
        "text": raw,
        "tags": "、".join(dissect_data["basics"]["type_tags"]),
        "hook_tech": dissect_data["hook"]["technique"] or "（未识别）",
        "hook_quote": dissect_data["hook"]["quote"] or "（未识别）",
        "boom_core": dissect_data["boom"]["core"] or "（未识别）",
        "audience": dissect_data["audience"]["who"] or "（未识别）",
        "expand": "；".join(dissect_data["migration"]["expand"]) or "（无）",
        "ending": dissect_data["migration"]["ending"] or "（无）",
        "quality_spec": QUALITY_SPEC,
        "quality_check": QUALITY_SELF_CHECK,
        **_fmt_materials(dissect_data["materials"]),
    }
    return account, shared


def _rewrite_call(
    cfg: dict,
    account: str,
    shared: dict,
    angle: dict,
    *,
    temp_delta: float = 0.0,
    extra_note: str = "",
) -> dict:
    """按单个角度调一次改写模型。"""
    # 角度序号：pitfall=1, howto=2, insight=3（按 REWRITE_ANGLES 顺序），
    # 用于注入「差异化硬约束」，确保三篇改写之间不雷同。
    angle_index = ANGLE_KEYS.index(angle["key"]) + 1 if angle["key"] in ANGLE_KEYS else 1
    prompt = _REWRITE_USER.format(
        angle_label=angle["label"],
        angle_desc=angle["desc"],
        angle_primary=angle["primary"],
        angle_secondary=angle["secondary"],
        angle_skeleton=angle["skeleton"],
        angle_forbidden=angle["forbidden"],
        angle_title_style=angle["title_style"],
        angle_words=angle["words"],
        angle_index=angle_index,
        **shared,
    )
    if extra_note:
        prompt = f"{prompt}\n\n【额外要求】\n{extra_note}"
    text_out = _chat(
        cfg,
        _REWRITE_SYSTEM.format(
            account=account,
            angle_label=angle["label"],
            angle_persona=angle["persona"],
            few_shot_examples=_build_few_shot(shared.get("style") or ""),
        ),
        prompt,
        temperature=min(1.2, max(0.1, float(angle["temp"]) + temp_delta)),
        max_tokens=8000,
        timeout=_REWRITE_TIMEOUT,
    )
    return _normalize_rewrite(_extract_json(text_out), angle)


def find_angle(angle_key: str) -> dict:
    for a in REWRITE_ANGLES:
        if a["key"] == angle_key:
            return a
    raise DissectError(
        f"没有「{angle_key}」这个改写角度，可选：" + "、".join(a["key"] for a in REWRITE_ANGLES)
    )


_REGEN_NOTE = (
    "这是「重新生成」，上一版已经存在。请换一个切入点重写：换开头钩子、换叙事顺序、"
    "换举例的侧重，标题也要和上一版明显不同。不要只是同义改写，要给出真正不一样的一版。"
)


def rewrite_one(angle_key: str, raw_text: str, dissect_data: Any = None) -> dict:
    """只重新生成某一个角度的文章（复用已有拆解结果，不重复拆解）。"""
    cfg = _deepseek_cfg()
    if not cfg["api_key"]:
        raise DissectError(
            "重新生成需要 DeepSeek 密钥。请到「系统配置 → DeepSeek」填写 API Key 后重试。"
        )
    angle = find_angle(angle_key)
    raw = (raw_text or "").strip()
    if len(raw) < 30:
        raise DissectError("原始文案丢失或过短，无法重新生成。请回到上一步重新拆解。")

    started = time.time()
    data = dissect_data if isinstance(dissect_data, dict) and dissect_data else None
    if data is None:
        data = _normalize_dissect(
            _extract_json(
                _chat(
                    cfg,
                    _DISSECT_SYSTEM,
                    _DISSECT_USER.format(text=raw),
                    temperature=0.3,
                    max_tokens=4000,
                    timeout=_DISSECT_TIMEOUT,
                )
            ),
            raw,
        )
    else:
        data = _normalize_dissect(data, raw)

    account, shared = _shared_ctx(data, raw)
    rewrite = _rewrite_call(
        cfg, account, shared, angle, temp_delta=0.08, extra_note=_REGEN_NOTE
    )
    return {
        "rewrite": rewrite,
        "angle_key": angle_key,
        "model": cfg["model"],
        "elapsed_sec": round(time.time() - started, 1),
    }


def analyze(url: str = "", text: str = "", meta: Any = None) -> dict:
    """拆解 + 改写。返回 {dissect, rewrite, rewrites, source, model, elapsed_sec}。"""
    cfg = _deepseek_cfg()
    if not cfg["api_key"]:
        raise DissectError(
            "爆款拆解需要 DeepSeek 密钥。请到「系统配置 → DeepSeek」填写 API Key 后重试。"
        )

    started = time.time()
    source: dict[str, Any] = blank_source()
    raw = (text or "").strip()

    if not raw:
        if not (url or "").strip():
            raise DissectError("请先粘贴抖音文案，或填一个抖音链接。")
        fetched = fetch_douyin(url)
        raw = fetched["text"]
        source = source_from_fetch(fetched)
    elif (url or "").strip():
        source["url"] = extract_url(url)
        source["complete"] = True
    else:
        source["complete"] = True
    source = _merge_meta(source, meta)

    if len(raw) < 30:
        raise DissectError(
            f"文案只有 {len(raw)} 个字，太短了拆不出东西。请粘贴完整的口播稿或字幕（建议 100 字以上）。"
        )
    # 超长文案截断，避免 token 爆掉；抖音口播极少超过 4000 字
    if len(raw) > 6000:
        raw = raw[:6000]
        source["note"] = (source.get("note") or "") + " 文案超过 6000 字，已截断后半部分。"

    # 第一步：拆解
    dissect_raw = _chat(
        cfg,
        _DISSECT_SYSTEM,
        _DISSECT_USER.format(text=raw),
        temperature=0.3,
        max_tokens=4000,
        timeout=_DISSECT_TIMEOUT,
    )
    dissect = _normalize_dissect(_extract_json(dissect_raw), raw)

    # 素材太薄就提前警告，不让用户拿着一份空拆解发懵
    warnings: list[str] = []
    comp = dissect["materials"]["completeness"]
    if comp["level"] == "thin":
        warnings.append(
            "拆解只抠到极少量具体素材（" + "、".join(comp["missing"][:3]) + "）。"
            "抓取到的内容不完整，建议手动粘贴完整文案后重跑，否则三篇文章都会偏空。"
        )
    elif comp["level"] == "partial":
        warnings.append("素材有缺口：" + "、".join(comp["missing"][:3]) + "，对应段落可能偏空。")
    if source.get("origin") == "url" and not source.get("complete", True):
        warnings.insert(0, source.get("note") or "")

    # 第二步：基于拆解结果 + 核心素材清单，三个角度并行改写
    account, shared = _shared_ctx(dissect, raw)

    def _one(angle: dict) -> dict:
        return _rewrite_call(cfg, account, shared, angle)

    rewrites: list[dict] = []
    errors: list[str] = []
    # 三次调用互不依赖，并行发出：总耗时 ≈ 单篇，而不是三倍
    with _futures.ThreadPoolExecutor(max_workers=len(REWRITE_ANGLES)) as pool:
        futures = {pool.submit(_one, a): a for a in REWRITE_ANGLES}
        done = {}
        for fut in _futures.as_completed(futures):
            angle = futures[fut]
            try:
                done[angle["key"]] = fut.result()
            except DissectError as e:
                errors.append(f"「{angle['label']}」生成失败：{e}")
                log.warning("改写角度 %s 失败：%s", angle["key"], e)
            except Exception as e:  # noqa: BLE001 - 单个角度崩了不该拖垮整次拆解
                errors.append(f"「{angle['label']}」生成异常：{type(e).__name__}")
                log.exception("改写角度 %s 异常", angle["key"])
    # 按 REWRITE_ANGLES 的顺序返回，保证前端 Tab 顺序稳定
    rewrites = [done[a["key"]] for a in REWRITE_ANGLES if a["key"] in done]

    if not rewrites:
        raise DissectError(
            "三个角度全部改写失败。" + ("；".join(errors[:2]) if errors else "请稍后重试。")
        )
    if errors:
        warnings.extend(errors)

    return {
        "dissect": dissect,
        # rewrite 保留为第一篇，兼容老前端 / 老调用方
        "rewrite": rewrites[0],
        "rewrites": rewrites,
        "warnings": [w for w in warnings if w],
        "source": source,
        "model": cfg["model"],
        "elapsed_sec": round(time.time() - started, 1),
        "raw_text": raw,
    }


# ---------------------------------------------------------------------------
# 选题库（SQLite，落盘到 backend/data/topic_library.db）
# ---------------------------------------------------------------------------
TOPIC_CATEGORIES = ("踩坑类", "干货类", "复盘类", "工具类", "其他")
TOPIC_PRIORITIES = ("高", "中", "低")
TOPIC_STATUSES = ("待生产", "生产中", "已完成")

# 从抖音改写角度推断分类，省得每次手选
_ANGLE_CATEGORY = {"pitfall": "踩坑类", "howto": "干货类", "insight": "复盘类"}

_TOPIC_COLS = (
    "id", "title", "content", "theme", "source", "category",
    "priority", "status", "angle_key", "tags", "created_at", "updated_at",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT,
    theme TEXT,
    source TEXT,
    category TEXT,
    priority TEXT,
    status TEXT,
    angle_key TEXT,
    tags TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS topic_trash (
    id TEXT PRIMARY KEY,
    title TEXT,
    content TEXT,
    theme TEXT,
    source TEXT,
    category TEXT,
    priority TEXT,
    status TEXT,
    angle_key TEXT,
    tags TEXT,
    created_at TEXT,
    updated_at TEXT,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS topic_versions (
    topic_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    saved_at TEXT,
    title TEXT,
    content TEXT,
    theme TEXT,
    category TEXT,
    tags TEXT,
    PRIMARY KEY (topic_id, version_id)
);
CREATE INDEX IF NOT EXISTS idx_topics_title ON topics(title);
"""


def _migrate_item(item: dict) -> dict:
    """老数据没有分类/优先级/状态字段，读的时候补默认值，不改盘上的老文件。"""
    cat = _s(item.get("category"), 20)
    pri = _s(item.get("priority"), 10)
    sta = _s(item.get("status"), 20)
    item = dict(item)
    item["category"] = cat if cat in TOPIC_CATEGORIES else "其他"
    item["priority"] = pri if pri in TOPIC_PRIORITIES else "中"
    item["status"] = sta if sta in TOPIC_STATUSES else "待生产"
    item.setdefault("id", uuid.uuid4().hex[:12])
    item.setdefault("updated_at", item.get("created_at", ""))
    raw_tags = item.get("tags")
    if isinstance(raw_tags, list):
        item["tags"] = [_s(str(t), 30) for t in raw_tags if str(t).strip()][:10]
    else:
        item["tags"] = []
    return item


def _db_conn() -> "sqlite3.Connection":
    """开一条连接，顺手确保表结构存在（CREATE TABLE IF NOT EXISTS 幂等）。"""
    conn = sqlite3.connect(TOPIC_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _parse_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _row_to_topic(row: "sqlite3.Row | None") -> "dict | None":
    if row is None:
        return None
    item = {c: row[c] for c in _TOPIC_COLS}
    item["tags"] = _parse_tags(item.get("tags"))
    if "deleted_at" in row:
        item["deleted_at"] = row["deleted_at"]
    return _migrate_item(item)


def _row_to_version(row: "sqlite3.Row") -> dict:
    return {
        "version_id": row["version_id"],
        "saved_at": row["saved_at"],
        "title": row["title"],
        "content": row["content"],
        "theme": row["theme"],
        "category": row["category"],
        "tags": _parse_tags(row["tags"]),
    }


def _insert_topic(conn: "sqlite3.Connection", item: dict) -> None:
    cols = ", ".join(_TOPIC_COLS)
    placeholders = ", ".join("?" for _ in _TOPIC_COLS)
    set_clause = ", ".join(f"{c}=excluded.{c}" for c in _TOPIC_COLS if c != "id")
    values = tuple(
        json.dumps(item["tags"], ensure_ascii=False) if c == "tags" else item.get(c, "")
        for c in _TOPIC_COLS
    )
    conn.execute(
        f"INSERT INTO topics ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {set_clause}",
        values,
    )


def _insert_trash(conn: "sqlite3.Connection", item: dict) -> None:
    cols = list(_TOPIC_COLS) + ["deleted_at"]
    placeholders = ", ".join("?" for _ in cols)
    set_clause = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "id")
    values = tuple(
        json.dumps(item["tags"], ensure_ascii=False) if c == "tags" else item.get(c, "")
        for c in cols
    )
    conn.execute(
        f"INSERT INTO topic_trash ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {set_clause}",
        values,
    )


def _snapshot_version_locked(conn: "sqlite3.Connection", topic_id: str, item: dict) -> None:
    """在已持有连接上给某选题拍快照（最多保留 _TOPIC_VERSION_MAX 条，最新在前）。"""
    if not topic_id:
        return
    rows = conn.execute(
        "SELECT version_id, saved_at, title, content, theme, category, tags "
        "FROM topic_versions WHERE topic_id=?",
        (topic_id,),
    ).fetchall()
    lst = [_row_to_version(r) for r in rows]
    snap = {
        "version_id": uuid.uuid4().hex[:10],
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "title": item.get("title", ""),
        "content": item.get("content", ""),
        "theme": item.get("theme", ""),
        "category": item.get("category", ""),
        "tags": item.get("tags", []),
    }
    lst.insert(0, snap)
    lst = lst[:_TOPIC_VERSION_MAX]
    conn.execute("DELETE FROM topic_versions WHERE topic_id=?", (topic_id,))
    conn.executemany(
        "INSERT INTO topic_versions "
        "(topic_id, version_id, saved_at, title, content, theme, category, tags) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [
            (topic_id, v["version_id"], v["saved_at"], v["title"], v["content"],
             v["theme"], v["category"], json.dumps(v["tags"], ensure_ascii=False))
            for v in lst
        ],
    )


def _snapshot_version(topic_id: str, item: dict) -> None:
    """公开快照接口（自带锁与连接），供模块外调用。"""
    topic_id = _s(topic_id, 40)
    with _DB_LOCK:
        conn = _db_conn()
        try:
            _snapshot_version_locked(conn, topic_id, item)
            conn.commit()
        finally:
            conn.close()


def save_topic(
    title: str,
    content: str = "",
    theme: str = "",
    source: str = "dissect",
    category: str = "",
    priority: str = "",
    status: str = "",
    angle_key: str = "",
    tags: list[str] | None = None,
) -> dict:
    """把改写好的选题存进选题库。同名选题按标题去重（覆盖旧的）。"""
    title = _s(title, 120)
    if not title:
        raise DissectError("选题标题不能为空。")

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    with _DB_LOCK:
        conn = _db_conn()
        try:
            row = conn.execute("SELECT * FROM topics WHERE title=?", (title,)).fetchone()
            old = _row_to_topic(row) if row else None
            if old:
                _snapshot_version_locked(conn, old["id"], old)

            cat = _s(category, 20)
            if cat not in TOPIC_CATEGORIES:
                cat = _ANGLE_CATEGORY.get(angle_key) or (old or {}).get("category") or "其他"
            pri = _s(priority, 10)
            if pri not in TOPIC_PRIORITIES:
                pri = (old or {}).get("priority") or "中"
            sta = _s(status, 20)
            if sta not in TOPIC_STATUSES:
                sta = (old or {}).get("status") or "待生产"
            if tags is None:
                tags = (old or {}).get("tags") or []
            clean_tags = [_s(str(t), 30) for t in tags if str(t).strip()][:10]

            topic_id = (old or {}).get("id") or uuid.uuid4().hex[:12]
            created_at = (old or {}).get("created_at") or now
            item = {
                "id": topic_id,
                "title": title,
                "content": _s(content, 40000),
                "theme": _s(theme, 40) or "AI副业",
                "source": source,
                "category": cat,
                "priority": pri,
                "status": sta,
                "angle_key": _s(angle_key, 20),
                "tags": clean_tags,
                "created_at": created_at,
                "updated_at": now,
            }
            _insert_topic(conn, item)
            total = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
            conn.commit()
        finally:
            conn.close()
    return {"ok": True, "item": item, "total": total}


_PRIORITY_ORDER = {"高": 0, "中": 1, "低": 2}


def list_topics(
    limit: int = 50,
    category: str = "",
    priority: str = "",
    status: str = "",
    keyword: str = "",
    tag: str = "",
) -> dict:
    """按分类/优先级/状态/关键词/标签筛选选题库。高优先级排前面。"""
    with _DB_LOCK:
        conn = _db_conn()
        try:
            rows = conn.execute("SELECT * FROM topics").fetchall()
        finally:
            conn.close()
    all_items = [_row_to_topic(r) for r in rows]
    kw = (keyword or "").strip().lower()
    tag_kw = (tag or "").strip().lower()

    def keep(i: dict) -> bool:
        if category and category != "全部" and i.get("category") != category:
            return False
        if priority and priority != "全部" and i.get("priority") != priority:
            return False
        if status and status != "全部" and i.get("status") != status:
            return False
        if kw and kw not in f"{i.get('title', '')} {i.get('theme', '')}".lower():
            return False
        if tag_kw and tag_kw not in [str(t).lower() for t in i.get("tags", [])]:
            return False
        return True

    items = [i for i in all_items if keep(i)]
    items.sort(key=lambda i: (_PRIORITY_ORDER.get(i.get("priority"), 1), i.get("created_at") or ""))
    return {
        "items": items[: max(1, limit)],   # 去掉了原 200 条上限
        "total": len(all_items),
        "filtered": len(items),
        "facets": {
            "categories": list(TOPIC_CATEGORIES),
            "priorities": list(TOPIC_PRIORITIES),
            "statuses": list(TOPIC_STATUSES),
        },
    }


def list_tags() -> dict:
    """返回选题库里出现过的全部标签（去重、按出现次数降序）。"""
    counts: dict[str, int] = {}
    with _DB_LOCK:
        conn = _db_conn()
        try:
            rows = conn.execute("SELECT tags FROM topics").fetchall()
        finally:
            conn.close()
    for r in rows:
        for t in _parse_tags(r["tags"]):
            t = str(t).strip()
            if t:
                counts[t] = counts.get(t, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"tags": [t for t, _ in ordered]}


def update_topic(topic_id: str, **fields: Any) -> dict:
    """按 id 局部更新选题（标题/正文/分类/优先级/状态/主题/标签）。"""
    topic_id = _s(topic_id, 40)
    with _DB_LOCK:
        conn = _db_conn()
        try:
            row = conn.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
            if row is None:
                raise DissectError("这条选题不存在，可能已经被删掉了，刷新一下再试。", status_code=404)
            item = _row_to_topic(row)
            # 正文被改动时，给当前版本拍快照（版本历史）
            if fields.get("content") is not None:
                _snapshot_version_locked(conn, topic_id, item)
            if (v := _s(fields.get("title"), 120)):
                dup = conn.execute(
                    "SELECT COUNT(*) FROM topics WHERE title=? AND id!=?", (v, topic_id)
                ).fetchone()[0]
                if dup:
                    raise DissectError(f"已经有一条叫「{v}」的选题了，换个标题。")
                item["title"] = v
            if fields.get("content") is not None:
                item["content"] = _s(fields.get("content"), 40000)
            if (v := _s(fields.get("theme"), 40)):
                item["theme"] = v
            for key, whitelist in (
                ("category", TOPIC_CATEGORIES),
                ("priority", TOPIC_PRIORITIES),
                ("status", TOPIC_STATUSES),
            ):
                v = _s(fields.get(key), 20)
                if v:
                    if v not in whitelist:
                        raise DissectError(f"{key} 只能是：{'/'.join(whitelist)}")
                    item[key] = v
            if "tags" in fields:
                raw = fields["tags"]
                if raw is None:
                    item["tags"] = []
                elif isinstance(raw, list):
                    item["tags"] = [_s(str(t), 30) for t in raw if str(t).strip()][:10]
                else:
                    item["tags"] = [_s(str(raw), 30)][:10]

            item["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "UPDATE topics SET title=?, content=?, theme=?, category=?, priority=?, "
                "status=?, angle_key=?, tags=?, updated_at=? WHERE id=?",
                (item["title"], item["content"], item["theme"], item["category"],
                 item["priority"], item["status"], item["angle_key"],
                 json.dumps(item["tags"], ensure_ascii=False), item["updated_at"], topic_id),
            )
            conn.commit()
        finally:
            conn.close()
    return {"ok": True, "item": item}


def delete_topic(topic_id: str) -> dict:
    """删除一条选题 → 移入回收站（可恢复）。"""
    topic_id = _s(topic_id, 40)
    with _DB_LOCK:
        conn = _db_conn()
        try:
            row = conn.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
            if row is None:
                raise DissectError("这条选题不存在，可能已经被删掉了。", status_code=404)
            item = _row_to_topic(row)
            item["deleted_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _insert_trash(conn, item)
            conn.execute("DELETE FROM topics WHERE id=?", (topic_id,))
            total = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
            conn.commit()
        finally:
            conn.close()
    return {"ok": True, "total": total}


def get_topic(topic_id: str) -> "dict | None":
    """按 id 取单条选题（拿去生产 / 批量操作时用）。"""
    topic_id = _s(topic_id, 40)
    with _DB_LOCK:
        conn = _db_conn()
        try:
            row = conn.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
        finally:
            conn.close()
    return _row_to_topic(row) if row else None


def delete_topics(ids: list[str]) -> dict:
    """批量删除选题 → 移入回收站（可恢复），跳过不存在的 id，不抛错。"""
    id_set = {_s(x, 40) for x in (ids or []) if x}
    if not id_set:
        return {"ok": True, "removed": 0, "total": 0}
    placeholders = ", ".join("?" for _ in id_set)
    with _DB_LOCK:
        conn = _db_conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM topics WHERE id IN ({placeholders})", tuple(id_set)
            ).fetchall()
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            removed = 0
            for r in rows:
                item = _row_to_topic(r)
                item["deleted_at"] = now
                _insert_trash(conn, item)
                removed += 1
            if removed:
                conn.execute(f"DELETE FROM topics WHERE id IN ({placeholders})", tuple(id_set))
                conn.commit()
            total = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
        finally:
            conn.close()
    return {"ok": True, "removed": removed, "total": total}


# ---------------------------------------------------------------------------
# 回收站（软删除落盘 topic_library.db 的 topic_trash 表）
# ---------------------------------------------------------------------------
def list_trash() -> dict:
    """返回回收站里的选题（按删除时间倒序）。"""
    with _DB_LOCK:
        conn = _db_conn()
        try:
            rows = conn.execute("SELECT * FROM topic_trash").fetchall()
        finally:
            conn.close()
    items = [_row_to_topic(r) for r in rows]
    items.sort(key=lambda i: i.get("deleted_at") or "", reverse=True)
    return {"items": items, "total": len(items)}


def restore_topic(topic_id: str) -> dict:
    """把回收站里的选题恢复到选题库。"""
    topic_id = _s(topic_id, 40)
    with _DB_LOCK:
        conn = _db_conn()
        try:
            row = conn.execute("SELECT * FROM topic_trash WHERE id=?", (topic_id,)).fetchone()
            if row is None:
                raise DissectError("回收站里找不到这条选题，可能已经被彻底删除了。", status_code=404)
            item = _row_to_topic(row)
            item.pop("deleted_at", None)
            conn.execute("DELETE FROM topic_trash WHERE id=?", (topic_id,))
            _insert_topic(conn, item)
            conn.commit()
        finally:
            conn.close()
    return {"ok": True, "item": item}


def purge_topic(topic_id: str) -> dict:
    """从回收站彻底删除一条选题（不可恢复）。"""
    topic_id = _s(topic_id, 40)
    with _DB_LOCK:
        conn = _db_conn()
        try:
            cur = conn.execute("DELETE FROM topic_trash WHERE id=?", (topic_id,))
            if cur.rowcount == 0:
                raise DissectError("回收站里找不到这条选题。", status_code=404)
            total = conn.execute("SELECT COUNT(*) FROM topic_trash").fetchone()[0]
            conn.commit()
        finally:
            conn.close()
    return {"ok": True, "total": total}


def empty_trash() -> dict:
    """清空回收站，同时清掉这些选题的版本历史。"""
    with _DB_LOCK:
        conn = _db_conn()
        try:
            conn.execute("DELETE FROM topic_trash")
            conn.execute("DELETE FROM topic_versions")
            conn.commit()
        finally:
            conn.close()
    return {"ok": True, "total": 0}


# ---------------------------------------------------------------------------
# 版本历史（按 topic id 归档到 topic_library.db 的 topic_versions 表）
# ---------------------------------------------------------------------------
def list_topic_versions(topic_id: str) -> dict:
    """列出某选题的版本历史（元数据，不含完整正文，前端按需取单条）。"""
    topic_id = _s(topic_id, 40)
    with _DB_LOCK:
        conn = _db_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM topic_versions WHERE topic_id=?", (topic_id,)
            ).fetchall()
        finally:
            conn.close()
    versions = []
    for r in rows:
        v = _row_to_version(r)
        meta = {k: val for k, val in v.items() if k != "content"}
        meta["content_len"] = len(v.get("content") or "")
        versions.append(meta)
    return {"topic_id": topic_id, "versions": versions, "total": len(versions)}


def get_topic_version(topic_id: str, version_id: str) -> "dict | None":
    """取某条历史版本的完整内容。"""
    topic_id = _s(topic_id, 40)
    version_id = _s(version_id, 20)
    with _DB_LOCK:
        conn = _db_conn()
        try:
            row = conn.execute(
                "SELECT * FROM topic_versions WHERE topic_id=? AND version_id=?",
                (topic_id, version_id),
            ).fetchone()
        finally:
            conn.close()
    return _row_to_version(row) if row else None


def restore_topic_version(topic_id: str, version_id: str) -> dict:
    """回退到某个历史版本：update_topic 会先把「当前内容」快照，再写回旧版本，不丢当前。"""
    topic_id = _s(topic_id, 40)
    version_id = _s(version_id, 20)
    snap = get_topic_version(topic_id, version_id)
    if not snap:
        raise DissectError("找不到这个历史版本，可能已被清空。", status_code=404)
    return update_topic(
        topic_id,
        title=snap.get("title", ""),
        content=snap.get("content", ""),
        theme=snap.get("theme", ""),
        category=snap.get("category", ""),
        tags=snap.get("tags", []),
    )
