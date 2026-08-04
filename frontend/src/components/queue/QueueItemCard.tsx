"use client";

import * as React from "react";
import {
  CheckCircle2,
  Clock,
  Loader2,
  Trash2,
  XCircle,
  FileText,
} from "lucide-react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { QueueItem, QueueItemStatus } from "@/lib/types";

const STATUS_META: Record<
  QueueItemStatus,
  { label: string; variant: "muted" | "warning" | "success" | "destructive"; icon: React.ElementType }
> = {
  waiting: { label: "等待中", variant: "muted", icon: Clock },
  running: { label: "执行中", variant: "warning", icon: Loader2 },
  success: { label: "已完成", variant: "success", icon: CheckCircle2 },
  failed: { label: "失败", variant: "destructive", icon: XCircle },
};

const SOURCE_LABELS: Record<string, string> = {
  manual: "手动添加",
  topic: "来自选题页",
  tasks: "来自历史任务",
  analytics: "来自数据分析",
  schedule: "定时任务触发",
};

interface QueueItemCardProps {
  item: QueueItem;
  onRemove: (item: QueueItem) => void;
}

export function QueueItemCard({ item, onRemove }: QueueItemCardProps) {
  const meta = STATUS_META[item.status] ?? STATUS_META.waiting;
  const Icon = meta.icon;
  const running = item.status === "running";

  return (
    <Card className={running ? "border-amber-500/50" : undefined}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={meta.variant}>
                <Icon
                  className={`mr-1 h-3 w-3 ${running ? "animate-spin" : ""}`}
                />
                {meta.label}
              </Badge>
              {item.issue !== null && (
                <Badge variant="outline">第 {item.issue} 期</Badge>
              )}
              <Badge variant="secondary">
                {SOURCE_LABELS[item.source] ?? item.source}
              </Badge>
            </div>
            <p className="mt-2 truncate text-sm font-medium" title={item.topic}>
              {item.topic}
            </p>
            {item.angle && (
              <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                {item.angle}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
              <span>加入 {item.created_at}</span>
              {item.started_at && <span>开始 {item.started_at}</span>}
              {item.finished_at && <span>结束 {item.finished_at}</span>}
            </div>
            {item.error && (
              <p className="mt-2 rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1 text-[11px] text-destructive">
                {item.error}
              </p>
            )}
          </div>

          <div className="flex shrink-0 flex-col items-end gap-1.5">
            {item.status === "success" && item.issue !== null && (
              <Link href="/tasks">
                <Button size="xs" variant="outline">
                  <FileText className="h-3 w-3" />
                  查看产出
                </Button>
              </Link>
            )}
            <Button
              size="icon-sm"
              variant="ghost"
              disabled={running}
              title={running ? "执行中的任务不能删除" : "移除"}
              onClick={() => onRemove(item)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
