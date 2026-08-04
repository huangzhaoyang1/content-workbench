"""历史任务读取逻辑（复用现有 Streamlit 工作台扫描 data/issues/<N>/result.json 的算法）。

所有异常都被吞掉并跳过损坏项，保证页面稳定；单文件损坏不影响全局。
"""
from __future__ import annotations

import base64
import datetime
import os
from pathlib import Path

from ..config import settings

_ISSUES_DIR = "data/issues"
_ARTICLE_PREVIEW_CHARS = 500


def _hist_status_of(rj: dict) -> str:
    s = str(rj.get("status") or "").lower()
    if s in ("ok", "success", "done", "published"):
        return "ok"
    if s in ("error", "failed", "fail"):
        return "error"
    return "unknown"


def _parse_dt(s):
    """兼容多种时间格式；解析失败返回 None（调用方显示「未知时间」）。"""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    fmts = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ")
    for f in fmts:
        try:
            return datetime.datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def _fmt_dt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "未知时间"


def _fmt_duration(sec) -> str:
    if sec is None or sec < 0:
        return "—"
    sec = int(sec)
    if sec < 60:
        return f"{sec}秒"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m}分{s}秒"
    h, m = divmod(m, 60)
    return f"{h}时{m}分"


def scan_issues() -> tuple[list[dict], list[str]]:
    """扫描 data/issues/<N>/result.json。返回 (任务列表, 跳过原因列表)。"""
    root = settings.streamlit_root
    issues_dir = root / _ISSUES_DIR
    tasks: list[dict] = []
    skipped: list[str] = []
    if not issues_dir.is_dir():
        return tasks, skipped

    entries = []
    for name in os.listdir(issues_dir):
        full = issues_dir / name
        if not full.is_dir() or not name.isdigit():
            continue
        entries.append((int(name), full))

    for issue_no, full in sorted(entries, key=lambda x: x[0], reverse=True):
        rj_path = full / "result.json"
        if not rj_path.exists():
            continue
        try:
            with open(rj_path, encoding="utf-8") as f:
                rj = _json_load(f)
        except Exception as e:
            skipped.append(f"第{issue_no}期:result.json 解析失败({type(e).__name__})")
            continue
        try:
            status = _hist_status_of(rj)
            try:
                completed_at = datetime.datetime.fromtimestamp(os.path.getmtime(rj_path))
            except Exception:
                completed_at = None
            try:
                started_at = datetime.datetime.fromtimestamp(os.path.getctime(full))
            except Exception:
                started_at = None
            duration = None
            if completed_at and started_at:
                duration = max(0.0, (completed_at - started_at).total_seconds())
            tasks.append({
                "issue": issue_no,
                "status": status,
                "title": rj.get("title") or rj.get("topic") or f"第{issue_no}期",
                "topic": rj.get("topic") or "",
                "angle": rj.get("angle") or "",
                "platform": rj.get("platform") or "wechat",
                "draft_status": rj.get("draft_status"),
                "error": rj.get("error"),
                "article_rel": rj.get("article_md"),
                "cover_rel": rj.get("cover"),
                "dir_path": str(full),
                "result_path": str(rj_path),
                "completed_at": completed_at,
                "started_at": started_at,
                "duration_sec": duration,
            })
        except Exception as e:
            skipped.append(f"第{issue_no}期:字段解析失败({type(e).__name__})")

    tasks.sort(
        key=lambda t: (
            0 if t["status"] == "running" else 1,
            t["completed_at"] or datetime.datetime.min,
            t["issue"],
        ),
        reverse=True,
    )
    return tasks, skipped


def _json_load(f) -> dict:
    import json as _json
    return _json.load(f)


def build_stats(tasks: list[dict]) -> dict:
    total = len(tasks)
    success = sum(1 for t in tasks if t["status"] == "ok")
    failed = sum(1 for t in tasks if t["status"] == "error")
    terminal = success + failed
    rate = (success / terminal) if terminal else None
    now = datetime.datetime.now()
    this_month = sum(
        1 for t in tasks
        if t["completed_at"] and t["completed_at"].year == now.year
        and t["completed_at"].month == now.month
    )
    durs = [t["duration_sec"] for t in tasks if t.get("duration_sec") is not None]
    avg_dur = (sum(durs) / len(durs)) if durs else None
    return {
        "total": total, "success": success, "failed": failed,
        "rate": rate, "this_month": this_month, "avg_duration": avg_dur,
    }


def filter_tasks(tasks: list[dict], keyword: str, status_f: str,
                 platform_f: str, time_f: str) -> list[dict]:
    kw = (keyword or "").strip().lower()
    now = datetime.datetime.now()
    out = []
    for t in tasks:
        if kw:
            blob = (str(t.get("title") or "") + str(t.get("topic") or "")).lower()
            if kw not in blob:
                continue
        if status_f and status_f != "全部":
            label = {"成功": "ok", "失败": "error", "进行中": "running"}.get(status_f)
            if t["status"] != label:
                continue
        if platform_f and platform_f != "全部":
            want = "wechat" if platform_f == "微信公众号" else "other"
            is_wechat = (t["platform"] or "").lower() == "wechat"
            if want == "wechat" and not is_wechat:
                continue
            if want == "other" and is_wechat:
                continue
        if time_f and time_f != "全部":
            days = {"近7天": 7, "近30天": 30, "近90天": 90}.get(time_f)
            if days and t["completed_at"]:
                if (now - t["completed_at"]).days > days:
                    continue
        out.append(t)
    return out


def paginate(tasks: list[dict], page: int, page_size: int) -> tuple[list[dict], int]:
    """分页。page 从 1 开始；page_size<=0 表示不分页。返回 (当页数据, 总页数)。"""
    total = len(tasks)
    if page_size <= 0:
        return tasks, 1
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, pages))
    start = (page - 1) * page_size
    return tasks[start:start + page_size], pages


def get_task_detail(issue: int) -> dict | None:
    """读取单期任务详情，含文章前 500 字预览与封面 base64（便于前端直接展示）。"""
    root = settings.streamlit_root
    issue_dir = root / _ISSUES_DIR / str(issue)
    rj_path = issue_dir / "result.json"
    if not rj_path.exists():
        return None
    try:
        with open(rj_path, encoding="utf-8") as f:
            rj = _json_load(f)
    except Exception:
        return None

    status = _hist_status_of(rj)
    try:
        completed_at = datetime.datetime.fromtimestamp(os.path.getmtime(rj_path))
    except Exception:
        completed_at = None
    try:
        started_at = datetime.datetime.fromtimestamp(os.path.getctime(issue_dir))
    except Exception:
        started_at = None
    duration = None
    if completed_at and started_at:
        duration = max(0.0, (completed_at - started_at).total_seconds())

    detail = {
        "issue": issue,
        "status": status,
        "title": rj.get("title") or rj.get("topic") or f"第{issue}期",
        "topic": rj.get("topic") or "",
        "angle": rj.get("angle") or "",
        "platform": rj.get("platform") or "wechat",
        "draft_status": rj.get("draft_status"),
        "error": rj.get("error"),
        "article_rel": rj.get("article_md"),
        "cover_rel": rj.get("cover"),
        "dir_path": str(issue_dir),
        "result_path": str(rj_path),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_sec": duration,
        "article_preview": None,
        "cover_base64": None,
    }

    # 文章预览（前 500 字）
    art_path = root / rj.get("article_md") if rj.get("article_md") else issue_dir / "article.md"
    if art_path and art_path.exists():
        try:
            text = art_path.read_text(encoding="utf-8", errors="replace")
            detail["article_preview"] = text[:_ARTICLE_PREVIEW_CHARS] + ("…" if len(text) > _ARTICLE_PREVIEW_CHARS else "")
        except Exception:
            pass

    # 封面图 base64
    cov_path = root / rj.get("cover") if rj.get("cover") else issue_dir / "cover.png"
    if cov_path and cov_path.exists():
        try:
            b64 = base64.b64encode(cov_path.read_bytes()).decode("ascii")
            detail["cover_base64"] = f"data:image/png;base64,{b64}"
        except Exception:
            pass
    return detail


def open_issue_dir(issue: int) -> tuple[bool, str]:
    """在系统文件管理器里打开某期产出目录。返回 (是否成功, 说明)。"""
    issue_dir = settings.streamlit_root / _ISSUES_DIR / str(issue)
    if not issue_dir.is_dir():
        return False, f"目录不存在：{issue_dir}"
    try:
        if os.name == "nt":
            os.startfile(str(issue_dir))  # type: ignore[attr-defined]
        else:
            import subprocess
            import sys
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, str(issue_dir)])
        return True, str(issue_dir)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
