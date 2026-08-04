import * as React from "react";
import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface StepDef {
  key: string;
  label: string;
}

interface StepsProps {
  steps: StepDef[];
  /** 当前所处步骤下标（0 起）；等于 steps.length 表示全部完成 */
  current: number;
  /** 当前步骤是否正在进行中（显示转圈） */
  running?: boolean;
  /** 当前步骤是否失败（显示红色） */
  failed?: boolean;
  className?: string;
}

/** 横向步骤指示器：已完成打勾、进行中转圈、未开始灰色。 */
export function Steps({
  steps,
  current,
  running = false,
  failed = false,
  className,
}: StepsProps) {
  return (
    <ol className={cn("flex items-center gap-1 overflow-x-auto", className)}>
      {steps.map((s, i) => {
        const done = i < current;
        const active = i === current;
        const isFailed = active && failed;
        return (
          <li key={s.key} className="flex min-w-0 flex-1 items-center gap-1.5">
            <div className="flex min-w-0 items-center gap-1.5">
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-medium transition-colors",
                  done &&
                    "border-emerald-500/50 bg-emerald-500/15 text-emerald-400",
                  active &&
                    !isFailed &&
                    "border-sidebar-primary bg-sidebar-primary/15 text-sidebar-primary",
                  isFailed && "border-destructive bg-destructive/15 text-destructive",
                  !done && !active && "border-border text-muted-foreground/60"
                )}
              >
                {done ? (
                  <Check className="h-3.5 w-3.5" />
                ) : active && running && !isFailed ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  i + 1
                )}
              </span>
              <span
                className={cn(
                  "truncate text-xs transition-colors",
                  done && "text-muted-foreground",
                  active && !isFailed && "font-medium text-foreground",
                  isFailed && "font-medium text-destructive",
                  !done && !active && "text-muted-foreground/60"
                )}
              >
                {s.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <span
                className={cn(
                  "h-px min-w-3 flex-1 transition-colors",
                  done ? "bg-emerald-500/40" : "bg-border"
                )}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
