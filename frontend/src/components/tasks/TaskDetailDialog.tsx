"use client";

import * as React from "react";
import {
  ChevronDown,
  ChevronRight,
  FileText,
  FolderOpen,
  ImageIcon,
  ListPlus,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { HistoryDetail } from "@/lib/types";
import {
  TaskStatusBadge,
  fmtDuration,
  fmtTime,
  platformLabel,
} from "./TaskCard";

interface TaskDetailDialogProps {
  open: boolean;
  loading: boolean;
  detail: HistoryDetail | null;
  regenerating: boolean;
  openingDir: boolean;
  onClose: () => void;
  onRegenerate: (mode: "queue" | "now") => void;
  onOpenDir: () => void;
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-2 text-sm">
      <span className="w-20 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 flex-1 break-all">{value ?? "—"}</span>
    </div>
  );
}

/** 历史任务详情：基本信息 / 选题 / 产出路径 / 文章预览（折叠）/ 封面。 */
export function TaskDetailDialog({
  open,
  loading,
  detail,
  regenerating,
  openingDir,
  onClose,
  onRegenerate,
  onOpenDir,
}: TaskDetailDialogProps) {
  const [showArticle, setShowArticle] = React.useState(false);

  React.useEffect(() => {
    if (open) setShowArticle(false);
  }, [open, detail?.issue]);

  return (
    <Dialog open={open} onClose={onClose}>
      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-7 w-40" />
          <Skeleton className="h-4 w-72" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : detail ? (
        <div>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold">第 {detail.issue} 期</h2>
                <TaskStatusBadge status={detail.status} />
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {detail.title || "（无标题）"}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={onOpenDir}
                disabled={openingDir || !detail.dir_path}
                title={detail.dir_path ?? "该期没有产出目录"}
              >
                {openingDir ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <FolderOpen className="h-4 w-4" />
                )}
                打开产出目录
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onRegenerate("queue")}
                disabled={regenerating || !detail.topic}
              >
                {regenerating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ListPlus className="h-4 w-4" />
                )}
                重新生成（入队）
              </Button>
              <Button
                size="sm"
                onClick={() => onRegenerate("now")}
                disabled={regenerating || !detail.topic}
              >
                <RefreshCw className="h-4 w-4" />
                立即重新生成
              </Button>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2">
            <div className="space-y-4">
              <section>
                <h3 className="mb-2 text-sm font-medium">基本信息</h3>
                <div className="space-y-1.5">
                  <Row label="平台" value={platformLabel(detail.platform)} />
                  <Row label="草稿状态" value={detail.draft_status || "—"} />
                  <Row label="开始时间" value={fmtTime(detail.started_at)} />
                  <Row label="完成时间" value={fmtTime(detail.completed_at)} />
                  <Row label="耗时" value={fmtDuration(detail.duration_sec)} />
                </div>
              </section>

              <section>
                <h3 className="mb-2 text-sm font-medium">选题信息</h3>
                <div className="space-y-1.5">
                  <Row label="选题" value={detail.topic || "—"} />
                  <Row label="切入角度" value={detail.angle || "—"} />
                </div>
              </section>

              <section>
                <h3 className="mb-2 text-sm font-medium">产出路径</h3>
                <div className="space-y-1.5 text-xs">
                  <Row
                    label="目录"
                    value={
                      <code className="text-[11px] text-muted-foreground">
                        {detail.dir_path || "—"}
                      </code>
                    }
                  />
                  <Row
                    label="文章"
                    value={
                      <code className="text-[11px] text-muted-foreground">
                        {detail.article_rel || "—"}
                      </code>
                    }
                  />
                  <Row
                    label="封面"
                    value={
                      <code className="text-[11px] text-muted-foreground">
                        {detail.cover_rel || "—"}
                      </code>
                    }
                  />
                </div>
              </section>

              {detail.error && (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 px-2.5 py-2 text-xs text-destructive">
                  <div className="font-medium">执行错误</div>
                  <div className="mt-1 break-all">{detail.error}</div>
                </div>
              )}
            </div>

            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-sm font-medium">
                <ImageIcon className="h-4 w-4" /> 封面预览
              </h3>
              {detail.cover_base64 ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={detail.cover_base64}
                  alt={`第 ${detail.issue} 期封面`}
                  className="w-full rounded-lg border border-border"
                />
              ) : (
                <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-border text-xs text-muted-foreground">
                  该期没有封面文件
                </div>
              )}
            </div>
          </div>

          {/* 文章预览（折叠） */}
          <section className="mt-5">
            <button
              type="button"
              onClick={() => setShowArticle((v) => !v)}
              className="flex w-full items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium transition-colors hover:bg-muted/40"
            >
              {showArticle ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
              <FileText className="h-4 w-4" />
              文章预览
              {detail.article_preview && (
                <Badge variant="muted" className="ml-auto">
                  {detail.article_preview.length} 字符
                </Badge>
              )}
            </button>
            {showArticle && (
              <div className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-black/30 p-3 text-xs leading-relaxed text-muted-foreground">
                {detail.article_preview || "（无预览内容）"}
              </div>
            )}
          </section>
        </div>
      ) : null}
    </Dialog>
  );
}
