"""抖音收藏同步：定时把主页 / 收藏夹里的视频抓下来，提取文案，攒成待拆解的素材池。

设计要点
--------
- 数据全部落在 backend/data/douyin_sync.json（config + records + runs 三段），
  与选题库解耦；「选入选题库」时才写 topic_library.json。
- 抓取分两步：①发现链接（主页/收藏夹页面里抠 aweme_id）②逐条走 dissect.fetch_douyin
  提取结构化文案。第②步和「爆款拆解」用的是同一套解析器，不重复造轮子。
- 抖音网页端反爬很严：收藏夹一般要登录、主页接口要签名。所以：
  * 配置里提供 cookie 字段（用户可粘贴自己的登录 Cookie，成功率高很多）；
  * 发现不到链接时如实记进本次运行日志，不假装成功；
  * 永远保留「手动粘贴一批链接」的入口，这条路 100% 能用。
- 定时用自己的 ticker 线程（复用 schedule.py 的 cron 解析），不去改动已有的
  选题定时任务，避免把跑得好好的功能改坏。
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any

from ..system.config import DATA_DIR, atomic_write_json
from ..content import dissect
from ..system.schedule import (
    ScheduleError,
    _parse_hhmm,
    cron_next,
    describe,
    parse_cron,
)

log = logging.getLogger("workbench.douyin_sync")

STORE = DATA_DIR / "douyin_sync.json"
_LOCK = threading.RLock()
_TICKER: threading.Thread | None = None
_STOP = threading.Event()
_TICK_SEC = 30
_SYNCING = threading.Event()

FREQUENCIES = ("daily", "weekly", "cron")
SOURCE_KINDS = ("favorite", "profile", "manual")
RECORD_STATUSES = ("new", "imported", "ignored")

MAX_RECORDS = 500
MAX_RUNS = 30


class SyncError(RuntimeError):
    """收藏同步配置/执行错误，路由层转 400。"""


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "sources": [],
    "cookie": "",
    "frequency": "daily",
    "time": "09:00",
    "weekday": 0,
    "cron": "0 9 * * *",
    "max_per_run": 10,
    "filters": {
        "min_digg": 0,
        "min_text_len": 0,
        "keywords": [],
        "exclude_keywords": [],
    },
    "next_run": None,
    "last_run": None,
    "last_result": "",
    "run_count": 0,
}


# ---------------------------------------------------------------------------
# 存储
# ---------------------------------------------------------------------------
def _blank() -> dict:
    return {"config": json.loads(json.dumps(DEFAULT_CONFIG)), "records": [], "runs": []}


def _read() -> dict:
    try:
        if STORE.exists():
            data = json.loads(STORE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                out = _blank()
                cfg = data.get("config")
                if isinstance(cfg, dict):
                    out["config"] = _merge_config(cfg)
                if isinstance(data.get("records"), list):
                    out["records"] = [r for r in data["records"] if isinstance(r, dict)]
                if isinstance(data.get("runs"), list):
                    out["runs"] = [r for r in data["runs"] if isinstance(r, dict)]
                return out
    except Exception:
        log.warning("douyin_sync.json 读取失败，使用空数据", exc_info=True)
    return _blank()


def _write(state: dict) -> None:
    state["records"] = state.get("records", [])[:MAX_RECORDS]
    state["runs"] = state.get("runs", [])[:MAX_RUNS]
    atomic_write_json(STORE, state)


def _merge_config(cfg: dict) -> dict:
    out = json.loads(json.dumps(DEFAULT_CONFIG))
    for k in out:
        if k in cfg:
            out[k] = cfg[k]
    out["filters"] = {**DEFAULT_CONFIG["filters"], **(cfg.get("filters") or {})}
    out["sources"] = [s for s in (cfg.get("sources") or []) if isinstance(s, dict)]
    return out


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
def _compute_next(cfg: dict, after: datetime | None = None) -> str | None:
    if not cfg.get("enabled"):
        return None
    now = (after or datetime.now()).replace(second=0, microsecond=0)
    freq = cfg.get("frequency") or "daily"
    try:
        if freq == "cron":
            nxt = cron_next(cfg.get("cron") or "", now)
            return nxt.strftime("%Y-%m-%d %H:%M") if nxt else None
        h, m = _parse_hhmm(cfg.get("time") or "09:00")
        if freq == "weekly":
            wd = max(0, min(6, int(cfg.get("weekday") or 0)))
            cand = now.replace(hour=h, minute=m)
            cand += timedelta(days=(wd - cand.weekday()) % 7)
            if cand <= now:
                cand += timedelta(days=7)
            return cand.strftime("%Y-%m-%d %H:%M")
        cand = now.replace(hour=h, minute=m)
        if cand <= now:
            cand += timedelta(days=1)
        return cand.strftime("%Y-%m-%d %H:%M")
    except (ScheduleError, SyncError):
        return None


def _decorate_config(cfg: dict) -> dict:
    out = dict(cfg)
    out["freq_label"] = describe(cfg)
    # cookie 不回传明文，只告诉前端有没有配
    out["cookie"] = ""
    out["cookie_set"] = bool((cfg.get("cookie") or "").strip())
    return out


def _validate_config(payload: dict, old: dict) -> dict:
    cfg = _merge_config({**old, **(payload or {})})
    freq = cfg.get("frequency") or "daily"
    if freq not in FREQUENCIES:
        raise SyncError("频率只能是 daily / weekly / cron")
    cfg["frequency"] = freq
    if freq == "cron":
        try:
            parse_cron(cfg.get("cron") or "")
        except ScheduleError as e:
            raise SyncError(str(e))
    else:
        # 复用 schedule._parse_hhmm（抛 ScheduleError），按本模块契约转成 SyncError → 路由层 400
        try:
            _parse_hhmm(cfg.get("time") or "09:00")
        except ScheduleError as e:
            raise SyncError(str(e))

    try:
        cfg["max_per_run"] = max(1, min(50, int(cfg.get("max_per_run") or 10)))
    except (TypeError, ValueError):
        cfg["max_per_run"] = 10
    cfg["weekday"] = max(0, min(6, int(cfg.get("weekday") or 0)))
    cfg["enabled"] = bool(cfg.get("enabled"))

    # 空 cookie 表示「不改」，不要把已存的 cookie 洗掉
    if "cookie" in (payload or {}):
        new_cookie = (payload.get("cookie") or "").strip()
        cfg["cookie"] = new_cookie if new_cookie else (old.get("cookie") or "")

    srcs: list[dict] = []
    for s in cfg.get("sources") or []:
        url = (s.get("url") or "").strip()
        if not url:
            continue
        kind = s.get("kind") if s.get("kind") in SOURCE_KINDS else "profile"
        srcs.append(
            {
                "id": s.get("id") or uuid.uuid4().hex[:8],
                "name": (s.get("name") or "").strip() or ("我的收藏夹" if kind == "favorite" else "抖音主页"),
                "url": url,
                "kind": kind,
                "enabled": bool(s.get("enabled", True)),
            }
        )
    cfg["sources"] = srcs[:10]

    f = cfg["filters"]
    try:
        f["min_digg"] = max(0, int(f.get("min_digg") or 0))
    except (TypeError, ValueError):
        f["min_digg"] = 0
    try:
        f["min_text_len"] = max(0, int(f.get("min_text_len") or 0))
    except (TypeError, ValueError):
        f["min_text_len"] = 0
    f["keywords"] = [str(k).strip() for k in (f.get("keywords") or []) if str(k).strip()][:12]
    f["exclude_keywords"] = [
        str(k).strip() for k in (f.get("exclude_keywords") or []) if str(k).strip()
    ][:12]
    return cfg


def get_config() -> dict:
    with _LOCK:
        state = _read()
        return _decorate_config(state["config"])


def save_config(payload: dict) -> dict:
    with _LOCK:
        state = _read()
        cfg = _validate_config(payload or {}, state["config"])
        cfg["next_run"] = _compute_next(cfg)
        state["config"] = cfg
        _write(state)
    _ensure_ticker()
    return _decorate_config(cfg)


# ---------------------------------------------------------------------------
# 链接发现
# ---------------------------------------------------------------------------
_ID_PATTERNS = (
    r'"aweme_id"\s*:\s*"(\d{6,})"',
    r'/video/(\d{6,})',
    r'"awemeId"\s*:\s*"(\d{6,})"',
    r'aweme_id=(\d{6,})',
)


def _fetch_html(url: str, cookie: str, timeout: int = 15) -> str:
    import requests  # 懒加载，未装 requests 时不影响其它功能

    headers = {
        "User-Agent": dissect._UA_DESKTOP,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.douyin.com/",
    }
    if cookie.strip():
        headers["Cookie"] = cookie.strip()
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    resp.encoding = resp.encoding or "utf-8"
    return resp.text or ""


def discover_links(url: str, cookie: str = "", limit: int = 10) -> tuple[list[str], str]:
    """从主页 / 收藏夹页面里抠出视频链接。返回 (链接列表, 说明)。"""
    clean = dissect.extract_url(url) or (url or "").strip()
    if not clean:
        return [], "链接为空"

    # 本身就是一条视频链接 → 直接返回
    if dissect._aweme_id(clean) or "v.douyin.com" in clean:
        return [clean], "单条视频链接"

    try:
        html = _fetch_html(clean, cookie)
    except Exception as e:  # noqa: BLE001
        return [], f"页面抓取失败：{type(e).__name__}"
    if not html:
        return [], "页面返回空内容"

    ids: list[str] = []
    for pat in _ID_PATTERNS:
        for m in re.finditer(pat, html):
            vid = m.group(1)
            if vid not in ids:
                ids.append(vid)
            if len(ids) >= limit:
                break
        if len(ids) >= limit:
            break

    if not ids:
        hint = "页面里没解析到视频链接"
        if not cookie.strip():
            hint += "（收藏夹/主页通常要登录，建议在配置里粘贴抖音 Cookie 再试）"
        else:
            hint += "（Cookie 可能已过期，或抖音改了页面结构；可改用「手动粘贴链接」）"
        return [], hint

    return [f"https://www.douyin.com/video/{i}" for i in ids], f"发现 {len(ids)} 条视频"


# ---------------------------------------------------------------------------
# 筛选
# ---------------------------------------------------------------------------
def _apply_filters(rec: dict, f: dict) -> tuple[bool, str]:
    """返回 (是否保留, 不保留的原因)。"""
    digg = (rec.get("stats") or {}).get("digg")
    min_digg = int(f.get("min_digg") or 0)
    if min_digg > 0:
        if digg is None:
            return False, f"点赞数没抓到，无法满足「≥{min_digg} 赞」"
        if digg < min_digg:
            return False, f"点赞 {digg} < {min_digg}"

    min_len = int(f.get("min_text_len") or 0)
    text = rec.get("text") or ""
    if min_len > 0 and len(text) < min_len:
        return False, f"文案 {len(text)} 字 < {min_len} 字"

    haystack = " ".join(
        str(rec.get(k) or "") for k in ("title", "desc", "text", "author")
    ) + " " + " ".join(rec.get("hashtags") or [])

    include = f.get("keywords") or []
    if include and not any(k in haystack for k in include):
        return False, "没命中任何关键词：" + "、".join(include[:5])

    for k in f.get("exclude_keywords") or []:
        if k in haystack:
            return False, f"命中排除词「{k}」"

    return True, ""


# ---------------------------------------------------------------------------
# 执行同步
# ---------------------------------------------------------------------------
def _make_record(fetched: dict, source_name: str) -> dict:
    stats = fetched.get("stats") if isinstance(fetched.get("stats"), dict) else {}
    return {
        "id": uuid.uuid4().hex[:10],
        "video_id": fetched.get("video_id") or "",
        "url": fetched.get("source_url") or "",
        "title": fetched.get("title") or "",
        "desc": fetched.get("desc") or "",
        "text": fetched.get("text") or "",
        "author": fetched.get("author") or "",
        "create_time": fetched.get("create_time") or "",
        "duration_sec": fetched.get("duration_sec"),
        "stats": {k: stats.get(k) for k in ("digg", "comment", "collect", "share")},
        "hashtags": list(fetched.get("hashtags") or [])[:12],
        "cover": fetched.get("cover") or "",
        "missing": list(fetched.get("missing") or [])[:12],
        "complete": bool(fetched.get("complete", False)),
        "source_name": source_name,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "new",
        "topic_id": "",
        "note": "",
    }


def run_sync(urls: list[str] | None = None, trigger: str = "manual") -> dict:
    """跑一次同步。urls 非空时只处理这批链接（手动模式），否则遍历配置里的来源。"""
    if _SYNCING.is_set():
        raise SyncError("上一次同步还在跑，请等它结束。")
    _SYNCING.set()
    started = datetime.now()
    messages: list[str] = []
    added = skipped = filtered = failed = 0
    new_records: list[dict] = []

    try:
        with _LOCK:
            state = _read()
            cfg = state["config"]
            known_ids = {r.get("video_id") for r in state["records"] if r.get("video_id")}
            known_urls = {r.get("url") for r in state["records"] if r.get("url")}
        cookie = cfg.get("cookie") or ""
        limit = int(cfg.get("max_per_run") or 10)
        filters = cfg.get("filters") or {}

        # ---- 1. 收集待抓链接 ----
        targets: list[tuple[str, str]] = []  # (url, source_name)
        if urls:
            for u in urls[:50]:
                clean = dissect.extract_url(u) or (u or "").strip()
                if clean:
                    targets.append((clean, "手动添加"))
            messages.append(f"手动模式：待处理 {len(targets)} 条链接")
        else:
            enabled_sources = [s for s in cfg.get("sources") or [] if s.get("enabled", True)]
            if not enabled_sources:
                messages.append("没有启用的来源，先到上面添加抖音主页 / 收藏夹链接。")
            for s in enabled_sources:
                links, note = discover_links(s.get("url") or "", cookie, limit)
                messages.append(f"「{s.get('name')}」{note}")
                for lk in links:
                    targets.append((lk, s.get("name") or ""))

        # 去重 + 限量
        seen: set[str] = set()
        dedup: list[tuple[str, str]] = []
        for u, name in targets:
            vid = dissect._aweme_id(u)
            key = vid or u
            if key in seen:
                continue
            seen.add(key)
            if (vid and vid in known_ids) or u in known_urls:
                skipped += 1
                continue
            dedup.append((u, name))
        dedup = dedup[:limit]

        if skipped:
            messages.append(f"跳过 {skipped} 条已经抓过的视频")

        # ---- 2. 逐条提取文案 ----
        for u, name in dedup:
            try:
                fetched = dissect.fetch_douyin(u)
            except dissect.DissectError as e:
                failed += 1
                messages.append(f"抓取失败：{u} —— {e}")
                continue
            except Exception as e:  # noqa: BLE001
                failed += 1
                messages.append(f"抓取异常：{u} —— {type(e).__name__}")
                continue

            rec = _make_record(fetched, name)
            keep, reason = _apply_filters(rec, filters)
            if not keep:
                filtered += 1
                messages.append(f"已过滤：{rec['title'] or rec['video_id'] or u} —— {reason}")
                continue
            new_records.append(rec)
            added += 1

        # ---- 3. 落盘 ----
        finished = datetime.now()
        run = {
            "id": uuid.uuid4().hex[:8],
            "trigger": trigger,
            "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_sec": round((finished - started).total_seconds(), 1),
            "added": added,
            "skipped": skipped,
            "filtered": filtered,
            "failed": failed,
            "messages": messages[:40],
        }
        summary = f"新增 {added}｜跳过 {skipped}｜过滤 {filtered}｜失败 {failed}"
        with _LOCK:
            state = _read()
            state["records"] = new_records + state["records"]
            state["runs"] = [run] + state["runs"]
            c = state["config"]
            c["last_run"] = finished.strftime("%Y-%m-%d %H:%M")
            c["last_result"] = summary
            c["run_count"] = int(c.get("run_count") or 0) + 1
            c["next_run"] = _compute_next(c, finished)
            _write(state)

        return {"ok": True, "run": run, "summary": summary, "records": new_records}
    finally:
        _SYNCING.clear()


# ---------------------------------------------------------------------------
# 记录管理
# ---------------------------------------------------------------------------
def list_records(
    status: str = "", keyword: str = "", limit: int = 100, source: str = ""
) -> dict:
    with _LOCK:
        state = _read()
        items = list(state["records"])
    total_all = len(items)
    if status and status in RECORD_STATUSES:
        items = [r for r in items if (r.get("status") or "new") == status]
    if source:
        items = [r for r in items if (r.get("source_name") or "") == source]
    kw = (keyword or "").strip()
    if kw:
        items = [
            r
            for r in items
            if kw in (r.get("title") or "")
            or kw in (r.get("desc") or "")
            or kw in (r.get("text") or "")
            or kw in (r.get("author") or "")
        ]
    counts = {
        s: sum(1 for r in state["records"] if (r.get("status") or "new") == s)
        for s in RECORD_STATUSES
    }
    return {
        "items": items[: max(1, min(500, limit))],
        "total": len(items),
        "total_all": total_all,
        "counts": counts,
    }


def get_record(record_id: str) -> dict:
    with _LOCK:
        for r in _read()["records"]:
            if r.get("id") == record_id:
                return r
    raise SyncError("这条记录不存在，可能已经被删掉了。")


def update_record(record_id: str, **fields: Any) -> dict:
    allowed = {"status", "note", "text", "title"}
    with _LOCK:
        state = _read()
        for r in state["records"]:
            if r.get("id") != record_id:
                continue
            for k, v in fields.items():
                if k in allowed and v is not None:
                    if k == "status" and v not in RECORD_STATUSES:
                        raise SyncError(f"状态只能是 {' / '.join(RECORD_STATUSES)}")
                    r[k] = v
            _write(state)
            return r
    raise SyncError("这条记录不存在，可能已经被删掉了。")


def delete_record(record_id: str) -> dict:
    with _LOCK:
        state = _read()
        for i, r in enumerate(state["records"]):
            if r.get("id") == record_id:
                state["records"].pop(i)
                _write(state)
                return {"ok": True, "total": len(state["records"])}
    raise SyncError("这条记录不存在，可能已经被删掉了。")


def clear_records(status: str = "") -> dict:
    with _LOCK:
        state = _read()
        before = len(state["records"])
        if status and status in RECORD_STATUSES:
            state["records"] = [
                r for r in state["records"] if (r.get("status") or "new") != status
            ]
        else:
            state["records"] = []
        _write(state)
        return {"ok": True, "removed": before - len(state["records"])}


_CATEGORY_HINTS = (
    ("踩坑类", ("踩坑", "翻车", "失败", "教训", "别再", "坑")),
    ("干货类", ("教程", "步骤", "方法", "怎么", "如何", "指南")),
    ("工具类", ("工具", "软件", "插件", "app", "AI ")),
)


def _guess_category(rec: dict) -> str:
    text = f"{rec.get('title', '')} {rec.get('desc', '')}"
    for cat, words in _CATEGORY_HINTS:
        if any(w.lower() in text.lower() for w in words):
            return cat
    return "其他"


def import_to_topics(ids: list[str], priority: str = "中") -> dict:
    """把选中的记录手动选入选题库。"""
    if not ids:
        raise SyncError("请先勾选要选入选题库的视频。")
    ok, fail = 0, 0
    msgs: list[str] = []
    with _LOCK:
        state = _read()
        index = {r.get("id"): r for r in state["records"]}
        for rid in ids[:50]:
            rec = index.get(rid)
            if not rec:
                fail += 1
                msgs.append(f"{rid}：记录不存在")
                continue
            title = (rec.get("title") or rec.get("desc") or "").strip()
            if not title:
                fail += 1
                msgs.append(f"{rec.get('video_id') or rid}：没有标题，先编辑补一个")
                continue
            body = (rec.get("text") or "").strip()
            content = body
            if rec.get("url"):
                content = f"{body}\n\n原视频：{rec['url']}"
            try:
                item = dissect.save_topic(
                    title=title[:80],
                    content=content,
                    theme="",
                    source="douyin_sync",
                    category=_guess_category(rec),
                    priority=priority,
                    status="待生产",
                )
                rec["status"] = "imported"
                rec["topic_id"] = (item.get("item") or {}).get("id", "") if isinstance(item, dict) else ""
                ok += 1
            except dissect.DissectError as e:
                fail += 1
                msgs.append(f"{title[:20]}：{e}")
        _write(state)
    return {"ok": True, "imported": ok, "failed": fail, "messages": msgs[:10]}


def list_runs(limit: int = 20) -> dict:
    with _LOCK:
        runs = _read()["runs"]
    return {"items": runs[: max(1, min(MAX_RUNS, limit))], "total": len(runs)}


def get_state() -> dict:
    """一次性把前端首屏要的东西给全。"""
    with _LOCK:
        state = _read()
    cfg = state["config"]
    counts = {
        s: sum(1 for r in state["records"] if (r.get("status") or "new") == s)
        for s in RECORD_STATUSES
    }
    return {
        "config": _decorate_config(cfg),
        "counts": counts,
        "total": len(state["records"]),
        "last_run": cfg.get("last_run"),
        "last_result": cfg.get("last_result"),
        "next_run": cfg.get("next_run"),
        "run_count": cfg.get("run_count") or 0,
        "running": _SYNCING.is_set(),
    }


# ---------------------------------------------------------------------------
# 定时线程
# ---------------------------------------------------------------------------
def _tick() -> None:
    now = datetime.now().replace(second=0, microsecond=0)
    fire = False
    with _LOCK:
        state = _read()
        cfg = state["config"]
        if not cfg.get("enabled"):
            if cfg.get("next_run"):
                cfg["next_run"] = None
                _write(state)
            return
        nxt = cfg.get("next_run")
        if not nxt:
            cfg["next_run"] = _compute_next(cfg, now)
            _write(state)
            return
        try:
            nxt_dt = datetime.strptime(nxt, "%Y-%m-%d %H:%M")
        except ValueError:
            cfg["next_run"] = _compute_next(cfg, now)
            _write(state)
            return
        if now >= nxt_dt:
            fire = True
            # 先把 next_run 推到下一次，避免同一分钟重复触发
            cfg["next_run"] = _compute_next(cfg, now)
            _write(state)

    if fire and not _SYNCING.is_set():
        try:
            res = run_sync(trigger="schedule")
            log.info("抖音收藏同步（定时）完成：%s", res.get("summary"))
        except Exception:
            log.exception("抖音收藏同步（定时）失败")


def _loop() -> None:
    while not _STOP.is_set():
        try:
            _tick()
        except Exception:
            log.exception("抖音收藏同步 tick 异常")
        _STOP.wait(_TICK_SEC)


def _ensure_ticker() -> None:
    global _TICKER
    if _TICKER is not None and _TICKER.is_alive():
        return
    _STOP.clear()
    _TICKER = threading.Thread(target=_loop, daemon=True, name="douyin-sync")
    _TICKER.start()


def startup() -> None:
    with _LOCK:
        state = _read()
        state["config"]["next_run"] = _compute_next(state["config"])
        try:
            _write(state)
        except Exception:
            log.warning("douyin_sync 启动写盘失败", exc_info=True)
    _ensure_ticker()


def shutdown() -> None:
    _STOP.set()
