"""任务队列：把选题排成一列，后台顺序跑流水线。

设计要点：
- 队列落地 backend/data/queue.json，后端重启不丢任务。
- 顺序执行（一次只跑一条流水线），避免多个 run_pipeline.py 抢同一个期号目录。
- 复用 services/pipeline.py 启动流水线，不重写任何 Python 逻辑。
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime

from ..config import DATA_DIR
from . import pipeline

_STORE = DATA_DIR / "queue.json"
_LOCK = threading.RLock()
_ITEMS: list[dict] = []
_RUNNER: threading.Thread | None = None
_STOP = threading.Event()
_LOADED = False

# 单条任务轮询流水线状态的最长时间（秒），防止卡死队列
_MAX_WAIT_SEC = 30 * 60


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    try:
        if _STORE.exists():
            data = json.loads(_STORE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for it in data:
                    # 上次异常退出时残留的 running 视为失败，避免永远卡住
                    if it.get("status") == "running":
                        it["status"] = "failed"
                        it["error"] = it.get("error") or "后端重启，任务中断"
                _ITEMS.extend(data)
    except Exception:
        pass


def _save() -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _STORE.write_text(
            json.dumps(_ITEMS, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def add(topic: str, angle: str = "", extra: str = "",
        platform: str = "wechat", source: str = "manual") -> dict:
    """加入队列，返回新任务。"""
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("选题主题不能为空")
    item = {
        "id": uuid.uuid4().hex[:10],
        "topic": topic,
        "angle": (angle or "").strip(),
        "extra": (extra or "").strip(),
        "platform": platform or "wechat",
        "source": source,          # manual / topic / tasks / schedule
        "status": "waiting",       # waiting / running / success / failed
        "issue": None,
        "task_id": None,
        "error": None,
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
    }
    with _LOCK:
        _load()
        _ITEMS.append(item)
        _save()
    return item


def add_many(items: list[dict], source: str = "manual") -> list[dict]:
    out = []
    for it in items or []:
        try:
            out.append(add(
                it.get("topic", ""), it.get("angle", ""), it.get("extra", ""),
                it.get("platform", "wechat"), source,
            ))
        except ValueError:
            continue
    return out


def remove(item_id: str) -> bool:
    with _LOCK:
        _load()
        for i, it in enumerate(_ITEMS):
            if it["id"] == item_id:
                if it["status"] == "running":
                    return False  # 正在跑的不允许删
                _ITEMS.pop(i)
                _save()
                return True
    return False


def clear(only_finished: bool = False) -> int:
    """清空队列。only_finished=True 时只清掉已完成/失败的。"""
    with _LOCK:
        _load()
        before = len(_ITEMS)
        if only_finished:
            keep = [it for it in _ITEMS if it["status"] in ("waiting", "running")]
        else:
            keep = [it for it in _ITEMS if it["status"] == "running"]
        _ITEMS[:] = keep
        _save()
        return before - len(_ITEMS)


def stats() -> dict:
    with _LOCK:
        _load()
        return {
            "waiting": sum(1 for i in _ITEMS if i["status"] == "waiting"),
            "running": sum(1 for i in _ITEMS if i["status"] == "running"),
            "success": sum(1 for i in _ITEMS if i["status"] == "success"),
            "failed": sum(1 for i in _ITEMS if i["status"] == "failed"),
            "total": len(_ITEMS),
        }


def snapshot() -> dict:
    with _LOCK:
        _load()
        running = _RUNNER is not None and _RUNNER.is_alive()
        return {
            "items": [dict(i) for i in _ITEMS],
            "stats": stats(),
            "is_running": running,
        }


# --------------------------------------------------------------------------
# 执行
# --------------------------------------------------------------------------
def _next_waiting() -> dict | None:
    for it in _ITEMS:
        if it["status"] == "waiting":
            return it
    return None


def _run_loop() -> None:
    """顺序取出等待中的任务并执行，跑完自然退出。"""
    while not _STOP.is_set():
        with _LOCK:
            item = _next_waiting()
            if not item:
                break
            item["status"] = "running"
            item["started_at"] = _now()
            _save()
            topic, angle, extra, platform = (
                item["topic"], item["angle"], item["extra"], item["platform"]
            )
            item_id = item["id"]

        try:
            res = pipeline.start(topic=topic, angle=angle, extra=extra, platform=platform)
            task_id, issue = res["task_id"], res["issue"]
            with _LOCK:
                cur = _find(item_id)
                if cur:
                    cur["task_id"], cur["issue"] = task_id, issue
                    _save()

            waited = 0.0
            while waited < _MAX_WAIT_SEC and not _STOP.is_set():
                time.sleep(2)
                waited += 2
                st = pipeline.get_status(task_id)
                if not st:
                    continue
                if st["status"] in ("success", "failed"):
                    with _LOCK:
                        cur = _find(item_id)
                        if cur:
                            cur["status"] = st["status"]
                            cur["error"] = st.get("error")
                            cur["finished_at"] = _now()
                            _save()
                    break
            else:
                with _LOCK:
                    cur = _find(item_id)
                    if cur and cur["status"] == "running":
                        cur["status"] = "failed"
                        cur["error"] = "执行超时（超过 30 分钟）"
                        cur["finished_at"] = _now()
                        _save()
        except Exception as e:
            with _LOCK:
                cur = _find(item_id)
                if cur:
                    cur["status"] = "failed"
                    cur["error"] = f"{type(e).__name__}: {e}"
                    cur["finished_at"] = _now()
                    _save()


def _find(item_id: str) -> dict | None:
    for it in _ITEMS:
        if it["id"] == item_id:
            return it
    return None


def start() -> dict:
    """开始执行队列（幂等：已在跑就直接返回）。"""
    global _RUNNER
    with _LOCK:
        _load()
        if _RUNNER is not None and _RUNNER.is_alive():
            return {"started": False, "reason": "队列已在执行中", **stats()}
        if not _next_waiting():
            return {"started": False, "reason": "队列中没有等待执行的任务", **stats()}
        _STOP.clear()
        _RUNNER = threading.Thread(target=_run_loop, daemon=True)
        _RUNNER.start()
        return {"started": True, **stats()}


def is_running() -> bool:
    return _RUNNER is not None and _RUNNER.is_alive()
