"use client";

import * as React from "react";
import {
  CheckCircle2,
  Clock,
  Eye,
  ListPlus,
  Lightbulb,
  XCircle,
  HelpCircle,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { HistoryStatus, HistoryTask } from "@/lib/types";

const STATUS_META: Record<
  HistoryStatus,
  { label: string; variant: "success" | "destructive" | "warning" | "muted"; icon: React.ElementType }
> = {
  ok: { label: "成功", variant: "success", icon: CheckCircle2 },
  error: { label: "失败", variant: "destructive", icon: XCircle },
  running: { label: "进行中", variant: "warning", icon: Clock },
  unknown: { label: "未知", variant: "muted", icon: HelpCircle },
};

export function TaskStatusBadge({ status }: { status: HistoryStatus }) {
  const meta = STATUS_META[status] ?? STATUS_META.unknown;
  const Icon = meta.icon;
  return (
    <Badge variant={meta.variant}>
      <Icon className="mr-1 h-3 w-3" />
      {meta.label}
    </Badge>
  );
}

export function fmtDuration(s: number | null): string {
  if (s === null || s === undefined) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m > 0 ? `${m}分${sec}秒` : `${sec}秒`;
}

export function fmtTime(v: string | null): string {
  if (!v) return "未知";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  return d.toLocaleString("zh-CN", { hour12: false });
}

export function platformLabel(p: string): string {
  if (p === "wechat") return "微信公众号";
  return p || "其他";
}

interface TaskCardProps {
  task: HistoryTask;
  onView: (issue: number) => void;
  onReuse: (task: HistoryTask) => void;
  onEnqueue: (task: HistoryTask) => void;
  enqueuing?: boolean;
}

/** 历史任务卡片：期号 + 标题 + 状态 + 三个快捷动作。 */
export function TaskCard({
  task,
  onView,
  onReuse,
  onEnqueue,
  enqueuing = false,
}: TaskCardProps) {
  return (
    <Card className="transition-colors hover:border-muted-foreground/30">
      <CardContent className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">第 {task.issue} 期</Badge>
              <TaskStatusBadge status={task.status} />
              <Badge variant="secondary">{platformLabel(task.platform)}</Badge>
              {task.draft_status && (
                <Badge variant="muted">{task.draft_status}</Badge>
              )}
            </div>
            <p
              className="mt-2 truncate text-sm font-medium"
              title={task.title}
            >
              {task.title || "（无标题）"}
            </p>
            {task.topic && (
              <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                选题：{task.topic}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
              <span>完成 {fmtTime(task.completed_at)}</span>
              <span>耗时 {fmtDuration(task.duration_sec)}</span>
            </div>
            {task.error && (
              <p className="mt-2 line-clamp-2 rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1 text-[11px] text-destructive">
                {task.error}
              </p>
            )}
          </div>

          <div className="flex shrink-0 flex-wrap gap-1.5">
            <Button size="xs" variant="outline" onClick={() => onView(task.issue)}>
              <Eye className="h-3 w-3" />
              查看详情
            </Button>
            <Button
              size="xs"
              variant="ghost"
              disabled={!task.topic}
              title={task.topic ? "把这个选题带到选题页" : "该期没有记录选题"}
              onClick={() => onReuse(task)}
            >
              <Lightbulb className="h-3 w-3" />
              复用选题
            </Button>
            <Button
              size="xs"
              variant="ghost"
              disabled={!task.topic || enqueuing}
              onClick={() => onEnqueue(task)}
            >
              <ListPlus className="h-3 w-3" />
              加入队列
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
