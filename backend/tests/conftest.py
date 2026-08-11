"""pytest 全局配置：把后端数据目录隔离到临时目录，确保测试绝不碰真实数据。

关键：环境变量必须在 import backend 之前设置，因为 config 模块在导入时
就会读取 WORKBENCH_DATA_DIR / STREAMLIT_PROJECT_ROOT 决定 DATA_DIR 与
settings.streamlit_root。conftest 在测试模块导入前被 pytest 加载，所以放在
这里的模块顶层最安全。
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="wb_test_")
DATA_DIR = os.path.join(_TMP, "data")
STREAM_ROOT = os.path.join(_TMP, "stream")
os.environ["WORKBENCH_DATA_DIR"] = DATA_DIR
os.environ["STREAMLIT_PROJECT_ROOT"] = STREAM_ROOT
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STREAM_ROOT, exist_ok=True)


def _cleanup() -> None:
    # 测试临时数据落在系统 temp，清理失败（如被安全删除钩子拦到回收站）也不影响。
    shutil.rmtree(_TMP, ignore_errors=True)


atexit.register(_cleanup)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_data():
    """每个用例开始前清空持久化文件与目录，保证用例间相互独立。"""
    paths = [
        os.path.join(DATA_DIR, "topic_library.json"),
        os.path.join(DATA_DIR, "topic_trash.json"),
        os.path.join(DATA_DIR, "topic_versions.json"),
        os.path.join(DATA_DIR, "task_tags.json"),
    ]
    for p in paths:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        except Exception:
            pass
    for d in (
        os.path.join(STREAM_ROOT, "data", "issues"),
        os.path.join(STREAM_ROOT, "data", "issues_trash"),
    ):
        shutil.rmtree(d, ignore_errors=True)
    yield
