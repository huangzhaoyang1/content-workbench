"use client";

import * as React from "react";
import { AlertTriangle, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  /** 已经过 friendlyMessage 处理的一句话 */
  message: string;
  title?: string;
  onRetry?: () => void;
  retryLabel?: string;
  retrying?: boolean;
  /** inline: 一行紧凑样式；block: 大块占位 */
  variant?: "inline" | "block";
  className?: string;
}

/** 统一的错误提示：说明原因 + 重试按钮。 */
export function ErrorState({
  message,
  title = "加载失败",
  onRetry,
  retryLabel = "重试",
  retrying = false,
  variant = "block",
  className,
}: ErrorStateProps) {
  if (variant === "inline") {
    return (
      <div
        className={cn(
          "flex flex-wrap items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive animate-fade-in",
          className
        )}
      >
        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
        <span className="min-w-0 flex-1 break-words">{message}</span>
        {onRetry && (
          <Button
            size="xs"
            variant="outline"
            onClick={onRetry}
            disabled={retrying}
            className="shrink-0 border-destructive/40 text-destructive hover:bg-destructive/10"
          >
            <RotateCw className={cn("mr-1 h-3 w-3", retrying && "animate-spin")} />
            {retryLabel}
          </Button>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-destructive/40 bg-destructive/5 px-6 py-12 text-center animate-fade-in",
        className
      )}
    >
      <AlertTriangle className="h-9 w-9 text-destructive/60" />
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="max-w-md text-xs leading-relaxed text-muted-foreground">
        {message}
      </p>
      {onRetry && (
        <Button
          size="sm"
          variant="outline"
          onClick={onRetry}
          disabled={retrying}
          className="mt-2"
        >
          <RotateCw className={cn("mr-1.5 h-3.5 w-3.5", retrying && "animate-spin")} />
          {retryLabel}
        </Button>
      )}
    </div>
  );
}
