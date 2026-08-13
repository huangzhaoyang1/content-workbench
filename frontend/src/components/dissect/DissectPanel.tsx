"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  Loader2,
  Library,
  Copy,
  Sparkles,
  Rocket,
  BookmarkPlus,
  AlertTriangle,
  Footprints,
  Wrench,
  Brain,
  FileText,
  RefreshCw,
  CheckCircle2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { useToast } from "@/components/ui/toast";
import { InputSection, type DissectInputValue } from "@/components/dissect/InputSection";
import { DissectAnalysis } from "@/components/dissect/DissectAnalysis";
import { MaterialChecklist } from "@/components/dissect/MaterialChecklist";
import { RewritePreview } from "@/components/dissect/RewritePreview";
import { TitleSwitcher, type TitleSwitcherItem } from "@/components/dissect/TitleSwitcher";
import { TopicLibraryDialog } from "@/components/dissect/TopicLibraryDialog";
import { api, friendlyMessage } from "@/lib/api";
import { queueDraft } from "@/lib/seed";
import type {
  DissectAnalyzeResult,
  RewriteResult,
  TopicLibraryItem,
  PipelineStatus,
} from "@/lib/types";

/** 三个改写角度的前端展示元信息（后端没返回 label 时兜底用）。 */
const ANGLE_META: Record<
  string,
  { label: string; icon: React.ComponentType<{ className?: string }>; category: string }
> = {
  pitfall: { label: "踩坑经历", icon: Footprints, category: "踩坑类" },
  howto: { label: "干货总结", icon: Wrench, category: "干货类" },
  insight: { label: "认知升级", icon: Brain, category: "复盘类" },
};

const FALLBACK_META = {
  label: "公众号改写",
  icon: FileText,
  category: "其他",
};

function angleKeyOf(r: RewriteResult, i: number): string {
  return r.angle_key || `rewrite-${i}`;
}

function metaOf(key: string) {
  return ANGLE_META[key] ?? FALLBACK_META;
}

/** 拆解面板：复用于「抖音线 / 即时拆解」Tab 与独立 /dissect 路由。
 *  embedded=true 时（嵌入抖音线 Tab）隐藏自己的小标题，由外层 PageHeader 提供。 */
export function DissectPanel({ embedded = false }: { embedded?: boolean }) {
  const router = useRouter();
  const { toast } = useToast();

  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<DissectAnalyzeResult | null>(null);
  const [lastInput, setLastInput] = React.useState<DissectInputValue | null>(null);
  const [tab, setTab] = React.useState("articles");

  const [angleOrder, setAngleOrder] = React.useState<string[]>([]);
  const [versions, setVersions] = React.useState<Record<string, RewriteResult[]>>({});
  const [activeVer, setActiveVer] = React.useState<Record<string, number>>({});
  const [titles, setTitles] = React.useState<Record<string, string>>({});
  const [activeAngle, setActiveAngle] = React.useState("");
  const [regenKey, setRegenKey] = React.useState("");

  const [saving, setSaving] = React.useState(false);
  const [copying, setCopying] = React.useState(false);
  const [libOpen, setLibOpen] = React.useState(false);
  const [libCount, setLibCount] = React.useState(0);

  // 抖音线后半衔接：候选选题 → 选择并生产 → 就地表单/日志（对齐热点线 /topic 体验）
  const [producePhase, setProducePhase] = React.useState<"idle" | "form" | "running" | "done">("idle");
  const [pickedKey, setPickedKey] = React.useState<string>("");
  const [fTopic, setFTopic] = React.useState("");
  const [fAngle, setFAngle] = React.useState("");
  const [fExtra, setFExtra] = React.useState("");
  const [fPlatform] = React.useState("wechat"); // 抖音线固定走微信平台，UI 不切换
  const [fReview, setFReview] = React.useState(true); // 抖音线默认进待审核（不再默认直推微信）
  const [task, setTask] = React.useState<PipelineStatus | null>(null);
  const [producing, setProducing] = React.useState(false);
  const logBoxRef = React.useRef<HTMLDivElement | null>(null);
  const logEndRef = React.useRef<HTMLDivElement | null>(null);
  const [autoScroll, setAutoScroll] = React.useState(true);

  const rewrites = React.useMemo<RewriteResult[]>(
    () =>
      angleOrder
        .map((k) => versions[k]?.[activeVer[k] ?? 0])
        .filter((r): r is RewriteResult => Boolean(r)),
    [angleOrder, versions, activeVer]
  );

  const currentKey = activeAngle || angleOrder[0] || "";
  const current = currentKey
    ? versions[currentKey]?.[activeVer[currentKey] ?? 0] ?? null
    : null;
  const currentTitle = titles[currentKey] ?? current?.titles?.[0] ?? "";

  const switcherItems = React.useMemo<TitleSwitcherItem[]>(
    () =>
      angleOrder
        .map((key): TitleSwitcherItem | null => {
          const r = versions[key]?.[activeVer[key] ?? 0];
          if (!r) return null;
          const meta = metaOf(key);
          return {
            key,
            title: titles[key] ?? r.titles?.[0] ?? "",
            angleLabel: r.angle_label || meta.label,
            angleDesc: r.angle_desc || "",
            icon: meta.icon,
            wordCount: r.word_count,
            score: r.quality?.total ?? null,
          };
        })
        .filter((x): x is TitleSwitcherItem => x !== null),
    [angleOrder, versions, activeVer, titles]
  );

  React.useEffect(() => {
    void api
      .dissectListTopics({ limit: 1 })
      .then((res) => setLibCount(res.total))
      .catch(() => undefined);
  }, []);

  const applyResult = (res: DissectAnalyzeResult) => {
    const list = res.rewrites?.length ? res.rewrites : res.rewrite ? [res.rewrite] : [];
    const order = list.map((r, i) => angleKeyOf(r, i));
    const v: Record<string, RewriteResult[]> = {};
    const av: Record<string, number> = {};
    const t: Record<string, string> = {};
    list.forEach((r, i) => {
      const k = order[i];
      v[k] = [r];
      av[k] = 0;
      t[k] = r.titles?.[0] ?? "";
    });
    setResult(res);
    setAngleOrder(order);
    setVersions(v);
    setActiveVer(av);
    setTitles(t);
    setActiveAngle(order[0] ?? "");
    setTab("articles");
    return list.length;
  };

  const runAnalyze = async (value: DissectInputValue) => {
    setError(null);
    setLoading(true);
    try {
      const res = await api.dissectAnalyze({
        url: value.url,
        text: value.text,
        meta: value.meta ?? null,
      });
      const n = applyResult(res);
      toast(`拆解完成：${n} 篇不同角度的文章，耗时 ${res.elapsed_sec}s`, "success");
    } catch (e) {
      setError(friendlyMessage(e, "拆解失败，请稍后重试"));
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (value: DissectInputValue) => {
    setLastInput(value);
    await runAnalyze(value);
  };

  const handleRedissect = async () => {
    if (!lastInput) return;
    await runAnalyze(lastInput);
  };

  const handleRegenerate = async () => {
    if (!result || !currentKey) return;
    setRegenKey(currentKey);
    const nextIdx = versions[currentKey]?.length ?? 1;
    try {
      const res = await api.dissectRewriteOne({
        angle_key: currentKey,
        raw_text: result.raw_text,
        dissect: result.dissect,
      });
      setVersions((prev) => ({
        ...prev,
        [currentKey]: [...(prev[currentKey] ?? []), res.rewrite],
      }));
      setActiveVer((prev) => ({ ...prev, [currentKey]: nextIdx }));
      setTitles((prev) => ({ ...prev, [currentKey]: res.rewrite.titles?.[0] ?? "" }));
      toast(
        `已生成第 ${nextIdx + 1} 版，耗时 ${res.elapsed_sec}s。点 v1 / v${nextIdx + 1} 可以对比。`,
        "success"
      );
    } catch (e) {
      toast(friendlyMessage(e, "重新生成失败"), "error");
    } finally {
      setRegenKey("");
    }
  };

  const handleSelectVersion = (i: number) => {
    if (!currentKey) return;
    setActiveVer((prev) => ({ ...prev, [currentKey]: i }));
    const v = versions[currentKey]?.[i];
    if (v) setTitles((prev) => ({ ...prev, [currentKey]: v.titles?.[0] ?? "" }));
  };

  const handleSaveTopic = async () => {
    if (!current || !currentTitle) return;
    setSaving(true);
    try {
      await api.dissectSaveTopic({
        title: currentTitle,
        content: current.content,
        theme: current.theme,
        angle_key: current.angle_key,
        category: metaOf(currentKey).category,
        priority: "中",
        status: "待生产",
      });
      setLibCount((n) => n + 1);
      toast(`已加入选题库（${metaOf(currentKey).category}）`, "success");
    } catch (e) {
      toast(friendlyMessage(e, "保存失败"), "error");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAll = async () => {
    if (rewrites.length < 2) return;
    setSaving(true);
    let ok = 0;
    try {
      for (let i = 0; i < angleOrder.length; i += 1) {
        const key = angleOrder[i];
        const r = versions[key]?.[activeVer[key] ?? 0];
        if (!r) continue;
        try {
          await api.dissectSaveTopic({
            title: titles[key] ?? r.titles?.[0] ?? "",
            content: r.content,
            theme: r.theme,
            angle_key: r.angle_key,
            category: metaOf(key).category,
            priority: "中",
            status: "待生产",
          });
          ok += 1;
        } catch {
          /* 单篇失败不阻断其它篇 */
        }
      }
      setLibCount((n) => n + ok);
      toast(
        ok === rewrites.length
          ? `${ok} 篇全部加入选题库`
          : `加入 ${ok} / ${rewrites.length} 篇，其余保存失败`,
        ok === rewrites.length ? "success" : "warning"
      );
    } finally {
      setSaving(false);
    }
  };

  // 「直接生产」改造为：对当前篇一键就地生产（默认待审核，不再跳 /queue 直推微信）
  const handleProduce = async () => {
    if (!current || !currentTitle) return;
    await startInlineProduce({
      topic: currentTitle,
      angle: current.angle_label ?? metaOf(currentKey).label,
      extra: current.content,
      review: true,
    });
  };

  // 候选卡片「选择并生产」：预填表单并就地展开
  const pickProduce = (key: string) => {
    const item = switcherItems.find((s) => s.key === key);
    const r = versions[key]?.[activeVer[key] ?? 0];
    setPickedKey(key);
    setFTopic(item?.title ?? r?.titles?.[0] ?? "");
    setFAngle(item?.angleLabel ?? r?.angle_label ?? "");
    setFExtra(r?.content ?? "");
    setFReview(true);
    setTask(null);
    setProducePhase("form");
  };

  // 就地启动流水线（带 review 透传；抖音线默认进待审核）
  const startInlineProduce = async (payload?: {
    topic?: string;
    angle?: string;
    extra?: string;
    review?: boolean;
  }) => {
    const topic = (payload?.topic ?? fTopic).trim();
    const angle = payload?.angle ?? fAngle;
    const extra = payload?.extra ?? fExtra;
    const review = payload?.review ?? fReview;
    if (!topic) {
      toast("请填写选题标题", "warning");
      return;
    }
    setProducing(true);
    try {
      const res = await api.startPipeline({
        topic,
        angle,
        extra,
        platform: fPlatform,
        review,
      });
      setTask({
        task_id: res.task_id,
        issue: res.issue,
        topic,
        angle,
        platform: fPlatform,
        status: "pending",
        logs: [],
        returncode: null,
        error: null,
        created_at: "",
        finished_at: null,
      });
      setAutoScroll(true);
      setProducePhase("running");
      toast(`已启动第 ${res.issue} 期流水线`, "success");
    } catch (e) {
      toast(friendlyMessage(e, "启动流水线失败"), "error");
    } finally {
      setProducing(false);
    }
  };

  // 就地轮询流水线状态（每 1.5s），对齐热点线 /topic 轮询逻辑
  const pollInline = React.useCallback(async (taskId: string) => {
    try {
      const st = await api.pipelineStatus(taskId);
      setTask(st);
      if (st.status === "success" || st.status === "failed") {
        setProducePhase(st.status === "success" ? "done" : "form");
        return false;
      }
      return true;
    } catch {
      return false;
    }
  }, []);

  React.useEffect(() => {
    if (producePhase !== "running" || !task) return;
    let active = true;
    const timer = setInterval(async () => {
      if (!active) return;
      const cont = await pollInline(task.task_id);
      if (!cont) {
        active = false;
        clearInterval(timer);
      }
    }, 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [producePhase, task, pollInline]);

  // 日志自动滚动到底（用户手动上滚时暂停）
  React.useEffect(() => {
    if (autoScroll) logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [task?.logs, autoScroll]);

  const handleCopy = async () => {
    if (!current || !currentTitle) return;
    setCopying(true);
    const text = `${currentTitle}\n\n${current.content}`;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        toast("文案已复制（含标题 + 公众号正文）", "success");
      } else {
        toast("当前环境不支持自动复制，请手动选择复制", "warning");
      }
    } catch {
      toast("复制失败，请手动选择复制", "error");
    } finally {
      setCopying(false);
    }
  };

  const handleLibProduce = (item: TopicLibraryItem) => {
    queueDraft.set({
      topic: item.title,
      angle: item.category === "其他" ? "" : item.category,
      extra: item.content,
      topic_id: item.id,
    });
    setLibOpen(false);
    toast("正在自动开始生产…", "info");
    router.push("/queue");
  };

  return (
    <div className="space-y-5">
      <div className={embedded ? "flex justify-end" : "flex items-center justify-between"}>
        {!embedded && <h2 className="text-lg font-semibold text-ink">即时拆解</h2>}
        <Button variant="outline" onClick={() => setLibOpen(true)}>
          <Library className="mr-1.5 h-4 w-4" />
          选题库（{libCount}）
        </Button>
      </div>

      <InputSection
        loading={loading}
        defaultTab="text"
        onSubmit={handleSubmit}
        onFetch={async (u) => {
          try {
            return await api.dissectFetch(u);
          } catch (e) {
            throw new Error(friendlyMessage(e, "抓取失败，请检查链接或改用手动粘贴"));
          }
        }}
      />

      {loading && (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border px-6 py-16 text-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm font-medium text-ink">正在拆素材 + 并行写 3 篇…</p>
          <p className="max-w-md text-xs leading-relaxed text-ink-2">
            先把原文里的案例、数字、金句全部抠出来，再按「踩坑经历 / 干货总结 /
            认知升级」三个角度同时开写，通常 60–150 秒。
          </p>
        </div>
      )}

      {!loading && error && <ErrorState message={error} title="拆解失败" />}

      {!loading && !error && !result && (
        <EmptyState
          icon={Sparkles}
          title="还没有拆解结果"
          description="在上方粘贴抖音视频文案（或链接）。填链接会先抓取、给你预览确认，再开始拆解。手动粘贴完整口播稿，抠出来的素材最多，文章质量最高。"
        />
      )}

      {!loading && !error && result && (
        <>
          {result.warnings && result.warnings.length > 0 && (
            <Alert variant="warning">
              <AlertDescription>
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <ul className="space-y-1">
                    {result.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              </AlertDescription>
            </Alert>
          )}

          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-2">
            <Badge variant="muted">
              来源：
              {result.source.origin === "transcribe"
                ? "视频转写"
                : result.source.origin === "url"
                ? "抖音链接"
                : "手动粘贴"}
            </Badge>
            {result.source.complete === false && (
              <Badge variant="warning">内容可能不完整</Badge>
            )}
            {result.source.author && <span>· 作者 {result.source.author}</span>}
            {result.source.create_time && <span>· 发布 {result.source.create_time}</span>}
            <span>· 模型 {result.model}</span>
            <span>· 耗时 {result.elapsed_sec}s</span>
            <span>· 产出 {rewrites.length} 篇</span>
            {result.source.note && <span>· {result.source.note}</span>}
            <Button
              variant="outline"
              size="sm"
              className="ml-auto"
              onClick={handleRedissect}
              disabled={loading || !lastInput}
              title="用同样的输入，重新拆一次并重写三篇"
            >
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              重新拆解
            </Button>
          </div>

          <Tabs defaultValue="articles" value={tab} onValueChange={setTab}>
            <TabsList className="flex-wrap">
              <TabsTrigger value="articles">
                <FileText className="mr-1.5 h-3.5 w-3.5" />
                公众号文章（{rewrites.length} 篇）
              </TabsTrigger>
              <TabsTrigger value="dissect">
                <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                拆解分析
              </TabsTrigger>
            </TabsList>

            <TabsContent value="articles">
              <div className="space-y-4">
                <TitleSwitcher
                  items={switcherItems}
                  activeKey={currentKey}
                  onSelect={setActiveAngle}
                />
                {current && (
                  <RewritePreview
                    key={currentKey}
                    rewrite={current}
                    selectedTitle={currentTitle}
                    onSelectTitle={(t) =>
                      setTitles((prev) => ({ ...prev, [currentKey]: t }))
                    }
                    onRegenerate={handleRegenerate}
                    regenerating={regenKey === currentKey}
                    versionCount={versions[currentKey]?.length ?? 1}
                    activeVersion={activeVer[currentKey] ?? 0}
                    onSelectVersion={handleSelectVersion}
                  />
                )}
              </div>
            </TabsContent>

            <TabsContent value="dissect">
              <div className="space-y-4">
                {result.dissect.materials && (
                  <MaterialChecklist materials={result.dissect.materials} />
                )}
                <DissectAnalysis result={result.dissect} />
              </div>
            </TabsContent>
          </Tabs>

          {/* 抖音线后半衔接：候选选题 → 选择并生产 → 就地表单/日志（对齐热点线 /topic 体验） */}
          {(producePhase === "idle" || producePhase === "form") && (
            <Card className="mt-5 animate-fade-in">
              <CardHeader>
                <CardTitle className="text-base">候选选题（来自抖音拆解 · {rewrites.length} 篇改写）</CardTitle>
                <CardDescription>
                  挑一篇直接生产，默认进入「待审核」（审后再发）；也可先存选题库再批量生产。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-3">
                  {switcherItems.map((it) => {
                    const Icon = it.icon;
                    return (
                      <div
                        key={it.key}
                        className={`rounded-lg border p-3 transition ${
                          pickedKey === it.key
                            ? "border-primary bg-primary/5"
                            : "border-border"
                        }`}
                      >
                        <div className="flex items-center gap-2 text-xs text-ink-2">
                          <Icon className="h-4 w-4" />
                          {it.angleLabel}
                        </div>
                        <div className="mt-1.5 line-clamp-2 text-sm font-medium text-ink">
                          {it.title}
                        </div>
                        {it.score != null && (
                          <Badge variant="muted" className="mt-2">
                            质量 {it.score}
                          </Badge>
                        )}
                        <Button
                          size="sm"
                          className="mt-3 w-full"
                          disabled={producing}
                          onClick={() => pickProduce(it.key)}
                        >
                          选择并生产
                        </Button>
                      </div>
                    );
                  })}
                </div>

                {producePhase === "form" && (
                  <div className="rounded-xl border border-border p-4">
                    <div className="mb-3 text-sm font-medium text-ink">
                      生产参数（第 {task?.issue ?? "—"} 期将进入「待审核」）
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1">
                        <Label>选题标题 *</Label>
                        <Input
                          value={fTopic}
                          onChange={(e) => setFTopic(e.target.value)}
                          placeholder="选题标题"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label>切入角度</Label>
                        <Input
                          value={fAngle}
                          onChange={(e) => setFAngle(e.target.value)}
                          placeholder="切入角度"
                        />
                      </div>
                    </div>
                    <div className="mt-3 space-y-1">
                      <Label>补充要求 / 备注</Label>
                      <Textarea
                        value={fExtra}
                        onChange={(e) => setFExtra(e.target.value)}
                        rows={3}
                        placeholder="补充要求 / 备注（可选）"
                      />
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-4">
                      <label className="flex items-center gap-2 text-sm text-ink">
                        <input
                          type="checkbox"
                          checked={fReview}
                          onChange={(e) => setFReview(e.target.checked)}
                          className="h-4 w-4"
                        />
                        先存为待审核（推荐：审后再发）
                      </label>
                      <span className="text-xs text-ink-2">平台：微信（默认）</span>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <Button onClick={() => startInlineProduce()} disabled={producing}>
                        {producing ? (
                          <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                        ) : (
                          <Rocket className="mr-1.5 h-4 w-4" />
                        )}
                        启动流水线
                      </Button>
                      <Button variant="ghost" onClick={() => setProducePhase("idle")}>
                        取消
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {(producePhase === "running" || producePhase === "done") && task && (
            <Card className="mt-5 animate-fade-in">
              <CardHeader>
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-base">生产日志 · 第 {task.issue} 期</CardTitle>
                  <Badge
                    variant={
                      task.status === "failed"
                        ? "destructive"
                        : task.status === "success"
                          ? "success"
                          : "muted"
                    }
                  >
                    {task.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div
                  ref={logBoxRef}
                  onScroll={(e) => {
                    const el = e.currentTarget;
                    if (el.scrollHeight - el.scrollTop - el.clientHeight > 40) {
                      setAutoScroll(false);
                    } else {
                      setAutoScroll(true);
                    }
                  }}
                  className="max-h-80 overflow-auto rounded-lg border border-border bg-black/40 p-3 font-mono text-xs leading-relaxed"
                >
                  {task.logs && task.logs.length > 0 ? (
                    task.logs.map((line, i) => (
                      <div
                        key={i}
                        className={
                          /\[error\]|Traceback|错误/.test(line)
                            ? "whitespace-pre-wrap text-destructive"
                            : /\[warn\]/.test(line)
                              ? "whitespace-pre-wrap text-amber-300/90"
                              : "whitespace-pre-wrap text-emerald-200/90"
                        }
                      >
                        {line}
                      </div>
                    ))
                  ) : (
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      等待日志输出…
                    </div>
                  )}
                  <div ref={logEndRef} />
                </div>

                {task.error && (
                  <Alert variant="destructive" className="mt-3">
                    <AlertTitle>执行错误</AlertTitle>
                    <AlertDescription>{task.error}</AlertDescription>
                  </Alert>
                )}

                {producePhase === "done" && task.status === "success" && (
                  <div className="mt-4 rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-4">
                    <div className="mb-3 flex flex-wrap items-center gap-2">
                      <Badge variant="success">
                        <CheckCircle2 className="mr-1 h-3 w-3" />
                        已进入待审核 · 第 {task.issue} 期
                      </Badge>
                    </div>
                    <div className="flex gap-2">
                      <Button onClick={() => router.push("/tasks?review=1")}>
                        <CheckCircle2 className="mr-1.5 h-4 w-4" />
                        去审核发布
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setProducePhase("idle");
                          setTask(null);
                        }}
                      >
                        返回
                      </Button>
                    </div>
                  </div>
                )}

                {producePhase === "done" && task.status === "failed" && (
                  <div className="mt-4 flex gap-2">
                    <Button variant="outline" onClick={() => setProducePhase("form")}>
                      返回修改
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          <div className="sticky bottom-4 z-10 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-subtle bg-surface/95 p-3 shadow-lg backdrop-blur">
            <div className="text-xs text-ink-2">
              当前操作：
              <span className="ml-1 font-medium text-ink">
                {current?.angle_label ?? metaOf(currentKey).label}
              </span>
              {currentTitle && (
                <span className="ml-2 hidden max-w-[280px] truncate align-bottom md:inline-block">
                  《{currentTitle}》
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {rewrites.length > 1 && (
                <Button variant="ghost" onClick={handleSaveAll} disabled={saving}>
                  <BookmarkPlus className="mr-1.5 h-4 w-4" />
                  {rewrites.length} 篇全存
                </Button>
              )}
              <Button variant="outline" onClick={handleSaveTopic} disabled={saving}>
                {saving ? (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                ) : (
                  <BookmarkPlus className="mr-1.5 h-4 w-4" />
                )}
                加入选题库
              </Button>
              <Button variant="outline" onClick={handleCopy} disabled={copying}>
                <Copy className="mr-1.5 h-4 w-4" />
                复制文案
              </Button>
              <Button onClick={handleProduce} disabled={producePhase === "running" || producing}>
                <Rocket className="mr-1.5 h-4 w-4" />
                直接生产
              </Button>
            </div>
          </div>
        </>
      )}

      <TopicLibraryDialog
        open={libOpen}
        onClose={() => setLibOpen(false)}
        onCountChange={setLibCount}
        onProduce={handleLibProduce}
        onGoTopicPage={() => {
          setLibOpen(false);
          router.push("/topic");
        }}
      />
    </div>
  );
}
