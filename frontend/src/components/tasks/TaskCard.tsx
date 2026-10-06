"use client";

import * as React from "react";
import {
  CheckCircle2,
  Clock,
  Eye,
  ListPlus,
  Lightbulb,
  Send,
  XCircle,
  HelpCircle,
  Trash2,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { HistoryStatus, HistoryTask } from "@/lib/types";

const STATUS_META: Record<
  HistoryStatus,
  { label: string; variant: "success" | "destructive" | "warning" | "muted"; icon: React.ElementType }
> = {
  ok: { label: "成功", variant: "success", icon: CheckCircle2 },
  error: { label: "失败", variant: "destructive", icon: XCircle },
  running: { label: "运行中", variant: "warning", icon: Clock },
  waiting: { label: "等待中", variant: "muted", icon: HelpCircle },
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
  if (p === "xiaohongshu") return "小红书";
  if (p === "douyin") return "抖音";
  return p || "其他";
}

interface TaskCardProps {
  task: HistoryTask;
  onView: (issue: number) => void;
  onReuse: (task: HistoryTask) => void;
  onEnqueue: (task: HistoryTask) => void;
  onDelete: (task: HistoryTask) => Promise<void>;
  /** 待审核卡片一键直接打开 ConfirmPublishDialog（跳过详情弹窗） */
  onConfirmPublish?: (task: HistoryTask) => void;
  enqueuing?: boolean;
  selected?: boolean;
  onToggle?: (issue: number) => void;
}

/** 历史任务卡片：期号 + 标题 + 状态 + 四个快捷动作（含删除）。 */
export function TaskCard({
  task,
  onView,
  onReuse,
  onEnqueue,
  onDelete,
  onConfirmPublish,
  enqueuing = false,
  selected = false,
  onToggle,
}: TaskCardProps) {
  const [pending, setPending] = React.useState<HistoryTask | null>(null);
  const [deleting, setDeleting] = React.useState(false);

  const confirmDelete = async () => {
    if (!pending) return;
    setDeleting(true);
    try {
      await onDelete(pending);
      setPending(null);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
    <Card className="transition-colors hover:border-muted-foreground/30">
      <CardContent className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          {onToggle && (
            <input
              type="checkbox"
              className="mt-1 h-4 w-4 shrink-0 cursor-pointer rounded border-border accent-primary"
              checked={selected}
              onChange={() => onToggle(task.issue)}
              aria-label={`选择第 ${task.issue} 期`}
            />
          )}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">第 {task.issue} 期</Badge>
              <TaskStatusBadge status={task.status} />
              <Badge variant="secondary">{platformLabel(task.platform)}</Badge>
              {task.draft_status && (
                <Badge
                  variant={
                    task.draft_status === "PENDING_REVIEW" ? "warning" : "muted"
                  }
                >
                  {task.draft_status === "PENDING_REVIEW"
                    ? "待审核"
                    : task.draft_status}
                </Badge>
              )}
              {task.quality && task.draft_status === "PENDING_REVIEW" && (
                <Badge
                  variant={task.quality.meets_threshold ? "success" : "destructive"}
                  title={
                    `质量总分 ${task.quality.total} / 门槛 ${task.quality.threshold}` +
                    (task.quality.block ? " · 命中违禁词" : "")
                  }
                >
                  {task.quality.block
                    ? "⚠ 违禁"
                    : `质量 ${task.quality.total}`}
                </Badge>
              )}
              {task.tags && task.tags.length > 0 && (
                <span className="inline-flex flex-wrap gap-1 align-middle">
                  {task.tags.map((t) => (
                    <Badge key={t} variant="outline" className="text-[10px]">
                      {t}
                    </Badge>
                  ))}
                </span>
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
            {task.draft_status === "PENDING_REVIEW" && onConfirmPublish && (
              <Button
                size="xs"
                variant="default"
                onClick={() => onConfirmPublish(task)}
                title="直接进入发布审核（封面期号→预览→发布）"
              >
                <Send className="h-3 w-3" />
                去审核
              </Button>
            )}
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
            <Button
              size="xs"
              variant="ghost"
              className="text-destructive hover:bg-destructive/10"
              onClick={() => setPending(task)}
            >
              <Trash2 className="h-3 w-3" />
              删除
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <ConfirmDialog
      open={pending !== null}
      title="移入回收站？"
      description={
        pending
          ? `确定把《${pending.title}》（第 ${pending.issue} 期）移入回收站吗？可在回收站里恢复。`
          : ""
      }
      confirmText="删除"
      destructive
      loading={deleting}
      onConfirm={confirmDelete}
      onCancel={() => !deleting && setPending(null)}
    />
    </>
  );
}
