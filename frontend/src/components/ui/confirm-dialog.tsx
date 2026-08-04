"use client";

import * as React from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  /** 危险操作用 destructive 按钮样式。 */
  destructive?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 危险操作二次确认框（清空队列、删除定时任务等）。 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmText = "确认",
  cancelText = "取消",
  destructive = true,
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onClose={loading ? () => undefined : onCancel} className="max-w-md">
      <div className="flex items-start gap-3">
        {destructive && (
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-destructive/15">
            <AlertTriangle className="h-4 w-4 text-destructive" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold">{title}</h3>
          {description && (
            <div className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
              {description}
            </div>
          )}
        </div>
      </div>
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel} disabled={loading}>
          {cancelText}
        </Button>
        <Button
          variant={destructive ? "destructive" : "default"}
          onClick={onConfirm}
          disabled={loading}
        >
          {loading && <Loader2 className="h-4 w-4 animate-spin" />}
          {confirmText}
        </Button>
      </div>
    </Dialog>
  );
}
