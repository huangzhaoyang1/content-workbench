"use client";

import * as React from "react";
import { Check, PackageCheck, RefreshCw, Loader2, History } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MarkdownLite } from "./MarkdownLite";
import { QualityScoreCard } from "./QualityScoreCard";
import { cn } from "@/lib/utils";
import type { RewriteResult } from "@/lib/types";

interface RewritePreviewProps {
  rewrite: RewriteResult;
  selectedTitle: string;
  onSelectTitle: (title: string) => void;
  /** 只重新生成这一篇 */
  onRegenerate?: () => void;
  regenerating?: boolean;
  /** 本篇的历史版本数（含当前） */
  versionCount?: number;
  /** 当前展示的是第几版，0 起 */
  activeVersion?: number;
  onSelectVersion?: (index: number) => void;
}

export function RewritePreview({
  rewrite,
  selectedTitle,
  onSelectTitle,
  onRegenerate,
  regenerating = false,
  versionCount = 1,
  activeVersion = 0,
  onSelectVersion,
}: RewritePreviewProps) {
  return (
    <div className="space-y-4">
      {/* 本篇角度 + 重新生成 + 版本切换 */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/25 bg-primary/5 px-3 py-2">
        {rewrite.angle_label && <Badge>{rewrite.angle_label}</Badge>}
        <span className="text-xs text-muted-foreground">{rewrite.angle_desc}</span>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          {versionCount > 1 && (
            <div className="flex items-center gap-1 rounded-lg border border-border bg-card px-1.5 py-1">
              <History className="h-3 w-3 text-muted-foreground" />
              {Array.from({ length: versionCount }).map((_, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => onSelectVersion?.(i)}
                  disabled={regenerating}
                  title={i === 0 ? "初版" : `第 ${i + 1} 版`}
                  className={cn(
                    "rounded px-1.5 py-0.5 text-[11px] tabular-nums transition-colors",
                    i === activeVersion
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted"
                  )}
                >
                  v{i + 1}
                </button>
              ))}
            </div>
          )}
          {onRegenerate && (
            <Button
              variant="outline"
              size="sm"
              onClick={onRegenerate}
              disabled={regenerating}
            >
              {regenerating ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              )}
              {regenerating ? "重写中…" : "重新生成这篇"}
            </Button>
          )}
        </div>
      </div>

      {regenerating && (
        <div className="flex items-center gap-2 rounded-lg border border-dashed border-border px-3 py-3 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
          正在换个切入点重写这一篇（30–90 秒）。上一版会保留，写完可以点 v1 / v2 对比。
        </div>
      )}

      {/* 质量评分 */}
      {rewrite.quality && <QualityScoreCard quality={rewrite.quality} />}

      {/* 本篇的备选标题（二级选择，只影响保存 / 复制时用哪个标题） */}
      <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
        <div className="mb-2 text-xs font-medium text-muted-foreground">
          本篇的备选标题（换一个说法，正文不变；用于「加入选题库 / 直接生产 / 复制」）
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          {rewrite.titles.map((t, i) => {
            const active = t === selectedTitle;
            return (
              <button
                key={i}
                type="button"
                onClick={() => onSelectTitle(t)}
                className={cn(
                  "group flex items-start gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-all",
                  active
                    ? "border-primary bg-primary/10 text-foreground"
                    : "border-border bg-muted/30 text-foreground/80 hover:border-primary/50"
                )}
              >
                <span
                  className={cn(
                    "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
                    active
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-muted-foreground/40"
                  )}
                >
                  {active && <Check className="h-3 w-3" />}
                </span>
                <span className="leading-snug">{t}</span>
              </button>
            );
          })}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{rewrite.theme}</Badge>
          {rewrite.word_count != null && (
            <span className="text-xs text-muted-foreground">
              {rewrite.word_count} 字
            </span>
          )}
          {rewrite.digest && (
            <span className="text-xs text-muted-foreground">· {rewrite.digest}</span>
          )}
        </div>
      </div>

      {/* 正文预览 */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <div className="mb-3 text-xs font-medium text-muted-foreground">
          公众号正文（已套用「高数据格式」：emoji 小标题 / 红色加粗 / 引用金句 / 短段落 / 列表）
        </div>
        <MarkdownLite content={rewrite.content} />
      </div>

      {/* 用到的核心素材（核对改写有没有真的消费素材清单） */}
      {(rewrite.materials_used?.length ?? 0) > 0 && (
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 text-sm shadow-sm">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-emerald-400">
            <PackageCheck className="h-3.5 w-3.5" />
            本篇用到的核心素材（对照「拆解分析 → 核心素材清单」核对）
          </div>
          <ul className="list-disc space-y-1 pl-5 text-xs leading-relaxed text-foreground/80">
            {rewrite.materials_used!.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 改动说明 */}
      {rewrite.changes.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-4 text-sm shadow-sm">
          <div className="mb-2 text-xs font-medium text-muted-foreground">
            本篇相比原视频做的关键改动（供人工复核）
          </div>
          <ul className="list-disc space-y-1 pl-5 text-foreground/80">
            {rewrite.changes.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
