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

import logging
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("workbench.transcribe")

# 视频时长上限：超过就不转写了（CPU 转写太慢、性价比低）
_MAX_DURATION_SEC = 600  # 10 分钟
# 整体超时（下载 + 转码 + 转写）：超过返回「转写超时，建议手动粘贴」
_OVERALL_TIMEOUT_SEC = 1200  # 20 分钟
# 下载音频单独超时
_DOWNLOAD_TIMEOUT_SEC = 300
# 转码单独超时
_CONVERT_TIMEOUT_SEC = 180
# whisper 默认模型（中文 small 够用；medium 质量更好但更慢；base 作兜底）
_DEFAULT_MODEL = "small"
_FALLBACK_MODEL = "base"

# yt-dlp 在 douyin 上经常需要登录态 / 签名，准备好友好错误信息
_DOWNLOAD_FAIL_HINT = (
    "视频下载失败（抖音对第三方下载限制很严，经常需要登录态或签名过期）。"
    "建议打开抖音 App，开字幕把完整口播稿复制粘贴进来，拆解质量反而最高。"
)


def _ffmpeg_exe() -> str | None:
    """优先用 imageio-ffmpeg 自带的 ffmpeg 二进制，避免系统级 ffmpeg 依赖。"""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # noqa: BLE001
        log.warning("imageio-ffmpeg 不可用：%s", e)
        return None


def _with_timeout(func, timeout: int, *args, **kwargs):
    """在线程里跑 func，超时返回 (None, '操作超时')；否则返回 func 的真实返回值。"""
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
        return None, "操作超时"
    if exc:
        return None, f"{type(exc[0]).__name__}: {exc[0]}"
    return box.get("r"), None


def _embedded_json_duration(url: str) -> tuple[float | None, str | None]:
    """用 yt-dlp 只取元数据（不下载），拿到时长，判断要不要继续。"""
    try:
        import yt_dlp
    except Exception as e:  # noqa: BLE001
        return None, f"yt-dlp 未安装：{e}"

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "simulate": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
        },
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        dur = info.get("duration")
        return (float(dur) if dur else None), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _download_audio(url: str, workdir: Path) -> tuple[str | None, str | None]:
    """用 yt-dlp 下载 bestaudio 并抽取成 mp3，返回 (音频路径, 错误)。"""
    try:
        import yt_dlp
    except Exception as e:  # noqa: BLE001
        return None, f"yt-dlp 未安装：{e}"

    out_tmpl = str(workdir / "audio.%(ext)s")
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "outtmpl": out_tmpl,
        "noplaylist": True,
        "noprogress": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
        },
    }
    ffmpeg = _ffmpeg_exe()
    if ffmpeg:
        ydl_opts["ffmpeg_location"] = str(Path(ffmpeg).parent)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"

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
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=_CONVERT_TIMEOUT_SEC)
        if r.returncode != 0:
            log.warning("ffmpeg 转码失败，退回原音频：%s", (r.stderr or "")[-300:])
            return audio_path, None
        return wav, None
    except Exception as e:  # noqa: BLE001
        log.warning("ffmpeg 转码异常，退回原音频：%s", e)
        return audio_path, None


def _transcribe(wav_path: str, *, model: str, timeout: int) -> tuple[str | None, str | None]:
    """在 CPU 上用 whisper 转写，带线程级超时保护。"""
    try:
        import whisper
    except Exception as e:  # noqa: BLE001
        return None, f"whisper 未安装：{e}"

    result: dict[str, Any] = {}
    exc: list[Exception] = []

    def _run() -> None:
        try:
            m = whisper.load_model(model)
            res = m.transcribe(wav_path, language="zh", fp16=False, verbose=False)
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
            "error": "缺少视频链接或 id",
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
                "error": (
                    f"视频时长约 {int(dur // 60)} 分，超过 10 分钟上限，"
                    "转写成本太高，建议手动粘贴完整口播稿。"
                ),
            }

        # ---------- 下载音频（带超时） ----------
        audio, aerr = _with_timeout(_download_audio, _DOWNLOAD_TIMEOUT_SEC, url, workdir)
        if aerr:
            if aerr == "操作超时":
                return {
                    "ok": False,
                    "text": "",
                    "duration_sec": (round(dur) if dur else None),
                    "engine": "whisper",
                    "error": f"{_DOWNLOAD_FAIL_HINT}（原因：下载超时）",
                }
            return {
                "ok": False,
                "text": "",
                "duration_sec": (round(dur) if dur else None),
                "engine": "whisper",
                "error": f"{_DOWNLOAD_FAIL_HINT}（原因：{aerr}）",
            }

        # ---------- 下载后再核一次时长（准确） ----------
        real_dur = _probe_duration(audio)
        if real_dur and real_dur > _MAX_DURATION_SEC:
            return {
                "ok": False,
                "text": "",
                "duration_sec": round(real_dur),
                "engine": "whisper",
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
            return {
                "ok": False,
                "text": "",
                "duration_sec": (round(dur) if dur else None),
                "engine": "whisper",
                "model": mdl,
                "error": terr,
            }

        return {
            "ok": True,
            "text": text,
            "duration_sec": (round(dur) if dur else None),
            "engine": "whisper",
            "model": mdl,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
