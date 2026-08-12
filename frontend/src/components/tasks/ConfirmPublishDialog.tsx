"use client";

import * as React from "react";
import { Image as ImageIcon, Loader2, AlertTriangle } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, friendlyMessage } from "@/lib/api";
import { MarkReview } from "@/components/brand/marks";

interface ConfirmPublishDialogProps {
  open: boolean;
  issue: number;
  defaultLabel?: string;
  onClose: () => void;
  /** 用户确认发布并带上封面期号标识（如「提示词工程合集 第3期」）。 */
  onConfirm: (coverLabel: string) => void;
}

/**
 * 审核三步走闭环：
 *  ① 填封面期号标识（默认「第N期」）
 *  ② 「生成封面预览」→ 从任务详情取已生成的封面图展示
 *  ③ 「确认发布」→ 调 /pipeline/publish（带 cover_label）
 * 预览未加载成功前，确认发布按钮置灰（防误发）；预览失败给明确提示 + 仍可直接发布（人在环不自动拦截）。
 */
export function ConfirmPublishDialog({
  open,
  issue,
  defaultLabel,
  onClose,
  onConfirm,
}: ConfirmPublishDialogProps) {
  const [label, setLabel] = React.useState(defaultLabel ?? `第 ${issue} 期`);
  const [coverSrc, setCoverSrc] = React.useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [previewError, setPreviewError] = React.useState<string | null>(null);
  const [coverReady, setCoverReady] = React.useState(false);

  // 每次打开时重置
  React.useEffect(() => {
    if (open) {
      setLabel(defaultLabel ?? `第 ${issue} 期`);
      setCoverSrc(null);
      setPreviewLoading(false);
      setPreviewError(null);
      setCoverReady(false);
    }
  }, [open, defaultLabel, issue]);

  const generatePreview = async () => {
    setPreviewLoading(true);
    setPreviewError(null);
    setCoverReady(false);
    try {
      // 真正按用户在输入框里实际输入的 label 重画封面，避免预览与最终发布不一致
      const res = await api.regenerateCover(issue, label.trim());
      if (res.ok && res.cover_base64) {
        setCoverSrc(res.cover_base64);
        setCoverReady(true);
      } else {
        setPreviewError(res.reason || "封面预览生成失败");
      }
    } catch (e) {
      setPreviewError(friendlyMessage(e, "封面预览生成失败"));
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleConfirm = () => {
    onConfirm(label.trim());
    onClose();
  };

  return (
    <Dialog open={open} onClose={onClose}>
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/15 text-accent">
            <MarkReview className="h-5 w-5" />
          </span>
          <div>
            <h3 className="text-base font-semibold">确认发布到第 {issue} 期</h3>
            <p className="text-xs text-muted-foreground">
              核对封面期号，预览无误后推送到公众号草稿箱。
            </p>
          </div>
        </div>

        {/* ① 封面期号标识 */}
        <div className="space-y-1.5">
          <Label htmlFor="cover-label">封面期号标识</Label>
          <Input
            id="cover-label"
            value={label}
            autoFocus
            placeholder="例如：提示词工程合集 第3期"
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && coverReady) handleConfirm();
            }}
          />
          <p className="text-[11px] text-muted-foreground">
            留空则用默认「第 {issue} 期」。该文字会在发布时绘制到封面右上角。
          </p>
        </div>

        {/* ② 生成封面预览 */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>封面预览</Label>
            <Button
              variant="outline"
              size="sm"
              onClick={generatePreview}
              disabled={previewLoading}
            >
              {previewLoading ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <ImageIcon className="mr-1.5 h-3.5 w-3.5" />
              )}
              {previewLoading ? "生成中…" : "生成封面预览"}
            </Button>
          </div>

          {previewLoading && (
            <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-border py-10 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在生成封面预览…
            </div>
          )}

          {!previewLoading && coverSrc && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={coverSrc}
              alt={`第 ${issue} 期封面预览`}
              className="mx-auto h-40 w-auto rounded-lg border border-subtle object-contain"
            />
          )}

          {!previewLoading && !coverSrc && !previewError && (
            <div className="flex flex-col items-center gap-1 rounded-lg border border-dashed border-border py-8 text-center text-xs text-muted-foreground">
              <ImageIcon className="h-5 w-5 opacity-50" />
              点「生成封面预览」查看本期封面
            </div>
          )}

          {previewError && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{previewError}</span>
            </div>
          )}
        </div>

        {/* ③ 确认发布（预览未就绪前置灰；预览失败给明确提示 + 仍可直接发布） */}
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          {previewError && (
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive"
              onClick={handleConfirm}
            >
              直接发布（无预览）
            </Button>
          )}
          <Button size="sm" onClick={handleConfirm} disabled={!coverReady}>
            {coverReady ? "确认发布" : "请先生成封面预览"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
