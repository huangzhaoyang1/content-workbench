import * as React from "react";
import { cn } from "@/lib/utils";

interface ProgressProps {
  /** 0-100；传 null/undefined 表示不确定进度（走动画条） */
  value?: number | null;
  className?: string;
  indicatorClassName?: string;
}

/** 进度条：支持确定进度与不确定进度两种形态。 */
export function Progress({
  value,
  className,
  indicatorClassName,
}: ProgressProps) {
  const indeterminate = value === null || value === undefined;
  const pct = indeterminate ? 0 : Math.max(0, Math.min(100, value));

  return (
    <div
      role="progressbar"
      aria-valuenow={indeterminate ? undefined : pct}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn(
        "relative h-1.5 w-full overflow-hidden rounded-full bg-muted",
        className
      )}
    >
      {indeterminate ? (
        <div
          className={cn(
            "absolute inset-y-0 left-0 w-1/3 animate-indeterminate rounded-full bg-sidebar-primary",
            indicatorClassName
          )}
        />
      ) : (
        <div
          className={cn(
            "h-full rounded-full bg-sidebar-primary transition-[width] duration-500 ease-out",
            indicatorClassName
          )}
          style={{ width: `${pct}%` }}
        />
      )}
    </div>
  );
}
