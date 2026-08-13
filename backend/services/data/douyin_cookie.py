"""抖音 / TikTok 登录 Cookie 解析与传递（转写 + 拆解共用）。

解决「cookie 全链路打通」的核心问题：
    前端 /douyin-sync 页 → backend/data/douyin_sync.json 的 config.cookie（字符串）
                          ↓
                  本模块：统一读取 + 格式探测
                          ↓
            ┌─────────────┴─────────────┐
    [字符串格式]                    [Netscape 文件格式]
    Cookie 头（k1=v1; k2=v2; …）   ASR_DOUYIN_COOKIES 指向的 .txt
            │                              │
            ▼                              ▼
    yt-dlp --add-header "Cookie:…"    yt-dlp cookiefile=<path>

优先级（与已有 ASR_DOUYIN_COOKIES 兼容，旧部署不需要改）：
  1. douyin_sync.json 里的 config.cookie（用户从 UI 粘贴的浏览器 Cookie 头）
  2. 环境变量 ASR_DOUYIN_COOKIES 指向的 Netscape cookies 文件（.bat 注入）

cookie 同时只读一遍，结构化后给 yt-dlp / requests 用。
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from ..system.config import DATA_DIR

log = logging.getLogger("workbench.douyin_cookie")

_DOUYIN_SYNC_PATH = DATA_DIR / "douyin_sync.json"

# 浏览器 Cookie 头里常见的强特征串；命中其一即可高置信判定「这是 Cookie 头字符串」
# 而不是 Netscape 行。Netscape 的字段分隔是 tab，并且只有 7 列。
_COOKIE_HEADER_HINT = ("=", ";")
_NETSCOOKIE_FIELD_COUNT = 7  # domain flag path secure expires name value


def _is_cookie_header_string(raw: str) -> bool:
    """粗判字符串更接近浏览器 Cookie 头 而不是 Netscape cookies.txt 行。

    Netscape 一行：domain<TAB>flag<TAB>path<TAB>secure<TAB>expires<TAB>name<TAB>value
    Cookie 头  ：name1=value1; name2=value2; name3=value3
    """
    s = raw.strip()
    if not s:
        return False
    if "\n" in s or "\r" in s:
        # 多行几乎一定是 Netscape 文件
        return False
    if ";" in s and "=" in s:
        return True
    if s.count("=") == 1 and " " not in s and "\t" not in s:
        # 单条 name=value 形如 "ttwid=xxx"，算 Cookie 头
        return True
    return False


def _read_douyin_sync_cookie() -> str:
    """从 douyin_sync.json 读出 config.cookie 字符串；缺失/损坏返回空。"""
    try:
        with open(_DOUYIN_SYNC_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return ""
    except Exception as e:  # noqa: BLE001
        log.warning("[douyin_cookie] 读 douyin_sync.json 失败：%s", e)
        return ""
    cfg = (data or {}).get("config") or {}
    ck = (cfg.get("cookie") or "").strip()
    return ck


def _read_env_cookie_file() -> str:
    """读环境变量 ASR_DOUYIN_COOKIES 对应的 Netscape 文件路径；文件不存在返回空。"""
    path = os.environ.get("ASR_DOUYIN_COOKIES", "").strip()
    if not path or not os.path.isfile(path):
        return ""
    return path


# 已编译正则：解析 Cookie 头里的 name=value 对，忽略空白/引号
_COOKIE_KV_RE = re.compile(r"([^=;\s]+)\s*=\s*(\"[^\"]*\"|[^;]+)")


def _parse_cookie_header(header: str) -> dict[str, str]:
    """把浏览器 Cookie 头字符串解析成 {name: value} dict。

    - 容忍 `name=value`、`name="value with,comma"`、`name=value; name2=v2`。
    - 不做 URL 解码，留给后端/yt-dlp 自己处理（yt-dlp 也不解码）。
    - value 含多余引号的会保留；空值会被丢弃。
    """
    out: dict[str, str] = {}
    for m in _COOKIE_KV_RE.finditer(header or ""):
        name = m.group(1).strip()
        val = m.group(2).strip()
        if val.startswith('"') and val.endswith('"') and len(val) >= 2:
            val = val[1:-1]
        if name and val:
            out[name] = val
    return out


def resolve_douyin_cookie() -> dict[str, Any]:
    """解析出抖音 cookie 的最终表现形态，给 yt-dlp / requests 直接用。

    返回示例：
        {"mode": "header", "header_value": "k1=v1; k2=v2", "name": "douyin_sync", "length": 432}
        {"mode": "cookiefile", "cookiefile": "C:/.../cookies.txt", "name": "env_file", "length": 0}
        {"mode": None, "name": None, "length": 0}

    调用方按 mode 决定怎么传给 yt-dlp：
        mode == "header"     → opts["http_headers"]["Cookie"] = info["header_value"]
        mode == "cookiefile" → opts["cookiefile"] = info["cookiefile"]

    想看「字符串长度」做日志时用 length，避免明文泄露。
    """
    # 优先级 1：UI 粘的 Cookie 头字符串
    sync_ck = _read_douyin_sync_cookie()
    if sync_ck:
        if _is_cookie_header_string(sync_ck):
            return {
                "mode": "header",
                "header_value": sync_ck,
                "name": "douyin_sync",
                "length": len(sync_ck),
            }
        # 看起来不像 Cookie 头（可能是整段文件内容 / 错误粘贴），继续尝试文件
        log.warning(
            "[douyin_cookie] douyin_sync.json 里的 cookie 字段不像 Cookie 头字符串（len=%d），"
            "尝试当文件路径",
            len(sync_ck),
        )
        if os.path.isfile(sync_ck):
            return {
                "mode": "cookiefile",
                "cookiefile": sync_ck,
                "name": "douyin_sync_path",
                "length": 0,
            }

    # 优先级 2：env 注入的 Netscape 文件（.bat / 老部署都走这）
    env_path = _read_env_cookie_file()
    if env_path:
        return {
            "mode": "cookiefile",
            "cookiefile": env_path,
            "name": "env_file",
            "length": 0,
        }

    return {"mode": None, "name": None, "length": 0}


def parse_cookie_header_for_requests(header: str) -> dict[str, str]:
    """公开给 requests.cookies 用：把浏览器 Cookie 头字符串解成 {name: value}。"""
    return _parse_cookie_header(header)


def header_to_netscape_file(header: str, *, domain: str = ".douyin.com") -> str:
    """把浏览器 Cookie 头字符串写成 Netscape cookies.txt 临时文件，返回路径。

    为什么要这条路径而不是直接 --add-header：
      yt-dlp 把 ``http_headers["Cookie"]`` 标为 deprecated（upstream 会发警告 + 部分风控
      站点拿到后直接判该请求无登录态），对抖音来说高频返回 "Fresh cookies are needed"。
      稳定做法是把 Cookie 头解析成 Netscape 格式 → ``yt_dlp`` 用 ``cookiefile`` 字段。
      本函数在 temp 目录写一个 .txt，调用方用 ``opts["cookiefile"] = 返回路径``。
    """
    import tempfile

    pairs = _parse_cookie_header(header)
    if not pairs:
        raise ValueError("Cookie 头解析为空，至少需要 1 条 name=value")
    # Netscape 一行字段：domain<TAB>flag<TAB>path<TAB>secure<TAB>expires<TAB>name<TAB>value
    lines = [
        "# Netscape HTTP Cookie File",
        "# Auto-generated by workbench douyin_cookie (UI Cookie → cookiefile)",
    ]
    for name, value in pairs.items():
        # flag 是 "TRUE/FALSE" 大写；secure=TRUE 让 douyin/iesdouyin 都生效
        lines.append(f"{domain}\tTRUE\t/\tTRUE\t2147483647\t{name}\t{value}")
    body = "\n".join(lines) + "\n"

    # delete=False + 手动删：yt-dlp 是懒加载、用完才打开文件句柄，等进程退再清理
    fd, path = tempfile.mkstemp(prefix="dy_cookie_", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    return path
