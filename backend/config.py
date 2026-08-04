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

# 后端自身目录
BACKEND_DIR = Path(__file__).resolve().parent
# 数据目录可用 WORKBENCH_DATA_DIR 覆盖（云平台上可指向可写卷）
DATA_DIR = Path(os.getenv("WORKBENCH_DATA_DIR") or (BACKEND_DIR / "data"))
CONFIG_PATH = DATA_DIR / "workbench_config.json"

# 现有 Streamlit 项目根目录（内含 scripts/ 与 data/issues/）
# 本地开发指向 Windows 上的老项目；云端不存在该目录，流水线功能自动降级。
DEFAULT_STREAMLIT_ROOT = r"C:\Users\黄朝扬\WorkBuddy\简约风格"


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
    "style": "",                                  # 文风要求
    "visual_style": "",                           # 视觉风格
    "hotspot_api": {"api_url": "", "api_key": "", "timeout": 10, "method": "GET"},
    "scheduled_tasks": [],                        # 定时任务列表
    # 智能搜索配置（SerpAPI 真实搜索 + DeepSeek 智能分析）
    "search_api": {"type": "serpapi", "api_key": ""},   # type: serpapi / custom
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "api_key": "", "model": "deepseek-chat"},
    "wechat": {"appid": "", "secret": ""},        # 公众号凭据（推草稿箱用）
    "daily_limit": 50,                            # 每日搜索上限（防止超额扣费）
}

# 密钥字段 → 环境变量名。环境变量优先级高于配置文件，且永远不落盘。
# 结构：(顶层字段, 子字段, 环境变量候选名...)
SECRET_ENV_MAP: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("search_api", "api_key", ("SERPAPI_KEY", "SERPAPI_API_KEY")),
    ("deepseek", "api_key", ("DEEPSEEK_API_KEY",)),
    ("wechat", "appid", ("WX_APPID", "WECHAT_APPID")),
    ("wechat", "secret", ("WX_SECRET", "WECHAT_SECRET")),
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


def atomic_write_json(path: Path, payload: dict, retries: int = 4) -> None:
    """原子写 JSON：先写同目录临时文件，再 os.replace 覆盖。

    Windows 上文件常被杀软/同步盘/编辑器短暂占用，直接 open(mode='w') 会抛
    PermissionError。这里用「临时文件 + 替换 + 指数退避重试」把瞬时占用扛过去，
    同时保证写一半崩溃时原文件不被截断。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    last_err: Exception | None = None
    for i in range(retries):
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{i}.tmp")
        try:
            _clear_readonly(path)
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)          # 同盘原子替换
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
        time.sleep(0.15 * (2 ** i))        # 0.15s / 0.3s / 0.6s / 1.2s
    raise ConfigWriteError(
        f"配置写入失败：{path}（{type(last_err).__name__}）。"
        "请确认文件未被其他程序（编辑器/同步盘/杀毒软件）占用或设为只读。"
    ) from last_err


def save_config(cfg: dict) -> dict:
    """落地配置（只保留已知字段，保持向后兼容），返回保存后的完整配置。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = {k: cfg.get(k, v) for k, v in DEFAULT_CONFIG.items()}
    out["hotspot_api"] = cfg.get("hotspot_api") or DEFAULT_CONFIG["hotspot_api"]
    out["search_api"] = cfg.get("search_api") or DEFAULT_CONFIG["search_api"]
    out["deepseek"] = cfg.get("deepseek") or DEFAULT_CONFIG["deepseek"]
    out["wechat"] = cfg.get("wechat") or DEFAULT_CONFIG["wechat"]
    # 由环境变量托管的密钥不落盘：避免云端把 key 写进容器磁盘 / 本地误提交。
    for section, field, names in SECRET_ENV_MAP:
        if _env(*names):
            out.setdefault(section, {})[field] = ""
    atomic_write_json(CONFIG_PATH, out)
    return load_config()


class Settings:
    """运行时只读的环境信息（脚本目录等，不随配置频繁变更）。"""

    def __init__(self) -> None:
        self.streamlit_root = streamlit_root()
        self.scripts_dir = self.streamlit_root / "scripts"
        self.data_dir = self.streamlit_root / "data"

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


settings = Settings()
