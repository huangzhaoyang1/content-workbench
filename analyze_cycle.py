#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每 9 天跑一次：分析上一周期的文章与运营数据，产出可执行的优化分析报告。

与 sync_obsidian.py 配合使用：
    1. 先跑 sync_obsidian.py      归档文章 + 数据
    2. 再跑 analyze_cycle.py      分析周期 → 写出 _metrics/cycle-analysis-*.md

报告内容：
    1. 方向表现（学 / 用 / 赚）—— 篇数、总/均阅读、在看、分享，并对比上一周期
    2. 标题层分析 —— 各方向阅读 TOP 标题、长度、首字、共性观察
    3. 排版层分析 —— 高/低阅读文章在 emoji / 红色加粗 / 引用块 / 列表 / 段落长度上的差异
    4. 封面待人工观察 —— 列出本期封面文件名，供你对比
    5. 机器规则建议 —— 基于简单规则的优化提示（待人工审核，不可直接执行）

用法：
    python analyze_cycle.py                # 分析最近 9 天
    python analyze_cycle.py --days 45      # 改窗口
    python analyze_cycle.py --vault D:\\Obsidian   # 指定库（默认读配置）
    python analyze_cycle.py --dry-run      # 只打印摘要

只依赖 Python 标准库。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 让脚本能 import 同目录的 sync_obsidian.py（复用其数据收集逻辑）
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync_obsidian as so  # noqa: E402

# ---------------------------------------------------------------------------
# 排版特征提取（自实现，不依赖 backend 包）
# ---------------------------------------------------------------------------
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U0000FE0F]"
)
RED_FONT_RE = re.compile(r'<font\s+color="red">')
ORDERED_RE = re.compile(r"^\s*\d+[.、)]\s+")
BULLET_RE = re.compile(r"^\s*[-*]\s+")


def extract_layout(text: str) -> dict:
    """对一篇 markdown 正文提取排版特征。"""
    lines = text.splitlines()
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return {
        "chars": len(text),
        "emoji": len(EMOJI_RE.findall(text)),
        "red_bold": len(RED_FONT_RE.findall(text)),
        "blockquote": sum(1 for l in lines if l.strip().startswith(">")),
        "ordered": sum(1 for l in lines if ORDERED_RE.match(l)),
        "bullet": sum(1 for l in lines if BULLET_RE.match(l)),
        "para_count": len(paras),
        "avg_para_len": round(sum(len(p) for p in paras) / len(paras)) if paras else 0,
    }


# 报告里展示的排版维度
LAYOUT_FIELDS = [
    ("emoji", "emoji 小标题数"),
    ("red_bold", "红色加粗数"),
    ("blockquote", "金句引用块行数"),
    ("ordered", "有序列表行数"),
    ("bullet", "无序列表行数"),
    ("para_count", "段落数"),
    ("avg_para_len", "平均段落长度"),
]

DIRECTION_ORDER = ["学", "用", "赚", "其他"]


# ---------------------------------------------------------------------------
# 数据准备
# ---------------------------------------------------------------------------
def collect_window(args) -> tuple[list, Path, Path]:
    """收集窗口内已推送的文章，挂上 metrics 与排版特征。"""
    project_root, vault_cfg = so.resolve_paths()
    vault = Path(args.vault).expanduser() if args.vault.strip() else vault_cfg
    if vault is None:
        raise SystemExit("找不到 Obsidian 库路径，请用 --vault 指定或配置 obsidian.vault_path。")

    issues_dir = project_root / "data" / "issues"
    if not issues_dir.is_dir():
        raise SystemExit(f"找不到出稿目录：{issues_dir}")

    pub_dates = so.load_pub_dates(issues_dir)
    all_articles = so.collect_articles(issues_dir, pub_dates)
    cutoff = datetime.now().date() - timedelta(days=args.days)
    articles = [
        a for a in all_articles
        if so.parse_date(a["date"]) and so.parse_date(a["date"]) >= cutoff
        and (a["published"] or a["draft_status"] in ("PUSHED_DRAFT", "PUBLISHED"))
    ]
    metrics_map = so.load_analytics_metrics()
    for a in articles:
        a["metrics"] = metrics_map.get(so.normalize_title(a["title"]), {})
        md = a["article_md"]
        a["layout"] = extract_layout(md.read_text(encoding="utf-8")) if md.is_file() else {}
    return articles, vault, issues_dir


# ---------------------------------------------------------------------------
# 分析
# ---------------------------------------------------------------------------
def direction_stats(articles: list) -> dict:
    """各方向的篇数 / 总·均阅读在看分享，仅统计有数据的篇。"""
    stats: dict = {}
    for direction in DIRECTION_ORDER:
        group = [a for a in articles if a["direction"] == direction]
        with_data = [a for a in group if a["metrics"].get("reads") is not None]
        stats[direction] = {
            "count": len(group),
            "with_data": len(with_data),
            "total_reads": sum(a["metrics"]["reads"] for a in with_data) if with_data else 0,
            "total_likes": sum(a["metrics"]["likes"] for a in with_data) if with_data else 0,
            "total_shares": sum(a["metrics"]["shares"] for a in with_data) if with_data else 0,
        }
    return stats


def top_titles(articles: list, limit: int = 3) -> list[dict]:
    """有阅读数据的标题，按阅读降序。"""
    with_data = [a for a in articles if a["metrics"].get("reads") is not None]
    with_data.sort(key=lambda a: a["metrics"]["reads"], reverse=True)
    return [
        {
            "date": a["date"],
            "direction": a["direction"],
            "title": a["title"],
            "reads": a["metrics"]["reads"],
            "len": len(a["title"]),
            "head": a["title"][:2],
        }
        for a in with_data[:limit]
    ]


def layout_compare(articles: list) -> dict:
    """把有数据的文章按阅读中位数分高/低两组，比较排版特征均值。"""
    with_data = [a for a in articles if a["metrics"].get("reads") is not None]
    if not with_data:
        return {}
    with_data.sort(key=lambda a: a["metrics"]["reads"])
    mid = len(with_data) // 2
    high = with_data[mid:]
    low = with_data[:mid]
    out: dict[str, dict] = {}
    for key, label in LAYOUT_FIELDS:
        h_vals = [a["layout"].get(key, 0) for a in high if a["layout"]]
        l_vals = [a["layout"].get(key, 0) for a in low if a["layout"]]
        if not h_vals or not l_vals:
            continue
        h_avg = round(sum(h_vals) / len(h_vals), 1)
        l_avg = round(sum(l_vals) / len(l_vals), 1)
        diff = h_avg - l_avg
        out[key] = {
            "label": label,
            "high": h_avg,
            "low": l_avg,
            "note": "明显更高" if diff > 1 else ("明显更低" if diff < -1 else "接近"),
        }
    return out


def read_prev_cycle(metrics_dir: Path, current_name: str) -> dict | None:
    """读上一个 cycle-*.md 汇总文件，解析方向表现表用于环比。"""
    files = sorted(metrics_dir.glob("cycle-*.md")) if metrics_dir.is_dir() else []
    files = [f for f in files if f.name != current_name and "analysis" not in f.name
             and "suggestion" not in f.name]
    if not files:
        return None
    text = files[-1].read_text(encoding="utf-8")
    stats: dict = {}
    for direction in DIRECTION_ORDER:
        m = re.search(rf"^\|\s*{direction}\s*\|\s*(\d+)\s*\|\s*([\d-]+)\s*\|\s*([\d-]+)\s*\|",
                      text, re.M)
        if m:
            stats[direction] = {
                "count": int(m.group(1)),
                "total_reads": m.group(2),
                "avg_reads": m.group(3),
            }
    return {"file": files[-1].name, "stats": stats}


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------
def build_report(articles: list, vault: Path, metrics_dir: Path) -> str:
    dates = sorted(a["date"] for a in articles)
    start, end = dates[0], dates[-1]
    stats = direction_stats(articles)
    tops = top_titles(articles)
    layout = layout_compare(articles)
    with_data = [a for a in articles if a["metrics"].get("reads") is not None]
    prev = read_prev_cycle(metrics_dir, "cycle-analysis")

    lines = [
        f"# 周期分析报告（{start} ~ {end}）",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} · 窗口 {len(articles)} 篇 · 有数据 {len(with_data)} 篇",
        "",
        "## 1. 三大方向表现",
        "",
        "| 方向 | 篇数 | 有数据 | 总阅读 | 均阅读 | 总在看 | 总分享 | 环比均阅读 |",
        "|------|------|--------|--------|--------|--------|--------|------------|",
    ]
    for direction in DIRECTION_ORDER:
        s = stats[direction]
        prev_s = (prev or {}).get("stats", {}).get(direction)
        prev_avg = prev_s.get("avg_reads") if prev_s else "-"
        count = s["count"]
        avg_reads = round(s["total_reads"] / s["with_data"]) if s["with_data"] else "-"
        lines.append(
            f"| {direction} | {count} | {s['with_data']} | {s['total_reads'] or '-'} | "
            f"{avg_reads} | {s['total_likes'] or '-'} | {s['total_shares'] or '-'} | "
            f"{prev_avg} |"
        )
    if prev:
        lines.append("")
        lines.append(f"> 环比依据上一份汇总 `{prev['file']}`（- 表示上一份无该方向数据）。")
    else:
        lines.append("")
        lines.append("> 暂无上一周期汇总，首次分析不显示环比。")

    lines += [
        "",
        "## 2. 标题层分析（有阅读数据，按阅读降序）",
        "",
    ]
    if tops:
        lines += [
            "| 日期 | 方向 | 标题 | 长度 | 首字 | 阅读 |",
            "|------|------|------|------|------|------|",
        ]
        for t in tops:
            lines.append(
                f"| {t['date']} | {t['direction']} | {t['title']} | "
                f"{t['len']} | {t['head']} | {t['reads']} |"
            )
        heads = [t["head"] for t in tops]
        lines += [
            "",
            f"- 阅读 TOP{len(tops)} 首字/词：{'、'.join(f'「{h}」' for h in heads) if heads else '-'}",
            "- 观察：高于平均阅读的标题是否更短 / 带数字 / 第一人称？请人工对照原文确认。",
        ]
    else:
        lines.append("- 本期没有文章带阅读数据。请先在「数据分析」页导入公众号后台数据后重跑。")

    lines += [
        "",
        "## 3. 排版层分析（按阅读中位数分高/低两组）",
        "",
    ]
    if layout:
        lines += [
            "| 排版元素 | 高阅读组均值 | 低阅读组均值 | 差异 |",
            "|----------|--------------|--------------|------|",
        ]
        for key in LAYOUT_FIELDS:
            item = layout.get(key)
            if item:
                lines.append(
                    f"| {item['label']} | {item['high']} | {item['low']} | {item['note']} |"
                )
        lines += [
            "",
            "- 排版数据来自 `quality.py` 同口径的粗略统计（emoji / 红色加粗 / 引用块 / 列表 / 段落）。",
            "- 差异为「明显更高/更低」的元素，建议下一周期在 prompt 里强化或弱化。",
        ]
    else:
        lines.append("- 无阅读数据，无法做排版分组对比。")

    lines += [
        "",
        "## 4. 封面待人工观察",
        "",
    ]
    covers = [f"issue{a['issue']}/{a['cover'].name}" for a in articles if a["cover"].is_file()]
    if covers:
        lines.append(f"- 本期封面：{ '、'.join(covers) }")
        lines.append("- 请人工对比高阅读文章的封面共性（颜色 / 文字 / 构图），公众号无 CTR 接口，这一步只能靠肉眼。")
    else:
        lines.append("- 本期无封面文件。")

    lines += [
        "",
        "## 5. 机器规则建议（待人工审核，勿直接执行）",
        "",
    ]
    suggestions = build_suggestions(stats, tops, layout, with_data)
    if suggestions:
        lines += [f"- {s}" for s in suggestions]
    else:
        lines.append("- 样本不足，暂无机器建议。先导满一个周期（≥9 天）的数据再分析。")
    lines.append("")

    return "\n".join(lines)


def build_suggestions(stats: dict, tops: list, layout: dict, with_data: list) -> list[str]:
    if len(with_data) < 3:
        return []
    out: list[str] = []
    # 方向权重
    scored = [(d, s["total_reads"] / s["with_data"] if s["with_data"] else 0)
              for d, s in stats.items() if s["with_data"]]
    scored = [x for x in scored if x[1] > 0]
    if scored:
        scored.sort(key=lambda x: x[1], reverse=True)
        best, best_avg = scored[0]
        if len(scored) >= 2 and best_avg > scored[1][1] * 1.3:
            out.append(f"「{best}」方向均阅读明显领先（{best_avg:.0f}），选题时提高该方向权重。")
    # 标题特征
    if tops:
        short_count = sum(1 for t in tops if t["len"] <= 20)
        if short_count >= max(1, len(tops) - 1):
            out.append("高阅读标题偏短（≤20 字），选题/改写时收紧标题长度。")
        heads = "、".join(f"「{t['head']}」" for t in tops)
        out.append(f"高阅读标题首字集中在 {heads}，可作后续起标题的风格参考。")
    # 排版
    if layout:
        for key in LAYOUT_FIELDS:
            item = layout.get(key)
            if item and item["note"] == "明显更高":
                out.append(f"高阅读组 {item['label']} 明显更高（{item['high']} vs {item['low']}），下一周期在改写 prompt 里强化该元素。")
            elif item and item["note"] == "明显更低":
                out.append(f"高阅读组 {item['label']} 明显更低（{item['high']} vs {item['low']}），建议检查是否过度使用。")
    return out


def write_cycle_insight(articles: list, stats: dict, out_path: Path) -> None:
    """把周期洞察写回 backend/data/cycle_insight.json，选题生成时自动注入。"""
    import json
    dates = sorted(a["date"] for a in articles)
    data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "period": f"{dates[0]} ~ {dates[-1]}",
        "directions": {
            d: {
                "count": s["count"],
                "avg_reads": round(s["total_reads"] / s["with_data"]) if s["with_data"] else None,
            }
            for d, s in stats.items()
        },
        "top_titles": [
            {"title": t["title"], "reads": t["reads"], "direction": t["direction"]}
            for t in top_titles(articles, 3)
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"周期洞察已写回：{out_path}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="分析上一周期文章与运营数据，产出优化分析报告",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--days", type=int, default=so.DEFAULT_DAYS,
                        help="分析最近 N 天内的文章（默认 9 天）")
    parser.add_argument("--vault", default="", help="Obsidian 库根目录（默认读配置）")
    parser.add_argument("--dry-run", action="store_true", help="只打印摘要，不写报告文件")
    args = parser.parse_args()

    articles, vault, issues_dir = collect_window(args)
    metrics_dir = vault / so.VAULT_FOLDER / "_metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    if not articles:
        print(f"窗口内没有文章可分析（最近 {args.days} 天）。先跑 sync_obsidian.py 归档后再分析。")
        return 0

    report = build_report(articles, vault, metrics_dir)
    dates = sorted(a["date"] for a in articles)
    fname = f"cycle-analysis-{dates[0].replace('-', '')}-{dates[-1].replace('-', '')}.md"
    if args.dry_run:
        for line in report.splitlines()[:12]:
            print(line)
        print("...")
        print(f"[dry-run] 将写入 _metrics/{fname}")
        return 0

    (metrics_dir / fname).write_text(report, encoding="utf-8")
    # 周期洞察写回后端，选题生成时自动注入（闭环最后一环）
    stats = direction_stats(articles)
    insight_path = Path(__file__).resolve().parent / "backend" / "data" / "cycle_insight.json"
    write_cycle_insight(articles, stats, insight_path)
    print(f"分析完成：{len(articles)} 篇，有数据 {sum(1 for a in articles if a['metrics'].get('reads') is not None)} 篇")
    print(f"报告已写入：{metrics_dir / fname}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
