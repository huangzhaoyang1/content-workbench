"""流水线调度：调用现有 scripts/run_pipeline.py，后台执行并实时收集日志。

存储：任务状态落盘到 data/tasks.json（复用 system.config.atomic_write_json 原子写），
进程重启后可恢复；内存 _TASKS 作为热数据（实时日志追加 / 即时查询），每次变更后同步落盘。
启动时发现「未完成」（pending/running）的旧任务会被标记为 failed（子进程已随重启终止），
「刚完成」（success/failed）的任务原样保留以供查询。
后台线程只把日志追加到 task["logs"] 列表，主线程读状态即可，无共享状态冲突。
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime

from ..system.config import settings, load_config, DATA_DIR, atomic_write_json
from ..data.preferences import load_preferences
from ..data.retrieval import search as retrieval_search
from .quality import score_article, QUALITY_THRESHOLD

# 任务存储：热数据在内存 _TASKS，持久化到 DATA_DIR/tasks.json
_TASKS: dict[str, dict] = {}
_LOCK = threading.Lock()
TASKS_PATH = DATA_DIR / "tasks.json"
_KEEP_RECENT = 50          # 最多保留最近 50 条任务记录（取代原 300s 定时清理）
_LOADED = False            # 懒加载标记：首次访问时从磁盘恢复


class PipelineUnavailable(RuntimeError):
    """本地流水线脚本不可用（典型场景：部署在云端，机器上没有 scripts/）。"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 持久化：内存热数据 <-> data/tasks.json
# ---------------------------------------------------------------------------
def _sort_key(task: dict) -> str:
    """排序键：以「完成时间」优先、「创建时间」兜底，保证『最近』语义正确。"""
    return task.get("finished_at") or task.get("created_at") or ""


def _load_tasks() -> dict:
    """从磁盘读取任务表；文件缺失或损坏时返回空表（不抛出，避免坏数据拖垮启动）。"""
    try:
        with open(TASKS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as e:
        print(f"[pipeline] tasks.json 读取失败，已忽略旧数据：{e}", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def _reconcile(tasks: dict) -> None:
    """启动调和：把『未完成』（pending/running）的旧任务标记为 failed。

    进程随重启终止后，这些任务的子进程已不存在、不可能再推进，
    标记为 failed 并附说明，避免前端看到永久 running。已完成任务原样保留。
    """
    for t in tasks.values():
        if t.get("status") in ("pending", "running"):
            t["status"] = "failed"
            t["error"] = "服务重启导致该任务中断（原后台进程已终止）"
            t.setdefault("logs", []).append("[interrupted] 服务重启，原任务进程已不存在")
            if not t.get("finished_at"):
                t["finished_at"] = _now()


def _trim_to_limit() -> None:
    """超出 _KEEP_RECENT 时丢弃最旧记录，仅保留最近 _KEEP_RECENT 条。"""
    if len(_TASKS) <= _KEEP_RECENT:
        return
    ordered = sorted(_TASKS.items(), key=lambda kv: _sort_key(kv[1]))
    for tid, _ in ordered[: len(_TASKS) - _KEEP_RECENT]:
        _TASKS.pop(tid, None)


def _persist() -> None:
    """把当前内存任务表原子写入 tasks.json。落盘失败仅告警，不影响任务执行。"""
    with _LOCK:
        _trim_to_limit()
        snapshot = {tid: {**t, "logs": list(t.get("logs", []))} for tid, t in _TASKS.items()}
    try:
        atomic_write_json(TASKS_PATH, snapshot)
    except Exception as e:  # noqa: BLE001
        print(f"[pipeline] 任务状态落盘失败（仅保留在内存）：{e}", file=sys.stderr)


def _ensure_loaded() -> None:
    """首次访问时从磁盘恢复任务并调和中断态（懒加载，避免导入期副作用）。"""
    global _LOADED, _TASKS
    if _LOADED:
        return
    with _LOCK:
        if _LOADED:                       # 双重检查，避免并发重复加载
            return
        loaded = _load_tasks()
        _reconcile(loaded)
        _TASKS = loaded
        _LOADED = True
    _persist()


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


def _supplement_refs_with_retrieval(references: str, topic: str, top_k: int = 5) -> str:
    """把历史素材检索结果（选题库 / 抖音同步）补充进 references，作为写作参考。

    命中结果按「标题 + 摘要」逐行追加；用户已传 references 时，用空行分隔后拼接。
    检索抛错或返回空一律静默降级：返回原 references，绝不阻塞出稿。
    """
    try:
        hits = retrieval_search(query=topic, top_k=top_k)
    except Exception as e:  # noqa: BLE001
        print(f"[pipeline] 历史素材检索失败，已跳过（不影响出稿）：{e}", file=sys.stderr)
        return references
    if not hits:
        return references
    lines: list[str] = ["【历史素材补充（自动检索，仅供写作引用）】"]
    for i, h in enumerate(hits, 1):
        title = str(h.get("title") or "").strip()
        content = str(h.get("content") or "").strip()
        if not title and not content:
            continue
        src = str(h.get("source") or "")
        label = {"douyin_sync": "抖音同步", "topic_library": "选题库"}.get(src, src or "素材")
        line = f"{i}. 【{label}】{title}"
        if content:
            line += f"：{content}"
        lines.append(line)
    if len(lines) <= 1:  # 全部为空被跳过
        return references
    block = "\n".join(lines)
    if references and references.strip():
        return references.rstrip() + "\n\n" + block
    return block


def start(topic: str, angle: str = "", extra: str = "",
          references: str = "", platform: str = "",
          review: bool = False, style_key: str = "",
          word_count: str = "", domains: list[str] | None = None,
          forbidden_topics: list[str] | None = None,
          auto_supplement_refs: bool = True) -> dict:
    """启动一次流水线，返回 {task_id, issue}。实际执行在后台线程进行。

    review=True 时追加 --no-publish：只产出本地文章+封面，草稿存为「待审核」，
    不推送公众号，等用户在工作台审核后「确认发布」。

    偏好默认值：未显式传参的字段（platform / style_key / word_count / domains /
    forbidden_topics）会回退到 data/preferences.json 里的用户偏好；显式参数优先。
    这些偏好仅作为「默认值」注入命令行，调用方每次都能按需覆盖。

    自动补充历史素材：auto_supplement_refs=True（默认）时，用 topic 检索选题库 /
    抖音同步，把命中结果的「标题+摘要」追加进 references 作为写作参考；关闭或检索
    失败/无命中时，references 保持原样，绝不阻塞出稿。
    """
    _ensure_loaded()
    avail = availability()
    if not avail["available"]:
        raise PipelineUnavailable(avail["reason"])
    cfg = load_config()
    prefs = load_preferences()
    # 偏好作为默认值，显式参数优先（非空覆盖）
    platform = (platform or prefs["default_platform"]) or "wechat"
    style_key = style_key or prefs["style_key"]
    word_count = word_count or prefs["word_count"]
    domains = domains if domains else prefs["domains"]
    forbidden_topics = forbidden_topics if forbidden_topics else prefs["forbidden_topics"]
    # 自动补充历史素材：检索选题库 / 抖音同步，把命中结果追加进 references。
    # 关闭（auto_supplement_refs=False）或不命中/抛错时，references 保持原样。
    if auto_supplement_refs:
        references = _supplement_refs_with_retrieval(references, topic)
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
    # 内容偏好：仅当非空时追加对应 CLI 标志，保证旧脚本（未配置偏好）的命令与原先完全一致。
    # 标志命名约定：--style / --word-count / --domains / --forbidden-topics
    # （run_pipeline.py 需对应支持这些参数才会生效；空值不传则行为不变）。
    if style_key:
        cmd += ["--style", style_key]
    if word_count:
        cmd += ["--word-count", str(word_count)]
    if domains:
        cmd += ["--domains", ",".join(domains)]
    if forbidden_topics:
        cmd += ["--forbidden-topics", ",".join(forbidden_topics)]
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
        "preferences": {
            "style_key": style_key,
            "word_count": word_count,
            "domains": domains,
            "forbidden_topics": forbidden_topics,
        },
    }
    with _LOCK:
        _TASKS[task_id] = task
    threading.Thread(target=_run_sync, args=(task_id, cmd), daemon=True).start()
    _persist()
    return {"task_id": task_id, "issue": issue}


def publish(issue: int, cover_label: str = "") -> dict:
    """把已存为「待审核」的某期推送到公众号。后台线程执行，返回 {task_id, issue}。

    cover_label 非空时，封面右上角绘制该文字替代默认「第N期」（合集期号由用户手动指定）。
    """
    _ensure_loaded()
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
    _persist()
    return {"task_id": task_id, "issue": issue}


def regenerate_cover(issue: int, cover_label: str = "") -> dict:
    """仅重画封面（不重写文章、不推送公众号），返回新封面 base64。

    cover_label 非空时覆盖默认「第N期」（用户在确认发布对话框实际输入的期号）。
    同步调用 run_pipeline.py --regenerate-cover；图像生成通常 5-30s，超时 120s 兜底。
    用于工作台「生成封面预览」按钮实时反映用户输入的封面期号。
    """
    avail = availability()
    if not avail["available"]:
        return {"ok": False, "reason": f"流水线不可用：{avail.get('reason', '未知')}"}
    issue_dir = settings.streamlit_root / "data" / "issues" / str(issue)
    if not (issue_dir / "result.json").exists():
        return {"ok": False, "reason": f"找不到第 {issue} 期 result.json"}
    cfg = load_config()
    py = cfg.get("python_path") or "python"
    script = settings.scripts_dir / "run_pipeline.py"
    cmd = [py, str(script), "--issue", str(issue), "--regenerate-cover"]
    if cover_label and cover_label.strip():
        cmd += ["--cover-label", cover_label.strip()]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "封面生成超时（>120s）"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"启动失败：{type(e).__name__}: {e}"}
    if proc.returncode != 0:
        stderr_tail = (proc.stderr or "")[-500:]
        return {"ok": False, "reason": f"封面生成失败（exit {proc.returncode}）", "stderr": stderr_tail}
    cover_path = issue_dir / "cover.png"
    if not cover_path.exists():
        return {"ok": False, "reason": "封面文件未生成"}
    try:
        b64 = base64.b64encode(cover_path.read_bytes()).decode("ascii")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"读取封面失败：{type(e).__name__}: {e}"}
    return {"ok": True, "cover_base64": f"data:image/png;base64,{b64}"}


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


def _attach_quality(issue: int) -> None:
    """审核流：对产出文章本地打分，把质量分写入该期 result.json 的 quality 字段。

    仅在 review 任务（--no-publish 出草稿）产出成功后调用，作为「确认发布」前的
    决策支持——不自动拦截，最终闸门是用户的确认发布 / 放弃。
    任何读取 / 打分 / 落盘异常都静默跳过，绝不阻塞或拖垮审核流。
    """
    issues_dir = settings.streamlit_root / "data" / "issues" / str(issue)
    rp = issues_dir / "result.json"
    if not rp.exists():
        return
    try:
        with open(rp, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    # 文章正文：优先 result.json 的 article_md（相对 streamlit_root），否则退化为 article.md
    art_rel = data.get("article_md")
    art_path = (settings.streamlit_root / art_rel) if art_rel else (issues_dir / "article.md")
    text = ""
    if art_path.exists():
        try:
            text = art_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
    if not text:
        return
    try:
        score = score_article(text)
    except Exception:
        return
    score["threshold"] = QUALITY_THRESHOLD
    score["meets_threshold"] = bool(score.get("total", 0) >= QUALITY_THRESHOLD)
    data["quality"] = score
    try:
        atomic_write_json(rp, data)
    except Exception as e:  # noqa: BLE001
        print(f"[pipeline] 质量分写入 result.json 失败（issue={issue}）：{e}", file=sys.stderr)


async def _run(task_id: str, cmd: list[str]) -> None:
    _ensure_loaded()
    task = _TASKS.get(task_id)
    if not task:
        return
    task["status"] = "running"
    _persist()
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
    # 审核流：任何「产出成功」的任务（含非 review 的推送失败但文章+封面已生成场景）
    # 都本地打分并写入 result.json 的 quality 字段（决策支持，不自动拦截）。
    # 推送失败但文章/封面已生成时，run_pipeline 已把整期置为 PENDING_REVIEW + exit 0，
    # 这里据此把质量分补上，让前端质量卡正常出现、三步审核弹窗可打开。
    if task.get("status") == "success":
        try:
            _attach_quality(task["issue"])
        except Exception as e:  # noqa: BLE001
            print(f"[pipeline] 质量打分跳过（issue={task['issue']}）：{e}", file=sys.stderr)
    _persist()


def _run_sync(task_id: str, cmd: list[str]) -> None:
    """同步包装：在后台线程里跑事件循环驱动异步 _run。

    start()/publish() 是同步调用且需立即返回，故仍用线程后台执行；
    此处用 asyncio.run 驱动协程，保持原有的「非阻塞后台执行」语义不变。
    """
    asyncio.run(_run(task_id, cmd))


def get_status(task_id: str) -> dict | None:
    """查询任务状态（含实时日志）。"""
    _ensure_loaded()
    return _TASKS.get(task_id)
