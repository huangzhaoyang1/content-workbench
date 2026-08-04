"use client";

import * as React from "react";
import {
  Upload,
  FileSpreadsheet,
  Loader2,
  Sparkles,
  Trash2,
  CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { AnalyticsDataset } from "@/lib/types";

interface UploadZoneProps {
  dataset: AnalyticsDataset | null;
  uploading: boolean;
  onUpload: (file: File) => void;
  onSample: () => void;
  onClear: () => void;
}

const ACCEPT = ".csv,.xlsx,.xls";
const FIELD_LABELS: Record<string, string> = {
  title: "标题",
  date: "日期",
  reads: "阅读量",
  likes: "在看",
  shares: "分享",
};

/** 数据上传区：点击 / 拖拽上传 + 示例数据 + 清空。 */
export function UploadZone({
  dataset,
  uploading,
  onUpload,
  onSample,
  onClear,
}: UploadZoneProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = React.useState(false);

  const pick = (files: FileList | null) => {
    const f = files?.[0];
    if (f) onUpload(f);
  };

  return (
    <Card>
      <CardContent className="p-5">
        <div
          role="button"
          tabIndex={0}
          onClick={() => !uploading && inputRef.current?.click()}
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
            if (!uploading) pick(e.dataTransfer.files);
          }}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors",
            dragging
              ? "border-sky-400/70 bg-sky-400/5"
              : "border-border hover:border-muted-foreground/40 hover:bg-muted/30",
            uploading && "pointer-events-none opacity-60"
          )}
        >
          {uploading ? (
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          ) : (
            <Upload className="h-8 w-8 text-muted-foreground/50" />
          )}
          <p className="text-sm font-medium">
            {uploading ? "正在解析文件…" : "点击选择文件，或把文件拖到这里"}
          </p>
          <p className="text-xs text-muted-foreground">
            支持公众号后台导出的 CSV / Excel（.csv .xlsx .xls），单个文件不超过 10MB
          </p>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => {
              pick(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={onSample} disabled={uploading}>
            <Sparkles className="h-4 w-4" />
            使用示例数据
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClear}
            disabled={uploading || !dataset}
          >
            <Trash2 className="h-4 w-4" />
            清空当前分析
          </Button>

          {dataset && (
            <div className="ml-auto flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              <FileSpreadsheet className="h-3.5 w-3.5" />
              <span className="font-medium text-foreground">
                {dataset.is_sample ? "示例数据" : dataset.filename}
              </span>
              <span>· {dataset.row_count} 条</span>
            </div>
          )}
        </div>

        {dataset && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px]">
            <span className="text-muted-foreground">识别到的列：</span>
            {(Object.keys(FIELD_LABELS) as Array<keyof typeof FIELD_LABELS>).map(
              (k) => {
                const col = dataset.mapping[k as keyof typeof dataset.mapping];
                return (
                  <Badge key={k} variant={col ? "secondary" : "muted"}>
                    {FIELD_LABELS[k]}
                    {col ? ` → ${col}` : " → 未识别"}
                  </Badge>
                );
              }
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
