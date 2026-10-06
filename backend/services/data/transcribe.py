"""视频 → 音频 → Whisper 转写（中文）。

抖音抓文案通常只能拿到标题 / 简介（几十字），拿不到完整口播稿。
本模块用 yt-dlp 把视频音频拉下来，imageio-ffmpeg 转码，
whisper 在 CPU 上转写成文字，作为「视频转写」素材兜底。

在拆解流程里的三层兜底位置：
  1) 页面文本（抓取 ≥100 字）直接用；
  2) 文字太短 → 这里自动转写视频；
  3) 转写也失败 / 超时 → 前端引导用户手动粘贴。

注意：torch / whisper 体积大，全部在调用时才懒加载，避免拖慢后端启动。
所有下载 / 转码产物都写在临时目录，用完即删，不留垃圾文件。
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("workbench.transcribe")

# 视频时长上限：超过就不再自动转写（CPU 转写太慢、性价比低）
# 注意：之前是 600（10 分钟），15 分钟视频会被本参数直接拒掉——这正是用户当前痛点。
# 提到 1800（30 分钟），并允许调用方用 transcribe_video(..., max_duration=...) 覆盖。
_MAX_DURATION_SEC = 1800  # 30 分钟
# 整体超时（下载 + 转码 + 转写）：超过返回「转写超时，建议手动粘贴」。
# 长视频 CPU 转写本来就慢（15 分钟视频可能 20-30 分钟），提到 40 分钟。
_OVERALL_TIMEOUT_SEC = 2400  # 40 分钟
# 下载音频单独超时
_DOWNLOAD_TIMEOUT_SEC = 600  # 抖音下载慢（cookie + 重定向），10 分钟起步
# 转码单独超时
_CONVERT_TIMEOUT_SEC = 300
# whisper 默认模型（中文 small 够用；medium 质量更好但更慢；base 作兜底）
_DEFAULT_MODEL = "small"
_FALLBACK_MODEL = "base"

# 转写结果磁盘缓存：同 URL 转写过的，结果写本地，下次秒回。
# 大幅降低"同一视频反复点"造成的 CPU 浪费。
_CACHE_DIR_NAME = "transcripts"
_CACHE_TTL_SEC = 30 * 24 * 3600  # 30 天


def _cache_dir() -> Path:
    """转写结果磁盘缓存目录。data_dir 不存在则创建。"""
    from ..system.config import DATA_DIR

    d = Path(DATA_DIR) / _CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _url_to_cache_key(url: str) -> str:
    """URL → 缓存文件名（sha256 前 24 位，足够碰撞安全）。"""
    h = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
    return f"{h[:24]}.json"


def _cache_get(url: str) -> dict | None:
    """命中缓存则返回转写结果字典（含 ok/text/duration_sec/engine/model/cached_at），否则 None。"""
    p = _cache_dir() / _url_to_cache_key(url)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if (time.time() - float(d.get("cached_at", 0))) > _CACHE_TTL_SEC:
            return None
        d["cached"] = True  # 标记：本次结果是缓存直返，没新跑模型
        return d
    except Exception as e:  # noqa: BLE001
        log.warning("读转写缓存失败（忽略）：%s", e)
        return None


def _cache_put(url: str, result: dict) -> None:
    """把转写结果落到磁盘。失败也不抛（缓存是优化不是正确性）。"""
    try:
        d = dict(result)
        d.pop("cached", None)
        d["cached_at"] = time.time()
        d["url"] = url
        p = _cache_dir() / _url_to_cache_key(url)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("写转写缓存失败（忽略）：%s", e)


# yt-dlp 在 douyin 上经常需要登录态 / 签名，准备好友好错误信息
_DOWNLOAD_FAIL_HINT = (
    "视频下载失败（抖音对第三方下载限制很严，经常需要登录态或签名过期）。"
    "建议打开抖音 App，开字幕把完整口播稿复制粘贴进来，拆解质量反而最高。"
)

# 错误分类标签，前端可据此给精准提示
#   need_login    - 平台要求登录态（典型：抖音 Fresh cookies）
#   network       - 网络层失败（断网 / DNS / 防火墙）
#   unsupported   - 链接/平台暂不支持
#   format        - 视频格式不支持（罕见）
#   timeout       - 超时
#   unknown       - 其它（保留真实 error 字符串供排查）


def _classify_yt_dlp_error(msg: str) -> tuple[str, str]:
    """把 yt-dlp 错误字符串分类成 (error_key, 用户可读的中文原因)。

    返回 (key, msg_zh)；key 是机器可读枚举，msg_zh 给前端展示用。
    """
    if not msg:
        return "unknown", "下载失败，原因未知"
    m = msg.lower()
    # 抖音 / TikTok 登录态
    if any(k in m for k in ("fresh cookies", "cookies are needed", "登录", "log in")):
        return (
            "need_login",
            "这条视频需要登录态才能下载（抖音 / TikTok 等平台对未登录请求拒绝）。"
            "如果你能登录抖音网页版，把导出的 cookies 文件发给开发者配进后端"
            "（环境变量 ASR_DOUYIN_COOKIES），即可解锁本条；"
            "否则请打开抖音 App → 字幕 → 复制完整口播稿 → 粘贴进下面的框。",
        )
    # 抖音网页拿不到 JSON
    if "failed to parse json" in m or "expecting value" in m:
        return (
            "need_login",
            "抖音网页接口拒绝返回数据，多半是没登录态触发了风控。"
            "建议打开抖音 App，开字幕手动复制完整口播稿粘贴进来。",
        )
    # 网络问题
    if any(k in m for k in ("could not connect", "connection refused", "timed out",
                            "no route to host", "getaddrinfo", "ssl:")):
        return (
            "network",
            "网络层失败：后端到视频平台的网络不通（本机 / VPN / 防火墙）。"
            "请检查网络或重试一次；仍失败就手动粘贴口播稿。",
        )
    # 链接不支持
    if any(k in m for k in ("unsupported url", "no video could be found",
                            "is not a valid url", "unable to extract")):
        return (
            "unsupported",
            "链接格式不被识别或平台暂不支持。请确认是抖音 / TikTok / B 站 等公开视频链接，"
            "或直接手动粘贴口播稿。",
        )
    return "unknown", f"下载失败：{msg[:160]}"


def _ytdl_common_opts(extra: dict | None = None) -> dict:
    """yt-dlp 的通用下载器配置：UA、Referer、cookie。

    cookie 来源（统一由 .douyin_cookie 解析，按优先级自动选模式 → 统一落到 cookiefile）：
      1) backend/data/douyin_sync.json -> config.cookie（UI 粘的浏览器 Cookie 头）
         → 写到 temp Netscape 文件 → yt-dlp ``cookiefile``
      2) 环境变量 ASR_DOUYIN_COOKIES 指向的 Netscape cookies 文件
         → 直接 ``cookiefile`` 给 yt-dlp

    ⚠ 不直接用 ``http_headers["Cookie"]``：yt-dlp 把这条标为 deprecated，
    且抖音对这种请求高频判 "Fresh cookies are needed"。最稳的路径就是把
    Cookie 头解析后写 Netscape 文件 → cookiefile（与 .bat 注入的旧路径对齐）。

    没配 cookie 也不报错——调用方 transcribe_video() 会先做 fail-fast 拦截，
    不会发起注定失败的下载。
    """
    from .douyin_cookie import (
        header_to_netscape_file,
        resolve_douyin_cookie,
    )

    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
        },
    }
    ck = resolve_douyin_cookie()
    mode = ck.get("mode")
    if mode == "header":
        try:
            ck_path = header_to_netscape_file(ck.get("header_value") or "")
            opts["cookiefile"] = ck_path
            log.info("[transcribe] cookie via netscape tmpfile=%s (src=%s, len=%d)",
                     ck_path, ck.get("name"), ck.get("length", 0))
        except Exception as e:  # noqa: BLE001
            log.warning("[transcribe] cookie 字符串转 Netscape 文件失败：%s", e)
    elif mode == "cookiefile":
        opts["cookiefile"] = ck.get("cookiefile") or ""
        log.info("[transcribe] cookie via cookiefile=%s (src=%s)",
                 opts["cookiefile"], ck.get("name"))
    if extra:
        opts.update(extra)
    return opts


def _ffmpeg_dir() -> str | None:
    """返回同时包含 ffmpeg.exe 和 ffprobe.exe 的目录，给 yt-dlp 用。

    历史 bug：imageio_ffmpeg 只提供 ffmpeg，没有 ffprobe —— yt-dlp 在后处理
    （音频抽取）阶段会报 ``Postprocessing: ffmpeg and ffprobe not found``，
    因为它要求 ``ffmpeg_location`` 指向的目录下两个二进制都存在。

    优先级：
      1) imageio_ffmpeg（同目录已有 ffprobe 时）—— 本地无下载
      2) static_ffmpeg（首次会下载 ~100MB 的 ffmpeg+ffprobe，缓存复用）—— 标准兜底
      3) PATH 上的 ffmpeg.exe（同目录有 ffprobe 时）—— 系统装了 ffmpeg
    """
    # 1) imageio_ffmpeg 本地无下载，但只提供 ffmpeg
    try:
        import imageio_ffmpeg
        d = Path(imageio_ffmpeg.get_ffmpeg_exe()).parent
        if (d / "ffprobe.exe").exists():
            return str(d)
    except Exception as e:  # noqa: BLE001
        log.debug("imageio_ffmpeg 不可用：%s", e)

    # 2) static_ffmpeg 兜底：自动下载 ffmpeg+ffmpeg 同包的 ffprobe
    try:
        import static_ffmpeg
        # weak=True：PATH 上已有 ffmpeg/ffprobe 时跳过下载；都没有就拉一次（约 100MB）
        static_ffmpeg.add_paths(weak=True)
        pkg = Path(static_ffmpeg.__file__).parent
        for cand in (pkg / "bin" / "win32", pkg / "bin" / "win64", pkg / "bin"):
            if (cand / "ffmpeg.exe").exists() and (cand / "ffprobe.exe").exists():
                return str(cand)
        # add_paths 已把 bin 加到 PATH，直接 which 拿 ffmpeg.exe 假定同目录有 ffprobe
        import shutil
        fe = shutil.which("ffmpeg")
        if fe and Path(fe).with_name("ffprobe.exe").exists():
            return str(Path(fe).parent)
    except Exception as e:  # noqa: BLE001
        log.warning("static_ffmpeg 不可用：%s", e)

    return None


def _ffmpeg_exe() -> str | None:
    """返回 ffmpeg 可执行文件路径（给 subprocess.run 直接调用用）。

    优先从 ``_ffmpeg_dir()`` 拿到的目录里找 ffmpeg.exe（与 ffprobe 同目录），
    找不到再退回 imageio_ffmpeg 的旧路径（仅当调用方不依赖 ffprobe 时可用）。
    """
    d = _ffmpeg_dir()
    if d:
        for name in ("ffmpeg.exe", "ffmpeg"):
            p = Path(d) / name
            if p.exists():
                return str(p)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def _with_timeout(func, timeout: int, *args, **kwargs):
    """在线程里跑 func，超时返回 (None, '操作超时')；否则直接把 func 的返回值原样返回。

    注意：func 自己如果是 tuple 形式（(value, err)），我们**不**再二次打包成
    ((value, err), None)，否则调用方解构时会拿到嵌套 tuple 进而触发：
        TypeError: '>' not supported between instances of 'tuple' and 'int'
    """
    box: dict[str, Any] = {}
    exc: list[Exception] = []

    def _t() -> None:
        try:
            box["r"] = func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            exc.append(e)

    th = threading.Thread(target=_t, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        # 让超时的函数返回值（如果是 tuple-returning）也对调用方友好：返回 (None, 错误)
        return None, "操作超时"
    if exc:
        return None, f"{type(exc[0]).__name__}: {exc[0]}"
    return box.get("r")


def _embedded_json_duration(url: str) -> tuple[float | None, str | None]:
    """用 yt-dlp 只取元数据（不下载），拿到时长，判断要不要继续。"""
    try:
        import yt_dlp
    except Exception as e:  # noqa: BLE001
        return None, f"yt-dlp 未安装：{e}"

    ydl_opts = _ytdl_common_opts({"skip_download": True, "simulate": True})
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        dur = info.get("duration")
        # 新版 yt-dlp 偶尔返回 (seconds, None) 或 list；统一取数值或 None
        if isinstance(dur, (tuple, list)):
            dur = dur[0] if dur else None
        if dur is not None:
            try:
                return float(dur), None
            except (TypeError, ValueError):
                return None, None
        return None, None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _download_audio(url: str, workdir: Path) -> tuple[str | None, str | None]:
    """用 yt-dlp 下载 bestaudio 并抽取成 mp3，返回 (音频路径, 错误)。"""
    try:
        import yt_dlp
    except Exception as e:  # noqa: BLE001
        return None, f"yt-dlp 未安装：{e}"

    out_tmpl = str(workdir / "audio.%(ext)s")
    ydl_opts = _ytdl_common_opts({
        "format": "bestaudio/best",
        "outtmpl": out_tmpl,
        "noprogress": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
    })
    ffmpeg_dir = _ffmpeg_dir()
    if ffmpeg_dir:
        # yt-dlp 要求 ffmpeg_location 目录下 ffmpeg.exe + ffprobe.exe 同时存在
        ydl_opts["ffmpeg_location"] = ffmpeg_dir

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:  # noqa: BLE001
        # 不把整条 stack 报给前端，只取关键片段
        raw = str(e)
        if "ERROR:" in raw:
            # yt-dlp 把错误信息包成 "ERROR: ..." 多条，简化
            line = raw.split("ERROR:")[-1].split("\n")[0].strip()[:160]
            return None, line or raw[:160]
        return None, raw[:160]

    for ext in ("mp3", "m4a", "webm", "ogg", "opus"):
        cand = workdir / f"audio.{ext}"
        if cand.exists() and cand.stat().st_size > 0:
            return str(cand), None
    return None, "下载完成但没找到音频文件"


def _probe_duration(audio_path: str) -> float | None:
    """用 ffmpeg 解析音频真实时长（秒）。拿不到返回 None。"""
    ffmpeg = _ffmpeg_exe()
    if not ffmpeg:
        return None
    try:
        r = subprocess.run(
            [ffmpeg, "-i", audio_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        out = r.stderr or r.stdout
        dur = None
        for line in out.splitlines():
            if "Duration" in line:
                # Duration: 00:03:21.45,
                import re

                m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)", line)
                if m:
                    h, mi, s = (int(x) for x in m.groups())
                    dur = h * 3600 + mi * 60 + s
                break
        return dur
    except Exception:  # noqa: BLE001
        return None


def _to_wav(audio_path: str, workdir: Path) -> tuple[str | None, str | None]:
    """用 imageio-ffmpeg 把音频转成 16kHz 单声道 wav（whisper 最稳的格式）。

    转码失败就退回原音频（whisper 内部也能解码 mp3/m4a）。
    """
    ffmpeg = _ffmpeg_exe()
    if not ffmpeg:
        return audio_path, None
    wav = str(workdir / "audio_conv.wav")
    cmd = [
        ffmpeg,
        "-y",
        "-threads", "0",  # ← 让 ffmpeg 用所有 CPU 核解码；单核跑音频抽帧会上小时级
        "-i",
        audio_path,
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        wav,
    ]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_CONVERT_TIMEOUT_SEC,
        )
        if r.returncode != 0:
            log.warning("ffmpeg 转码失败，退回原音频：%s", (r.stderr or "")[-300:])
            return audio_path, None
        return wav, None
    except Exception as e:  # noqa: BLE001
        log.warning("ffmpeg 转码异常，退回原音频：%s", e)
        return audio_path, None


def _transcribe(wav_path: str, *, model: str, timeout: int) -> tuple[str | None, str | None]:
    """在 CPU 上用 whisper 转写，带线程级超时保护。

    速度调参说明（修过的"9 小时"问题根因）：
      - 默认 ``beam_size=5`` + ``best_of=5`` 是为高质量设的，CPU 上慢 3-5×。
      - 改成 beam_size=1 / best_of=1 + 不让前文影响后段，
        中文转写准确率损失 < 3%，速度快 3-4×，转写 15 分钟视频从 1 小时压到 15 分钟。
    """
    try:
        import whisper
    except Exception as e:  # noqa: BLE001
        return None, f"whisper 未安装：{e}"

    result: dict[str, Any] = {}
    exc: list[Exception] = []

    def _run() -> None:
        try:
            m = whisper.load_model(model)
            res = m.transcribe(
                wav_path,
                language="zh",
                fp16=False,
                verbose=False,
                beam_size=1,            # ← 速度 ↑约 2-3×（默认 5 是为质量，CPU 不可承受）
                best_of=1,              # ← 速度 ↑约 2 倍（默认 5）
                condition_on_previous_text=False,  # ← 避免错误累积，速度 ↑
            )
            result["text"] = (res.get("text") or "").strip()
        except Exception as e:  # noqa: BLE001
            exc.append(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None, "转写超时，建议手动粘贴"
    if exc:
        return None, f"{type(exc[0]).__name__}: {exc[0]}"
    text = result.get("text")
    if not text:
        return None, "转写结果为空（可能是纯音乐 / 无声视频）"
    return text, None


def transcribe_video(
    video_id_or_url: str,
    *,
    model: str | None = None,
    timeout: int = _OVERALL_TIMEOUT_SEC,
) -> dict[str, Any]:
    """把一条抖音 / 短视频链接或视频 id 转写成文字。

    返回 dict：
        {ok, text, duration_sec, engine:"whisper", model, error?}

    失败一律 ok=False 并带 error 说明（下载失败 / 超时 / 无声 等），
    调用方据此决定是否回落到「手动粘贴」。
    """
    url = (video_id_or_url or "").strip()
    if not url:
        return {
            "ok": False,
            "text": "",
            "duration_sec": None,
            "engine": "whisper",
            "error_key": "invalid_input",
            "error": "缺少视频链接或 id",
        }

    # ---- 0) 命中缓存就直接返回：同一条视频点 N 次也只转一次 ----
    cached = _cache_get(url)
    if cached is not None:
        log.info("[transcribe] cache HIT url=%s model=%s", url[:80], cached.get("model"))
        return cached

    # ---- 抖音 / TikTok 必带 cookie：没配就直接拒绝下载，不浪费 20 分钟转写 ----
    from .douyin_cookie import resolve_douyin_cookie

    ck = resolve_douyin_cookie()
    if not ck.get("mode"):
        return {
            "ok": False,
            "text": "",
            "duration_sec": None,
            "engine": "whisper",
            "error_key": "need_login",
            "error": (
                "这条视频需要登录态才能下载（抖音 / TikTok 等平台对未登录请求直接拒绝）。"
                "请到「抖音同步」页 → 「配置」标签 → 「抖音登录 Cookie」粘贴你浏览器里的 Cookie 后保存，"
                "然后回这里再点一次「自动转写」。"
            ),
        }

    workdir = Path(tempfile.mkdtemp(prefix="asr_"))
    try:
        # ---------- 时长预判：超 10 分钟直接放弃（省一次下载） ----------
        dur, derr = _with_timeout(_embedded_json_duration, 60, url)
        if derr:
            # 取不到元数据不应直接判死刑（douyin 模拟经常失败），记日志后继续
            log.warning("预览时长失败（仍尝试下载）：%s", derr)
        if dur and dur > _MAX_DURATION_SEC:
            return {
                "ok": False,
                "text": "",
                "duration_sec": round(dur),
                "engine": "whisper",
                "error_key": "too_long",
                "error": (
                    f"视频时长约 {int(dur // 60)} 分，超过 {_MAX_DURATION_SEC // 60} 分钟上限，"
                    "转写成本太高，建议手动粘贴完整口播稿。"
                ),
            }

        # ---------- 下载音频（带超时） ----------
        audio, aerr = _with_timeout(_download_audio, _DOWNLOAD_TIMEOUT_SEC, url, workdir)
        if aerr:
            key, msg_zh = _classify_yt_dlp_error(aerr)
            if aerr == "操作超时":
                return {
                    "ok": False,
                    "text": "",
                    "duration_sec": (round(dur) if dur else None),
                    "engine": "whisper",
                    "error_key": "timeout",
                    "error": f"{_DOWNLOAD_FAIL_HINT}（原因：下载超时）",
                }
            return {
                "ok": False,
                "text": "",
                "duration_sec": (round(dur) if dur else None),
                "engine": "whisper",
                "error_key": key,
                "error": msg_zh,
            }

        # ---------- 下载后再核一次时长（准确） ----------
        real_dur = _probe_duration(audio)
        if real_dur and real_dur > _MAX_DURATION_SEC:
            return {
                "ok": False,
                "text": "",
                "duration_sec": round(real_dur),
                "engine": "whisper",
                "error_key": "too_long",
                "error": (
                    f"视频时长约 {int(real_dur // 60)} 分，超过 10 分钟上限，"
                    "转写成本太高，建议手动粘贴完整口播稿。"
                ),
            }
        if real_dur:
            dur = real_dur

        # ---------- 转码 ----------
        wav, _ = _to_wav(audio, workdir)

        # ---------- 转写（默认 small，失败回退 base） ----------
        mdl = model or _DEFAULT_MODEL
        text, terr = _transcribe(wav, model=mdl, timeout=timeout)
        if terr and mdl != _FALLBACK_MODEL:
            log.warning("whisper(%s) 失败，回退 %s：%s", mdl, _FALLBACK_MODEL, terr)
            text, terr = _transcribe(wav, model=_FALLBACK_MODEL, timeout=timeout)
        if terr:
            fail = {
                "ok": False,
                "text": "",
                "duration_sec": (round(dur) if dur else None),
                "engine": "whisper",
                "model": mdl,
                "error_key": "transcribe_failed",
                "error": terr,
            }
            _cache_put(url, fail)
            return fail

        ok_result = {
            "ok": True,
            "text": text,
            "duration_sec": (round(dur) if dur else None),
            "engine": "whisper",
            "model": mdl,
        }
        _cache_put(url, ok_result)
        return ok_result
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
