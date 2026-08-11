"""历史任务读取逻辑（复用现有 Streamlit 工作台扫描 data/issues/<N>/result.json 的算法）。

所有异常都被吞掉并跳过损坏项，保证页面稳定；单文件损坏不影响全局。
"""
from __future__ import annotations

import base64
import datetime
import json
import os
from pathlib import Path

from ..system.config import settings, DATA_DIR

_ISSUES_DIR = "data/issues"
_TRASH_DIR = "data/issues_trash"   # 回收站（软删除落这里，与 issues 同级）
_ARTICLE_PREVIEW_CHARS = 500

# 任务标签存在独立 sidecar 文件，不污染流水线产出的 result.json
_TASK_TAGS_PATH = DATA_DIR / "task_tags.json"
_TAG_MAX = 10


def _clip(s: str, n: int) -> str:
    s = str(s).strip()[:n]
    return s


def _read_task_tags() -> dict:
    try:
        if _TASK_TAGS_PATH.exists():
            data = json.loads(_TASK_TAGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _write_task_tags(tags: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _TASK_TAGS_PATH.write_text(
            json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def get_task_tags(issue: int) -> list[str]:
    return list(_read_task_tags().get(str(int(issue)), []))


def set_task_tags(issue: int, tags: list[str]) -> list[str]:
    """设置某期任务的标签（覆盖式）。空列表即清空。"""
    issue = int(issue)
    clean = [_clip(t, 30) for t in (tags or []) if str(t).strip()][:_TAG_MAX]
    all_tags = _read_task_tags()
    if clean:
        all_tags[str(issue)] = clean
    else:
        all_tags.pop(str(issue), None)
    _write_task_tags(all_tags)
    return clean


def list_task_tags() -> list[str]:
    """返回所有任务标签（去重，按出现次数降序）。"""
    counts: dict[str, int] = {}
    for v in _read_task_tags().values():
        for t in (v or []):
            t = str(t).strip()
            if t:
                counts[t] = counts.get(t, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [t for t, _ in ordered]


class TasksError(Exception):
    """任务操作的可预期错误（如找不到某期），由路由层或统一异常处理器转成 404 等友好状态码。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _hist_status_of(rj: dict) -> str:
    s = str(rj.get("status") or "").lower()
    if s in ("ok", "success", "done", "published"):
        return "ok"
    if s in ("error", "failed", "fail"):
        return "error"
    if s in ("running", "processing", "in_progress"):
        return "running"
    if s in ("waiting", "pending", "queued"):
        return "waiting"
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


def _read_one_issue(issue_dir: Path, issue_no: int, tag_map: dict) -> tuple[dict | None, str | None]:
    """读单期 result.json 转成任务 dict。返回 (task, error)；error 非空表示跳过原因。"""
    rj_path = issue_dir / "result.json"
    if not rj_path.exists():
        return None, None
    try:
        with open(rj_path, encoding="utf-8") as f:
            rj = _json_load(f)
    except Exception as e:
        return None, f"第{issue_no}期:result.json 解析失败({type(e).__name__})"
    try:
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
        task = {
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
            "dir_path": str(issue_dir),
            "result_path": str(rj_path),
            "completed_at": completed_at,
            "started_at": started_at,
            "duration_sec": duration,
            "tags": list(tag_map.get(str(issue_no), [])),
        }
        return task, None
    except Exception as e:
        return None, f"第{issue_no}期:字段解析失败({type(e).__name__})"


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

    tag_map = _read_task_tags()

    for issue_no, full in sorted(entries, key=lambda x: x[0], reverse=True):
        task, err = _read_one_issue(full, issue_no, tag_map)
        if err:
            skipped.append(err)
            continue
        if task:
            tasks.append(task)

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
                 platform_f: str, time_f: str, tag_f: str = "") -> list[dict]:
    kw = (keyword or "").strip().lower()
    tag_kw = (tag_f or "").strip().lower()
    now = datetime.datetime.now()
    out = []
    for t in tasks:
        if kw:
            blob = (str(t.get("title") or "") + str(t.get("topic") or "")).lower()
            if kw not in blob:
                continue
        if tag_kw and tag_kw not in [str(x).lower() for x in (t.get("tags") or [])]:
            continue
        if status_f and status_f != "全部":
            label = {
                "成功": "ok", "失败": "error",
                "运行中": "running", "等待中": "waiting",
            }.get(status_f)
            if label and t["status"] != label:
                continue
        if platform_f and platform_f != "全部":
            # 已知平台映射；其余（含未知标签）不做过滤，避免误伤
            mapping = {
                "微信公众号": "wechat",
                "小红书": "xiaohongshu",
                "抖音": "douyin",
                "其他": "other",
            }
            want = mapping.get(platform_f)
            if want == "other":
                # 「其他」= 非微信/小红书/抖音 的任意平台
                if (t["platform"] or "").lower() in ("wechat", "xiaohongshu", "douyin"):
                    continue
            elif want:
                if (t["platform"] or "").lower() != want:
                    continue
        if time_f and time_f != "全部":
            if time_f == "近7天":
                if not (t["completed_at"] and (now - t["completed_at"]).days <= 7):
                    continue
            elif time_f == "近30天":
                if not (t["completed_at"] and (now - t["completed_at"]).days <= 30):
                    continue
            elif time_f == "本月":
                if not (t["completed_at"]
                        and t["completed_at"].year == now.year
                        and t["completed_at"].month == now.month):
                    continue
            elif time_f == "上月":
                if now.month == 1:
                    ly, lm = now.year - 1, 12
                else:
                    ly, lm = now.year, now.month - 1
                if not (t["completed_at"]
                        and t["completed_at"].year == ly
                        and t["completed_at"].month == lm):
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
        "tags": get_task_tags(issue),
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


def delete_task(issue: int) -> dict:
    """删除某期任务 → 移到回收站（data/issues_trash/<N>，可恢复），连同整期产出目录一起移动。

    返回 {"ok": True, "issue": int, "trashed": str(回收站目录路径)}。
    目录不存在时抛 TasksError，便于路由层转成 404。
    """
    if not isinstance(issue, int) or issue <= 0:
        raise TasksError(f"非法的任务期号：{issue}")
    issues_dir = settings.streamlit_root / _ISSUES_DIR
    issue_dir = issues_dir / str(issue)
    if not issue_dir.is_dir():
        raise TasksError(f"第 {issue} 期不存在或已被删除", status_code=404)

    # 防御：确保要删的是 issues 目录下的合法子目录，避免误删其它东西
    try:
        issue_dir.resolve().relative_to(issues_dir.resolve())
    except Exception as e:
        raise TasksError(f"路径不合法，拒绝删除：{e}") from e

    import shutil

    trash_dir = settings.streamlit_root / _TRASH_DIR
    trash_dir.mkdir(parents=True, exist_ok=True)
    dest = trash_dir / str(issue)
    if dest.exists():
        shutil.rmtree(dest)  # 覆盖回收站里同名旧副本
    shutil.move(str(issue_dir), str(dest))
    return {"ok": True, "issue": issue, "trashed": str(dest)}


def list_trash_tasks() -> dict:
    """列出回收站里的历史任务（移入 data/issues_trash 的期）。"""
    trash_dir = settings.streamlit_root / _TRASH_DIR
    tasks: list[dict] = []
    if not trash_dir.is_dir():
        return {"tasks": [], "total": 0}
    tag_map = _read_task_tags()
    for name in os.listdir(trash_dir):
        full = trash_dir / name
        if not full.is_dir() or not name.isdigit():
            continue
        task, _err = _read_one_issue(full, int(name), tag_map)
        if task:
            task["trashed"] = True
            tasks.append(task)
    tasks.sort(
        key=lambda t: (t["completed_at"] or datetime.datetime.min, t["issue"]),
        reverse=True,
    )
    return {"tasks": tasks, "total": len(tasks)}


def restore_task(issue: int) -> dict:
    """把回收站里的某期任务恢复到 data/issues/<N>。"""
    if not isinstance(issue, int) or issue <= 0:
        raise TasksError(f"非法的任务期号：{issue}")
    trash_dir = settings.streamlit_root / _TRASH_DIR
    src = trash_dir / str(issue)
    if not src.is_dir():
        raise TasksError(f"回收站里找不到第 {issue} 期", status_code=404)
    issues_dir = settings.streamlit_root / _ISSUES_DIR
    dest = issues_dir / str(issue)
    # 防御：确保目标位置合法
    try:
        dest.resolve().relative_to(issues_dir.resolve())
    except Exception as e:
        raise TasksError(f"路径不合法，拒绝恢复：{e}") from e
    if dest.exists():
        raise TasksError(f"第 {issue} 期已存在，为避免覆盖不予恢复")
    import shutil

    shutil.move(str(src), str(dest))
    return {"ok": True, "issue": issue, "restored": str(dest)}


def purge_task(issue: int) -> dict:
    """从回收站彻底删除某期任务（不可恢复）。"""
    if not isinstance(issue, int) or issue <= 0:
        raise TasksError(f"非法的任务期号：{issue}")
    trash_dir = settings.streamlit_root / _TRASH_DIR
    src = trash_dir / str(issue)
    if not src.is_dir():
        raise TasksError(f"回收站里找不到第 {issue} 期", status_code=404)
    import shutil

    shutil.rmtree(src)
    set_task_tags(issue, [])  # 连带清掉标签
    return {"ok": True, "issue": issue}


def empty_task_trash() -> dict:
    """清空回收站（所有移入的期都彻底删除）。"""
    trash_dir = settings.streamlit_root / _TRASH_DIR
    if not trash_dir.is_dir():
        return {"ok": True, "removed": 0}
    import shutil

    removed = 0
    for name in os.listdir(trash_dir):
        full = trash_dir / name
        if full.is_dir() and name.isdigit():
            set_task_tags(int(name), [])  # 连带清掉标签
            shutil.rmtree(full)
            removed += 1
    return {"ok": True, "removed": removed}
