"use client";

import * as React from "react";
import { Gauge, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
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
}: {
  quality: QualityScore;
  className?: string;
}) {
  const total = tone(quality.total / 100);

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
            改进建议（按最该改的排序）
          </div>
          <ul className="space-y-1 text-xs leading-relaxed text-foreground/75">
            {quality.advice.map((a, i) => (
              <li key={i}>· {a}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
