"use client";

import * as React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ImagePlus,
  Loader2,
  RefreshCw,
  Settings2,
  Trash2,
  X,
  ScanLine,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { OcrStatus, ScreenshotItem, ScreenshotStatus } from "@/lib/types";

interface ScreenshotZoneProps {
  items: ScreenshotItem[];
  /** 是否有图片正在识别中 */
  busy: boolean;
  /** 视觉模型配置状态，null 表示还没探测到 */
  status: OcrStatus | null;
  /** 识别成功、可供导入的文章总条数 */
  readyCount: number;
  onAdd: (files: File[]) => void;
  onRemove: (id: string) => void;
  onRetry: (id: string) => void;
  onClearAll: () => void;
  onReview: () => void;
  onGoConfig: () => void;
}

const ACCEPT = ".png,.jpg,.jpeg,image/png,image/jpeg";
const MAX_FILES = 10;

const STATUS_META: Record<
  ScreenshotStatus,
  { label: string; variant: "muted" | "secondary" | "success" | "destructive" }
> = {
  pending: { label: "待识别", variant: "muted" },
  recognizing: { label: "识别中", variant: "secondary" },
  success: { label: "识别成功", variant: "success" },
  failed: { label: "识别失败", variant: "destructive" },
};

/**
 * 截图识别导入区：拖拽 / 点击上传多张公众号后台截图，
 * 逐张展示缩略图与识别状态，识别完成后交给确认对话框入库。
 */
export function ScreenshotZone({
  items,
  busy,
  status,
  readyCount,
  onAdd,
  onRemove,
  onRetry,
  onClearAll,
  onReview,
  onGoConfig,
}: ScreenshotZoneProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = React.useState(false);

  const pick = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    const files = Array.from(list).slice(0, MAX_FILES);
    onAdd(files);
  };

  const failed = items.filter((i) => i.status === "failed");
  const succeeded = items.filter((i) => i.status === "success");
  const notConfigured = status !== null && !status.configured;

  return (
    <Card>
      <CardContent className="p-5">
        {/* 视觉模型没配好时提前提示，别让用户传完图才发现用不了 */}
        {status?.hint && (
          <Alert variant={notConfigured ? "destructive" : "warning"} className="mb-4">
            <AlertTitle className="flex items-center gap-1.5">
              <AlertTriangle className="h-4 w-4" />
              {notConfigured ? "还没配置视觉模型" : "当前视觉模型可能无法识别"}
            </AlertTitle>
            <AlertDescription>{status.hint}</AlertDescription>
            <div className="mt-3">
              <Button size="sm" variant="outline" onClick={onGoConfig}>
                <Settings2 className="h-4 w-4" />
                去配置
              </Button>
            </div>
          </Alert>
        )}

        <div
          role="button"
          tabIndex={0}
          onClick={() => !busy && inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (!busy) pick(e.dataTransfer.files);
          }}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors",
            dragging
              ? "border-violet-400/70 bg-violet-400/5"
              : "border-border hover:border-muted-foreground/40 hover:bg-muted/30",
            busy && "pointer-events-none opacity-60"
          )}
        >
          {busy ? (
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          ) : (
            <ImagePlus className="h-8 w-8 text-muted-foreground/50" />
          )}
          <p className="text-sm font-medium">
            {busy ? "AI 正在识别截图…" : "点击选择截图，或把图片拖到这里"}
          </p>
          <p className="text-xs text-muted-foreground">
            支持 png / jpg / jpeg，可一次选多张，单张不超过 10MB
          </p>
          <p className="text-[11px] text-muted-foreground/70">
            截公众号后台「内容分析 → 单篇文章数据」的列表，标题和数字清晰即可
          </p>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            multiple
            className="hidden"
            onChange={(e) => {
              pick(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {items.length > 0 && (
          <>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {items.map((it) => {
                const meta = STATUS_META[it.status];
                return (
                  <div
                    key={it.id}
                    className="group relative overflow-hidden rounded-lg border border-border bg-muted/20"
                  >
                    <div className="relative h-24 w-full overflow-hidden bg-black/20">
                      {/* blob 预览用原生 img：next/image 不支持 object URL */}
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={it.previewUrl}
                        alt={it.file.name}
                        className="h-full w-full object-cover object-top"
                      />
                      {it.status === "recognizing" && (
                        <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                          <Loader2 className="h-5 w-5 animate-spin text-white" />
                        </div>
                      )}
                      {it.status === "success" && (
                        <div className="absolute right-1.5 top-1.5 rounded-full bg-emerald-500/90 p-0.5">
                          <CheckCircle2 className="h-3.5 w-3.5 text-white" />
                        </div>
                      )}
                      <button
                        type="button"
                        aria-label="移除这张截图"
                        onClick={() => onRemove(it.id)}
                        disabled={it.status === "recognizing"}
                        className="absolute left-1.5 top-1.5 rounded-full bg-black/60 p-1 text-white opacity-0 transition-opacity hover:bg-black/80 focus-visible:opacity-100 group-hover:opacity-100 disabled:pointer-events-none"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                    <div className="space-y-1 p-2">
                      <p className="truncate text-[11px] text-muted-foreground" title={it.file.name}>
                        {it.file.name}
                      </p>
                      <div className="flex flex-wrap items-center gap-1">
                        <Badge variant={meta.variant} className="px-1.5 py-0 text-[10px]">
                          {meta.label}
                        </Badge>
                        {it.status === "success" && (
                          <span className="text-[10px] text-muted-foreground">
                            {it.articles.length} 篇
                          </span>
                        )}
                        {it.status === "success" && it.confidence === "low" && (
                          <Badge variant="warning" className="px-1.5 py-0 text-[10px]">
                            存疑
                          </Badge>
                        )}
                      </div>
                      {it.status === "failed" && (
                        <div className="space-y-1">
                          <p className="line-clamp-3 text-[10px] leading-tight text-destructive">
                            {it.error}
                          </p>
                          <Button
                            size="xs"
                            variant="outline"
                            className="h-5 w-full"
                            onClick={() => onRetry(it.id)}
                            disabled={busy}
                          >
                            <RefreshCw className="h-3 w-3" />
                            重试
                          </Button>
                        </div>
                      )}
                      {it.status === "success" && it.note && (
                        <p className="line-clamp-2 text-[10px] leading-tight text-amber-400/90">
                          {it.note}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={onReview} disabled={busy || readyCount === 0}>
                <ScanLine className="h-4 w-4" />
                查看识别结果（{readyCount} 条）
              </Button>
              <Button size="sm" variant="ghost" onClick={onClearAll} disabled={busy}>
                <Trash2 className="h-4 w-4" />
                清空截图
              </Button>
              <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
                <span>
                  共 {items.length} 张 · 成功 {succeeded.length}
                </span>
                {failed.length > 0 && (
                  <span className="text-destructive">失败 {failed.length}</span>
                )}
              </div>
            </div>
          </>
        )}

        {items.length === 0 && (
          <p className="mt-4 text-center text-xs text-muted-foreground">
            还没有上传截图。识别结果会先给你确认、可以手动改，确认后才会入库。
          </p>
        )}
      </CardContent>
    </Card>
  );
}
