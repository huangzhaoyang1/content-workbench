"use client";

import * as React from "react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ConfirmPublishDialogProps {
  open: boolean;
  issue: number;
  defaultLabel?: string;
  onClose: () => void;
  /** 用户确认发布并带上封面期号标识（如「提示词工程合集 第3期」）。 */
  onConfirm: (coverLabel: string) => void;
}

/**
 * 确认发布前的二次确认：让用户手动指定封面右上角的期号标识。
 * 合集场景期号不连续，故不自动用全局第N期，而由用户填写并核对。
 */
export function ConfirmPublishDialog({
  open,
  issue,
  defaultLabel,
  onClose,
  onConfirm,
}: ConfirmPublishDialogProps) {
  const [label, setLabel] = React.useState(defaultLabel ?? `第 ${issue} 期`);

  // 每次打开时重置为预填值
  React.useEffect(() => {
    if (open) setLabel(defaultLabel ?? `第 ${issue} 期`);
  }, [open, defaultLabel, issue]);

  const handleConfirm = () => {
    onConfirm(label.trim());
    onClose();
  };

  return (
    <Dialog open={open} onClose={onClose}>
      <div className="space-y-4">
        <div>
          <h3 className="text-base font-semibold">确认发布到第 {issue} 期</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            发布前请核对封面右上角的期号标识。你可能有多个合集，期号不连续，请手动填写。
          </p>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="cover-label">封面期号标识</Label>
          <Input
            id="cover-label"
            value={label}
            autoFocus
            placeholder="例如：提示词工程合集 第3期"
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleConfirm();
            }}
          />
          <p className="text-[11px] text-muted-foreground">
            留空则使用默认「第 {issue} 期」。该文字会绘制在封面右上角。
          </p>
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button size="sm" onClick={handleConfirm}>
            确认发布
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
