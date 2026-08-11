"""本地 OCR 驱动：Tesseract 识别截图文字，再由 DeepSeek 整理成结构化 JSON。

整体链路（与 PaddleOCR 驱动完全一致，只换识别引擎）：
    截图 → Tesseract 出文字（按表格行结构重排）→ DeepSeek(deepseek-chat)
         → 归一化成 {articles, summary, confidence, note}

为什么加 Tesseract：
- PaddleOCR 依赖 paddlepaddle，在高版本 Python（3.12/3.13）下经常装不上；
- Tesseract 是独立的 C++ 程序，跟 Python 版本无关，Windows 一键安装包，稳定可靠；
- Python 侧只需要一个很轻的 pytesseract（纯封装，不含模型）。

安装要点（错误提示里也会告诉用户）：
- Windows 安装包：https://github.com/UB-Mannheim/tesseract/wiki
- 安装时务必在 Additional language data 里勾选 Chinese (Simplified)，否则只能认英文；
- 默认装到 C:\\Program Files\\Tesseract-OCR\\，不会自动加进 PATH，
  所以配置里支持手动填 tesseract.exe 的完整路径。
"""
from __future__ import annotations

import logging
import os
import shutil
from typing import Any

from ..system.config import load_config
from . import ocr_structure, vision
from .ocr_strategy import OcrError

log = logging.getLogger("workbench.ocr_tesseract")

# 结果里标注的引擎名，同时会写进 DeepSeek 提示词
ENGINE_NAME = "Tesseract OCR"

INSTALL_URL = "https://github.com/UB-Mannheim/tesseract/wiki"
DEFAULT_WINDOWS_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# 中文简体 + 英文。装了中文语言包才有 chi_sim，没装时自动降级为纯英文并提示。
LANG_CHINESE = "chi_sim"
LANG_ENGLISH = "eng"

# --oem 3：默认引擎（LSTM）；--psm 6：按「一整块规整文本」处理，最贴合后台表格截图；
# preserve_interword_spaces：保留词间空格，便于后面按空隙还原列。
_TESS_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1"

# 置信度低于此值的词丢弃（Tesseract 对边框、图标常给出很低的置信度垃圾字符）
_MIN_CONF = 15.0

# 小图放大后识别率明显更高；宽度低于该值时按整数倍放大
_MIN_WIDTH_FOR_OCR = 1600
_MAX_SCALE = 3

INSTALL_HINT = (
    f"没检测到 Tesseract OCR。请先安装：{INSTALL_URL} "
    "（Windows 下载 tesseract-ocr-w64-setup-xxx.exe，安装时务必在 "
    "「Additional language data」里勾选 Chinese (Simplified) 中文语言包）。"
    "装好后到「配置 → 高级」把 tesseract.exe 路径填成实际安装位置"
    f"（默认是 {DEFAULT_WINDOWS_CMD}），点「检测」确认可用。"
)

# 语言包探测结果缓存：{(cmd, tessdata): [langs...]}，避免每次识别都拉起一次子进程
_LANG_CACHE: dict[tuple[str, str], list[str]] = {}


# --------------------------------------------------------------------------
# 配置与可执行文件定位
# --------------------------------------------------------------------------
def resolve_config() -> dict:
    """取 ocr 段里 Tesseract 相关配置，做好兜底。"""
    cfg = load_config()
    ocr = cfg.get("ocr") or {}
    return {
        "tesseract_cmd": (ocr.get("tesseract_cmd") or "").strip(),
        "tessdata_dir": (ocr.get("tessdata_dir") or "").strip(),
    }


def resolve_cmd(cmd: str = "") -> str:
    """定位 tesseract 可执行文件。

    顺序：显式传入 → 配置里填的 → PATH 里的 tesseract → Windows 默认安装路径。
    全都找不到时返回配置值（或默认路径），交给上层报「没装」的友好错误。
    """
    candidate = (cmd or "").strip() or resolve_config()["tesseract_cmd"]
    if candidate and os.path.isfile(candidate):
        return candidate
    found = shutil.which("tesseract")
    if found:
        return found
    if os.path.isfile(DEFAULT_WINDOWS_CMD):
        return DEFAULT_WINDOWS_CMD
    return candidate or DEFAULT_WINDOWS_CMD


def _tessdata_arg(tessdata_dir: str) -> str:
    """把语言包目录拼成 tesseract 的命令行参数（pytesseract 内部用 shlex 拆分）。"""
    d = (tessdata_dir or "").strip()
    if not d:
        return ""
    return f' --tessdata-dir "{d}"'


def _load_pytesseract():
    """懒加载 pytesseract，未安装时给出可执行的修复建议。"""
    try:
        import pytesseract  # noqa: WPS433 懒加载，和其它服务保持一致
    except Exception as e:
        raise OcrError(
            "Python 侧的 pytesseract 尚未安装。请在后端环境执行 "
            "`pip install -r backend/requirements.txt` 后重启服务再试。"
        ) from e
    return pytesseract


def _languages(pytesseract: Any, cmd: str, tessdata_dir: str) -> list[str]:
    """列出当前 Tesseract 可用语言包（带缓存）。"""
    key = (cmd, tessdata_dir)
    if key in _LANG_CACHE:
        return _LANG_CACHE[key]
    try:
        langs = list(pytesseract.get_languages(config=_tessdata_arg(tessdata_dir).strip()))
    except Exception:
        langs = []
    _LANG_CACHE[key] = langs
    return langs


def _pick_lang(langs: list[str]) -> str:
    """有中文包就 chi_sim+eng，没有就退回纯英文。"""
    if LANG_CHINESE in langs:
        return f"{LANG_CHINESE}+{LANG_ENGLISH}"
    if LANG_ENGLISH in langs:
        return LANG_ENGLISH
    # 语言列表拿不到时（老版本 tesseract 不支持 --list-langs）按常规组合赌一把
    return f"{LANG_CHINESE}+{LANG_ENGLISH}"


# --------------------------------------------------------------------------
# 可用性检测（配置页「检测」按钮 / 状态探测都走这里）
# --------------------------------------------------------------------------
def detect(tesseract_cmd: str = "", tessdata_dir: str = "") -> dict:
    """检测 Tesseract 是否可用，返回给前端的检测结果。

    允许传入「用户刚在输入框里改、还没保存」的路径，方便先测后存。
    """
    cfg = resolve_config()
    cmd = resolve_cmd(tesseract_cmd)
    tdir = (tessdata_dir or "").strip() or cfg["tessdata_dir"]

    base = {
        "ok": False,
        "cmd": cmd,
        "version": "",
        "languages": [],
        "has_chinese": False,
        "message": "",
    }

    try:
        pytesseract = _load_pytesseract()
    except OcrError as e:
        base["message"] = str(e)
        return base

    if not os.path.isfile(cmd):
        base["message"] = (
            f"路径「{cmd}」上没有找到 tesseract.exe。{INSTALL_HINT}"
        )
        return base

    pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        version = str(pytesseract.get_tesseract_version())
    except Exception as e:
        base["message"] = (
            f"找到了文件但没法运行（{type(e).__name__}）。"
            "请确认这是 tesseract.exe 本体、且安装未损坏。" + INSTALL_HINT
        )
        return base

    _LANG_CACHE.pop((cmd, tdir), None)  # 手动检测时强制刷新语言包缓存
    langs = _languages(pytesseract, cmd, tdir)
    has_cn = LANG_CHINESE in langs

    base.update(
        {
            "ok": True,
            "version": version,
            "languages": langs,
            "has_chinese": has_cn,
        }
    )
    if has_cn:
        base["message"] = (
            f"Tesseract {version} 可用，已装中文语言包（chi_sim），可以直接识别公众号截图。"
        )
    elif langs:
        base["message"] = (
            f"Tesseract {version} 可用，但没检测到中文语言包（chi_sim），"
            f"现在只能识别英文。请重新运行安装包，在「Additional language data」里"
            f"勾选 Chinese (Simplified)；或手动把 chi_sim.traineddata 放进 tessdata 目录。"
            f"下载地址：{INSTALL_URL}"
        )
    else:
        base["message"] = (
            f"Tesseract {version} 可用，但列不出语言包（可能是 tessdata 目录不对）。"
            "可在下面单独指定语言包目录后重新检测。"
        )
    return base


def status() -> dict:
    """给前端的可用性探测：不做真实识别，只看程序在不在、中文包有没有。"""
    cfg = resolve_config()
    res = detect(cfg["tesseract_cmd"], cfg["tessdata_dir"])
    ok = bool(res["ok"])
    if ok and not res["has_chinese"]:
        hint = res["message"]  # 能跑但没中文包，属于「能用但要提醒」
    else:
        hint = "" if ok else res["message"]
    return {
        "configured": ok,
        "model": ENGINE_NAME + (f" {res['version']}" if res["version"] else ""),
        "endpoint": res["cmd"] or "本地",
        "inherited": False,
        "hint": hint,
        "mode": "tesseract",
        "note": "文字识别在本地完成、不上传图片；整理成数据这一步用 DeepSeek。",
    }


# --------------------------------------------------------------------------
# 图片预处理与行重排（纯逻辑，可单测）
# --------------------------------------------------------------------------
def _preprocess(img):
    """灰度 + 适度放大 + 拉对比度：公众号后台字号偏小，放大后识别率明显更好。"""
    from PIL import Image, ImageOps

    gray = ImageOps.grayscale(img)
    w, h = gray.size
    if w < _MIN_WIDTH_FOR_OCR and w > 0:
        scale = min(_MAX_SCALE, max(1, round(_MIN_WIDTH_FOR_OCR / w)))
        if scale > 1:
            gray = gray.resize((w * scale, h * scale), Image.LANCZOS)
    return ImageOps.autocontrast(gray)


def _rebuild_rows(data: dict) -> str:
    """把 pytesseract 的 image_to_data 结果重排成「一行一记录、列用 Tab 分隔」的纯文本。

    data 是 image_to_data(output_type=DICT) 的返回：text / conf / left / top /
    width / height 等等长列表。公众号后台是规整表格，这里按词框的 y 坐标聚类成
    「行」，行内按 x 排序，词与词之间空隙足够大就判定为换列（Tab），
    能较好还原「标题 / 阅读量 / 在看 …」的列关系。
    """
    texts = data.get("text") or []
    n = len(texts)
    words: list[tuple[int, int, int, int, str]] = []
    for i in range(n):
        txt = str(texts[i] or "").strip()
        if not txt:
            continue
        try:
            conf = float((data.get("conf") or [])[i])
        except (TypeError, ValueError, IndexError):
            conf = -1.0
        # Tesseract 在 block/line/page 层级会返回 conf=-1，这类不是「词」，必须丢弃；
        # 同时过滤掉置信度过低的真实词（边框/图标常被认成垃圾字符）。
        if conf < _MIN_CONF:
            continue
        try:
            left = int((data.get("left") or [])[i])
            top = int((data.get("top") or [])[i])
            width = int((data.get("width") or [])[i])
            height = int((data.get("height") or [])[i])
        except (TypeError, ValueError, IndexError):
            continue
        words.append((left, top, width, height, txt))

    if not words:
        return ""

    heights = sorted(w[3] for w in words)
    med_h = heights[len(heights) // 2] or 10
    row_th = max(6.0, med_h * 0.6)
    col_gap = max(12.0, med_h * 0.8)

    words.sort(key=lambda w: (w[1], w[0]))
    rows: list[list[tuple[int, int, int, int, str]]] = []
    cur: list[tuple[int, int, int, int, str]] = []
    cur_y: float | None = None
    for w in words:
        top = w[1]
        if cur_y is None or abs(top - cur_y) <= row_th:
            cur.append(w)
            cur_y = cur_y if cur_y is not None else top
        else:
            rows.append(cur)
            cur = [w]
            cur_y = top
    if cur:
        rows.append(cur)

    lines: list[str] = []
    for row in rows:
        row.sort(key=lambda w: w[0])
        parts: list[str] = []
        prev_right: int | None = None
        for left, _top, width, _h, txt in row:
            if prev_right is not None:
                parts.append("\t" if (left - prev_right) > col_gap else " ")
            parts.append(txt)
            prev_right = left + width
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def recognize(content: bytes, filename: str = "") -> dict:
    """识别一张截图：Tesseract 出文字 → DeepSeek 整理成结构化数据。"""
    # 沿用视觉模型的三重图片校验（大小 / 扩展名 / magic bytes）
    vision.validate_image(filename, content)

    pytesseract = _load_pytesseract()
    cfg = resolve_config()
    cmd = resolve_cmd(cfg["tesseract_cmd"])
    if not os.path.isfile(cmd):
        raise OcrError(INSTALL_HINT)
    pytesseract.pytesseract.tesseract_cmd = cmd

    try:
        from io import BytesIO

        from PIL import Image
    except Exception as e:
        raise OcrError(
            f"本地 OCR 依赖缺失（Pillow）：{type(e).__name__}。请重装后端依赖后重试。"
        ) from e

    try:
        img = Image.open(BytesIO(content))
        img.load()
    except Exception as e:
        raise OcrError(f"「{filename or '图片'}」无法作为图片打开：{type(e).__name__}。") from e

    prepared = _preprocess(img)
    langs = _languages(pytesseract, cmd, cfg["tessdata_dir"])
    lang = _pick_lang(langs)
    config = _TESS_CONFIG + _tessdata_arg(cfg["tessdata_dir"])

    try:
        data = pytesseract.image_to_data(
            prepared,
            lang=lang,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as e:
        msg = str(e)
        if "not installed" in msg.lower() or "tesseractnotfound" in type(e).__name__.lower():
            raise OcrError(INSTALL_HINT) from e
        if "Failed loading language" in msg or "traineddata" in msg:
            raise OcrError(
                f"Tesseract 缺少语言包「{lang}」。请重新运行安装包并勾选 "
                f"Chinese (Simplified)，或把 chi_sim.traineddata 放进 tessdata 目录。"
                f"下载地址：{INSTALL_URL}"
            ) from e
        raise OcrError(
            f"Tesseract 识别失败（{type(e).__name__}）：{msg[:200]}。"
            "请换一张清晰、未被遮挡的截图重试。"
        ) from e

    text = _rebuild_rows(data)
    if not text.strip():
        extra = "" if LANG_CHINESE in langs else "（当前没检测到中文语言包，中文会识别不出来）"
        raise OcrError(
            f"从「{filename or '这张图'}」没有识别到任何文字{extra}。"
            "请确认是清晰、未被弹窗遮挡的公众号后台截图。"
        )

    log.info(
        "Tesseract(%s) 提取文字 %d 行，交给 DeepSeek 整理", lang, text.count("\n") + 1
    )
    # 结构化走共享层（与 PaddleOCR 驱动同一套提示词与错误处理）
    return ocr_structure.structure(text, filename, ENGINE_NAME)
