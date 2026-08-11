"use client";

import * as React from "react";
import { Check } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface TitleSwitcherItem {
  key: string;
  /** 该篇当前选中的标题 */
  title: string;
  angleLabel: string;
  angleDesc: string;
  icon: React.ComponentType<{ className?: string }>;
  wordCount?: number | null;
  score?: number | null;
}

interface TitleSwitcherProps {
  items: TitleSwitcherItem[];
  activeKey: string;
  onSelect: (key: string) => void;
}

/**
 * 标题 ←→ 文章联动选择器。
 * 一个标题 = 一篇独立角度的文章，点标题就切下面的正文，不是「一篇文章配三个标题」。
 */
export function TitleSwitcher({ items, activeKey, onSelect }: TitleSwitcherProps) {
  if (items.length === 0) return null;
  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="mb-3 text-xs font-medium text-muted-foreground">
        三个标题 = 三篇角度完全不同的文章。点标题即可切换下方正文。
      </div>
      <div className="grid gap-2 lg:grid-cols-3">
        {items.map((item, i) => {
          const active = item.key === activeKey;
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => onSelect(item.key)}
              aria-pressed={active}
              className={cn(
                "flex flex-col gap-2 rounded-lg border p-3 text-left transition-all",
                active
                  ? "border-primary bg-primary/10 shadow-sm"
                  : "border-border bg-muted/20 hover:border-primary/50 hover:bg-muted/40"
              )}
            >
              <div className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
                    active
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-muted-foreground/40"
                  )}
                >
                  {active && <Check className="h-3 w-3" />}
                </span>
                <Icon
                  className={cn(
                    "h-3.5 w-3.5",
                    active ? "text-primary" : "text-muted-foreground"
                  )}
                />
                <span className="text-[11px] font-medium text-muted-foreground">
                  标题 {i + 1} · {item.angleLabel}
                </span>
                {item.score != null && (
                  <span className="ml-auto rounded bg-muted px-1 text-[10px] tabular-nums text-muted-foreground">
                    {item.score}
                  </span>
                )}
              </div>

              <div
                className={cn(
                  "text-sm font-medium leading-snug",
                  active ? "text-foreground" : "text-foreground/80"
                )}
              >
                {item.title || "（该篇没有标题）"}
              </div>

              <div className="flex items-center gap-2">
                <Badge variant={active ? "secondary" : "muted"}>
                  {item.angleDesc || item.angleLabel}
                </Badge>
                {item.wordCount != null && (
                  <span className="text-[11px] tabular-nums text-muted-foreground">
                    {item.wordCount} 字
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
