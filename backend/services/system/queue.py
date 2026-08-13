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

from .config import DATA_DIR
from ..content import pipeline, dissect

_STORE = DATA_DIR / "queue.json"
_LOCK = threading.RLock()
_ITEMS: list[dict] = []
_RUNNER: threading.Thread | None = None
_STOP = threading.Event()
_SKIP_CURRENT = threading.Event()  # 置位后通知执行循环跳过当前任务
_LOADED = False

# 单条任务轮询流水线状态的最长时间（秒），防止卡死队列
_MAX_WAIT_SEC = 10 * 60


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    changed = False
    try:
        if _STORE.exists():
            data = json.loads(_STORE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for it in data:
                    # 上次异常退出时残留的 running：
                    #   定时任务(schedule) 回退 waiting 以便重启后重新调度；
                    #   其余来源视为失败，避免永远卡住。
                    if it.get("status") == "running":
                        changed = True
                        if it.get("source") == "schedule":
                            it["status"] = "waiting"
                            it["error"] = it.get("error") or "后端重启，定时任务中断，已重新排队"
                        else:
                            it["status"] = "failed"
                            it["error"] = it.get("error") or "后端重启，任务中断"
                _ITEMS.extend(data)
    except Exception:
        pass
    # 状态恢复后立刻落盘，避免下次启动又重复处理同一批中断任务
    if changed:
        _save()


def _save() -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _STORE.write_text(
            json.dumps(_ITEMS, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def add(topic: str, angle: str = "", extra: str = "",
        platform: str = "wechat", source: str = "manual",
        topic_id: str = "", review: bool = False) -> dict:
    """加入队列，返回新任务。topic_id 可选，用于和「选题库」联动翻转状态。

    review=True 时透传给 pipeline.start，流水线只产出本地文章+封面，
    草稿存为「待审核」（不推送微信）。用于抖音线等希望先审后发的场景。
    旧条目/旧调用无 review 字段时默认 False，行为不变。
    """
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
        "topic_id": (topic_id or "").strip(),  # 关联选题库条目 id（可为空）
        "review": bool(review),    # 透传：是否走「待审核」而非直推微信
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
                it.get("topic_id", ""),
                it.get("review", False),
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


def skip_current() -> dict:
    """跳过当前正在执行的任务：标记为 skipped，并让执行循环继续下一条。

    返回 {ok, id?}；没有正在执行的任务时 ok=False（带中文 reason）。
    """
    with _LOCK:
        _load()
        cur = next((it for it in _ITEMS if it["status"] == "running"), None)
        if not cur:
            return {"ok": False, "reason": "当前没有正在执行的任务"}
        # 执行线程还在跑 → 用事件通知它跳出；线程已死（异常态）→ 直接标记
        if _RUNNER is not None and _RUNNER.is_alive():
            _SKIP_CURRENT.set()
        else:
            cur["status"] = "skipped"
            cur["error"] = "用户已跳过"
            cur["finished_at"] = _now()
            _save()
            _flip_topic(cur.get("topic_id") or "", "待生产")
    return {"ok": True, "id": cur["id"]}


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


def _flip_topic(topic_id: str, status: str) -> None:
    """把关联的选题库条目状态翻到指定值。选题不存在时静默忽略，绝不影响流水线。"""
    if not topic_id:
        return
    try:
        dissect.update_topic(topic_id, status=status)
    except Exception:
        pass


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
            review = bool(item.get("review", False))  # 透传：旧条目无此字段默认 False

        # 联动选题库：开始生产即标记「生产中」
        _flip_topic(item.get("topic_id") or "", "生产中")

        final_status: str | None = None
        try:
            res = pipeline.start(topic=topic, angle=angle, extra=extra, platform=platform, review=review)
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
                if _SKIP_CURRENT.is_set():
                    # 用户点了「跳过当前任务」：标记 skipped，跳出轮询，继续下一条
                    _SKIP_CURRENT.clear()
                    with _LOCK:
                        cur = _find(item_id)
                        if cur:
                            cur["status"] = "skipped"
                            cur["error"] = "用户已跳过"
                            cur["finished_at"] = _now()
                            _save()
                    final_status = "待生产"
                    break
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
                    final_status = "已完成" if st["status"] == "success" else "待生产"
                    break
            else:
                with _LOCK:
                    cur = _find(item_id)
                    if cur and cur["status"] == "running":
                        cur["status"] = "failed"
                        cur["error"] = f"执行超时（超过 {_MAX_WAIT_SEC // 60} 分钟）"
                        cur["finished_at"] = _now()
                        _save()
                final_status = "待生产"
        except Exception as e:
            with _LOCK:
                cur = _find(item_id)
                if cur:
                    cur["status"] = "failed"
                    cur["error"] = f"{type(e).__name__}: {e}"
                    cur["finished_at"] = _now()
                    _save()
            final_status = "待生产"

        # 联动选题库：成功→已完成；失败/超时/异常→回退「待生产」以便重试
        if final_status:
            _flip_topic(item.get("topic_id") or "", final_status)


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
