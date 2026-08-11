"""云端 OCR 驱动：百度智能云 OCR 识别截图文字，再由 DeepSeek 整理成结构化 JSON。

整体链路（与 PaddleOCR / Tesseract 驱动完全一致，只换识别引擎）：
    截图 → 百度 OCR（通用文字识别·高精度版）→ DeepSeek(deepseek-chat)
         → 归一化成 {articles, summary, confidence, note}

为什么加百度 OCR：
- 百度中文 OCR 准确率高、国内服务速度快，每天 1000 次免费额度，个人完全够用；
- 纯云端调用，不需要在本地装任何程序，也不受 Python 版本影响；
- 适合表格类截图（公众号后台数据列表）。

关键点：
- 百度 OCR 走 OAuth 2.0 client_credentials 换 access_token，token 默认 30 天有效，
  这里做了进程内缓存并在过期前自动刷新，避免每次识别都去换 token；
- 用的是「通用文字识别（高精度版）」= accurate_basic（免费额度 1000/天），
  返回每个识别到的词，已按阅读顺序排好，这里我们直接按行拼回文本；
  若该接口返回了 location（部分版本），则按 y→x 排序还原行序。
- 结构化复用共享层 ocr_structure（与另外两种本地引擎同一套提示词与错误处理）。
"""
from __future__ import annotations

import base64
import logging
import time

from ..system.config import load_config
from . import ocr_structure, vision
from .ocr_strategy import OcrError

log = logging.getLogger("workbench.ocr_baidu")

# 结果里标注的引擎名，同时写进 DeepSeek 提示词
ENGINE_NAME = "百度 OCR"

# 百度智能云 OCR 控制台（创建应用、拿 API Key / Secret Key 的地方）
APPLY_URL = "https://console.bce.baidu.com/ai/#/ai/ocr/overview"
APPLY_HINT = (
    f"需要先到百度智能云创建应用并获取 API Key / Secret Key：{APPLY_URL}\n"
    "（创建应用后，在「应用列表」里能看到 API Key 和 Secret Key，填到「配置 → 高级」即可。）"
)

# 获取 access_token 的 OAuth 端点，与调用 OCR 的 REST 端点
_OAUTH_URL = "https://aip.baidubce.com/oauth/2.0/token"
_OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"

# 网络超时（秒）
_TIMEOUT = 30

# access_token 进程内缓存：key -> {token, expires_at}，过期前 60 秒视为失效自动刷新
_TOKEN_CACHE: dict[str, dict] = {}

# 百度 OCR 常见错误码 → 友好提示
_BAIDU_ERRORS: dict[int, str] = {
    17: "百度 OCR 免费额度已用尽（每日 1000 次）。请在百度智能云控制台查看用量，或次日再试。",
    18: "百度 OCR 请求频率超限（QPS）。请稍等几秒后再试。",
    111: "百度 access_token 已过期，请重新保存配置（或稍后重试）以刷新令牌。",
    110: "百度 access_token 无效，请检查 API Key / Secret Key 是否正确。",
    216201: "图片格式不支持，请上传 PNG / JPG / JPEG / BMP 格式的截图。",
    216202: "图片大小超限，请将截图裁剪到百度允许的尺寸后重试。",
    282000: "百度 OCR 服务内部错误，请稍后重试。",
}


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------
def resolve_config() -> dict:
    """取 ocr 段里百度相关的密钥配置，做好兜底。"""
    cfg = load_config()
    ocr = cfg.get("ocr") or {}
    return {
        "api_key": (ocr.get("baidu_api_key") or "").strip(),
        "secret_key": (ocr.get("baidu_secret_key") or "").strip(),
    }


# --------------------------------------------------------------------------
# access_token 获取（带缓存、过期自动刷新）
# --------------------------------------------------------------------------
def get_access_token(api_key: str, secret_key: str) -> str:
    """用 API Key / Secret Key 换 access_token，带进程内缓存。

    百度返回的 expires_in 通常约 30 天（2592000 秒），我们提前 60 秒判定过期，
    这样临近过期时下一次调用会重新获取，避免用着用着突然失效。
    """
    cache_key = f"{api_key}|{secret_key}"
    now = time.time()
    cached = _TOKEN_CACHE.get(cache_key)
    if cached and cached["expires_at"] > now:
        return cached["token"]

    import requests  # 懒加载，和 vision / ocr_structure 保持一致

    try:
        r = requests.post(
            _OAUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": api_key,
                "client_secret": secret_key,
            },
            timeout=_TIMEOUT,
        )
    except requests.exceptions.Timeout as e:
        raise OcrError("获取百度 access_token 超时，请检查网络后重试。") from e
    except requests.exceptions.RequestException as e:
        raise OcrError(f"连接百度授权服务失败（{type(e).__name__}），请检查网络。") from e

    try:
        data = r.json()
    except ValueError as e:
        raise OcrError("百度授权服务返回了无法解析的响应，请稍后重试。") from e

    if "error" in data:
        desc = data.get("error_description") or data.get("error") or ""
        raise OcrError(
            f"获取百度 access_token 失败：{desc}。请检查 API Key / Secret Key 是否正确。"
        )
    token = (data.get("access_token") or "").strip()
    if not token:
        raise OcrError("百度返回了空的 access_token，请检查密钥或稍后重试。")

    try:
        expires_in = int(data.get("expires_in") or 0)
    except (TypeError, ValueError):
        expires_in = 0
    # 没有过期时间就保守地只缓存 1 小时
    ttl = expires_in - 60 if expires_in > 120 else 3600
    _TOKEN_CACHE[cache_key] = {"token": token, "expires_at": now + ttl}
    return token


# --------------------------------------------------------------------------
# 可用性检测（配置页「测试连接」按钮 / 状态探测都走这里）
# --------------------------------------------------------------------------
def detect(api_key: str = "", secret_key: str = "") -> dict:
    """检测百度 OCR 密钥是否可用，返回给前端的检测结果。

    允许传入「用户刚在输入框里改、还没保存」的密钥，方便先测后存。
    """
    cfg = resolve_config()
    ak = (api_key or "").strip() or cfg["api_key"]
    sk = (secret_key or "").strip() or cfg["secret_key"]

    base: dict = {"ok": False, "has_key": bool(ak and sk), "message": ""}

    if not (ak and sk):
        base["message"] = "请填写百度 OCR 的 API Key 和 Secret Key。" + APPLY_HINT
        return base

    try:
        get_access_token(ak, sk)
    except OcrError as e:
        base["message"] = str(e)
        return base

    base["ok"] = True
    base["message"] = (
        "连接成功，已获取百度 access_token，可正常调用「通用文字识别（高精度版）」。\n"
        "每天免费额度 1000 次，个人使用完全够用。"
    )
    return base


def status() -> dict:
    """给前端的可用性探测：不做真实识别，只看密钥在不在。"""
    cfg = resolve_config()
    has = bool(cfg["api_key"] and cfg["secret_key"])
    return {
        "configured": has,
        "model": ENGINE_NAME + " 高精度版",
        "endpoint": "aip.baidubce.com",
        "inherited": False,
        "hint": "" if has else ("百度 OCR 尚未配置密钥。" + APPLY_HINT),
        "mode": "baidu_ocr",
        "note": (
            "调用百度智能云「通用文字识别（高精度版）」识别文字，再交由 DeepSeek 整理成数据；"
            "每天 1000 次免费额度。"
        ),
    }


# --------------------------------------------------------------------------
# 文字结果行重排（纯逻辑，可单测）
# --------------------------------------------------------------------------
def _rebuild_rows(items: list[dict]) -> str:
    """把百度 OCR 返回的 words_result 整理成「一行一条」纯文本。

    accurate_basic 通常只返回 words（已按阅读顺序排好），没有坐标；
    若某些版本返回了 location（top/left），则按 y→x 排序还原行序。
    """
    if not items:
        return ""
    has_loc = all(isinstance(it.get("location"), dict) for it in items)
    if has_loc:
        items = sorted(
            items,
            key=lambda it: (
                it["location"].get("top", 0),
                it["location"].get("left", 0),
            ),
        )
    lines = [str(it.get("words", "")).strip() for it in items if str(it.get("words", "")).strip()]
    return "\n".join(lines)


def _safe_json(resp) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {}


def _baidu_error(body: dict) -> str:
    code = body.get("error_code")
    msg = body.get("error_msg") or ""
    if code in _BAIDU_ERRORS:
        return _BAIDU_ERRORS[code]
    if code is not None:
        return f"百度 OCR 调用失败（错误码 {code}）：{msg}".strip()
    return f"百度 OCR 返回异常：{msg or '未知错误'}".strip()


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def recognize(content: bytes, filename: str = "") -> dict:
    """识别一张截图：百度 OCR 出文字 → DeepSeek 整理成结构化数据。"""
    # 沿用视觉模型的三重图片校验（大小 / 扩展名 / magic bytes）
    vision.validate_image(filename, content)

    cfg = resolve_config()
    ak, sk = cfg["api_key"], cfg["secret_key"]
    if not (ak and sk):
        raise OcrError("百度 OCR 尚未配置 API Key / Secret Key。" + APPLY_HINT)

    try:
        token = get_access_token(ak, sk)
    except OcrError:
        raise

    import requests  # 懒加载

    img_b64 = base64.b64encode(content).decode("ascii")
    try:
        r = requests.post(
            _OCR_URL,
            params={"access_token": token},
            data={"image": img_b64},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=_TIMEOUT,
        )
    except requests.exceptions.Timeout as e:
        raise OcrError("百度 OCR 请求超时（超过 30 秒），请稍后重试。") from e
    except requests.exceptions.RequestException as e:
        raise OcrError(f"连接百度 OCR 失败（{type(e).__name__}），请检查网络。") from e

    body = _safe_json(r)
    if r.status_code != 200 or "error_code" in body:
        # 额度用尽 / 密钥失效等，抛出用户能看懂的提示
        raise OcrError(_baidu_error(body))

    items = body.get("words_result") or []
    text = _rebuild_rows(items)
    if not text.strip():
        raise OcrError(
            "百度 OCR 没有从这张图识别出文字。请确认是清晰、未被弹窗遮挡的公众号后台截图。"
        )

    log.info(
        "百度 OCR 提取文字 %d 行，交给 DeepSeek 整理", text.count("\n") + 1
    )
    # 结构化走共享层（与 PaddleOCR / Tesseract 驱动同一套提示词与错误处理）
    return ocr_structure.structure(text, filename, ENGINE_NAME)
