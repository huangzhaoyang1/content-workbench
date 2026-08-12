# -*- coding: utf-8 -*-
"""评估运行器：读 eval_questions.json，按 category 路由到真实服务层，比对 expected_keywords，落盘结果。

路由：
  - dissect          → services.content.dissect.analyze(text=sample_text)
                        题目缺 sample_text/url → SKIP（按规则不编造输入）
  - topic            → services.content.topic.generate(cfg)            （纯模板，无 LLM）
  - hotspot          → services.integration.hotspot.search(cfg, kw, time_label)
                        kw 取自题目『...』引用，缺则 SKIP（不编造检索词）
  - retrieval_history→ services.data.retrieval.search(query=question)  （本地 jieba + SQLite）

记分：每题 expected_keywords「任一命中即过」（二进制 pass/fail，子串匹配）。
结果：eval/result/{id}_{category}.json（单题）；eval/result/_summary.json（汇总）。

设计原则（建立可重复基线，不是刷高分）：
  - 逐条串行执行（天然限并发，便于将来有 key 时也不打爆配额）。
  - 每个服务调用包 try/except：报错记 status=error，不中断整体。
  - skipped / error 不计入准确率分母（属输入/基建缺口，单独汇报），准确率 = passed / ran。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTENT_ROOT = HERE.parent.parent  # content-workbench/
sys.path.insert(0, str(CONTENT_ROOT))

from backend.services.system.config import load_config  # noqa: E402
from backend.services.content import dissect as s_dissect  # noqa: E402
from backend.services.content import topic as s_topic  # noqa: E402
from backend.services.integration import hotspot as s_hotspot  # noqa: E402
from backend.services.data import retrieval as s_retrieval  # noqa: E402

QUESTIONS = HERE / "eval_questions.json"
RESULT_DIR = HERE / "result"
TIME_LABEL_DEFAULT = "近7天"


def _extract_quoted(text: str) -> str:
    """提取题目中『...』/「...」内的第一个短语作为检索词。"""
    m = re.search(r"[「『](.+?)[」』]", text or "")
    return m.group(1) if m else ""


def _extract_time_label(text: str) -> str:
    for label in ("最近一周", "近7天", "近 7 天", "本周", "近30天", "近30 天", "近一月", "最近一月", "本月"):
        if label in (text or ""):
            return label
    return TIME_LABEL_DEFAULT


def _to_text(obj) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


def _score(out_text: str, expected: list) -> tuple[bool, list, list]:
    hits = [k for k in expected if k and k in out_text]
    missed = [k for k in expected if k and k not in out_text]
    return (len(hits) > 0, hits, missed)


# --------------------------------------------------------------------------- #
# 各 category 的调用实现（返回 dict，含 status: ran|skipped|error）
# --------------------------------------------------------------------------- #
def run_dissect(q: dict) -> dict:
    sample = q.get("sample_text") or q.get("url")
    if not str(sample or "").strip():
        return {"status": "skipped", "reason": "缺 sample_text/url，按规则跳过（不编造输入）"}
    try:
        if q.get("url"):
            out = s_dissect.analyze(url=str(sample))
        else:
            out = s_dissect.analyze(text=str(sample))
        return {"status": "ran", "output": _to_text(out), "service": "dissect.analyze"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}


def run_topic(q: dict, cfg: dict) -> dict:
    try:
        out = s_topic.generate(cfg)
        return {"status": "ran", "output": _to_text(out), "service": "topic.generate"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}


def run_hotspot(q: dict, cfg: dict) -> dict:
    kw = _extract_quoted(q.get("question", "")) or (q.get("keyword") or "")
    if not kw:
        return {"status": "skipped", "reason": "无法从题目可靠提取检索词（无『...』引用且缺 keyword 字段，不编造）"}
    time_label = _extract_time_label(q.get("question", ""))
    try:
        out = s_hotspot.search(cfg, kw, time_label)
        return {"status": "ran", "output": _to_text(out), "service": "hotspot.search",
                "keyword": kw, "time_label": time_label}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}


def run_retrieval(q: dict) -> dict:
    query = q.get("query") or q.get("question") or ""
    if not str(query).strip():
        return {"status": "skipped", "reason": "缺 query/question，不编造"}
    try:
        out = s_retrieval.search(query=str(query), top_k=5)
        return {"status": "ran", "output": _to_text(out), "service": "retrieval.search", "query": str(query)}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}


def dispatch(q: dict, cfg: dict) -> dict:
    cat = q.get("category")
    if cat == "dissect":
        return run_dissect(q)
    if cat == "topic":
        return run_topic(q, cfg)
    if cat == "hotspot":
        return run_hotspot(q, cfg)
    if cat == "retrieval_history":
        return run_retrieval(q)
    return {"status": "skipped", "reason": f"未知 category: {cat}"}


def main() -> dict:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    cfg = load_config()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    per_cat: dict[str, list[int, int]] = {}  # cat -> [passed, attempted(ran)]

    print(f"评估题目数: {len(questions)}\n")
    for q in questions:
        qid = q.get("id")
        cat = q.get("category")
        t0 = time.time()
        try:
            r = dispatch(q, cfg)
        except Exception as e:  # noqa: BLE001 兜底：单题异常不中断整体
            r = {"status": "error", "reason": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}
        dt = time.time() - t0

        rec = {
            "id": qid,
            "category": cat,
            "question": q.get("question"),
            "status": r["status"],
            "elapsed_sec": round(dt, 3),
            "service": r.get("service"),
        }
        if r["status"] == "ran":
            out_text = r.get("output", "")
            passed, hits, missed = _score(out_text, q.get("expected_keywords", []))
            rec.update({
                "passed": passed,
                "hits": hits,
                "missed": missed,
                "output_excerpt": out_text[:2000],
            })
            if r.get("keyword"):
                rec["keyword"] = r["keyword"]
            if r.get("query"):
                rec["query"] = r["query"]
            per_cat.setdefault(cat, [0, 0])
            per_cat[cat][1] += 1
            if passed:
                per_cat[cat][0] += 1
            verdict = "PASS" if passed else "FAIL"
        else:
            rec["reason"] = r.get("reason")
            if r.get("trace"):
                rec["trace"] = r.get("trace")
            verdict = "SKIP" if r["status"] == "skipped" else "ERR "

        out_path = RESULT_DIR / f"{qid}_{cat}.json"
        out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(rec)
        extra = r.get("reason") or (",".join(rec.get("hits", [])) or "")
        print(f"[{qid:>2}] {cat:<16} {r['status']:<7} {verdict:<4} {dt:5.2f}s  {extra}")

    # ---------------- 汇总 ----------------
    attempted = sum(v[1] for v in per_cat.values())
    passed = sum(v[0] for v in per_cat.values())
    overall = (passed / attempted) if attempted else 0.0
    cat_acc = {c: (p / a if a else None) for c, (p, a) in per_cat.items()}
    errored = [r for r in results if r["status"] == "error"]
    skipped = [r for r in results if r["status"] == "skipped"]
    weakest = None
    valid = [(c, a) for c, a in cat_acc.items() if a is not None]
    if valid:
        weakest = min(valid, key=lambda kv: kv[1])

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_questions": len(questions),
        "attempted": attempted,
        "skipped": len(skipped),
        "errored": len(errored),
        "passed": passed,
        "failed": attempted - passed,
        "overall_accuracy": round(overall, 4),
        "per_category_accuracy": {c: (round(a, 4) if a is not None else None) for c, a in cat_acc.items()},
        "per_category_counts": {c: {"passed": p, "attempted": a} for c, (p, a) in per_cat.items()},
        "weakest_category": {"category": weakest[0], "accuracy": round(weakest[1], 4)} if weakest else None,
        "skipped_questions": [{"id": r["id"], "category": r["category"], "reason": r.get("reason")} for r in skipped],
        "errored_questions": [{"id": r["id"], "category": r["category"], "reason": r.get("reason")} for r in errored],
    }
    (RESULT_DIR / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n==================== 汇总 ====================")
    print(f"总题数={len(questions)}  尝试(ran)={attempted}  跳过={len(skipped)}  报错={len(errored)}")
    print(f"通过={passed}  失败={attempted - passed}")
    print(f"整体准确率(以 ran 为分母) = {overall:.2%}")
    for c, a in cat_acc.items():
        cnt = per_cat[c]
        print(f"  {c:<16}: {('%.2f%%' % (a * 100)) if a is not None else 'N/A':>8}  ({cnt[0]}/{cnt[1]})")
    if weakest:
        print(f"最弱类别: {weakest[0]} ({weakest[1]:.2%})")
    print("\n跳过题目（不编造输入）:")
    for s in summary["skipped_questions"]:
        print(f"  #{s['id']} {s['category']}: {s['reason']}")
    if errored:
        print("\n报错题目（基建/依赖缺口）:")
        for e in summary["errored_questions"]:
            print(f"  #{e['id']} {e['category']}: {e['reason']}")
    print(f"\n明细: eval/result/{{id}}_{{category}}.json  |  汇总: eval/result/_summary.json")
    return summary


if __name__ == "__main__":
    main()
