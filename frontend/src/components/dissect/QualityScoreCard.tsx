"use client";

import * as React from "react";
import { Gauge, TriangleAlert, Loader2, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { QualityScore } from "@/lib/types";

/** 分数 → 配色。85+ 优秀，70+ 合格，55+ 待打磨，其余不合格 */
function tone(ratio: number) {
  if (ratio >= 0.85) return { bar: "bg-emerald-500", text: "text-emerald-400" };
  if (ratio >= 0.7) return { bar: "bg-sky-500", text: "text-sky-400" };
  if (ratio >= 0.55) return { bar: "bg-amber-500", text: "text-amber-400" };
  return { bar: "bg-destructive", text: "text-destructive" };
}

function gradeVariant(grade: string) {
  if (grade === "优秀") return "success" as const;
  if (grade === "合格") return "secondary" as const;
  if (grade === "待打磨") return "warning" as const;
  return "destructive" as const;
}

export function QualityScoreCard({
  quality,
  className,
  onImprove,
  improving = false,
  improveLabel = "按建议一键改稿",
}: {
  quality: QualityScore;
  className?: string;
  /** 点击「按建议一键改稿」的回调；不传则不显示按钮 */
  onImprove?: () => void;
  improving?: boolean;
  /** 按钮文案（TaskDetailDialog 场景用「按建议重新生成」） */
  improveLabel?: string;
}) {
  const total = tone(quality.total / 100);

  // 把 advice 按「[维度] 」前缀分组，让建议更好消化
  const adviceGroups = React.useMemo(() => {
    const map = new Map<string, string[]>();
    for (const a of quality.advice) {
      const m = a.match(/^\[([^\]]+)\]\s*(.*)$/);
      const key = m ? m[1] : "其他";
      const text = m ? m[2] : a;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(text);
    }
    return Array.from(map.entries()) as Array<[string, string[]]>;
  }, [quality.advice]);

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-card p-4 shadow-sm",
        className
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <Gauge className="h-3.5 w-3.5" />
          内容质量评分（格式 / 有料 / 共鸣 / 传播，各 25 分）
        </div>
        <div className="flex items-center gap-2">
          <span className={cn("text-2xl font-semibold tabular-nums", total.text)}>
            {quality.total}
          </span>
          <span className="text-xs text-muted-foreground">/ 100</span>
          <Badge variant={gradeVariant(quality.grade)}>{quality.grade}</Badge>
        </div>
      </div>

      <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
        {quality.dimensions.map((d) => {
          const ratio = d.full > 0 ? d.score / d.full : 0;
          const t = tone(ratio);
          const weakest = d.label === quality.weakest;
          return (
            <div key={d.key}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span
                  className={cn(
                    "flex items-center gap-1",
                    weakest ? "font-medium text-foreground" : "text-muted-foreground"
                  )}
                >
                  {d.label}
                  {weakest && (
                    <span className="rounded bg-amber-500/15 px-1 text-[10px] text-amber-400">
                      最弱项
                    </span>
                  )}
                </span>
                <span className={cn("tabular-nums", t.text)}>
                  {d.score}/{d.full}
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className={cn("h-full rounded-full transition-all", t.bar)}
                  style={{ width: `${Math.min(100, Math.max(0, ratio * 100))}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {quality.advice.length > 0 && (
        <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-amber-400">
            <TriangleAlert className="h-3.5 w-3.5" />
            改进建议（按维度分组 · 按最该改的排序）
          </div>
          <div className="space-y-2.5">
            {adviceGroups.map(([key, items]: [string, string[]]) => (
              <div key={key}>
                <div className="mb-1 flex items-center gap-1 text-[11px] font-medium text-amber-400/80">
                  <span className="rounded bg-amber-500/15 px-1.5 py-0.5">{key}</span>
                  <span className="text-muted-foreground">{items.length} 条</span>
                </div>
                <ul className="space-y-1 text-xs leading-relaxed text-foreground/75">
                  {items.map((it, i) => (
                    <li key={i}>· {it}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          {onImprove && (
            <Button
              size="sm"
              variant="outline"
              className="mt-3 w-full"
              onClick={onImprove}
              disabled={improving}
              title="让 AI 在当前正文基础上逐条落实以上建议，生成新的一版（原版保留，可对比）"
            >
              {improving ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              )}
              {improving ? `正在${improveLabel.replace("按建议", "").trim()}…` : improveLabel}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
