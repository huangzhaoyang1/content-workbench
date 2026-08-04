import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";

interface StatCardProps {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: LucideIcon;
  /** 数值文字色调，用来区分成功 / 失败 / 中性。 */
  tone?: "default" | "success" | "danger" | "warning" | "info";
  className?: string;
}

const TONE: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "text-foreground",
  success: "text-emerald-400",
  danger: "text-destructive",
  warning: "text-amber-400",
  info: "text-sky-400",
};

/** 指标卡：概览区通用的「标题 + 大数字 + 说明」小卡片。 */
export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
  className,
}: StatCardProps) {
  return (
    <Card className={className}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">{label}</span>
          {Icon && <Icon className="h-4 w-4 text-muted-foreground/70" />}
        </div>
        <div className={cn("mt-1.5 text-2xl font-semibold tabular-nums", TONE[tone])}>
          {value}
        </div>
        {hint && (
          <div className="mt-1 text-[11px] text-muted-foreground">{hint}</div>
        )}
      </CardContent>
    </Card>
  );
}
