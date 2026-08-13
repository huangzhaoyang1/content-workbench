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
  Cookie,
} from "lucide-react";
import { useRouter } from "next/navigation";
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
import { api } from "@/lib/api";
import type {
  DissectFetchResult,
  DissectSource,
  DissectTranscribeResult,
} from "@/lib/types";

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

/** 从抖音分享口令里抠出真正的 URL。
 *  抖音 App 复制出来的分享口令格式：
 *    "4.38 复制打开抖音，看看【...】让我... https://v.douyin.com/oN45lt7e5bk/04/20 oDH:/e"
 *  其中真正可用的 URL 只有 "https://v.douyin.com/oN45lt7e5bk/"，
 *  后面的 "/04/20 oDH:/e" 是抖音分享跟踪码，必须剥掉。
 *  优先级与后端 extract_url() 一致。 */
const SHARE_URL_PATTERNS: RegExp[] = [
  // 短链 v/www/m.douyin.com/<short_id>（用 negative lookahead 排除 /video/ /share/ 等长链）
  /https?:\/\/[a-zA-Z]+\.douyin\.com\/(?!video\/|share\/|note\/|user\/)[A-Za-z0-9_-]+/,
  // 长链 www.douyin.com/video/<digits>
  /https?:\/\/www\.douyin\.com\/video\/\d+/,
  // iesdouyin 分享页
  /https?:\/\/[a-zA-Z]*iesdouyin\.com\/share\/video\/\d+/,
  // 兜底：任意 URL
  /https?:\/\/[^\s\u4e00-\u9fff，。！？、）)]+/,
];
function extractShareUrl(text: string): string {
  for (const pat of SHARE_URL_PATTERNS) {
    const m = text.match(pat);
    if (m) return m[0].replace(/\/$/, "");
  }
  return "";
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
  const router = useRouter();
  const [tab, setTab] = React.useState<"url" | "text">(defaultTab);
  const [url, setUrl] = React.useState("");
  const [text, setText] = React.useState("");
  const [urlError, setUrlError] = React.useState<string | null>(null);

  // 抓取预览态
  const [fetching, setFetching] = React.useState(false);
  const [fetched, setFetched] = React.useState<DissectFetchResult | null>(null);
  const [draft, setDraft] = React.useState("");

  // 自动转写态（页面文本太短时触发，非阻塞页面）
  const [transcribing, setTranscribing] = React.useState(false);
  const [transcribeError, setTranscribeError] = React.useState<string | null>(null);
  // 拆开 message 和 error_key：转写错误 key 用于分类引导（need_login → 提示去配 Cookie）
  const [transcribeErrorKey, setTranscribeErrorKey] = React.useState<
    DissectTranscribeResult["error_key"] | null
  >(null);
  const [transcribed, setTranscribed] = React.useState(false);

  // 粘贴时若检测到分享口令里夹着链接，自动抽出 + 闪一下提示
  const [extracted, setExtracted] = React.useState(false);

  const handleFetch = async () => {
    if (!onFetch || !url.trim()) return;
    setUrlError(null);
    setFetching(true);
    // 新一轮抓取：清掉上一次的转写态
    setTranscribing(false);
    setTranscribeError(null);
    setTranscribeErrorKey(null);
    setTranscribed(false);
    try {
      const res = await onFetch(url.trim());
      setFetched(res);
      setDraft(res.text ?? "");
      // 抓取被反爬/验证页拦截：后端返回 needs_transcribe，这里直接自动触发
      // 「视频转写」兜底（约 5–30 分钟）。成功即用完整口播稿，失败才引导手动粘贴。
      if (res.needs_transcribe) {
        void runTranscribe(url.trim());
        return;
      }
      // 时长感知的「是否要自动转写」判定，和后端 dissect._should_trigger_transcribe 行为一致：
      //   - 中文口播按 3.5 字/秒估算应有字数；
      //   - 抓到的字数 < max(300, expected * 0.2) 时触发 Whisper 转写。
      //   - 15 分钟视频（900s）阈值约 630 字，188 字简介会被触发（核心修复目标）；
      //   - 30 秒短视频阈值约 300 字，简介 200 字不会误触发。
      // 是后台长任务（约 5–30 分钟），用 fire-and-forget 触发，不冻结页面。
      const dur = res.duration_sec ?? 0;
      const expected = dur > 0 ? Math.round(dur * 3.5) : 0;
      const threshold = Math.max(300, expected > 0 ? Math.round(expected * 0.2) : 300);
      if (((res.text ?? "").trim().length < threshold) && dur > 0) {
        void runTranscribe(url.trim());
      }
    } catch (e) {
      setFetched(null);
      setUrlError(
        e instanceof Error ? e.message : "抓取失败，请检查链接或改用手动粘贴"
      );
    } finally {
      setFetching(false);
    }
  };

  /** 调用后端 Whisper 转写接口，把视频音频转成完整口播稿。 */
  const runTranscribe = async (u: string) => {
    setTranscribing(true);
    setTranscribeError(null);
    setTranscribeErrorKey(null);
    try {
      const r = await api.dissectTranscribe(u);
      if (r.ok && r.text) {
        setDraft(r.text);
        setTranscribed(true);
      } else {
        setTranscribeError(r.error || "转写失败，原因未知");
        setTranscribeErrorKey(r.error_key ?? null);
      }
    } catch (e) {
      setTranscribeError(
        e instanceof Error ? e.message : "转写请求失败，请稍后重试"
      );
      setTranscribeErrorKey(null);
    } finally {
      setTranscribing(false);
    }
  };

  const resetFetch = () => {
    setFetched(null);
    setDraft("");
    setUrlError(null);
    setTranscribing(false);
    setTranscribeError(null);
    setTranscribeErrorKey(null);
    setTranscribed(false);
  };

  const handleSubmit = () => {
    setUrlError(null);
    if (tab === "url") {
      if (!fetched) {
        void handleFetch();
        return;
      }
      // 若这一步的文案来自视频转写（页面文本太短自动转写、或反爬拦截兜底转写），
      // 把素材来源标记为 transcribe，后端 analyze 会透传到结果徽章「视频转写」。
      const meta =
        transcribed
          ? {
              origin: "transcribe" as const,
              url: url.trim(),
              note: "",
              complete: true,
            }
          : (fetched.source ?? null);
      onSubmit({
        url: url.trim(),
        text: draft.trim(),
        meta,
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
                  placeholder="粘贴抖音分享文本或链接，会自动识别 URL（例如 https://v.douyin.com/xxxxx/）"
                  value={url}
                  error={!!urlError}
                  onChange={(e) => {
                    setUrl(e.target.value);
                    if (fetched) resetFetch();
                  }}
                  onPaste={(e) => {
                    // 用户从抖音 App 复制粘贴通常是「标题 + 链接 + 复制提示」一整段。
                    // 含中文的「分享口令」里识别出 URL 就替换成纯 URL，免得自己抠。
                    const text = e.clipboardData.getData("text") || "";
                    if (/[\u4e00-\u9fff]/.test(text)) {
                      const m = extractShareUrl(text);
                      if (m && m !== text) {
                        e.preventDefault();
                        setUrl(m);
                        setExtracted(true);
                        window.setTimeout(() => setExtracted(false), 2500);
                        if (fetched) resetFetch();
                      }
                    }
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
              {extracted && (
                <p className="flex items-center gap-1 text-xs text-emerald-600">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  已从分享文本中自动提取链接
                </p>
              )}
              {!fetched && !urlError && !extracted && (
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

                {/* 自动转写进度 / 失败引导（页面文本太短时触发） */}
                {transcribing && (
                  <div className="flex items-start gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3 text-xs leading-relaxed text-ink">
                    <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-primary" />
                    <div>
                      正在转写视频内容…（约 5–30 分钟，CPU 模式）
                      <div className="mt-0.5 text-ink-2">
                        先把视频音频拉下来再用 Whisper 转成文字，完成后会自动填进口播文案框；你也可以直接手动粘贴。
                      </div>
                    </div>
                  </div>
                )}
                {!transcribing && transcribeError && (
                  <Alert variant="warning">
                    <AlertDescription>
                      <div className="flex items-start gap-2">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                        <div className="space-y-1 text-xs leading-relaxed">
                          <div>视频转写失败：{transcribeError}</div>
                          {/* 失败原因 = 需要登录态：直接给「去配置 Cookie」入口，闭环 */}
                          {transcribeErrorKey === "need_login" ? (
                            <div className="space-y-2">
                              <div>
                                自动转写需要登录态才能下载音频；去「抖音同步」页粘贴一下你的 Cookie，保存后回来再试。
                              </div>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => router.push("/douyin-sync")}
                                className="mt-1 h-7 gap-1.5 text-xs"
                              >
                                <Cookie className="h-3.5 w-3.5" />
                                去配置 Cookie
                              </Button>
                            </div>
                          ) : (
                            <div>
                              建议打开抖音 App，开字幕把完整口播稿复制粘贴到下面的框里再拆解；手动粘贴的文案最完整，拆解质量最高。
                            </div>
                          )}
                        </div>
                      </div>
                    </AlertDescription>
                  </Alert>
                )}

                {/* 可编辑文案 */}
                <div className="space-y-2">
                  <Label htmlFor="dy-draft" required>
                    口播文案（可直接编辑，确认后再拆解）
                    {transcribed && (
                      <Badge variant="success" className="ml-2">
                        视频转写
                      </Badge>
                    )}
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

            {/* ---------- 抓取被反爬拦截 → 自动转写兜底 ---------- */}
            {fetched?.needs_transcribe && (
              <div className="space-y-3 rounded-xl border border-primary/25 bg-primary/5 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="warning">抓取被拦截</Badge>
                  <span className="text-[11px] text-muted-foreground">
                    抖音反爬拦截了页面抓取，已自动改用「视频转写」拿完整口播稿
                  </span>
                </div>

                {/* 自动转写进度 */}
                {transcribing && (
                  <div className="flex items-start gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3 text-xs leading-relaxed">
                    <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-primary" />
                    <div>
                      正在尝试自动转写视频内容（约 5–30 分钟）…
                      <div className="mt-0.5 text-muted-foreground">
                        先把视频音频拉下来再用 Whisper 转成文字，完成后会自动填进口播文案框；你也可以直接手动粘贴。
                      </div>
                    </div>
                  </div>
                )}

                {/* 转写失败引导 */}
                {!transcribing && transcribeError && (
                  <Alert variant="warning">
                    <AlertDescription>
                      <div className="flex items-start gap-2">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                        <div className="space-y-1 text-xs leading-relaxed">
                          <div>视频转写也没成功：{transcribeError}</div>
                          {transcribeErrorKey === "need_login" ? (
                            <div className="space-y-2">
                              <div>
                                自动转写需要登录态。去「抖音同步」页扫码登录或粘贴 Cookie，保存后回来再试。
                              </div>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => router.push("/douyin-sync")}
                                className="mt-1 h-7 gap-1.5 text-xs"
                              >
                                <Cookie className="h-3.5 w-3.5" />
                                去登录 / 配 Cookie
                              </Button>
                            </div>
                          ) : (
                            <div>建议打开抖音 App 开字幕，把完整口播稿复制粘贴到下面的框里再拆解。</div>
                          )}
                        </div>
                      </div>
                    </AlertDescription>
                  </Alert>
                )}

                {/* 可编辑文案（转写完成后自动填入；也可手动粘贴覆盖） */}
                <div className="space-y-2">
                  <Label htmlFor="dy-draft-antibot" required>
                    口播文案（可直接编辑，确认后再拆解）
                    {transcribed && (
                      <Badge variant="success" className="ml-2">
                        视频转写
                      </Badge>
                    )}
                  </Label>
                  <Textarea
                    id="dy-draft-antibot"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    disabled={busy}
                    placeholder="自动转写完成后会填到这里；也可手动粘贴抖音字幕/口播稿覆盖。"
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
