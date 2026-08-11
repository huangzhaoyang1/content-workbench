import * as React from "react";
import { cn } from "@/lib/utils";

export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {
  /** 校验失败：红边 + 红色 focus ring */
  error?: boolean;
}

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, error, ...props }, ref) => (
    <select
      ref={ref}
      aria-invalid={error || undefined}
      className={cn(
        "flex h-9 w-full rounded-lg border border-input bg-background px-3 py-1 text-sm text-foreground shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        // 原生下拉弹层由浏览器绘制，深色主题下必须显式给 option 上色，
        // 否则 Windows/Chrome 会白底 + 继承的浅色文字 = 选项肉眼不可见。
        "[&>optgroup]:bg-popover [&>optgroup]:text-popover-foreground [&>option]:bg-popover [&>option]:text-popover-foreground",
        error && "border-destructive focus-visible:ring-destructive/60",
        className
      )}
      {...props}
    >
      {children}
    </select>
  )
);
Select.displayName = "Select";

export { Select };
