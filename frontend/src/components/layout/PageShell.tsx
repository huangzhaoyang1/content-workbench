import * as React from "react";
import { cn } from "@/lib/utils";

const MAX_W = {
  sm: "max-w-3xl",
  md: "max-w-4xl",
  lg: "max-w-5xl",
  xl: "max-w-6xl",
} as const;

interface PageShellProps {
  children: React.ReactNode;
  /** 内容最大宽度，默认 lg(1024px) */
  width?: keyof typeof MAX_W;
  className?: string;
}

/**
 * 页面统一外壳：负责全站一致的最大宽度与响应式内边距。
 * 移动端 16px、平板 24px、桌面 32px。
 */
export function PageShell({ children, width = "lg", className }: PageShellProps) {
  return (
    <div
      className={cn(
        "mx-auto w-full animate-page-in px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10",
        MAX_W[width],
        className
      )}
    >
      {children}
    </div>
  );
}

interface PageHeaderProps {
  title: string;
  description?: React.ReactNode;
  /** 右侧操作区（按钮 / 状态徽章） */
  actions?: React.ReactNode;
  className?: string;
}

/** 页面标题区：标题 + 副标题 + 右侧操作，移动端自动换行。 */
export function PageHeader({
  title,
  description,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between",
        className
      )}
    >
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
          {title}
        </h1>
        {description && (
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      )}
    </div>
  );
}
