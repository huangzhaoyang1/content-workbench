#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把最近产出的公众号文章 + 运营数据一键同步到 Obsidian 笔记库。

使用场景：每 9 天（3 轮内容循环）运行一次，把这段周期里推送过的文章、
封面、以及后台导入的阅读数据归档进 Obsidian，形成可追溯的历史档案。

用法：
    python sync_obsidian.py                      # 同步最近 9 天的文章
    python sync_obsidian.py --days 14            # 改成最近 14 天
    python sync_obsidian.py --vault D:\\Obsidian  # 指定笔记库根目录（不填则读配置 obsidian.vault_path）
    python sync_obsidian.py --force              # 已同步过的文章也重新写
    python sync_obsidian.py --dry-run            # 只打印计划，不写任何文件

在 Obsidian 里生成的目录结构：
    <vault>/AI学习日记/
        _index.md                    文章索引（自动维护）
        _metrics/cycle-YYYYMMDD-YYYYMMDD.md   9 天周期数据汇总
        articles/2026-08-24-学-标题.md        文章正文（带 YAML frontmatter）
        covers/2026-08-24-学-issue99113.png   封面图

数据来源：
    <project_root>/data/issues/<N>/  出稿目录（result.json / article.md / cover）
    <project_root>/data/issues/issue-YYYY-MM-DD-pub-<N>.md  已发布记录（文件名带日期）
    backend/data/analytics_last.json  导入的公众号运营数据（按标题匹配阅读/在看/分享）

只依赖 Python 标准库，任何 python3 都能跑。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DATA_DIR = SCRIPT_DIR / "backend" / "data"
CONFIG_PATH = BACKEND_DATA_DIR / "workbench_config.json"
ANALYTICS_PATH = BACKEND_DATA_DIR / "analytics_last.json"

DEFAULT_DAYS = 9                       # 一轮内容循环 = 3 方向 × 3 天
VAULT_FOLDER = "AI学习日记"            # vault 内归档子目录
SYNC_STATE_FILE = "_sync_state.json"   # 记录已同步过的 issue 号

# 三大内容方向（学 / 用 / 赚）+ 关键词启发式判定。
# 关键词同时匹配标题与 result.json 的 angle 字段，命中词最多者为该篇方向。
# 注意：避免单字泛词（如「用」「省」「赚」「学」）误伤，用词组代替。
DIRECTIONS = [
    ("学", ["学习", "方法", "认知", "思考", "复盘", "踩坑", "日记", "笔记", "入门",
            "小白", "概念", "理解", "读完", "看完", "记录", "心得", "误区", "真相",
            "形态", "本质", "是什么", "为什么"]),
    ("用", ["工具", "实测", "测试", "教程", "清单", "提效", "效率", "免费", "插件",
            "安装", "使用", "对比", "流程", "自动化", "工作流", "codex", "deepseek",
            "harness", "提示词", "模型", "面板", "开源", "部署", "脚本", "ai写作"]),
    ("赚", ["副业", "变现", "赚钱", "收入", "收益", "流量", "公众号", "粉丝", "涨粉",
            "涨阅读", "阅读量", "账单", "省钱", "降价", "涨价", "成本", "充值", "定价",
            "省下", "省了", "付费", "价格", "月入", "稿费", "账", "便宜", "暴利"]),
]

ISSUE_DIR_RE = re.compile(r"^\d+$")
PUB_DATE_RE = re.compile(r"issue-(\d{4}-\d{2}-\d{2})-pub-(\d+)\.md")
NUMBER_RE = re.compile(r"\d+")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"[警告] {msg}", flush=True)


def safe_name(text: str, max_len: int = 40) -> str:
    """文件名安全化：去掉非法字符与换行，截断长度。"""
    text = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        text = "未命名"
    return text[:max_len].rstrip(".").strip() or "未命名"


def normalize_title(title: str) -> str:
    """标题归一化，用于与 analytics 记录匹配。"""
    return re.sub(r"[\s《》「」【】'\"“”‘’]+", "", (title or "")).lower()


def match_direction(title: str, angle: str) -> str:
    """按关键词规则把一篇文章归到「学 / 用 / 赚」，都不命中则归「其他」。"""
    text = f"{title or ''} {angle or ''}".lower()
    best_dir, best_hits = "其他", 0
    for name, keywords in DIRECTIONS:
        hits = sum(1 for kw in keywords if kw.lower() in text)
        if hits > best_hits:
            best_dir, best_hits = name, hits
    return best_dir


def load_json(path: Path) -> dict | list | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 数据收集
# ---------------------------------------------------------------------------
def resolve_paths() -> tuple[Path, Path | None]:
    """返回 (project_root, vault)。vault 可能为 None（未配置）。"""
    cfg = load_json(CONFIG_PATH)
    cfg = cfg if isinstance(cfg, dict) else {}
    project_root = (cfg.get("project_root") or "").strip()
    if project_root:
        root = Path(project_root)
    else:
        # 兜底：常见 side-hustle 路径
        root = Path.home() / "WorkBuddy" / "2026-07-28-10-03-37" / "side-hustle"
    vault_raw = (cfg.get("obsidian") or {}).get("vault_path") or ""
    vault = Path(vault_raw).expanduser() if vault_raw.strip() else None
    return root, vault


def collect_articles(issues_dir: Path, pub_dates: dict[str, str]) -> list[dict]:
    """扫描 issues 目录，收集有 result.json 的文章条目。"""
    articles: list[dict] = []
    if not issues_dir.is_dir():
        return articles
    for d in sorted(issues_dir.iterdir(), key=lambda p: p.name):
        if not d.is_dir() or not ISSUE_DIR_RE.match(d.name):
            continue
        result = load_json(d / "result.json")
        if not isinstance(result, dict):
            continue
        issue_no = d.name
        article = {
            "issue": issue_no,
            "title": (result.get("title") or result.get("topic") or "").strip(),
            "angle": (result.get("angle") or "").strip(),
            "draft_status": (result.get("draft_status") or "").upper(),
            "status": (result.get("status") or ""),
            "quality": result.get("quality") if isinstance(result.get("quality"), dict) else None,
            "article_md": d / (result.get("article_md") and Path(result["article_md"]).name or "article.md"),
            "cover": d / (result.get("cover") and Path(result["cover"]).name or "cover.png"),
            "mtime": datetime.fromtimestamp(d.stat().st_mtime).date(),
            "published": issue_no in pub_dates,
        }
        article["date"] = pub_dates.get(issue_no) or article["mtime"]
        article["direction"] = match_direction(article["title"], article["angle"])
        articles.append(article)
    return articles


def load_pub_dates(issues_dir: Path) -> dict[str, str]:
    """从 issue-YYYY-MM-DD-pub-<N>.md 文件名解析「已发布记录」的日期 → {issue: date}。"""
    dates: dict[str, str] = {}
    if not issues_dir.is_dir():
        return dates
    for f in issues_dir.glob("issue-*-pub-*.md"):
        m = PUB_DATE_RE.match(f.name)
        if m:
            dates[m.group(2)] = m.group(1)
    return dates


def load_analytics_metrics() -> dict[str, dict]:
    """读 analytics_last.json，返回 {归一化标题: {reads, likes, shares}}。"""
    data = load_json(ANALYTICS_PATH)
    if not isinstance(data, dict):
        return {}
    records = data.get("records") or []
    metrics: dict[str, dict] = {}
    for r in records:
        if not isinstance(r, dict) or not (r.get("title") or "").strip():
            continue
        metrics[normalize_title(r.get("title") or "")] = {
            "reads": r.get("reads"),
            "likes": r.get("likes"),
            "shares": r.get("shares"),
        }
    return metrics


def fmt_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 写 Obsidian
# ---------------------------------------------------------------------------
def ensure_dirs(vault: Path) -> dict[str, Path]:
    base = vault / VAULT_FOLDER
    dirs = {
        "articles": base / "articles",
        "covers": base / "covers",
        "metrics": base / "_metrics",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def load_synced_state(vault: Path) -> dict:
    state_file = vault / VAULT_FOLDER / SYNC_STATE_FILE
    data = load_json(state_file)
    return data if isinstance(data, dict) else {}


def save_synced_state(vault: Path, state: dict) -> None:
    state_file = vault / VAULT_FOLDER / SYNC_STATE_FILE
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_frontmatter(article: dict, metrics: dict | None) -> str:
    q = article.get("quality") or {}
    lines = [
        "---",
        f"title: \"{article['title']}\"",
        f"date: {article['date']}",
        f"direction: {article['direction']}",
        f"issue: {article['issue']}",
        f"published: {str(article['published']).lower()}",
        f"draft_status: \"{article['draft_status']}\"",
    ]
    if q:
        lines.append(f"quality: {q.get('total', '')}")
        lines.append(f"grade: \"{q.get('grade', '')}\"")
    if metrics:
        lines.append(f"reads: {metrics.get('reads', '') or ''}")
        lines.append(f"likes: {metrics.get('likes', '') or ''}")
        lines.append(f"shares: {metrics.get('shares', '') or ''}")
    lines.append("article_url: \"\"")
    lines.append("---")
    return "\n".join(lines)


def clean_article_body(md: Path) -> str:
    text = md.read_text(encoding="utf-8")
    # 去掉首行「已 AI 润色」这类 HTML 注释
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("<!--"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def write_article(article: dict, dirs: dict[str, Path], metrics: dict, force: bool, state: dict) -> str:
    """写一篇文章到 Obsidian，返回相对归档目录的文件名（'' 表示跳过）。"""
    issue = article["issue"]
    if not force and state.get(issue):
        return ""
    md = article["article_md"]
    if not md.is_file():
        warn(f"issue {issue} 缺 article.md，跳过")
        return ""
    title_safe = safe_name(article["title"])
    fname = f"{article['date']}-{article['direction']}-{title_safe}.md"
    out_md = dirs["articles"] / fname

    matched = metrics.get(normalize_title(article["title"]))
    body = clean_article_body(md)
    if not body:
        warn(f"issue {issue} 正文为空，跳过")
        return ""
    content = build_frontmatter(article, matched) + "\n\n" + body + "\n"
    out_md.write_text(content, encoding="utf-8")

    # 封面
    cover_src = article["cover"]
    if cover_src.is_file():
        cover_name = f"{article['date']}-{article['direction']}-issue{issue}{cover_src.suffix.lower()}"
        shutil.copy2(cover_src, dirs["covers"] / cover_name)

    state[issue] = {
        "synced_at": datetime.now().isoformat(timespec="seconds"),
        "date": article["date"],
        "direction": article["direction"],
        "title": article["title"],
        "has_metrics": bool(matched),
    }
    return fname


def write_cycle_metrics(articles: list[dict], dirs: dict[str, Path], force: bool) -> str:
    """按方向生成周期汇总表，写入 _metrics/cycle-*.md。返回相对文件名。"""
    if not articles:
        return ""
    dates = sorted(article["date"] for article in articles if article["date"])
    start, end = dates[0], dates[-1]
    fname = f"cycle-{start.replace('-', '')}-{end.replace('-', '')}.md"
    out = dirs["metrics"] / fname

    lines = [
        f"# 周期数据汇总（{start} ~ {end}）",
        "",
        "> 三大方向：**学**（AI 学习方法/认知） · **用**（AI 工具/实操） · **赚**（AI 副业/变现）",
        "",
        "## 三大方向表现",
        "",
        "| 方向 | 篇数 | 总阅读 | 均阅读 | 总在看 | 均在看 | 总分享 | 均分享 | 表现最好的标题 |",
        "|------|------|--------|--------|--------|--------|--------|--------|----------------|",
    ]
    order = ["学", "用", "赚", "其他"]
    for direction in order:
        group = [a for a in articles if a["direction"] == direction]
        if not group:
            continue
        reads = [a["metrics"]["reads"] for a in group if a["metrics"].get("reads") is not None]
        likes = [a["metrics"]["likes"] for a in group if a["metrics"].get("likes") is not None]
        shares = [a["metrics"]["shares"] for a in group if a["metrics"].get("shares") is not None]

        def avg(vals: list[float]) -> str:
            return f"{sum(vals) / len(vals):.0f}" if vals else "-"

        best = max(group, key=lambda a: (a["metrics"].get("reads") or -1))
        best_title = best["title"] if best["metrics"].get("reads") is not None else "-"
        lines.append(
            f"| {direction} | {len(group)} | {sum(reads) if reads else '-'} | "
            f"{avg(reads)} | {sum(likes) if likes else '-'} | {avg(likes)} | "
            f"{sum(shares) if shares else '-'} | {avg(shares)} | {best_title} |"
        )
    lines.append("")
    lines.append("## 明细")
    lines.append("")
    lines.append("| 日期 | 方向 | 标题 | 阅读 | 在看 | 分享 | 质量分 |")
    lines.append("|------|------|------|------|------|------|--------|")
    for a in sorted(group := articles, key=lambda x: x["date"]):
        m = a["metrics"]
        lines.append(
            f"| {a['date']} | {a['direction']} | {a['title']} | "
            f"{m.get('reads') or '-'} | {m.get('likes') or '-'} | "
            f"{m.get('shares') or '-'} | {a['quality'].get('total') if a['quality'] else '-'} |"
        )
    lines.append("")
    lines.append("> 阅读/在看/分享来自「数据分析」页导入的后台数据；没导入的文章显示 -。")
    lines.append("> 下一轮建议运行日期：" + fmt_date(datetime.now().date() + timedelta(days=DEFAULT_DAYS)))
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return fname


def write_index(articles: list[dict], dirs: dict[str, Path]) -> None:
    lines = [
        "# AI学习日记 · 素材档案",
        "",
        "> 自动生成：每次运行 `sync_obsidian.py` 会更新本索引。",
        "",
        "## 最近文章",
        "",
        "| 日期 | 方向 | 标题 | 阅读 | 在看 | 分享 |",
        "|------|------|------|------|------|------|",
    ]
    for a in sorted(articles, key=lambda x: x["date"], reverse=True)[:30]:
        m = a["metrics"]
        lines.append(
            f"| {a['date']} | {a['direction']} | {a['title']} | "
            f"{m.get('reads') or '-'} | {m.get('likes') or '-'} | {m.get('shares') or '-'} |"
        )
    lines.append("")
    lines.append("## 周期汇总")
    lines.append("")
    lines.append("- [[_metrics/cycle- 汇总文件]] 见 `_metrics/` 目录")
    lines.append("")
    (dirs["articles"].parent / "_index.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="把最近产出的公众号文章 + 数据同步到 Obsidian",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                        help="同步最近 N 天内的文章（默认 9 天 = 3 轮内容循环）")
    parser.add_argument("--vault", default="", help="Obsidian 笔记库根目录（不填则读配置 obsidian.vault_path）")
    parser.add_argument("--force", action="store_true", help="已同步过的文章也重新写")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不写任何文件")
    args = parser.parse_args()

    project_root, vault_cfg = resolve_paths()
    vault = Path(args.vault).expanduser() if args.vault.strip() else vault_cfg

    if vault is None:
        log("找不到 Obsidian 笔记库路径。两种方式二选一：")
        log("  1) 运行：python sync_obsidian.py --vault D:\\你的Obsidian库")
        log("  2) 在「设置」里给 workbench_config.json 的 obsidian.vault_path 填上库路径")
        return 1

    issues_dir = project_root / "data" / "issues"
    if not issues_dir.is_dir():
        log(f"找不到出稿目录：{issues_dir}。请检查 workbench_config.json 的 project_root。")
        return 1

    pub_dates = load_pub_dates(issues_dir)
    all_articles = collect_articles(issues_dir, pub_dates)

    # 过滤：最近 N 天 + 已推送/已发布（跳过从未推送的草稿）
    cutoff = datetime.now().date() - timedelta(days=args.days)
    articles = [
        a for a in all_articles
        if parse_date(a["date"]) and parse_date(a["date"]) >= cutoff
        and (a["published"] or a["draft_status"] in ("PUSHED_DRAFT", "PUBLISHED"))
    ]
    metrics_map = load_analytics_metrics()
    for a in articles:
        a["metrics"] = metrics_map.get(normalize_title(a["title"]), {})

    log(f"出稿目录：{issues_dir}")
    log(f"Obsidian 库：{vault / VAULT_FOLDER}")
    log(f"最近 {args.days} 天内可归档：{len(articles)} 篇"
        f"（另有 {len(all_articles) - len(articles)} 篇不在窗口/未推送）")

    if args.dry_run:
        for a in sorted(articles, key=lambda x: x["date"]):
            log(f"  [计划] {a['date']} {a['direction']} 阅读={a['metrics'].get('reads', '-')} {a['title']}")
        log("dry-run 完成，未写任何文件。")
        return 0

    dirs = ensure_dirs(vault)
    state = load_synced_state(vault)
    written = 0
    skipped = 0
    for a in sorted(articles, key=lambda x: x["date"]):
        fname = write_article(a, dirs, metrics_map, args.force, state)
        if fname:
            written += 1
            log(f"  [写入] {fname}")
        else:
            skipped += 1
    cycle_file = write_cycle_metrics(articles, dirs, args.force)
    if cycle_file:
        log(f"  [写入] _metrics/{cycle_file}")
    save_synced_state(vault, state)
    write_index(articles, dirs)
    log(f"完成：新增/更新 {written} 篇，跳过已同步 {skipped} 篇。")
    log("在 Obsidian 里刷新即可看到「AI学习日记」文件夹。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
