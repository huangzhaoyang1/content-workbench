"""流水线调度：调用现有 scripts/run_pipeline.py，后台执行并实时收集日志。

设计：单进程内存任务表（Phase 2 足够；生产可换 Redis/DB）。
后台线程只把日志追加到 task["logs"] 列表，主线程读状态即可，无共享状态冲突。
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from datetime import datetime

from ..system.config import settings, load_config

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
          references: str = "", platform: str = "wechat",
          review: bool = False) -> dict:
    """启动一次流水线，返回 {task_id, issue}。实际执行在后台线程进行。

    review=True 时追加 --no-publish：只产出本地文章+封面，草稿存为「待审核」，
    不推送公众号，等用户在工作台审核后「确认发布」。
    """
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
        "--issue", str(issue),
    ]
    if review:
        cmd.append("--no-publish")
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
        "review": review,
        "action": "produce",
    }
    with _LOCK:
        _TASKS[task_id] = task
    threading.Thread(target=_run_sync, args=(task_id, cmd), daemon=True).start()
    return {"task_id": task_id, "issue": issue}


def publish(issue: int, cover_label: str = "") -> dict:
    """把已存为「待审核」的某期推送到公众号。后台线程执行，返回 {task_id, issue}。

    cover_label 非空时，封面右上角绘制该文字替代默认「第N期」（合集期号由用户手动指定）。
    """
    avail = availability()
    if not avail["available"]:
        raise PipelineUnavailable(avail["reason"])
    cfg = load_config()
    py = cfg.get("python_path") or "python"
    script = settings.scripts_dir / "run_pipeline.py"
    task_id = uuid.uuid4().hex[:12]
    cmd = [py, str(script), "--issue", str(issue), "--publish-only"]
    if cover_label and cover_label.strip():
        cmd += ["--cover-label", cover_label.strip()]
    task = {
        "task_id": task_id,
        "issue": issue,
        "topic": "",
        "angle": "",
        "platform": "wechat",
        "status": "pending",
        "logs": [],
        "returncode": None,
        "error": None,
        "created_at": _now(),
        "finished_at": None,
        "review": False,
        "action": "publish",
    }
    with _LOCK:
        _TASKS[task_id] = task
    threading.Thread(target=_run_sync, args=(task_id, cmd), daemon=True).start()
    return {"task_id": task_id, "issue": issue}


def discard(issue: int) -> dict:
    """把「待审核」的某期标记为放弃：只改本地 result.json，不调用微信。"""
    issues_dir = settings.streamlit_root / "data" / "issues" / str(issue)
    rp = issues_dir / "result.json"
    if not rp.exists():
        return {"ok": False, "reason": f"找不到该期 result.json：{rp}"}
    try:
        with open(rp, encoding="utf-8") as f:
            data = json.load(f)
        data["draft_status"] = "DISCARDED"
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": str(e)}


async def _run(task_id: str, cmd: list[str]) -> None:
    task = _TASKS.get(task_id)
    if not task:
        return
    task["status"] = "running"
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(settings.streamlit_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        async for line in proc.stdout:
            # rstrip("\r\n") 复刻原 text=True 的 universal-newline 行为（\r\n / \r -> 干净行尾）
            task["logs"].append(line.decode("utf-8", errors="replace").rstrip("\r\n"))
        await proc.wait()
        task["returncode"] = proc.returncode
        task["status"] = "success" if proc.returncode == 0 else "failed"
        if proc.returncode != 0:
            task["error"] = task["logs"][-1] if task["logs"] else "非零退出码"
    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        task["logs"].append(f"[error] {e}")
    task["finished_at"] = _now()
    _schedule_cleanup(task_id)


def _run_sync(task_id: str, cmd: list[str]) -> None:
    """同步包装：在后台线程里跑事件循环驱动异步 _run。

    start()/publish() 是同步调用且需立即返回，故仍用线程后台执行；
    此处用 asyncio.run 驱动协程，保持原有的「非阻塞后台执行」语义不变。
    """
    asyncio.run(_run(task_id, cmd))


def _schedule_cleanup(task_id: str, delay: int = 300) -> None:
    """任务完成后延迟 delay 秒从 _TASKS 移除该记录（非阻塞：后台 Timer 线程）。

    删除前加锁复核任务仍为终态（success/failed），避免误删仍在运行或被重置的任务。
    """
    def _remove() -> None:
        with _LOCK:
            task = _TASKS.get(task_id)
            if task is None:
                return
            if task.get("status") in ("success", "failed"):
                _TASKS.pop(task_id, None)

    timer = threading.Timer(delay, _remove)
    timer.daemon = True
    timer.start()


def get_status(task_id: str) -> dict | None:
    """查询任务状态（含实时日志）。"""
    return _TASKS.get(task_id)
