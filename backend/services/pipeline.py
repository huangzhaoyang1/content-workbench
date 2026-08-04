"""流水线调度：调用现有 scripts/run_pipeline.py，后台执行并实时收集日志。

设计：单进程内存任务表（Phase 2 足够；生产可换 Redis/DB）。
后台线程只把日志追加到 task["logs"] 列表，主线程读状态即可，无共享状态冲突。
"""
from __future__ import annotations

import os
import subprocess
import threading
import uuid
from datetime import datetime

from ..config import settings, load_config

# 内存任务存储：task_id -> task dict
_TASKS: dict[str, dict] = {}
_LOCK = threading.Lock()


class PipelineUnavailable(RuntimeError):
    """本地流水线脚本不可用（典型场景：部署在云端，机器上没有 scripts/）。"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def availability() -> dict:
    """流水线可用性，用于前端提前禁用按钮 / 给出说明。"""
    script = settings.scripts_dir / "run_pipeline.py"
    ok = script.exists()
    if ok:
        return {"available": True, "reason": "", "scripts_dir": str(settings.scripts_dir)}
    reason = (
        "当前后端运行在云端，没有本地流水线脚本（scripts/run_pipeline.py），"
        "出稿功能请在本机启动后端使用；线上仅支持热点搜索与选题生成。"
        if settings.is_cloud
        else f"未找到流水线脚本：{script}。请在配置页把「项目根目录」指向包含 scripts/ 的本地项目。"
    )
    return {"available": False, "reason": reason, "scripts_dir": str(settings.scripts_dir)}


def _next_issue() -> int:
    """取 data/issues 下最大数字期号 +1（与现有脚本逻辑一致）。"""
    issues_dir = settings.streamlit_root / "data" / "issues"
    if not issues_dir.is_dir():
        return 1
    nums = [int(n) for n in os.listdir(issues_dir) if n.isdigit()]
    return (max(nums) + 1) if nums else 1


def start(topic: str, angle: str = "", extra: str = "",
          references: str = "", platform: str = "wechat") -> dict:
    """启动一次流水线，返回 {task_id, issue}。实际执行在后台线程进行。"""
    avail = availability()
    if not avail["available"]:
        raise PipelineUnavailable(avail["reason"])
    cfg = load_config()
    py = cfg.get("python_path") or "python"
    script = settings.scripts_dir / "run_pipeline.py"
    issue = _next_issue()
    task_id = uuid.uuid4().hex[:12]
    cmd = [
        py, str(script),
        "--topic", topic,
        "--angle", angle or "",
        "--platform", platform,
        "--extra", extra or "",
        "--references", references or "",
    ]
    task = {
        "task_id": task_id,
        "issue": issue,
        "topic": topic,
        "angle": angle,
        "platform": platform,
        "status": "pending",
        "logs": [],
        "returncode": None,
        "error": None,
        "created_at": _now(),
        "finished_at": None,
    }
    with _LOCK:
        _TASKS[task_id] = task
    threading.Thread(target=_run, args=(task_id, cmd), daemon=True).start()
    return {"task_id": task_id, "issue": issue}


def _run(task_id: str, cmd: list[str]) -> None:
    task = _TASKS.get(task_id)
    if not task:
        return
    task["status"] = "running"
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(settings.streamlit_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            task["logs"].append(line.rstrip("\n"))
        proc.wait()
        task["returncode"] = proc.returncode
        task["status"] = "success" if proc.returncode == 0 else "failed"
        if proc.returncode != 0:
            task["error"] = task["logs"][-1] if task["logs"] else "非零退出码"
    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        task["logs"].append(f"[error] {e}")
    task["finished_at"] = _now()


def get_status(task_id: str) -> dict | None:
    """查询任务状态（含实时日志）。"""
    return _TASKS.get(task_id)
