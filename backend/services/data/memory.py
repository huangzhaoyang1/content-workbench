"""对话记忆：SQLite 落盘 backend/data/memory.db。

表 conversation_turns(id, session_id, role, content, created_at)。
供 dissect 路由把「最近若干轮对话」拼进上下文，并把本次输入输出存回，
实现连续对话体验（拆解说人话、续写不跑题）。

设计要点：
- 一行 = 一轮（user / assistant / system），session_id 区分不同会话。
- 写读都走同一把模块锁，低并发下足够；SQLite 单文件、零依赖。
- get_recent 取最近 limit 条（默认 6），按时间升序返回（自然对话顺序），
  方便直接拼进 prompt；超过 limit 的旧轮不返回，天然限制上下文体积。
- 历史轮次拼进上下文时会截断到 MAX_TURN_CHARS，避免上一轮超长输出把
  本次 token 撑爆；完整输出仍原样落盘（audit / history 可追溯）。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime

from ..system.config import DATA_DIR

MEMORY_DB_PATH = DATA_DIR / "memory.db"
_LOCK = threading.Lock()
MAX_TURN_CHARS = 600          # 拼上下文时单轮最大字符数（截断历史超长输出）
VALID_ROLES = ("user", "assistant", "system")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_turns (
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON conversation_turns(session_id, created_at);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _db_conn() -> "sqlite3.Connection":
    """开一条连接，顺手确保表结构存在（CREATE TABLE IF NOT EXISTS 幂等）。"""
    conn = sqlite3.connect(MEMORY_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def save_turn(session_id: str, role: str, content: str) -> dict:
    """存一条对话轮次，返回落盘后的记录（含 id / created_at）。

    session_id 必填；role 限定为 user/assistant/system；content 不可为空。
    """
    session_id = (session_id or "").strip()
    role = (role or "").strip()
    content = content or ""
    if not session_id:
        raise ValueError("session_id 不能为空")
    if role not in VALID_ROLES:
        raise ValueError(f"role 必须是 {VALID_ROLES} 之一，收到：{role!r}")
    if not content.strip():
        raise ValueError("content 不能为空")
    record = {
        "id": uuid.uuid4().hex[:12],
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": _now(),
    }
    with _LOCK, _db_conn() as conn:
        conn.execute(
            "INSERT INTO conversation_turns "
            "(id, session_id, role, content, created_at) "
            "VALUES (:id, :session_id, :role, :content, :created_at)",
            record,
        )
        conn.commit()
    return record


def get_recent(session_id: str, limit: int = 6) -> list[dict]:
    """取某会话最近 limit 条对话（按时间升序，即自然对话顺序）。

    session_id 空时返回 []；limit 夹紧到 [1, 50]。
    """
    session_id = (session_id or "").strip()
    if not session_id:
        return []
    limit = max(1, min(int(limit), 50))
    with _LOCK, _db_conn() as conn:
        rows = conn.execute(
            "SELECT id, session_id, role, content, created_at "
            "FROM conversation_turns "
            "WHERE session_id = ? "
            "ORDER BY created_at DESC, rowid DESC "
            "LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def format_turns(turns: list[dict], max_chars: int = MAX_TURN_CHARS) -> str:
    """把若干轮对话渲染成可拼进 prompt 的文本。

    超长轮次（典型是上一轮的超长输出）截断到 max_chars，防止上下文无限膨胀。
    """
    if not turns:
        return ""
    label = {"user": "用户", "assistant": "助手", "system": "系统"}
    parts: list[str] = []
    for t in turns:
        role = label.get(t.get("role"), t.get("role", "?"))
        content = t.get("content") or ""
        if len(content) > max_chars:
            content = content[:max_chars] + "…(已截断)"
        parts.append(f"【{role}】{content}")
    return "\n".join(parts)


def get_recent_context(session_id: str, limit: int = 6, max_chars: int = MAX_TURN_CHARS) -> str:
    """取最近 limit 轮并渲染成上下文文本；无会话/无记录时返回空串。"""
    return format_turns(get_recent(session_id, limit), max_chars)
