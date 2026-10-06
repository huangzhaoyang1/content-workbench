"""config.save_config 不落盘密钥字段 + Settings 读取 project_root 的回归测试。

验证：
1. api_key / secret / baidu_api_key / baidu_secret_key 无论是否配环境变量，
   落盘后必须为空；其余非密钥字段正常读写。
2. STREAMLIT_PROJECT_ROOT 未设置时，Settings 会回退读取配置文件里的 project_root。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_save_config_strips_secret_fields():
    from backend.services.system import config

    cfg = {
        "account_name": "测试号",
        "deepseek": {"base_url": "https://x/v1", "api_key": "sk-TOPSECRET", "model": "deepseek-chat"},
        "wechat": {"appid": "wx_pub_id", "secret": "wx_secret_value"},
        "ocr": {"mode": "baidu_ocr", "baidu_api_key": "ak123", "baidu_secret_key": "sk456"},
        "search_api": {"type": "serpapi", "api_key": "serp_key"},
        "vision": {"base_url": "", "api_key": "vl_key", "model": "deepseek-vl2"},
        "hotspot_api": {"api_url": "http://h", "api_key": "hot_key", "timeout": 10},
    }
    config.save_config(cfg)
    saved = json.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))
    # 所有密钥字段落盘后必须为空（绝不含真实值）
    assert saved["deepseek"]["api_key"] == ""
    assert saved["wechat"]["secret"] == ""
    assert saved["ocr"]["baidu_api_key"] == ""
    assert saved["ocr"]["baidu_secret_key"] == ""
    assert saved["search_api"]["api_key"] == ""
    assert saved["vision"]["api_key"] == ""
    assert saved["hotspot_api"]["api_key"] == ""
    # 非密钥字段正常保留
    assert saved["account_name"] == "测试号"
    assert saved["deepseek"]["base_url"] == "https://x/v1"
    assert saved["wechat"]["appid"] == "wx_pub_id"
    assert saved["ocr"]["mode"] == "baidu_ocr"


def test_save_config_persists_non_secret_fields():
    from backend.services.system import config

    cfg = {"account_name": "另一号", "daily_limit": 7}
    config.save_config(cfg)
    saved = json.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))
    assert saved["account_name"] == "另一号"
    assert saved["daily_limit"] == 7


def test_settings_falls_back_to_config_project_root():
    """无 STREAMLIT_PROJECT_ROOT 环境变量时，Settings 从配置文件读取 project_root。"""
    from backend.services.system import config

    with tempfile.TemporaryDirectory(prefix="wb_settings_") as tmp:
        stream_root = os.path.join(tmp, "stream")
        data_dir = os.path.join(tmp, "data")
        os.makedirs(stream_root, exist_ok=True)
        os.makedirs(data_dir, exist_ok=True)
        # 创建模拟流水线脚本
        os.makedirs(os.path.join(stream_root, "scripts"), exist_ok=True)
        Path(os.path.join(stream_root, "scripts", "run_pipeline.py")).write_text("# stub")

        cfg = config.DEFAULT_CONFIG.copy()
        cfg["project_root"] = stream_root
        config_path = Path(data_dir) / "workbench_config.json"
        config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

        env = os.environ.copy()
        env["WORKBENCH_DATA_DIR"] = data_dir
        env.pop("STREAMLIT_PROJECT_ROOT", None)

        repo_root = Path(__file__).resolve().parents[2]
        code = (
            "import sys; "
            f"sys.path.insert(0, r'{repo_root}'); "
            "from backend.services.system import config; "
            "print('STREAMLIT_ROOT=', config.settings.streamlit_root); "
            "print('PIPELINE_AVAILABLE=', config.settings.pipeline_available)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert f"STREAMLIT_ROOT= {stream_root}" in result.stdout
        assert "PIPELINE_AVAILABLE= True" in result.stdout
