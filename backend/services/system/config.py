"""后端配置管理。

配置文件位于 backend/data/workbench_config.json，首次启动时自动复用现有
Streamlit 项目的 workbench_config.json（保持相同结构，向后兼容）。
流水线脚本目录仍指向现有 Streamlit 项目（scripts/ 与 data/issues/）。
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import time
from pathlib import Path

# 后端自身目录（本文件已迁至 backend/services/system/config.py：
# 先 .parent 去掉文件名到 system/，再 .parent.parent 上溯到 backend/）
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
# 数据目录可用 WORKBENCH_DATA_DIR 覆盖（云平台上可指向可写卷）
DATA_DIR = Path(os.getenv("WORKBENCH_DATA_DIR") or (BACKEND_DIR / "data"))
CONFIG_PATH = DATA_DIR / "workbench_config.json"

# 现有 Streamlit 项目根目录（内含 scripts/ 与 data/issues/）
# 默认空串 → 回退到当前工作目录（始终存在）；可在配置页或环境变量
# STREAMLIT_PROJECT_ROOT 指定本地老项目路径。路径不存在时由 Settings 给出友好提示，不崩溃。
DEFAULT_STREAMLIT_ROOT = ""


def _env(*names: str) -> str:
    """按顺序取第一个非空环境变量，全空返回空串。"""
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip()
    return ""

DEFAULT_CONFIG = {
    "project_root": DEFAULT_STREAMLIT_ROOT,
    "python_path": "python",                      # Python 解释器（运行流水线脚本用）
    "account_name": "扬的AI学习日记",              # 公众号名称
    "positioning": "",                            # 内容定位
    "style": "",                                  # 文风要求（空 = 由 dissect 侧用默认文风兜底）
    "visual_style": "",                           # 视觉风格
    "hotspot_api": {"api_url": "", "api_key": "", "timeout": 10, "method": "GET"},
    "scheduled_tasks": [],                        # 定时任务列表
    # 智能搜索配置（SerpAPI 真实搜索 + DeepSeek 智能分析）
    "search_api": {"type": "serpapi", "api_key": ""},   # type: serpapi / custom
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "api_key": "", "model": "deepseek-chat"},
    # 视觉模型（截图识别用，OpenAI 兼容协议）。
    # base_url / api_key 留空时自动沿用上面的 deepseek 配置；
    # 但 DeepSeek 官方 API 没有视觉模型，真要用截图识别就得在这里单独指一个 VL 端点，
    # 例如 https://api.siliconflow.cn/v1 + deepseek-ai/deepseek-vl2。
    "vision": {"base_url": "", "api_key": "", "model": "deepseek-vl2"},
    # LLM 调用成本估算单价（元 / 每百万 token）。
    # 仅供 llm_usage.cost_est 做量级估算（非精确账单）：
    #   cost_est = (prompt_tokens*input + completion_tokens*output) / 1_000_000
    # 缓存命中/未命中等复杂计费在此合并为单一定价；改这里即可调整估算口径，不影响实际扣费。
    "llm_pricing": {
        "default": {"input": 1.0, "output": 4.0},            # 兜底价（未知模型按此估）
        "deepseek-chat": {"input": 1.0, "output": 4.0},
        "deepseek-reasoner": {"input": 4.0, "output": 16.0},
        "deepseek-vl2": {"input": 1.0, "output": 4.0},       # 硅基流动等托管的 VL2 估算价
    },
    # 截图识别（OCR）策略：默认本地 PaddleOCR，零配置可用。
    # mode 可选 paddle_ocr / tesseract / baidu_ocr / vision_model：
    # - paddle_ocr ：本地 PaddleOCR（依赖 paddlepaddle，高版本 Python 可能装不上）
    # - tesseract  ：本地 Tesseract（独立 C++ 程序，与 Python 版本无关，最稳）
    # - baidu_ocr  ：百度智能云 OCR（通用文字识别·高精度版，中文准确率高、每天 1000 次免费）
    # - vision_model：云端视觉模型（需单独配一个支持 VL 的端点，见 vision 段）
    # tesseract_cmd / tessdata_dir 只在 tesseract 模式下生效；
    # tesseract_cmd 留空时自动去 PATH 和 Windows 默认安装目录里找。
    # baidu_api_key / baidu_secret_key 只在 baidu_ocr 模式下生效。
    "ocr": {
        "mode": "paddle_ocr",
        "tesseract_cmd": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        "tessdata_dir": "",
        "baidu_api_key": "",
        "baidu_secret_key": "",
    },
    "wechat": {"appid": "", "secret": ""},        # 公众号凭据（推草稿箱用）
    "daily_limit": 50,                            # 每日搜索上限（防止超额扣费）
    "custom_forbidden_words": [],                 # 用户自定义违禁词（quality.py 合规扫描用）
}

# 密钥字段 → 环境变量名。环境变量优先级高于配置文件，且永远不落盘。
# 结构：(顶层字段, 子字段, 环境变量候选名...)
SECRET_ENV_MAP: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("search_api", "api_key", ("SERPAPI_KEY", "SERPAPI_API_KEY")),
    ("deepseek", "api_key", ("DEEPSEEK_API_KEY",)),
    ("vision", "api_key", ("VISION_API_KEY",)),
    ("wechat", "appid", ("WX_APPID", "WECHAT_APPID")),
    ("wechat", "secret", ("WX_SECRET", "WECHAT_SECRET")),
    ("ocr", "baidu_api_key", ("BAIDU_OCR_API_KEY",)),
    ("ocr", "baidu_secret_key", ("BAIDU_OCR_SECRET_KEY",)),
)

# 密钥类字段名（落盘前一律置空，绝不写入配置文件）。
# 这些字段运行时只从环境变量读取（见 SECRET_ENV_MAP / _overlay_env）。
# 与 SECRET_ENV_MAP 不同：这里按「字段名」匹配所有分层，且无条件剔除，
# 不依赖环境变量是否已设置——只要叫这个名字就是密钥。
SECRET_FIELD_NAMES: frozenset[str] = frozenset(
    {"api_key", "secret", "baidu_api_key", "baidu_secret_key"}
)


def streamlit_root() -> Path:
    """现有 Streamlit 项目根目录（可用环境变量覆盖）。"""
    env = os.getenv("STREAMLIT_PROJECT_ROOT")
    return Path(env) if env else Path(DEFAULT_STREAMLIT_ROOT)


def _ensure_config_file() -> None:
    """确保配置文件存在：优先复用现有 Streamlit 配置，失败时不抛异常。

    云端首次启动时目录是空的，写盘失败（只读文件系统）也不能让整个服务挂掉，
    load_config() 会退回 DEFAULT_CONFIG + 环境变量。
    """
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_PATH.exists():
            return
        src = streamlit_root() / "workbench_config.json"
        if src.exists():
            try:
                shutil.copy(src, CONFIG_PATH)
                return
            except Exception:
                pass
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def load_config() -> dict:
    """读取配置，并做字段兜底，保证结构稳定。"""
    _ensure_config_file()
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    # 嵌套字段兜底
    cfg["hotspot_api"] = {**DEFAULT_CONFIG["hotspot_api"], **(cfg.get("hotspot_api") or {})}
    cfg["search_api"] = {**DEFAULT_CONFIG["search_api"], **(cfg.get("search_api") or {})}
    cfg["deepseek"] = {**DEFAULT_CONFIG["deepseek"], **(cfg.get("deepseek") or {})}
    cfg["vision"] = {**DEFAULT_CONFIG["vision"], **(cfg.get("vision") or {})}
    cfg["llm_pricing"] = {**DEFAULT_CONFIG["llm_pricing"], **(cfg.get("llm_pricing") or {})}
    cfg["ocr"] = {**DEFAULT_CONFIG["ocr"], **(cfg.get("ocr") or {})}
    cfg["wechat"] = {**DEFAULT_CONFIG["wechat"], **(cfg.get("wechat") or {})}
    _overlay_env(cfg)
    return cfg


def env_managed_fields() -> set[str]:
    """返回当前由环境变量托管的字段（形如 "deepseek.api_key"）。"""
    return {
        f"{sec}.{fld}"
        for sec, fld, names in SECRET_ENV_MAP
        if _env(*names)
    }


def _overlay_env(cfg: dict) -> None:
    """把环境变量里的密钥/端点覆盖到配置上（原地修改）。

    云端部署时密钥只放平台的环境变量，不进代码仓库、不写磁盘。
    本地开发不设环境变量时，行为与旧版完全一致（沿用配置文件里的值）。
    """
    for section, field, names in SECRET_ENV_MAP:
        val = _env(*names)
        if val:
            cfg.setdefault(section, {})[field] = val
    # 非密钥类的可选覆盖
    base_url = _env("DEEPSEEK_BASE_URL")
    if base_url:
        cfg["deepseek"]["base_url"] = base_url
    model = _env("DEEPSEEK_MODEL")
    if model:
        cfg["deepseek"]["model"] = model
    vision_base = _env("VISION_BASE_URL")
    if vision_base:
        cfg["vision"]["base_url"] = vision_base
    vision_model = _env("VISION_MODEL")
    if vision_model:
        cfg["vision"]["model"] = vision_model
    ocr_mode = _env("OCR_MODE")
    if ocr_mode:
        cfg["ocr"]["mode"] = ocr_mode
    tess_cmd = _env("TESSERACT_CMD")
    if tess_cmd:
        cfg["ocr"]["tesseract_cmd"] = tess_cmd
    tessdata = _env("TESSDATA_DIR", "TESSDATA_PREFIX")
    if tessdata:
        cfg["ocr"]["tessdata_dir"] = tessdata
    baidu_ak = _env("BAIDU_OCR_API_KEY")
    if baidu_ak:
        cfg["ocr"]["baidu_api_key"] = baidu_ak
    baidu_sk = _env("BAIDU_OCR_SECRET_KEY")
    if baidu_sk:
        cfg["ocr"]["baidu_secret_key"] = baidu_sk
    limit = _env("DAILY_LIMIT")
    if limit.isdigit():
        cfg["daily_limit"] = int(limit)
    if _env("SERPAPI_KEY", "SERPAPI_API_KEY"):
        cfg["search_api"]["type"] = cfg["search_api"].get("type") or "serpapi"


class ConfigWriteError(RuntimeError):
    """配置落盘失败（只读、被占用、无权限等），由路由层转成 4xx/5xx 友好提示。"""


def _clear_readonly(path: Path) -> None:
    """去掉 Windows 只读属性（配置可能是从只读源文件 copy 过来的）。"""
    try:
        if path.exists() and not (os.stat(path).st_mode & stat.S_IWRITE):
            os.chmod(path, os.stat(path).st_mode | stat.S_IWRITE)
    except Exception:
        pass


def atomic_write_json(path: Path, payload: dict, retries: int = 6) -> None:
    """原子写 JSON：先写同目录临时文件，再 os.replace 覆盖。

    Windows 上文件常被杀软/同步盘/编辑器短暂占用，直接 open(mode='w') 会抛
    PermissionError。这里用「临时文件 + 替换 + 指数退避重试」把瞬时占用扛过去，
    同时保证写一半崩溃时原文件不被截断。

    额外对 Windows PermissionError 做 remove+rename 兜底：某些情况下文件句柄
    不允许 MOVEFILE_REPLACE_EXISTING，但允许先删除再重命名。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    last_err: Exception | None = None
    for i in range(retries):
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{i}.tmp")
        try:
            _clear_readonly(path)
            tmp.write_text(text, encoding="utf-8")
            try:
                os.replace(tmp, path)          # 同盘原子替换
            except PermissionError:
                # Windows 兜底：先删目标再重命名，偶尔能绕过只读/占用句柄
                if path.exists():
                    path.unlink()
                os.rename(tmp, path)
            return
        except PermissionError as e:
            last_err = e
        except OSError as e:
            last_err = e
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
        time.sleep(0.15 * (2 ** i))        # 0.15s / 0.3s / 0.6s / 1.2s / 2.4s / 4.8s
    raise ConfigWriteError(
        f"配置写入失败：{path}（{type(last_err).__name__}）。"
        "请确认文件未被其他程序（编辑器/同步盘/杀毒软件）占用或设为只读。"
    ) from last_err


def save_config(cfg: dict) -> dict:
    """落地配置（只保留已知字段，保持向后兼容），返回保存后的完整配置。

    注意：密钥类字段（api_key / secret / baidu_api_key / baidu_secret_key）永不写入
    配置文件——落盘前一律置空，运行时仅从环境变量读取（见 SECRET_ENV_MAP / _overlay_env）。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = {k: cfg.get(k, v) for k, v in DEFAULT_CONFIG.items()}
    out["hotspot_api"] = cfg.get("hotspot_api") or DEFAULT_CONFIG["hotspot_api"]
    out["search_api"] = cfg.get("search_api") or DEFAULT_CONFIG["search_api"]
    out["deepseek"] = cfg.get("deepseek") or DEFAULT_CONFIG["deepseek"]
    out["vision"] = {**DEFAULT_CONFIG["vision"], **(cfg.get("vision") or {})}
    out["llm_pricing"] = {**DEFAULT_CONFIG["llm_pricing"], **(cfg.get("llm_pricing") or {})}
    out["ocr"] = {**DEFAULT_CONFIG["ocr"], **(cfg.get("ocr") or {})}
    out["wechat"] = cfg.get("wechat") or DEFAULT_CONFIG["wechat"]
    # 密钥字段永不落盘：无论是否配置环境变量，配置文件里这些字段都置空，
    # 运行时仅从环境变量读取（见 SECRET_ENV_MAP / _overlay_env）。
    for obj in out.values():
        if isinstance(obj, dict):
            for name in SECRET_FIELD_NAMES:
                if name in obj:
                    obj[name] = ""
    atomic_write_json(CONFIG_PATH, out)
    return load_config()


class Settings:
    """运行时只读的环境信息（脚本目录等，不随配置频繁变更）。"""

    def __init__(self) -> None:
        env = os.getenv("STREAMLIT_PROJECT_ROOT")
        if env:
            self._streamlit_root = Path(env)
        else:
            # 环境变量未设置时，回退到配置文件里的 project_root；
            # 这里不调用 load_config()，避免与 _ensure_config_file() 形成循环。
            cfg_root = ""
            try:
                if CONFIG_PATH.exists():
                    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                    cfg_root = cfg.get("project_root", "")
            except Exception:
                pass
            self._streamlit_root = Path(cfg_root) if cfg_root else Path(DEFAULT_STREAMLIT_ROOT)
        self._root_warning = ""
        self.scripts_dir = self._streamlit_root / "scripts"
        self.data_dir = self._streamlit_root / "data"

    @property
    def streamlit_root(self) -> Path:
        """现有 Streamlit 项目根目录（Path）。

        若该目录不存在：不抛异常、不崩溃，仅把友好中文提示写入
        _root_warning，由 streamlit_root_message 暴露给前端/状态接口展示。
        """
        root = self._streamlit_root
        if root.exists():
            self._root_warning = ""
        else:
            self._root_warning = (
                f"项目根目录不存在：{root}。"
                "请检查「项目根目录」配置是否正确——它应指向包含 scripts/ 与 "
                "data/issues/ 的本地 Streamlit 项目目录。可在配置页修改，或设置"
                "环境变量 STREAMLIT_PROJECT_ROOT 指向正确路径后重启后端。"
            )
        return root

    @property
    def streamlit_root_message(self) -> str:
        """项目根目录不存在时的友好提示；目录存在时返回空串。"""
        _ = self.streamlit_root  # 触发上面的校验逻辑
        return self._root_warning

    @property
    def project_root(self) -> str:
        return str(self.streamlit_root)

    @property
    def pipeline_available(self) -> bool:
        """本地流水线脚本是否可用（云端没有这些脚本 → 功能降级）。"""
        return (self.scripts_dir / "run_pipeline.py").exists()

    @property
    def is_cloud(self) -> bool:
        """是否运行在云端托管平台上。"""
        return bool(
            os.getenv("RENDER")
            or os.getenv("RAILWAY_ENVIRONMENT")
            or os.getenv("FLY_APP_NAME")
            or os.getenv("WORKBENCH_CLOUD")
        )

    @property
    def auth_enabled(self) -> bool:
        """是否开启访问鉴权（部署时开启，本地默认关）。

        用 property 实时读环境变量：部署改环境变量后无需改代码，
        也便于测试时临时置位，无需重载模块。
        """
        return os.getenv("WORKBENCH_AUTH_ENABLED", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    @property
    def auth_token(self) -> str | None:
        """鉴权令牌（Bearer 令牌值）。未配置返回 None。"""
        return os.getenv("WORKBENCH_AUTH_TOKEN") or None

    @property
    def auth_realm(self) -> str:
        """鉴权域（出现在 401 的 WWW-Authenticate 头里）。"""
        return os.getenv("WORKBENCH_AUTH_REALM", "ContentWorkbench")


settings = Settings()
