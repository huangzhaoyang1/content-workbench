"""定时任务：按每天 / 每周 / 自定义 cron 的节奏，把选题自动投进任务队列。

设计要点：
- 不引入 APScheduler/croniter，内置一个最小 cron 匹配器（标准 5 字段），依赖为零。
- 后台每 30 秒 tick 一次，命中就入队；同一分钟不会重复触发（按 last_fire_key 去重）。
- 数据落地 backend/data/schedule.json，与 workbench_config.json 解耦，配置文件格式不变。
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta

from ..config import DATA_DIR
from . import queue as task_queue

_STORE = DATA_DIR / "schedule.json"
_LOCK = threading.RLock()
_JOBS: list[dict] = []
_LOADED = False
_TICKER: threading.Thread | None = None
_STOP = threading.Event()

_TICK_SEC = 30
FREQUENCIES = ("daily", "weekly", "cron")
_WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class ScheduleError(Exception):
    """定时任务配置错误，路由层转 400。"""


# --------------------------------------------------------------------------
# 极简 cron（分 时 日 月 周），支持 * / */n / a-b / a,b,c / 数字
# --------------------------------------------------------------------------
def _parse_field(expr: str, lo: int, hi: int) -> set[int]:
    values: set[int] = set()
    for part in str(expr).split(","):
        part = part.strip()
        if not part:
            raise ScheduleError(f"cron 字段为空：{expr}")
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            try:
                step = int(step_s)
            except ValueError:
                raise ScheduleError(f"cron 步长非法：{step_s}")
            if step <= 0:
                raise ScheduleError("cron 步长必须大于 0")
            part = part or "*"
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, _, b = part.partition("-")
            try:
                start, end = int(a), int(b)
            except ValueError:
                raise ScheduleError(f"cron 区间非法：{part}")
        else:
            try:
                start = end = int(part)
            except ValueError:
                raise ScheduleError(f"cron 取值非法：{part}")
        if start < lo or end > hi or start > end:
            raise ScheduleError(f"cron 取值超出范围（{lo}-{hi}）：{part}")
        values.update(range(start, end + 1, step))
    if not values:
        raise ScheduleError(f"cron 字段无有效取值：{expr}")
    return values


def parse_cron(expr: str) -> list[set[int]]:
    """解析 5 字段 cron，返回 [分, 时, 日, 月, 周] 的取值集合。"""
    fields = str(expr or "").split()
    if len(fields) != 5:
        raise ScheduleError("cron 需要 5 个字段：分 时 日 月 周，例如 30 18 * * *")
    bounds = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
    return [_parse_field(f, lo, hi) for f, (lo, hi) in zip(fields, bounds)]


def _cron_match(sets: list[set[int]], dt: datetime) -> bool:
    minute, hour, dom, month, dow = sets
    # cron 里周日既可写 0 也可写 7；Python weekday(): 周一=0…周日=6
    py_dow = dt.weekday()
    cron_dow = (py_dow + 1) % 7  # 转成 周日=0 的习惯写法
    return (
        dt.minute in minute
        and dt.hour in hour
        and dt.day in dom
        and dt.month in month
        and (cron_dow in dow or (cron_dow == 0 and 7 in dow))
    )


def cron_next(expr: str, after: datetime | None = None, limit_days: int = 366) -> datetime | None:
    """从 after 之后逐分钟找下一个命中时间（最多找一年）。"""
    sets = parse_cron(expr)
    cur = (after or datetime.now()).replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = cur + timedelta(days=limit_days)
    while cur < end:
        if _cron_match(sets, cur):
            return cur
        cur += timedelta(minutes=1)
    return None


# --------------------------------------------------------------------------
# 下次执行时间
# --------------------------------------------------------------------------
def _parse_hhmm(t: str) -> tuple[int, int]:
    try:
        h, m = str(t or "").split(":")
        h, m = int(h), int(m)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
        return h, m
    except Exception:
        raise ScheduleError("执行时间格式应为 HH:MM，例如 18:30")


def compute_next_run(job: dict, after: datetime | None = None) -> str | None:
    """算出下次执行时间字符串；禁用的任务返回 None。"""
    if not job.get("enabled"):
        return None
    now = (after or datetime.now()).replace(second=0, microsecond=0)
    freq = job.get("frequency")
    if freq == "cron":
        nxt = cron_next(job.get("cron") or "", now)
        return nxt.strftime("%Y-%m-%d %H:%M") if nxt else None
    h, m = _parse_hhmm(job.get("time") or "09:00")
    if freq == "daily":
        cand = now.replace(hour=h, minute=m)
        if cand <= now:
            cand += timedelta(days=1)
        return cand.strftime("%Y-%m-%d %H:%M")
    if freq == "weekly":
        try:
            wd = int(job.get("weekday", 0))
        except (TypeError, ValueError):
            wd = 0
        wd = max(0, min(6, wd))
        cand = now.replace(hour=h, minute=m)
        delta = (wd - cand.weekday()) % 7
        cand += timedelta(days=delta)
        if cand <= now:
            cand += timedelta(days=7)
        return cand.strftime("%Y-%m-%d %H:%M")
    raise ScheduleError(f"不支持的频率：{freq}")


def describe(job: dict) -> str:
    """给前端一句人话描述。"""
    freq = job.get("frequency")
    if freq == "daily":
        return f"每天 {job.get('time') or '—'}"
    if freq == "weekly":
        try:
            wd = _WEEKDAY_LABELS[int(job.get("weekday", 0))]
        except Exception:
            wd = "周一"
        return f"每{wd[1:]} {job.get('time') or '—'}"
    if freq == "cron":
        return f"cron: {job.get('cron') or '—'}"
    return "—"


# --------------------------------------------------------------------------
# 存储
# --------------------------------------------------------------------------
def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    try:
        if _STORE.exists():
            data = json.loads(_STORE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                _JOBS.extend(data)
    except Exception:
        pass


def _save() -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _STORE.write_text(
            json.dumps(_JOBS, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _validate(payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ScheduleError("任务名称不能为空")
    topic = (payload.get("topic") or "").strip()
    if not topic:
        raise ScheduleError("选题主题不能为空")
    freq = payload.get("frequency") or "daily"
    if freq not in FREQUENCIES:
        raise ScheduleError("频率只能是 daily / weekly / cron")
    job = {
        "name": name,
        "topic": topic,
        "angle": (payload.get("angle") or "").strip(),
        "extra": (payload.get("extra") or "").strip(),
        "platform": payload.get("platform") or "wechat",
        "frequency": freq,
        "time": payload.get("time") or "09:00",
        "weekday": int(payload.get("weekday") or 0),
        "cron": (payload.get("cron") or "").strip(),
        "enabled": bool(payload.get("enabled", True)),
    }
    if freq == "cron":
        parse_cron(job["cron"])       # 提前校验，非法直接报错
    else:
        _parse_hhmm(job["time"])
    return job


def _decorate(job: dict) -> dict:
    out = dict(job)
    out["freq_label"] = describe(job)
    return out


def list_jobs() -> list[dict]:
    with _LOCK:
        _load()
        return [_decorate(j) for j in _JOBS]


def create(payload: dict) -> dict:
    job = _validate(payload)
    job.update({
        "id": uuid.uuid4().hex[:10],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_run": None,
        "last_result": None,
        "run_count": 0,
    })
    job["next_run"] = compute_next_run(job)
    with _LOCK:
        _load()
        _JOBS.append(job)
        _save()
    _ensure_ticker()
    return _decorate(job)


def update(job_id: str, payload: dict) -> dict | None:
    with _LOCK:
        _load()
        for j in _JOBS:
            if j["id"] != job_id:
                continue
            # 只切开关时允许省略其它字段
            if set(payload.keys()) <= {"enabled"}:
                j["enabled"] = bool(payload.get("enabled"))
            else:
                merged = {**j, **payload}
                j.update(_validate(merged))
            j["next_run"] = compute_next_run(j)
            _save()
            _ensure_ticker()
            return _decorate(j)
    return None


def delete(job_id: str) -> bool:
    with _LOCK:
        _load()
        for i, j in enumerate(_JOBS):
            if j["id"] == job_id:
                _JOBS.pop(i)
                _save()
                return True
    return False


# --------------------------------------------------------------------------
# 调度线程
# --------------------------------------------------------------------------
def _tick() -> None:
    now = datetime.now().replace(second=0, microsecond=0)
    fired: list[dict] = []
    with _LOCK:
        _load()
        for j in _JOBS:
            if not j.get("enabled"):
                j["next_run"] = None
                continue
            nxt = j.get("next_run")
            if not nxt:
                try:
                    j["next_run"] = compute_next_run(j, now)
                except ScheduleError:
                    j["enabled"] = False
                continue
            try:
                nxt_dt = datetime.strptime(nxt, "%Y-%m-%d %H:%M")
            except ValueError:
                j["next_run"] = compute_next_run(j, now)
                continue
            if now >= nxt_dt:
                fired.append(dict(j))
                j["last_run"] = now.strftime("%Y-%m-%d %H:%M")
                j["run_count"] = int(j.get("run_count") or 0) + 1
                try:
                    j["next_run"] = compute_next_run(j, now)
                except ScheduleError:
                    j["enabled"] = False
                    j["next_run"] = None
        if fired:
            _save()

    for j in fired:
        try:
            task_queue.add(
                topic=j["topic"], angle=j.get("angle", ""), extra=j.get("extra", ""),
                platform=j.get("platform", "wechat"), source="schedule",
            )
            _set_result(j["id"], "已入队")
        except Exception as e:
            _set_result(j["id"], f"入队失败：{type(e).__name__}")
    if fired:
        try:
            task_queue.start()   # 自动开跑，用户不用手点
        except Exception:
            pass


def _set_result(job_id: str, msg: str) -> None:
    with _LOCK:
        for j in _JOBS:
            if j["id"] == job_id:
                j["last_result"] = msg
                _save()
                return


def _loop() -> None:
    while not _STOP.is_set():
        try:
            _tick()
        except Exception:
            pass
        _STOP.wait(_TICK_SEC)


def _ensure_ticker() -> None:
    global _TICKER
    if _TICKER is not None and _TICKER.is_alive():
        return
    _STOP.clear()
    _TICKER = threading.Thread(target=_loop, daemon=True)
    _TICKER.start()


def startup() -> None:
    """应用启动时调用：恢复任务、重算下次执行时间、拉起调度线程。"""
    with _LOCK:
        _load()
        for j in _JOBS:
            try:
                j["next_run"] = compute_next_run(j)
            except ScheduleError:
                j["enabled"] = False
                j["next_run"] = None
        _save()
    _ensure_ticker()


def shutdown() -> None:
    _STOP.set()
