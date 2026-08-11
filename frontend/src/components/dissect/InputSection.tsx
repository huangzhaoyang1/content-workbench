"use client";

import * as React from "react";
import {
  Link2,
  ClipboardPaste,
  Sparkles,
  Loader2,
  Download,
  RotateCw,
  AlertTriangle,
  Heart,
  MessageCircle,
  Star,
  Clock,
  User,
  CalendarClock,
  Hash,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { DissectFetchResult, DissectSource } from "@/lib/types";

export interface DissectInputValue {
  url: string;
  text: string;
  /** 抓取阶段拿到的视频元信息，手动改文案后仍带着走 */
  meta?: DissectSource | null;
}

interface InputSectionProps {
  loading: boolean;
  defaultTab?: "url" | "text";
  onSubmit: (value: DissectInputValue) => void;
  /** 只抓取不拆解 */
  onFetch?: (url: string) => Promise<DissectFetchResult>;
}

const MISSING = "未抓到";

function fmtNum(n: number | null | undefined): string {
  if (n == null) return MISSING;
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  return String(n);
}

function fmtDuration(sec: number | null | undefined): string {
  if (sec == null || sec <= 0) return MISSING;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}分${String(s).padStart(2, "0")}秒` : `${s}秒`;
}

/** 结构化字段的一个小格子 */
function Field({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  const empty = value === MISSING;
  return (
    <div className="flex items-center gap-1.5 rounded-lg border border-border bg-muted/30 px-2.5 py-1.5">
      <Icon
        className={cn(
          "h-3.5 w-3.5 shrink-0",
          empty ? "text-muted-foreground/50" : "text-primary/80"
        )}
      />
      <span className="shrink-0 text-[11px] text-muted-foreground">{label}</span>
      <span
        className={cn(
          "truncate text-xs tabular-nums",
          empty ? "text-muted-foreground/60" : "font-medium text-foreground"
        )}
      >
        {value}
      </span>
    </div>
  );
}

export function InputSection({
  loading,
  defaultTab = "text",
  onSubmit,
  onFetch,
}: InputSectionProps) {
  const [tab, setTab] = React.useState<"url" | "text">(defaultTab);
  const [url, setUrl] = React.useState("");
  const [text, setText] = React.useState("");
  const [urlError, setUrlError] = React.useState<string | null>(null);

  // 抓取预览态
  const [fetching, setFetching] = React.useState(false);
  const [fetched, setFetched] = React.useState<DissectFetchResult | null>(null);
  const [draft, setDraft] = React.useState("");

  const handleFetch = async () => {
    if (!onFetch || !url.trim()) return;
    setUrlError(null);
    setFetching(true);
    try {
      const res = await onFetch(url.trim());
      setFetched(res);
      setDraft(res.text ?? "");
    } catch (e) {
      setFetched(null);
      setUrlError(
        e instanceof Error ? e.message : "抓取失败，请检查链接或改用手动粘贴"
      );
    } finally {
      setFetching(false);
    }
  };

  const resetFetch = () => {
    setFetched(null);
    setDraft("");
    setUrlError(null);
  };

  const handleSubmit = () => {
    setUrlError(null);
    if (tab === "url") {
      if (!fetched) {
        void handleFetch();
        return;
      }
      onSubmit({
        url: url.trim(),
        text: draft.trim(),
        meta: fetched.source ?? null,
      });
      return;
    }
    onSubmit({ url: "", text: text.trim(), meta: null });
  };

  const busy = loading || fetching;
  const canSubmit =
    !busy &&
    (tab === "url"
      ? fetched
        ? draft.trim().length >= 30
        : url.trim().length > 0
      : text.trim().length >= 30);

  const src = fetched?.source;
  const missing = src?.missing ?? [];

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <Tabs
        defaultValue={defaultTab}
        value={tab}
        onValueChange={(v) => setTab(v as "url" | "text")}
      >
        <TabsList className="mb-4">
          <TabsTrigger value="url">
            <Link2 className="mr-1.5 h-3.5 w-3.5" />
            抖音链接
          </TabsTrigger>
          <TabsTrigger value="text">
            <ClipboardPaste className="mr-1.5 h-3.5 w-3.5" />
            手动粘贴
          </TabsTrigger>
        </TabsList>

        <TabsContent value="url">
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="dy-url">抖音分享链接 / 口令</Label>
              <div className="flex gap-2">
                <Input
                  id="dy-url"
                  placeholder="粘贴抖音分享链接，例如 https://v.douyin.com/xxxxx/ （或带链接的分享口令）"
                  value={url}
                  error={!!urlError}
                  onChange={(e) => {
                    setUrl(e.target.value);
                    if (fetched) resetFetch();
                  }}
                  disabled={busy}
                />
                <Button
                  variant={fetched ? "outline" : "default"}
                  onClick={handleFetch}
                  disabled={busy || !url.trim()}
                  className="shrink-0"
                >
                  {fetching ? (
                    <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  ) : fetched ? (
                    <RotateCw className="mr-1.5 h-4 w-4" />
                  ) : (
                    <Download className="mr-1.5 h-4 w-4" />
                  )}
                  {fetching ? "抓取中…" : fetched ? "重新抓取" : "抓取文案"}
                </Button>
              </div>
              {urlError && <p className="text-xs text-destructive">{urlError}</p>}
              {!fetched && !urlError && (
                <p className="text-xs leading-relaxed text-muted-foreground">
                  先抓取、后拆解：抓完会把标题、口播文案、描述、发布时间、点赞/评论/收藏数
                  列出来给你确认，文案可以直接改，确认没问题再开始拆解。
                </p>
              )}
            </div>

            {/* ---------- 抓取结果预览 ---------- */}
            {fetched && src && (
              <div className="space-y-3 rounded-xl border border-primary/25 bg-primary/5 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge>抓取结果</Badge>
                  {src.strategy && (
                    <span className="text-[11px] text-muted-foreground">
                      解析方式：{src.strategy}
                    </span>
                  )}
                  {src.video_id && (
                    <span className="text-[11px] text-muted-foreground">
                      · 视频 ID {src.video_id}
                    </span>
                  )}
                </div>

                {/* 标题 */}
                <div className="space-y-1">
                  <div className="text-[11px] text-muted-foreground">视频标题</div>
                  <div
                    className={cn(
                      "text-sm leading-snug",
                      src.title
                        ? "font-medium text-foreground"
                        : "text-muted-foreground/60"
                    )}
                  >
                    {src.title || MISSING}
                  </div>
                </div>

                {/* 描述 */}
                {src.desc && src.desc !== src.title && (
                  <div className="space-y-1">
                    <div className="text-[11px] text-muted-foreground">视频描述</div>
                    <div className="text-xs leading-relaxed text-foreground/80">
                      {src.desc}
                    </div>
                  </div>
                )}

                {/* 结构化小字段 */}
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  <Field icon={User} label="作者" value={src.author || MISSING} />
                  <Field
                    icon={CalendarClock}
                    label="发布"
                    value={src.create_time || MISSING}
                  />
                  <Field
                    icon={Clock}
                    label="时长"
                    value={fmtDuration(src.duration_sec)}
                  />
                  <Field icon={Heart} label="点赞" value={fmtNum(src.stats?.digg)} />
                  <Field
                    icon={MessageCircle}
                    label="评论"
                    value={fmtNum(src.stats?.comment)}
                  />
                  <Field
                    icon={Star}
                    label="收藏"
                    value={fmtNum(src.stats?.collect)}
                  />
                </div>

                {/* 话题标签 */}
                {(src.hashtags?.length ?? 0) > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Hash className="h-3 w-3 text-muted-foreground" />
                    {src.hashtags!.map((h, i) => (
                      <Badge key={i} variant="muted">
                        {h}
                      </Badge>
                    ))}
                  </div>
                )}

                {/* 缺失提示 */}
                {(missing.length > 0 || (fetched.hints?.length ?? 0) > 0) && (
                  <Alert variant="warning">
                    <AlertDescription>
                      <div className="flex items-start gap-2">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                        <div className="space-y-1 text-xs leading-relaxed">
                          {missing.length > 0 && (
                            <div>
                              以下字段没抓到，可手动补：
                              <span className="font-medium text-foreground">
                                {missing.join("、")}
                              </span>
                            </div>
                          )}
                          {fetched.hints?.map((h, i) => (
                            <div key={i}>{h}</div>
                          ))}
                        </div>
                      </div>
                    </AlertDescription>
                  </Alert>
                )}

                {/* 可编辑文案 */}
                <div className="space-y-2">
                  <Label htmlFor="dy-draft" required>
                    口播文案（可直接编辑，确认后再拆解）
                  </Label>
                  <Textarea
                    id="dy-draft"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    disabled={busy}
                    placeholder="抓到的文案会填在这里。如果只抓到简介，建议打开抖音开字幕，把完整口播稿粘进来覆盖。"
                    className="min-h-[180px] resize-y bg-card font-mono text-[13px] leading-relaxed"
                  />
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>至少 30 字才能拆解；200 字以上质量明显更好。</span>
                    <span
                      className={cn(
                        draft.length > 0 && draft.length < 30 && "text-amber-400",
                        draft.length >= 200 && "text-emerald-400"
                      )}
                    >
                      {draft.length} 字
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="text">
          <div className="space-y-2">
            <Label htmlFor="dy-text" required>
              视频文案 / 口播稿
            </Label>
            <Textarea
              id="dy-text"
              placeholder="把抖音视频的字幕或口播稿粘贴到这里（建议 100 字以上，越长拆得越准）。"
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={busy}
              className="min-h-[160px] resize-y font-mono text-[13px] leading-relaxed"
            />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>文案至少 30 字；超过 6000 字会自动截断。</span>
              <span className={cn(text.length > 0 && text.length < 30 && "text-amber-400")}>
                {text.length} 字
              </span>
            </div>
          </div>
        </TabsContent>
      </Tabs>

      <div className="mt-4 flex items-center justify-end gap-2">
        <Button onClick={handleSubmit} disabled={!canSubmit}>
          {busy ? (
            <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
          ) : tab === "url" && !fetched ? (
            <Download className="mr-1.5 h-4 w-4" />
          ) : (
            <Sparkles className="mr-1.5 h-4 w-4" />
          )}
          {loading
            ? "拆解中…"
            : fetching
              ? "抓取中…"
              : tab === "url" && !fetched
                ? "抓取文案"
                : "开始拆解并改写"}
        </Button>
      </div>
    </div>
  );
}
