"use client";

import * as React from "react";
import { AlertTriangle, Loader2, Trash2, Upload, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Dialog } from "@/components/ui/dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { OcrArticle, OcrSummary } from "@/lib/types";

interface OcrConfirmDialogProps {
  open: boolean;
  /** 各张截图识别出的文章（已在页面层做过批内去重） */
  articles: OcrArticle[];
  /** 各张截图的账号级指标，只展示不入库 */
  summaries: OcrSummary[];
  importing: boolean;
  onCancel: () => void;
  onConfirm: (articles: OcrArticle[]) => void;
}

/** 表格里每行的可编辑草稿：统一用字符串，避免受控 number input 的空值抖动。 */
interface DraftRow {
  id: string;
  title: string;
  date: string;
  reads: string;
  likes: string;
  wow: string;
  shares: string;
  collects: string;
}

type NumField = "reads" | "likes" | "wow" | "shares" | "collects";

const NUM_FIELDS: Array<{ key: NumField; label: string; width: string }> = [
  { key: "reads", label: "阅读量", width: "w-[92px]" },
  { key: "likes", label: "在看", width: "w-[76px]" },
  { key: "wow", label: "点赞", width: "w-[76px]" },
  { key: "shares", label: "分享", width: "w-[76px]" },
  { key: "collects", label: "收藏", width: "w-[76px]" },
];

function toStr(v: number | null | undefined): string {
  return v === null || v === undefined ? "" : String(v);
}

function toNum(s: string): number | null {
  const t = s.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? Math.round(n) : null;
}

/** 数字格子合法性：空 或 非负整数。 */
function badNumber(s: string): boolean {
  const t = s.trim();
  if (!t) return false;
  const n = Number(t);
  return !Number.isFinite(n) || n < 0;
}

let seq = 0;
const nextId = () => `row-${Date.now().toString(36)}-${seq++}`;

/**
 * 识别结果确认对话框：入库前让用户逐条核对、修改识别错误的数据。
 * 点「确认导入」才会真正写入，点「取消」直接丢弃。
 */
export function OcrConfirmDialog({
  open,
  articles,
  summaries,
  importing,
  onCancel,
  onConfirm,
}: OcrConfirmDialogProps) {
  const [rows, setRows] = React.useState<DraftRow[]>([]);
  const [touched, setTouched] = React.useState(false);

  // 每次打开对话框时用最新识别结果重置草稿
  React.useEffect(() => {
    if (!open) return;
    setRows(
      articles.map((a) => ({
        id: nextId(),
        title: a.title ?? "",
        date: a.date ?? "",
        reads: toStr(a.reads),
        likes: toStr(a.likes),
        wow: toStr(a.wow),
        shares: toStr(a.shares),
        collects: toStr(a.collects),
      }))
    );
    setTouched(false);
  }, [open, articles]);

  const patch = (id: string, key: keyof DraftRow, value: string) => {
    setTouched(true);
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, [key]: value } : r)));
  };

  const removeRow = (id: string) => {
    setTouched(true);
    setRows((rs) => rs.filter((r) => r.id !== id));
  };

  // 校验：标题必填；数字必须是非负数；至少要有一个指标有值
  const invalid = React.useMemo(() => {
    const map = new Map<string, string>();
    rows.forEach((r) => {
      if (!r.title.trim()) {
        map.set(r.id, "标题不能为空");
        return;
      }
      const bad = NUM_FIELDS.find((f) => badNumber(r[f.key]));
      if (bad) {
        map.set(r.id, `${bad.label}要填非负整数`);
        return;
      }
      const hasMetric = NUM_FIELDS.some((f) => r[f.key].trim() !== "");
      if (!hasMetric) map.set(r.id, "至少要有一项数据");
    });
    return map;
  }, [rows]);

  const lowConfidenceNote = summaries.length === 0;
  const accountRows = summaries.filter(
    (s) =>
      s.followers_delta !== null ||
      s.new_followers !== null ||
      s.total_reads !== null
  );

  const canSubmit = rows.length > 0 && invalid.size === 0 && !importing;

  const submit = () => {
    if (!canSubmit) return;
    const payload: OcrArticle[] = rows.map((r) => ({
      title: r.title.trim(),
      date: r.date.trim() || null,
      reads: toNum(r.reads),
      likes: toNum(r.likes),
      wow: toNum(r.wow),
      shares: toNum(r.shares),
      collects: toNum(r.collects),
    }));
    onConfirm(payload);
  };

  return (
    <Dialog open={open} onClose={importing ? () => undefined : onCancel} className="max-w-5xl">
      <div className="mb-4">
        <h2 className="text-lg font-semibold">确认识别结果</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          AI 识别难免有误差，导入前先核对一遍。任何格子都能直接改，不需要的行可以删掉。
          确认导入后会按「标题 + 日期」自动去重。
        </p>
      </div>

      {accountRows.length > 0 && (
        <Alert variant="info" className="mb-4">
          <AlertTitle className="flex items-center gap-1.5">
            <Users className="h-4 w-4" />
            截图里的账号整体数据
          </AlertTitle>
          <AlertDescription>
            <div className="mt-1 flex flex-wrap gap-2">
              {accountRows.map((s, i) => (
                <span key={i} className="flex flex-wrap gap-2">
                  {s.followers_delta !== null && (
                    <Badge variant="secondary">净增关注 {s.followers_delta}</Badge>
                  )}
                  {s.new_followers !== null && (
                    <Badge variant="muted">新关注 {s.new_followers}</Badge>
                  )}
                  {s.lost_followers !== null && (
                    <Badge variant="muted">取关 {s.lost_followers}</Badge>
                  )}
                  {s.total_reads !== null && (
                    <Badge variant="muted">总阅读 {s.total_reads}</Badge>
                  )}
                  {s.date_range && <Badge variant="muted">{s.date_range}</Badge>}
                </span>
              ))}
            </div>
            <p className="mt-2 text-xs opacity-80">
              账号级指标只做展示参考，不会写入文章数据表。
            </p>
          </AlertDescription>
        </Alert>
      )}

      {rows.length === 0 ? (
        <EmptyState
          icon={AlertTriangle}
          title="没有可导入的数据"
          description={
            touched
              ? "所有行都被删掉了。关掉这个窗口，重新上传截图再试。"
              : "这批截图没有识别出文章数据，换一张更清晰、只包含数据列表的截图重试。"
          }
        />
      ) : (
        <>
          <div className="max-h-[46vh] overflow-auto rounded-lg border border-border">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-card">
                <TableRow>
                  <TableHead className="w-[44px]">#</TableHead>
                  <TableHead className="min-w-[240px]">标题</TableHead>
                  <TableHead className="w-[140px]">发布日期</TableHead>
                  {NUM_FIELDS.map((f) => (
                    <TableHead key={f.key} className={f.width}>
                      {f.label}
                    </TableHead>
                  ))}
                  <TableHead className="w-[48px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r, i) => {
                  const err = invalid.get(r.id);
                  return (
                    <TableRow key={r.id}>
                      <TableCell className="p-2 text-xs text-muted-foreground">
                        {i + 1}
                      </TableCell>
                      <TableCell className="p-2">
                        <Input
                          value={r.title}
                          error={!!err && !r.title.trim()}
                          onChange={(e) => patch(r.id, "title", e.target.value)}
                          placeholder="文章标题"
                          className="h-8 text-xs"
                        />
                        {err && (
                          <p className="mt-1 text-[10px] text-destructive">{err}</p>
                        )}
                      </TableCell>
                      <TableCell className="p-2">
                        <Input
                          type="date"
                          value={r.date}
                          onChange={(e) => patch(r.id, "date", e.target.value)}
                          className="h-8 text-xs [&::-webkit-calendar-picker-indicator]:opacity-60 [&::-webkit-calendar-picker-indicator]:invert"
                        />
                      </TableCell>
                      {NUM_FIELDS.map((f) => (
                        <TableCell key={f.key} className="p-2">
                          <Input
                            inputMode="numeric"
                            value={r[f.key]}
                            error={badNumber(r[f.key])}
                            onChange={(e) => patch(r.id, f.key, e.target.value)}
                            placeholder="—"
                            className="h-8 text-xs"
                          />
                        </TableCell>
                      ))}
                      <TableCell className="p-2">
                        <Button
                          size="icon-xs"
                          variant="ghost"
                          aria-label="删除这一行"
                          onClick={() => removeRow(r.id)}
                          disabled={importing}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          {lowConfidenceNote && (
            <p className="mt-2 text-[11px] text-muted-foreground">
              提示：识别不到的数字会留空，留空的字段不会被当成 0 参与统计。
            </p>
          )}
        </>
      )}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs text-muted-foreground">
          共 {rows.length} 条
          {invalid.size > 0 && (
            <span className="ml-2 text-destructive">{invalid.size} 条待修正</span>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onCancel} disabled={importing}>
            取消
          </Button>
          <Button size="sm" onClick={submit} disabled={!canSubmit}>
            {importing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            确认导入{rows.length > 0 ? `（${rows.length} 条）` : ""}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
