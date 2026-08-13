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
from ..system.llm_usage import call as llm_call
from .quality import QUALITY_SELF_CHECK, QUALITY_SPEC, score_article
from .validate import validate_dissect

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

    def __init__(
        self, message: str, status_code: int = 400, error_key: str | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        # error_key 用来让前端/上层做「分类引导」：
        #   grab_antibot  → 抓到验证页/空页面/被反爬拦截，应自动转写兜底
        #   invalid_url   → 链接本身非法（不要尝试转写）
        self.error_key = error_key


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
    import requests  # 懒加载，与 hotspot.py / vision.py 保持一致（异常类型仍在此用到）

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
        r = llm_call(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            module="dissect",
            payload=payload,
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
# 但「不完整提示阈值」是**时长感知**的——短视频简介就能覆盖全部内容，
# 长视频简介却只有完整口播的 1/10。我们用视频时长（秒）×3.5（中文口播约 3-4 字/秒）
# 估算应有字数，再取 20% 作为阈值。这样：
#   - 30 秒短视频   expected≈105 → threshold=max(300,21)=300；200字简介达标（合理）
#   - 15 分钟视频   expected≈3150 → threshold=630；简介 188 字会触发转写（符合本轮修复目标）
# 看不到 duration_sec（极端情况）时退回保守值 300。
_INCOMPLETE_RATIO = 0.2
_INCOMPLETE_MIN_CHARS = 300


def _expected_chars(duration_sec) -> int:
    """根据视频时长估算「应有口播稿字数」。中文口播按 3.5 字/秒。"""
    if duration_sec and duration_sec > 0:
        return int(duration_sec * 3.5)
    return 0


def _incomplete_threshold_chars(duration_sec) -> int:
    """简介不完整的触发阈值：expected * 0.2 但不少于 300。"""
    exp = _expected_chars(duration_sec)
    if exp <= 0:
        return _INCOMPLETE_MIN_CHARS
    return max(_INCOMPLETE_MIN_CHARS, int(exp * _INCOMPLETE_RATIO))


def _should_trigger_transcribe(text: str, duration_sec=None) -> bool:
    """是否要自动触发视频转写：抓到的文字明显少于应有口播稿字数时返回 True。

    适用场景：抖音链接抓取通常只返回视频简介（几十~几百字），长视频那点简介
    完全没法拆出案例和数据，触发 Whisper 自动转写给出完整口播稿。
    """
    n = len((text or "").strip())
    return n < _incomplete_threshold_chars(duration_sec)


def _is_incomplete_fetch(text: str, duration_sec=None) -> bool:
    """抓到的文案是否看起来不像完整口播稿（只是简介）。

    阈值比触发转写略宽——字数 < expected * 0.4 时就该给「内容不完整」警告。
    """
    n = len((text or "").strip())
    exp = _expected_chars(duration_sec)
    if exp <= 0:
        # 拿不到时长退保守：< 1000 字就算不完整
        return n < 1000
    return n < int(exp * 0.4)


_INCOMPLETE_WARN = (
    "⚠️ 抓取到的内容不完整（只拿到 {n} 字，预期约 {exp} 字）。"
    "这种情况下拆不出具体案例和数据，改写出来的文章会很空。"
    "建议让系统自动转写视频，或改用「手动粘贴」：把视频完整文案贴进来重跑一次。"
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
    """从抖音分享口令里抠出真正的链接（分享文本里混着大量提示语）。

    抖音 App 复制出来的分享口令格式：
        "4.38 复制打开抖音，看看【...】让我... https://v.douyin.com/oN45lt7e5bk/04/20 oDH:/e"
    其中真正可用的 URL 只有 "https://v.douyin.com/oN45lt7e5bk/"，
    后面的 "/04/20 oDH:/e" 是抖音分享跟踪码，必须剥掉。

    优先级：
      1. 抖音短链 v/www/m.douyin.com/<short_id>（排除带 /video/ /share/ 等长链路径）
      2. 抖音长链 www.douyin.com/video/<digits>
      3. iesdouyin 分享页 ...iesdouyin.com/share/video/<digits>
      4. 兜底：任意 URL（可能含多余路径，给 yt-dlp 自动 follow redirect 兜住）
    """
    s = (raw or "").strip()
    patterns = (
        # 短链：排除 /video/ /share/ /note/ /user/ 等长链关键词，否则 pattern 1
        # 会把 "https://www.douyin.com/video/<digits>" 的 "video" 当成短链 ID 抠错。
        r"https?://[a-zA-Z]+\.douyin\.com/(?!video/|share/|note/|user/)[A-Za-z0-9_-]+",
        r"https?://www\.douyin\.com/video/\d+",
        r"https?://[a-zA-Z]*iesdouyin\.com/share/video/\d+",
    )
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            return m.group(0)
    # 兜底：任何 http(s) URL（遇到空白/中文/中文标点停）
    m = re.search(r"https?://[^\s\u4e00-\u9fff，。！？、）)]+", s)
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


def _load_netscape_cookies(path: str) -> dict:
    """从 Netscape cookies.txt 里读出 {name: value} dict（requests.cookies 用）。

    抖音对未登录请求直接拒，必须带 cookie；user 可以把浏览器导出的
    Netscape cookies.txt 放到 ASR_DOUYIN_COOKIES 路径下，本函数会自动读取。

    格式（Netscape HTTP Cookie File 标准）：
        domain  flag  path  secure  expires  name  value
    行首 `#` 是注释（但 `# Netscape HTTP Cookie File` / `#HttpOnly_` 是元数据，要保留 #HttpOnly_）。
    """
    import http.cookiejar

    jar = http.cookiejar.MozillaCookieJar(path)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:  # noqa: BLE001
        log.warning("[dissect] 读取 cookie 文件失败 (%s): %s", path, e)
        return {}
    return {c.name: c.value for c in jar}


def _http_get(url: str, *, mobile: bool = True, timeout: int = 15):
    import os
    import requests
    import urllib3  # 懒加载
    from ..data.douyin_cookie import (
        parse_cookie_header_for_requests,
        resolve_douyin_cookie,
    )

    headers = {
        "User-Agent": _UA_MOBILE if mobile else _UA_DESKTOP,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.douyin.com/",
    }
    # 抖音抓取的实战坑：v.douyin.com → iesdouyin.com → www.douyin.com 三跳重定向里，
    # 经常出现证书链不匹配 / 中间代理替换证书，导致 SSLError。我们只抓公开视频页内容，
    # 不带任何用户凭据，业界抖音/TikTok 抓取一律 verify=False；只在本进程内静默警告。
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # 带 cookie：抖音对未登录的抓取直接返回验证页/空 HTML。
    # 双路径（统一交给 .data.douyin_cookie 探测）：
    #   ①AI内容工作台.bat 注入的 Netscape cookies.txt (env ASR_DOUYIN_COOKIES)
    #   ②前端「抖音同步」页「抖音登录 Cookie」输入框 → douyin_sync.json 字符串
    cookies: dict[str, str] = {}
    ck = resolve_douyin_cookie()
    mode = ck.get("mode")
    if mode == "header":
        cookies = parse_cookie_header_for_requests(ck.get("header_value") or "")
        if cookies:
            log.info("[dissect] 已加载 %d 条 douyin cookies（src=%s, len=%d）",
                     len(cookies), ck.get("name"), ck.get("length", 0))
    elif mode == "cookiefile":
        cookies = _load_netscape_cookies(ck.get("cookiefile") or "")
        if cookies:
            log.info("[dissect] 已加载 %d 条 douyin cookies（src=%s, file=%s）",
                     len(cookies), ck.get("name"), ck.get("cookiefile"))

    return requests.get(
        url,
        headers=headers,
        cookies=cookies or None,
        timeout=timeout,
        allow_redirects=True,
        verify=False,
    )


def _ytdlp_extract_douyin(raw_url: str) -> dict | None:
    """首选：让 yt-dlp 解析抖音视频页元数据。

    为什么用 yt-dlp：现代抖音视频页是 SPA，HTML 拉下来只是个空 `<body>` + JS，
    真实视频数据（标题/作者/时长/点赞/封面…）是通过 XHR + `_VIDEO_PAGE_RENDER_DATA_`
    注入的。我们自己的 requests+_parse_embedded_json 对短链（v.douyin.com）基本
    无解——短链会先重定向到首页或被反爬拦截，根本拿不到视频页 HTML。

    yt-dlp 的内置 Douyin extractor 处理了所有这些坑：跟随短链重定向、解析 SPA
    注入的 JSON、应用 cookie 解封登录态墙、提取标准化字段。已在沙箱用用户
    ASR_DOUYIN_COOKIES 实测：直链 https://www.douyin.com/video/7669733815660596507
    + cookie → 标题/作者/时长 921s/点赞 34050/封面 全部能拿到。

    返回值（命中时）：
        {
          "video_id", "title", "desc", "author", "create_time",
          "duration_sec", "cover", "stats": {digg, comment, share, play},
          "strategy": "ytdlp",
        }
    字段抓不到的填 "" 或 None。

    返回 None 的情况（不抛异常，调用方继续走 requests+regex 兜底）：
        - douyin cookie 未配置（yt-dlp 对 douyin 必须带 cookie）
        - 任何 yt-dlp 解析失败（短链失效、视频私密、反爬、网络错误等）
    """
    from ..data.douyin_cookie import (
        header_to_netscape_file,
        resolve_douyin_cookie,
    )

    ck = resolve_douyin_cookie()
    mode = ck.get("mode")
    if not mode:
        log.debug("[dissect] 未配置 douyin cookie，跳过 yt-dlp 路径")
        return None

    try:
        import yt_dlp  # 懒加载；只有触发 yt-dlp 路径时才要
    except Exception as e:  # noqa: BLE001
        log.warning("[dissect] yt-dlp 未安装/不可用：%s", e)
        return None

    # 与 services/data/transcribe.py 的 _ytdl_common_opts 保持一致；
    # 抖音需要 Referer 才能拿到视频页，否则会被反爬截到首页。
    # ⚠ 不直接用 --add-header "Cookie: ..."：yt-dlp deprecated + 抖音对这种请求
    # 高频判 Fresh cookies；统一先把 cookie 字符串写 Netscape 临时文件再 cookiefile。
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "extract_flat": False,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
        },
    }
    if mode == "header":
        try:
            ck_path = header_to_netscape_file(ck.get("header_value") or "")
            ydl_opts["cookiefile"] = ck_path
            log.info("[dissect] cookie via netscape tmpfile=%s (src=%s, len=%d)",
                     ck_path, ck.get("name"), ck.get("length", 0))
        except Exception as e:  # noqa: BLE001
            log.warning("[dissect] cookie 字符串转 Netscape 文件失败：%s", e)
            return None
    else:  # cookiefile
        ydl_opts["cookiefile"] = ck.get("cookiefile") or ""
        log.info("[dissect] cookie via cookiefile=%s (src=%s)",
                 ydl_opts["cookiefile"], ck.get("name"))

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(raw_url, download=False)
    except Exception as e:  # noqa: BLE001
        # 抖音典型的几种 yt-dlp 错误：
        #   - "[Douyin] xxx: Fresh cookies (not necessarily logged in) are needed"
        #     → cookie 过期，用户需要重新导出
        #   - "Unsupported URL: https://www.douyin.com/" → 短链失效/被反爬重定向到首页
        #   - 网络层错误
        # 这些都不在本函数抛，让调用方走兜底 + 把错误上抛给前端
        msg = str(e)[:240]
        log.info("[dissect] yt-dlp 解析失败：%s", msg)
        return {"_error": msg}

    if not isinstance(info, dict):
        return None

    # yt-dlp Douyin extractor 的字段映射（实测过）
    # title=视频标题；description=完整描述/口播文案（注意：抖音网页版 description
    # 是公开页面上的视频简介，不一定是口播完整稿）；uploader/nickname=作者昵称；
    # uploader_id=作者 sec_uid；duration=秒；like_count=点赞；comment_count=评论；
    # view_count=播放；upload_date='YYYYMMDD'；thumbnail=封面 URL；id=aweme_id。
    duration = info.get("duration")
    if isinstance(duration, (tuple, list)):
        duration = duration[0] if duration else None

    def _first_str(*keys):
        for k in keys:
            v = info.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    def _int_or_none(k):
        v = info.get(k)
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "video_id": str(info.get("id") or ""),
        "title": _first_str("title"),
        "desc": _first_str("description"),
        "author": _first_str("uploader", "channel", "creator"),
        "create_time": _fmt_upload_date(info.get("upload_date")),
        "duration_sec": int(duration) if duration else None,
        "cover": _first_str("thumbnail"),
        "stats": {
            "digg": _int_or_none("like_count"),
            "comment": _int_or_none("comment_count"),
            "collect": None,  # 抖音收藏 yt-dlp extractor 没有直接字段，跳过
            "share": _int_or_none("share_count") or _int_or_none("repost_count"),
            "play": _int_or_none("view_count"),
        },
        "strategy": "ytdlp",
    }


def _fmt_upload_date(s):
    """yt-dlp upload_date 形如 '20240813'，转 ISO/年月日。"""
    if not s or not isinstance(s, str) or len(s) != 8 or not s.isdigit():
        return ""
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def _assemble_result(*, url: str, title: str, desc: str, author: str,
                    create_time: str, duration_sec, cover: str, stats: dict,
                    video_id: str, strategy: str) -> dict:
    """yt-dlp 路径命中后用它把字段映射成 fetch_douyin 的标准输出 schema。

    字段语义与下方 item 装配路径完全一致（missing / complete / note / text 计算也一致），
    只是不再依赖 _parse_embedded_json 抓到的抖音原生 dict。
    """
    hashtags = re.findall(r"#([^\s#]{1,20})", desc)
    text = re.sub(r"#[^\s#]{1,20}", "", desc).strip() or title

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
    complete = not _is_incomplete_fetch(text, duration_sec)
    if not complete:
        missing.insert(0, _FIELD_LABELS["text"])

    note = (
        "已抓到视频描述。抖音网页端不提供口播字幕，如果下面的文案不是完整口播稿，"
        "建议手动补全后再拆解，出来的文章会具体得多。"
        if complete
        else _INCOMPLETE_WARN.format(
            n=len(text),
            exp=_expected_chars(duration_sec) or len(text) * 5,
        )
    )

    return {
        "video_id": video_id,
        "title": title,
        "desc": desc,
        "text": text,
        "author": author,
        "create_time": create_time,
        "duration_sec": duration_sec,
        "stats": stats,
        "hashtags": hashtags[:12],
        "cover": cover,
        "source_url": url,
        "complete": complete,
        "missing": missing,
        "note": note,
        "strategy": strategy,
    }


def fetch_douyin(raw_url: str) -> dict:
    """从抖音链接尽力抓取**结构化**视频信息。

    返回 dict，字段固定，抓不到的给空值并记进 missing，绝不静默编造：
        video_id / title / desc / text / author / create_time / duration_sec
        stats{digg,comment,collect,share} / cover / source_url
        complete / missing / note / strategy

    三层抓取路径：
      1. yt-dlp（首选）：自带 Douyin extractor，对 SPA / 短链 / cookie 三连击做过全套处理
         —— 我们实测光这一条就能拿到标题/作者/时长/点赞/封面全字段。
      2. requests + _parse_embedded_json（兜底）：自己拼 UA/Referer/cookie 直拉 HTML，
         找 `_VIDEO_PAGE_RENDER_DATA_` 注入的 JSON。
      3. requests + regex（最后兜底）：用 meta description + 标题标签凑出基础字段。

    只有在「一个字都没抓到」时才抛 DissectError，其余情况一律返回部分结果，
    交给用户在前端补齐——这比直接失败有用得多。
    """
    import requests  # 懒加载

    url = extract_url(raw_url)
    if not url:
        raise DissectError(
            "没识别出链接。请粘贴完整的抖音分享链接（含 http），或改用「手动粘贴」。",
            error_key="invalid_url",
        )
    if "douyin.com" not in url and "iesdouyin.com" not in url:
        raise DissectError(
            f"这不像抖音链接：{url}。目前只支持抖音，其他平台请用「手动粘贴」。",
            error_key="invalid_url",
        )

    # ============ 路径 1: yt-dlp ============
    ytdlp_meta = _ytdlp_extract_douyin(url)
    if ytdlp_meta and ytdlp_meta.get("title"):
        # yt-dlp 命中：title 必有，video_id 也必有（都拿到说明视频确存在）
        yt_err = ytdlp_meta.pop("_error", None)
        log.info("[dissect] yt-dlp 路径命中：title=%r, id=%s", ytdlp_meta.get("title"), ytdlp_meta.get("video_id"))
        return _assemble_result(
            url=url,
            title=ytdlp_meta["title"],
            desc=ytdlp_meta["desc"],
            author=ytdlp_meta["author"],
            create_time=ytdlp_meta["create_time"],
            duration_sec=ytdlp_meta["duration_sec"],
            cover=ytdlp_meta["cover"],
            stats=ytdlp_meta["stats"],
            video_id=ytdlp_meta["video_id"],
            strategy="ytdlp",
        )
    elif ytdlp_meta and ytdlp_meta.get("_error"):
        # yt-dlp 尝试过但报错（cookie 过期/短链失效等）—— 仍走兜底路径，但
        # 兜底也基本会失败，最后抛友好错里附上 yt-dlp 的原始错误便于排查
        log.info("[dissect] yt-dlp 路径失败：%s", ytdlp_meta["_error"])
        yt_dlp_err = ytdlp_meta["_error"]
    else:
        # yt-dlp 不可用（未装/未配 cookies）—— 静默走兜底
        yt_dlp_err = None

    # ============ 路径 2: requests + _parse_embedded_json ============
    try:
        r = _http_get(url)
    except requests.exceptions.Timeout as e:
        raise DissectError(f"抓取抖音页面超时。{_MANUAL_HINT}") from e
    except requests.exceptions.SSLError as e:
        # 历史：在 requests 默认 verify=True 下，抖音重定向链经常出现证书不匹配。
        # 我们在 _http_get 里已经全局 verify=False；如果还走到这里说明是更深的网络问题。
        raise DissectError(
            f"抓取抖音页面失败（SSL 握手错误）。可能是公司/网络代理拦截了抖音，"
            f"或抖音对该 IP 段做了限制。建议切到「手动粘贴」。{_MANUAL_HINT}"
        ) from e
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

    # ============ 路径 3: regex (在 item 为 None 时最后兜底) ============
    # 如果 item 拿到了，直接走装配；否则用 regex 从 meta description 抠出基础字段。
    # 但若整个 HTML 没 _VIDEO_PAGE_RENDER_DATA_ 且短链 final_url 是首页（无 /video/），
    # 说明这八成是个**失效短链 / 被反爬重定向到首页**——这种情况下不要把首页 meta
    # desc 当视频文案，**直接报错**（用 yt-dlp 的原始错误给用户更具体的指引）。
    if item is None:
        looks_like_homepage = (
            vid is None
            and ("/video/" not in final_url)
            and "iesdouyin" not in final_url
        )
        if looks_like_homepage:
            extra = ""
            if yt_dlp_err:
                if "Fresh cookies" in yt_dlp_err:
                    extra = "（cookie 已过期，请重新导出 douyin.com 的 cookies 覆盖旧的，再重启 .bat）"
                elif "Unsupported URL" in yt_dlp_err:
                    extra = "（短链已失效/被反爬，建议换一个视频，或用抖音 App「复制完整链接」拿到长链再试）"
                else:
                    extra = f"（{yt_dlp_err}）"
            raise DissectError(
                f"没能从这个链接里读到视频信息。{extra or _MANUAL_HINT}",
                error_key="grab_antibot",
            )

    # ---------- 组装结构化结果（item 优先，regex 兜底） ----------
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
            f"没能从这个链接里读到任何视频信息（抖音返回的是验证页或空页面）。{_MANUAL_HINT}",
            error_key="grab_antibot",
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
    complete = not _is_incomplete_fetch(text, duration_sec)
    if not complete:
        missing.insert(0, _FIELD_LABELS["text"])

    note = (
        "已抓到视频描述。抖音网页端不提供口播字幕，如果下面的文案不是完整口播稿，"
        "建议手动补全后再拆解，出来的文章会具体得多。"
        if complete
        else _INCOMPLETE_WARN.format(
            n=len(text),
            exp=_expected_chars(duration_sec) or len(text) * 5,
        )
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


def transcribe_video_url(url: str) -> dict:
    """拆解流程的「视频转写」兜底：把抖音链接转写成完整口播稿。

    这是三层兜底里的第 2 层（第 1 层是页面文本，第 3 层是手动粘贴）。
    实际转写由 services/data/transcribe.py 完成（yt-dlp + whisper，CPU 模式）。

    返回 {ok, text, duration_sec, engine, model, error?, error_key?}。
    失败 / 超时都返回 ok=False + 中文原因，前端据此引导用户手动粘贴。
    """
    from ..data.transcribe import transcribe_video

    # 用户可能把整段抖音分享口令粘进来（含标题/话题/"复制此链接..."等噪声），
    # 先用 extract_url 抠出真正的 URL；找不到再报错，避免把整坨塞给 yt-dlp。
    cleaned = extract_url((url or "").strip())
    if not cleaned:
        return {
            "ok": False,
            "text": "",
            "duration_sec": None,
            "engine": "whisper",
            "error": "没识别出链接。请粘贴完整的抖音分享链接（含 http），或改用「手动粘贴」。",
            "error_key": "invalid_url",
        }
    if "douyin.com" not in cleaned and "iesdouyin.com" not in cleaned:
        return {
            "ok": False,
            "text": "",
            "duration_sec": None,
            "engine": "whisper",
            "error": f"这不像抖音链接：{cleaned}。目前只支持抖音，其他平台请用「手动粘贴」。",
            "error_key": "invalid_url",
        }
    return transcribe_video(cleaned)


# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------
from ..prompts import load_dissect, load_dissect_angles, load_dissect_default_style

_DSECT = load_dissect()
_DISSECT_SYSTEM = _DSECT["_DISSECT_SYSTEM"]
_DISSECT_USER = _DSECT["_DISSECT_USER"]
_REWRITE_FEW_SHOT = _DSECT["_REWRITE_FEW_SHOT"]
_DEFAULT_STYLE = load_dissect_default_style()



def _build_few_shot(style: str) -> str:
    """组装 few-shot 示例；若账号配置了非默认的自定义文风，作为补充追加。"""
    few_shot = _REWRITE_FEW_SHOT
    if style and style != _DEFAULT_STYLE:
        few_shot = f"{few_shot}\n\n（再补充一下你的文风设定：{style}）"
    return few_shot


_REWRITE_SYSTEM = _DSECT["_REWRITE_SYSTEM"]
REWRITE_ANGLES = load_dissect_angles()
ANGLE_KEYS = tuple(a["key"] for a in REWRITE_ANGLES)
_REWRITE_USER = _DSECT["_REWRITE_USER"]



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
    # 前端把「视频转写」结果标成 transcribe，这里要能透传进最终 source，
    # 拆解结果徽章才能正确显示「素材来源=视频转写」。
    if meta.get("origin") in ("url", "manual", "transcribe"):
        source["origin"] = meta["origin"]
    return source


def fetch_preview(url: str) -> dict:
    """只抓取不拆解：给前端做「抓取结果预览 / 编辑」用。

    抓取被反爬拦截（验证页/空页面）时，不直接报失败，而是返回一个
    ``needs_transcribe=True`` 的信号，由前端自动触发「视频转写」兜底
    （避免 /fetch 接口被 40 分钟的转写任务阻塞）。
    """
    if not (url or "").strip():
        raise DissectError("请先填一个抖音分享链接。")
    try:
        fetched = fetch_douyin(url)
    except DissectError as e:
        key = getattr(e, "error_key", None)
        # 链接本身非法（没识别出 / 不是抖音链接）：转写也处理不了，直接报错，不兜底。
        if key == "invalid_url":
            raise
        # 其它抓取失败（反爬验证页 / 空页面 / 网络被拦 / 超时 等）：
        # 自动转写兜底由前端触发（不阻塞 /fetch 接口），转写成功即用完整口播稿，
        # 失败才引导手动粘贴。
        return {
            "text": "",
            "source": None,
            "hints": [
                "抓取失败（抖音反爬拦截或网络不通）。已自动改用「视频转写」"
                "把视频音频转成完整口播稿（约 5–30 分钟）。"
            ],
            "note": "",
            "complete": False,
            "duration_sec": None,
            "video_id": "",
            "needs_transcribe": True,
            "transcribe_error": str(e),
        }
    source = source_from_fetch(fetched)
    text = fetched.get("text") or ""
    duration_sec = fetched.get("duration_sec")
    hints: list[str] = []
    if fetched.get("missing"):
        hints.append("没抓到：" + "、".join(fetched["missing"][:6]))
    if _is_incomplete_fetch(text, duration_sec):
        exp = _expected_chars(duration_sec)
        hints.append(
            _INCOMPLETE_WARN.format(
                n=len(text),
                exp=exp if exp > 0 else len(text) * 5,  # 退化给个直观倍数
            )
        )
    if _should_trigger_transcribe(text, duration_sec):
        exp = _expected_chars(duration_sec)
        mins = max(5, (exp // 3)) // 60 or 5
        hint = (
            f"文字 {len(text)} 字，远少于预期口播稿（{exp} 字）。"
            "系统会自动尝试把视频音频转写成完整口播稿（约 5–30 分钟，CPU 模式）；"
            "若转写失败，你也可以打开抖音开字幕，把完整口播稿手动粘贴进来。"
        )
        hints.append(hint)
    return {
        "text": text,
        "source": source,
        "hints": hints,
        "note": fetched.get("note") or "",
        "complete": bool(fetched.get("complete", False)),
        # 给前端用于时长感知 trigger 判定
        "duration_sec": duration_sec,
        "video_id": fetched.get("video_id") or "",
    }


def _shared_ctx(dissect_data: dict, raw: str) -> tuple[str, dict]:
    """组装喂给改写模型的公共上下文（拆解 + 素材 + 账号定位）。"""
    account_cfg = load_config()
    account = account_cfg.get("account_name") or "扬的AI学习日记"
    shared = {
        "account": account,
        "positioning": account_cfg.get("positioning") or "非技术小白跟扬一起学 AI、一起搞副业",
        "style": account_cfg.get("style") or load_dissect_default_style(),
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


def analyze(url: str = "", text: str = "", meta: Any = None, context: str = "") -> dict:
    """拆解 + 改写。返回 {dissect, rewrite, rewrites, source, model, elapsed_sec}。

    context 为可选的「历史对话上下文」文本（由调用方从记忆里取好再传进来），
    非空时拼到拆解 prompt 前面，让本次拆解延续之前的背景与偏好。
    """
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
    user_prompt = _DISSECT_USER.format(text=raw)
    if context and context.strip():
        user_prompt = (
            "以下是与用户的近期对话记录，用于理解背景与偏好，拆解时请延续上下文：\n"
            f"{context}\n\n"
            "———— 以上是历史上下文 ————\n\n"
            f"{user_prompt}"
        )
    dissect_raw = _chat(
        cfg,
        _DISSECT_SYSTEM,
        user_prompt,
        temperature=0.3,
        max_tokens=4000,
        timeout=_DISSECT_TIMEOUT,
    )
    # 结构硬校验（M 项）：LLM 输出解析为 dict 后、归一化前先过校验。
    # 失败则把校验错误作为补充提示回灌模型重试 1 次；重试仍失败走现有错误路径。
    parsed = _extract_json(dissect_raw)
    ok, verrs = validate_dissect(parsed)
    if not ok:
        retry_user = (
            user_prompt
            + "\n\n【重要】上一轮输出未通过结构校验，请严格按下方字段要求重新输出 JSON：\n"
            + "\n".join(f"- {e}" for e in verrs[:8])
        )
        dissect_raw = _chat(
            cfg,
            _DISSECT_SYSTEM,
            retry_user,
            temperature=0.3,
            max_tokens=4000,
            timeout=_DISSECT_TIMEOUT,
        )
        parsed = _extract_json(dissect_raw)
        ok, verrs = validate_dissect(parsed)
        if not ok:
            raise DissectError("拆解结果结构校验未通过：" + "；".join(verrs[:6]))
    dissect = _normalize_dissect(parsed, raw)

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
