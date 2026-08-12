"""中文检索：对 topic_library.json / douyin_sync.json 建 SQLite FTS5 索引（jieba 分词）。

表 retrieval_docs(doc_id, source, category, title, content, created_at, priority)
- FTS5 虚拟表；title / content 列存「原文」用于返回展示，title_seg / content_seg 列存
  「jieba 分词后空格拼接」的文本，真正参与 FTS5 全文索引（unicode61 按空格切词）。
  其余列（doc_id / source / category / priority / created_at）为 UNINDEXED 元数据，用于过滤。
- 分词策略：jieba.cut 切词 → 丢弃纯空白/纯标点 token → 空格拼接。索引与查询用同一套分词，
  保证「索引侧」和「查询侧」词表一致。
- 检索 search(query, filters, top_k=5)：query 同样 jieba 分词 → 拼成 FTS5 MATCH；
  filters 支持 category(精确) / priority(精确) / 时间范围(start,end，对 created_at 做 BETWEEN)。
- 索引库位于 backend/data/retrieval.db；data/retrieval_index.py 可手动重建。
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from ..system.config import DATA_DIR

try:
    import jieba
    jieba.setLogLevel(logging.WARNING)   # 抑制 jieba 的 "Loading model" 之类日志
    _JIEBA_OK = True
except Exception:   # pragma: no cover - jieba 未安装时模块仍可导入，仅建/检索引失败并给出明确报错
    _JIEBA_OK = False

RETRIEVAL_DB_PATH = DATA_DIR / "retrieval.db"
_TABLE = "retrieval_docs"
_LOCK = threading.Lock()

# 来源文件名 -> 在索引里的 source 标记
_TOPIC_FILE = "topic_library.json"
_DOUYIN_FILE = "douyin_sync.json"

# 建表语句（FTS5）。title/content 存原文（展示用，UNINDEXED 不参与检索）；
# title_seg/content_seg 存分词结果，是真正被检索的列。priority 为用户要求的过滤维度，
# 原文 schema 未列但过滤需要，这里作为 UNINDEXED 列补上。
_SCHEMA = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS {_TABLE} USING fts5(
    doc_id      UNINDEXED,
    source      UNINDEXED,
    category    UNINDEXED,
    title       UNINDEXED,
    content     UNINDEXED,
    title_seg,
    content_seg,
    priority    UNINDEXED,
    created_at  UNINDEXED,
    tokenize='unicode61'
);
"""

# 中文/数字/字母 至少含一个，才算有效词（丢弃纯标点 token）
_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]")
_PRIORITY_RANK = {"低": 1, "中": 2, "高": 3}

_jieba_inited = False


def _ensure_jieba() -> None:
    """懒初始化 jieba 词典（首次切词前调用一次，预热避免首次检索变慢）。"""
    global _jieba_inited
    if not _JIEBA_OK:
        raise RuntimeError(
            "未安装 jieba，无法建索引/检索。请先 `pip install jieba`，"
            "或运行 backend/data/retrieval_index.py 前确认依赖已就绪。"
        )
    if not _jieba_inited:
        jieba.initialize()
        _jieba_inited = True


def _seg(text: str) -> str:
    """jieba 分词 → 过滤纯标点 → 空格拼接，作为 FTS5 索引/查询串。"""
    _ensure_jieba()
    if not text:
        return ""
    toks = [t for t in jieba.cut(text) if t and t.strip() and _TOKEN_RE.search(t)]
    return " ".join(toks)


def _norm_dt(value) -> str:
    """统一 created_at 为 'YYYY-MM-DD HH:MM:SS' 文本，便于字典序比较 / 时间范围过滤。

    - 已是该格式的字符串原样返回；
    - 纯数字（Unix 秒级时间戳）转成可读时间；
    - 其它情况转 str 兜底。
    """
    if value is None:
        return ""
    s = str(value).strip()
    if s.isdigit() and len(s) >= 9:
        try:
            return datetime.fromtimestamp(int(s)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return s
    return s


def _norm_start(value: str) -> str:
    """时间范围下界：'YYYY-MM-DD' 补 ' 00:00:00'。"""
    s = (value or "").strip()
    return s if len(s) > 10 else s + " 00:00:00" if s else ""


def _norm_end(value: str) -> str:
    """时间范围上界：'YYYY-MM-DD' 补 ' 23:59:59'。"""
    s = (value or "").strip()
    return s if len(s) > 10 else s + " 23:59:59" if s else ""


# --------------------------------------------------------------------------- #
# 文档收集：把两个 JSON 归一成统一的 doc 结构
# --------------------------------------------------------------------------- #
def _collect_docs() -> list[dict]:
    docs: list[dict] = []

    # 1) topic_library.json -> items[]
    tp = DATA_DIR / _TOPIC_FILE
    if tp.exists():
        try:
            data = json.loads(tp.read_text(encoding="utf-8"))
            items = data.get("items") if isinstance(data, dict) else None
            if isinstance(items, list):
                for rec in items:
                    if not isinstance(rec, dict):
                        continue
                    title = str(rec.get("title") or "")
                    content = str(rec.get("content") or "")
                    cid = str(rec.get("id") or "")
                    docs.append({
                        "doc_id": f"topic:{cid}" if cid else f"topic:{len(docs)}",
                        "source": str(rec.get("source") or "topic_library"),
                        "category": str(rec.get("category") or "未分类"),
                        "title": title,
                        "content": content,
                        "priority": str(rec.get("priority") or ""),
                        "created_at": _norm_dt(rec.get("created_at") or rec.get("updated_at")),
                    })
        except Exception:
            pass

    # 2) douyin_sync.json -> records[]
    dp = DATA_DIR / _DOUYIN_FILE
    if dp.exists():
        try:
            data = json.loads(dp.read_text(encoding="utf-8"))
            records = data.get("records") if isinstance(data, dict) else None
            if isinstance(records, list):
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    title = str(rec.get("title") or "")
                    content = " ".join(
                        str(rec.get(k) or "")
                        for k in ("desc", "text", "note")
                        if rec.get(k)
                    ).strip()
                    cid = str(rec.get("id") or "")
                    docs.append({
                        "doc_id": f"douyin:{cid}" if cid else f"douyin:{len(docs)}",
                        "source": str(rec.get("source_name") or "douyin_sync"),
                        "category": str(rec.get("category") or "未分类"),
                        "title": title,
                        "content": content,
                        "priority": str(rec.get("priority") or ""),
                        "created_at": _norm_dt(rec.get("create_time") or rec.get("fetched_at")),
                    })
        except Exception:
            pass

    return docs


# --------------------------------------------------------------------------- #
# 索引构建 / 查询
# --------------------------------------------------------------------------- #
def _db_conn() -> "sqlite3.Connection":
    RETRIEVAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(RETRIEVAL_DB_PATH)
    conn.row_factory = sqlite3.Row
    # 强制 autocommit：建虚拟表用普通 execute，事务由 build_index 显式 BEGIN/COMMIT 控制，
    # 避免 isolation_level 默认行为在「建表后立即写数据」时触发
    # "cannot start a transaction within a transaction"。
    conn.isolation_level = None
    conn.execute(_SCHEMA.strip())   # CREATE VIRTUAL TABLE IF NOT EXISTS，幂等
    return conn


def build_index(force: bool = False) -> int:
    """重建 FTS5 索引，返回索引文档数。force=True 时先清空旧表。

    索引逻辑：对每个 doc 的 title/content 做 jieba 分词，写进 title_seg/content_seg；
    原文留在 title/content 列供结果展示。
    """
    docs = _collect_docs()
    with _LOCK:
        conn = _db_conn()
        try:
            if force:
                conn.execute(f"DELETE FROM {_TABLE}")
            else:
                # 非强制模式也先清空，保证与源数据一致（本模块每次全量重建）
                conn.execute(f"DELETE FROM {_TABLE}")
            conn.execute("BEGIN")
            for d in docs:
                conn.execute(
                    f"INSERT INTO {_TABLE} "
                    "(doc_id, source, category, title, content, title_seg, content_seg, priority, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (d["doc_id"], d["source"], d["category"], d["title"], d["content"],
                     _seg(d["title"]), _seg(d["content"]), d["priority"], d["created_at"]),
                )
            conn.execute("COMMIT")
        finally:
            conn.close()
    return len(docs)


def _has_index() -> bool:
    if not RETRIEVAL_DB_PATH.exists():
        return False
    try:
        with _LOCK, _db_conn() as conn:
            n = conn.execute(f"SELECT count(*) FROM {_TABLE}").fetchone()[0]
        return n > 0
    except Exception:
        return False


def ensure_index() -> None:
    """懒建索引：索引库缺失或为空时自动全量构建（首次检索时触发）。"""
    if not _has_index():
        build_index(force=True)


def search(query: str, filters: dict | None = None, top_k: int = 5) -> list[dict]:
    """中文检索。

    query  : 关键词（会 jieba 分词后与索引做 AND 匹配）；为空时退化为「仅按过滤器浏览」。
    filters: 可选 {category, priority, start, end}
             - category : 精确匹配分类
             - priority : 精确匹配优先级（'高'/'中'/'低'，为空串表示未设）
             - start/end: created_at 时间范围（'YYYY-MM-DD' 或完整时间戳）
    top_k  : 返回条数，默认 5。
    返回    : [{doc_id, source, category, title, content, priority, created_at, rank}, ...]
             rank 为 bm25 分值（越小越相关；无关键词时为 None）。
    """
    ensure_index()
    filters = filters or {}
    top_k = max(1, int(top_k))

    tokens = [t for t in _seg(query).split() if t] if query else []
    match_expr = " ".join(f'"{tok.replace(chr(34), chr(34) * 2)}"' for tok in tokens)

    where: list[str] = []
    params: list = []
    if match_expr:
        where.append(f"{_TABLE} MATCH ?")
        params.append(match_expr)
    if filters.get("category"):
        where.append("category = ?")
        params.append(str(filters["category"]))
    if filters.get("start"):
        where.append("created_at >= ?")
        params.append(_norm_start(str(filters["start"])))
    if filters.get("end"):
        where.append("created_at <= ?")
        params.append(_norm_end(str(filters["end"])))
    # priority 精确匹配（含空串）。注：priority 是文本档位，非数值；若需「>=某档」可用 _PRIORITY_RANK 自扩展。
    if "priority" in filters:
        where.append("priority = ?")
        params.append(str(filters["priority"]))

    if match_expr:
        sql = (f"SELECT doc_id, source, category, title, content, priority, created_at, "
               f"bm25({_TABLE}) AS rank FROM {_TABLE}")
        order = "ORDER BY rank"
    else:
        sql = (f"SELECT doc_id, source, category, title, content, priority, created_at, "
               f"NULL AS rank FROM {_TABLE}")
        order = "ORDER BY created_at DESC"

    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" {order} LIMIT ?"
    params.append(top_k)

    with _LOCK, _db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def index_stats() -> dict:
    """索引概况：库是否存在、文档数、各来源分布。"""
    if not RETRIEVAL_DB_PATH.exists():
        return {"exists": False, "db_path": str(RETRIEVAL_DB_PATH), "doc_count": 0, "by_source": {}}
    try:
        with _LOCK, _db_conn() as conn:
            n = conn.execute(f"SELECT count(*) FROM {_TABLE}").fetchone()[0]
            by_src = {r["source"]: r["c"] for r in
                      conn.execute(f"SELECT source, count(*) AS c FROM {_TABLE} GROUP BY source").fetchall()}
        return {"exists": True, "db_path": str(RETRIEVAL_DB_PATH), "doc_count": n, "by_source": by_src}
    except Exception as e:
        return {"exists": True, "db_path": str(RETRIEVAL_DB_PATH), "doc_count": 0,
                "by_source": {}, "error": str(e)}
