"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Sparkles,
  Loader2,
  Play,
  ArrowRight,
  CheckCircle2,
  XCircle,
  Clock,
  Terminal,
  Flame,
  ExternalLink,
  FileText,
  BarChart3,
  ListPlus,
  X,
  ListChecks,
  Image as ImageIcon,
  FolderOpen,
  RotateCw,
} from "lucide-react";
import { api, friendlyMessage } from "@/lib/api";
import { topicSeeds } from "@/lib/seed";
import type {
  HistoryDetail,
  HotspotItem,
  PipelineStartResult,
  PipelineStatus,
  TopicCandidate,
  TopicSeed,
} from "@/lib/types";
import { useToast } from "@/components/ui/toast";
import { PageShell, PageHeader } from "@/components/layout/PageShell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button, LinkButton } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label, FieldError } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { EmptyState } from "@/components/ui/empty-state";
import { Progress } from "@/components/ui/progress";
import { Steps, type StepDef } from "@/components/ui/steps";

type Phase = "idle" | "generating" | "ready" | "producing" | "running" | "done";

/** 页面整体流程指示 */
const FLOW_STEPS: StepDef[] = [
  { key: "material", label: "准备素材" },
  { key: "topic", label: "生成选题" },
  { key: "form", label: "确认参数" },
  { key: "run", label: "生产执行" },
  { key: "done", label: "完成" },
];

/** 流水线内部阶段：靠日志关键字推断进度 */
const PIPELINE_STAGES: { key: string; label: string; match: RegExp }[] = [
  { key: "init", label: "初始化", match: /^===\s*第\d+期/ },
  { key: "article", label: "写文章", match: /\[OK\]\s*文章完成/ },
  { key: "cover", label: "生成封面", match: /\[OK\]\s*封面完成/ },
  { key: "assemble", label: "装配归档", match: /\[OK\]\s*已装配到/ },
  { key: "publish", label: "推送草稿", match: /\[OK\]\s*推送/ },
];

export default function TopicPage() {
  const { toast } = useToast();
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("idle");
  const [hotspots, setHotspots] = useState<HotspotItem[]>([]);
  const [seeds, setSeeds] = useState<TopicSeed[]>([]);
  const [topics, setTopics] = useState<TopicCandidate[]>([]);
  const [picked, setPicked] = useState<TopicCandidate | null>(null);
  const [enqueuing, setEnqueuing] = useState<string | null>(null);
  const [genError, setGenError] = useState<string | null>(null);

  // 生产表单
  const [formTopic, setFormTopic] = useState("");
  const [formAngle, setFormAngle] = useState("");
  const [formExtra, setFormExtra] = useState("");
  const [formPlatform, setFormPlatform] = useState("wechat");
  const [formErrors, setFormErrors] = useState<{
    topic?: string;
    angle?: string;
  }>({});

  // 流水线状态
  const [task, setTask] = useState<PipelineStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const logBoxRef = useRef<HTMLDivElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  // 完成后的结果摘要
  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [showArticle, setShowArticle] = useState(false);

  // 读取热点素材页带入的选中素材 + 数据分析/历史任务带来的选题参考
  useEffect(() => {
    const raw = sessionStorage.getItem("selected_hotspots");
    if (raw) {
      try {
        setHotspots(JSON.parse(raw) as HotspotItem[]);
      } catch {
        /* ignore */
      }
    }
    setSeeds(topicSeeds.all());
    setPhase("ready");
  }, []);

  const removeSeed = (topic: string) => setSeeds(topicSeeds.remove(topic));

  const clearSeeds = () => {
    topicSeeds.clear();
    setSeeds([]);
    toast("已清空选题参考", "success");
  };

  const clearHotspots = () => {
    sessionStorage.removeItem("selected_hotspots");
    setHotspots([]);
    toast("已清空带入的热点素材", "success");
  };

  const handleGenerate = async () => {
    setPhase("generating");
    setTopics([]);
    setPicked(null);
    setGenError(null);
    try {
      const res = await api.generateTopics({
        hotspots: hotspots.map((h) => ({
          id: h.id,
          title: h.title,
          summary: h.summary,
          source: h.source,
          url: h.url,
        })),
        data_suggestions: seeds.map((s) => ({
          name: s.topic,
          angle: s.angle ?? "",
          evidence: s.note ?? "",
          from: s.from,
        })),
        data_insight:
          seeds.length > 0
            ? `已有 ${seeds.length} 条来自数据复盘/往期产出的选题参考，请优先围绕这些方向展开。`
            : null,
      });
      setTopics(res.topics);
      setPhase("ready");
      toast(`生成了 ${res.topics.length} 个候选选题`, "success");
    } catch (e) {
      const msg = friendlyMessage(e, "生成选题失败");
      setGenError(msg);
      toast(msg, "error");
      setPhase("ready");
    }
  };

  /** 把候选选题直接排进任务队列，不占用当前流水线。 */
  const addToQueue = async (t: TopicCandidate) => {
    setEnqueuing(t.topic);
    try {
      await api.addQueue({
        topic: t.topic,
        angle: t.angle,
        extra: t.structure ? `建议结构：${t.structure}` : "",
        source: "topic",
      });
      toast("已加入任务队列", {
        type: "success",
        action: { label: "去队列", onClick: () => router.push("/queue") },
      });
    } catch (e) {
      toast(friendlyMessage(e, "加入队列失败"), "error");
    } finally {
      setEnqueuing(null);
    }
  };

  const pickTopic = (t: TopicCandidate) => {
    setPicked(t);
    setFormTopic(t.topic);
    setFormAngle(t.angle);
    setFormExtra("");
    setFormErrors({});
    setPhase("producing");
  };

  const validate = () => {
    const errs: { topic?: string; angle?: string } = {};
    if (!formTopic.trim()) errs.topic = "选题不能为空";
    else if (formTopic.trim().length < 4) errs.topic = "选题太短了，至少 4 个字";
    if (!formAngle.trim()) errs.angle = "切入角度不能为空";
    setFormErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const startPipeline = async () => {
    if (!validate()) {
      toast("请先补全带 * 的必填项", "warning");
      return;
    }
    setStarting(true);
    setDetail(null);
    setDetailError(null);
    setShowArticle(false);
    try {
      const refs = hotspots.map((h) => h.url).filter(Boolean).join(",");
      const res: PipelineStartResult = await api.startPipeline({
        topic: formTopic.trim(),
        angle: formAngle,
        extra: formExtra,
        references: refs,
        platform: formPlatform,
      });
      setTask({
        task_id: res.task_id,
        issue: res.issue,
        topic: formTopic,
        angle: formAngle,
        platform: formPlatform,
        status: "pending",
        logs: [],
        returncode: null,
        error: null,
        created_at: "",
        finished_at: null,
      });
      setAutoScroll(true);
      setPhase("running");
      toast(`已启动第 ${res.issue} 期流水线`, "success");
    } catch (e) {
      toast(friendlyMessage(e, "启动流水线失败"), "error");
    } finally {
      setStarting(false);
    }
  };

  /** 流水线完成后拉取产出详情，展示标题/正文预览/封面 */
  const loadDetail = useCallback(
    async (issue: number) => {
      setDetailLoading(true);
      setDetailError(null);
      try {
        setDetail(await api.taskDetail(issue));
      } catch (e) {
        setDetail(null);
        setDetailError(friendlyMessage(e, "读取产出详情失败"));
      } finally {
        setDetailLoading(false);
      }
    },
    []
  );

  // 轮询流水线状态
  const poll = useCallback(
    async (taskId: string) => {
      try {
        const st = await api.pipelineStatus(taskId);
        setTask(st);
        if (st.status === "success" || st.status === "failed") {
          setPhase("done");
          if (st.status === "success") {
            toast("流水线执行成功", {
              type: "success",
              action: {
                label: "看产出",
                onClick: () => router.push(`/tasks?issue=${st.issue}`),
              },
            });
            void loadDetail(st.issue);
          } else {
            toast("流水线执行失败，请查看日志", "error");
          }
          return false; // 停止轮询
        }
        return true;
      } catch {
        return false;
      }
    },
    [toast, router, loadDetail]
  );

  useEffect(() => {
    if (phase !== "running" || !task) return;
    let active = true;
    const timer = setInterval(async () => {
      if (!active) return;
      const cont = await poll(task.task_id);
      if (!cont) {
        active = false;
        clearInterval(timer);
      }
    }, 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [phase, task, poll]);

  // 日志自动滚动到底（用户手动上滚时暂停）
  useEffect(() => {
    if (autoScroll) logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [task?.logs, autoScroll]);

  const onLogScroll = () => {
    const el = logBoxRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    setAutoScroll(atBottom);
  };

  // ---------- 派生状态 ----------

  /** 顶部流程当前步骤 */
  const flowStep = useMemo(() => {
    if (phase === "running") return 3;
    if (phase === "done") return task?.status === "success" ? 5 : 3;
    if (phase === "producing") return 2;
    if (topics.length > 0) return 2;
    if (phase === "generating") return 1;
    return hotspots.length > 0 || seeds.length > 0 ? 1 : 0;
  }, [phase, task?.status, topics.length, hotspots.length, seeds.length]);

  /** 流水线内部进度 */
  const stageInfo = useMemo(() => {
    const logs = task?.logs ?? [];
    let idx = 0;
    PIPELINE_STAGES.forEach((s, i) => {
      if (logs.some((l) => s.match.test(l))) idx = i + 1;
    });
    const total = PIPELINE_STAGES.length;
    const pct =
      task?.status === "success"
        ? 100
        : Math.round((Math.min(idx, total) / total) * 100);
    return { idx: Math.min(idx, total), total, pct };
  }, [task?.logs, task?.status]);

  const statusBadge = (status: string) => {
    if (status === "running")
      return (
        <Badge variant="warning">
          <Clock className="mr-1 h-3 w-3" /> 进行中
        </Badge>
      );
    if (status === "success")
      return (
        <Badge variant="success">
          <CheckCircle2 className="mr-1 h-3 w-3" /> 成功
        </Badge>
      );
    if (status === "failed")
      return (
        <Badge variant="destructive">
          <XCircle className="mr-1 h-3 w-3" /> 失败
        </Badge>
      );
    return (
      <Badge variant="muted">
        <Clock className="mr-1 h-3 w-3" /> 等待中
      </Badge>
    );
  };

  const handleOpenDir = async () => {
    if (!task) return;
    try {
      await api.openTaskDir(task.issue);
      toast("已在文件管理器中打开", "success");
    } catch (e) {
      toast(friendlyMessage(e, "打开目录失败"), "error");
    }
  };

  const resetForNext = () => {
    setPhase("ready");
    setTask(null);
    setPicked(null);
    setDetail(null);
    setDetailError(null);
    setShowArticle(false);
  };

  return (
    <PageShell width="md">
      <PageHeader
        title="选题与生产"
        description="基于热点素材生成候选选题，选定后一键启动生产流水线并实时查看日志。"
        actions={
          <>
            <LinkButton href="/hotspot" variant="ghost" size="sm">
              <Flame className="h-4 w-4" />
              热点素材
            </LinkButton>
            <LinkButton href="/queue" variant="outline" size="sm">
              <ListChecks className="h-4 w-4" />
              任务队列
            </LinkButton>
          </>
        }
      />

      {/* 流程指示器 */}
      <Card className="mt-5">
        <CardContent className="p-4">
          <Steps
            steps={FLOW_STEPS}
            current={flowStep}
            running={phase === "generating" || phase === "running"}
            failed={phase === "done" && task?.status === "failed"}
          />
        </CardContent>
      </Card>

      {/* 数据分析 / 历史任务带来的选题参考 */}
      {seeds.length > 0 && (
        <Card className="mt-5 animate-fade-in border-sky-500/40">
          <CardContent className="p-4">
            <div className="flex flex-wrap items-center gap-2">
              <BarChart3 className="h-4 w-4 text-sky-400" />
              <span className="text-sm font-medium">选题参考</span>
              <Badge variant="secondary">{seeds.length} 条</Badge>
              <Button
                variant="ghost"
                size="xs"
                className="ml-auto"
                onClick={clearSeeds}
              >
                清空
              </Button>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              来自数据分析和历史任务，点「生成选题」时会一起作为方向依据。
            </p>
            <div className="mt-3 space-y-1.5">
              {seeds.map((s) => (
                <div
                  key={s.topic}
                  className="flex items-start gap-2 rounded-lg border border-border px-2.5 py-1.5 transition-colors hover:border-muted-foreground/40"
                >
                  <Badge variant="muted" className="mt-0.5 shrink-0">
                    {s.from === "analytics"
                      ? "数据"
                      : s.from === "tasks"
                        ? "往期"
                        : "热点"}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm">{s.topic}</div>
                    {s.note && (
                      <div className="truncate text-[11px] text-muted-foreground">
                        {s.note}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => removeSeed(s.topic)}
                    className="mt-0.5 shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                    title="移除"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 素材来源提示 */}
      <Card className="mt-5">
        <CardContent className="flex flex-wrap items-center gap-2 p-4 text-sm">
          <Flame className="h-4 w-4 shrink-0 text-muted-foreground" />
          {hotspots.length > 0 ? (
            <>
              <span className="text-muted-foreground">
                已带入 <b className="text-foreground">{hotspots.length}</b>{" "}
                条热点素材：
              </span>
              {hotspots.slice(0, 4).map((h, i) => (
                <Badge key={i} variant="outline">
                  {h.source}
                </Badge>
              ))}
              {hotspots.length > 4 && (
                <Badge variant="muted">+{hotspots.length - 4}</Badge>
              )}
              <Button variant="ghost" size="xs" onClick={clearHotspots}>
                <X className="h-3 w-3" />
                清空
              </Button>
            </>
          ) : (
            <span className="text-muted-foreground">
              未带入热点素材（将仅按账号定位生成选题）。
              <Link href="/hotspot" className="ml-1 text-sky-400 hover:underline">
                去热点素材页挑几条
              </Link>
            </span>
          )}
          <Button
            variant="outline"
            size="sm"
            className="ml-auto w-full sm:w-auto"
            onClick={handleGenerate}
            disabled={phase === "generating"}
          >
            {phase === "generating" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            {phase === "generating" ? "生成中…" : "生成选题"}
          </Button>
        </CardContent>
      </Card>

      {genError && phase !== "generating" && (
        <div className="mt-4">
          <Alert variant="destructive">
            <AlertTitle>生成选题失败</AlertTitle>
            <AlertDescription className="flex flex-wrap items-center gap-2">
              <span>{genError}</span>
              <Button
                size="xs"
                variant="outline"
                onClick={handleGenerate}
                className="border-destructive/40 text-destructive hover:bg-destructive/10"
              >
                <RotateCw className="h-3 w-3" />
                重试
              </Button>
            </AlertDescription>
          </Alert>
        </div>
      )}

      {phase === "generating" && (
        <div className="mt-5 space-y-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在结合热点与数据参考生成候选选题…
          </div>
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      )}

      {/* 选题卡片 */}
      {topics.length > 0 && phase !== "generating" && (
        <div className="mt-6 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">候选选题</h2>
            <Badge variant="secondary">{topics.length} 个</Badge>
            <Button
              variant="ghost"
              size="xs"
              className="ml-auto"
              onClick={handleGenerate}
            >
              <RotateCw className="h-3 w-3" />
              换一批
            </Button>
          </div>
          {topics.map((t, i) => (
            <Card
              key={i}
              className={
                picked === t
                  ? "animate-fade-in border-emerald-500/60"
                  : "animate-fade-in transition-colors hover:border-muted-foreground/30"
              }
            >
              <CardHeader className="pb-2">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <CardTitle className="text-base">{t.topic}</CardTitle>
                  <div className="flex shrink-0 gap-1.5">
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={enqueuing === t.topic}
                      onClick={() => addToQueue(t)}
                      title="不占用当前流水线，稍后在任务队列里批量执行"
                    >
                      {enqueuing === t.topic ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <ListPlus className="h-4 w-4" />
                      )}
                      加入队列
                    </Button>
                    <Button
                      size="sm"
                      variant={picked === t ? "secondary" : "default"}
                      onClick={() => pickTopic(t)}
                    >
                      选择并生产
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
                <CardDescription>{t.angle}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div>
                  <span className="text-muted-foreground">建议结构：</span>
                  {t.structure}
                </div>
                {t.background && (
                  <div className="rounded-md bg-muted/50 px-2.5 py-1.5 text-xs text-muted-foreground">
                    {t.background}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* 生产表单 */}
      {phase === "producing" && picked && (
        <Card className="mt-6 animate-fade-in">
          <CardHeader>
            <CardTitle className="text-base">生产参数</CardTitle>
            <CardDescription>确认或调整内容，启动流水线。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="f-topic" required>
                选题
              </Label>
              <Input
                id="f-topic"
                value={formTopic}
                error={!!formErrors.topic}
                onChange={(e) => {
                  setFormTopic(e.target.value);
                  if (formErrors.topic)
                    setFormErrors((p) => ({ ...p, topic: undefined }));
                }}
              />
              <FieldError>{formErrors.topic}</FieldError>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="f-angle" required>
                切入角度
              </Label>
              <Textarea
                id="f-angle"
                value={formAngle}
                rows={2}
                error={!!formErrors.angle}
                onChange={(e) => {
                  setFormAngle(e.target.value);
                  if (formErrors.angle)
                    setFormErrors((p) => ({ ...p, angle: undefined }));
                }}
              />
              <FieldError>{formErrors.angle}</FieldError>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="f-extra">补充要求（可选）</Label>
              <Textarea
                id="f-extra"
                value={formExtra}
                onChange={(e) => setFormExtra(e.target.value)}
                placeholder="例如：开头加一个真实踩坑小故事；结尾留一个互动问题"
                rows={2}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="f-platform">发布平台</Label>
              <Select
                id="f-platform"
                value={formPlatform}
                onChange={(e) => setFormPlatform(e.target.value)}
              >
                <option value="wechat">微信公众号</option>
                <option value="other">其他</option>
              </Select>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button
                onClick={startPipeline}
                disabled={starting}
                className="w-full sm:w-auto"
              >
                {starting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                {starting ? "启动中…" : "启动流水线"}
              </Button>
              <Button
                variant="ghost"
                onClick={() => setPhase("ready")}
                className="w-full sm:w-auto"
              >
                返回选题
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 实时日志 */}
      {(phase === "running" || phase === "done") && (
        <Card className="mt-6 animate-fade-in">
          <CardHeader className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Terminal className="h-4 w-4" />
                <CardTitle className="text-base">
                  生产日志 · 第 {task?.issue} 期
                </CardTitle>
              </div>
              {task && statusBadge(task.status)}
            </div>
            {/* 流水线阶段进度 */}
            <div className="space-y-2">
              <Steps
                steps={PIPELINE_STAGES.map((s) => ({
                  key: s.key,
                  label: s.label,
                }))}
                current={stageInfo.idx}
                running={phase === "running"}
                failed={task?.status === "failed"}
              />
              <div className="flex items-center gap-3">
                <Progress
                  value={phase === "running" && stageInfo.idx === 0 ? null : stageInfo.pct}
                  indicatorClassName={
                    task?.status === "failed"
                      ? "bg-destructive"
                      : task?.status === "success"
                        ? "bg-emerald-500"
                        : undefined
                  }
                />
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                  {stageInfo.pct}%
                </span>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div
              ref={logBoxRef}
              onScroll={onLogScroll}
              className="max-h-80 overflow-auto rounded-lg border border-border bg-black/40 p-3 font-mono text-xs leading-relaxed"
            >
              {task?.logs && task.logs.length > 0 ? (
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
            <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted-foreground">
              <span>共 {task?.logs?.length ?? 0} 行 · 每 1.5 秒自动刷新</span>
              {!autoScroll && (
                <button
                  type="button"
                  className="text-sky-400 hover:underline"
                  onClick={() => {
                    setAutoScroll(true);
                    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
                  }}
                >
                  回到底部
                </button>
              )}
            </div>

            {task?.error && (
              <Alert variant="destructive" className="mt-3">
                <AlertTitle>执行错误</AlertTitle>
                <AlertDescription>{task.error}</AlertDescription>
              </Alert>
            )}

            {/* 完成后的结果摘要 */}
            {phase === "done" && (
              <div className="mt-4 space-y-4">
                {task?.status === "success" ? (
                  <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="success">
                        <CheckCircle2 className="mr-1 h-3 w-3" />
                        已完成第 {task.issue} 期
                      </Badge>
                      {detail?.draft_status && (
                        <Badge variant="muted">{detail.draft_status}</Badge>
                      )}
                      {detailLoading && (
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          读取产出…
                        </span>
                      )}
                    </div>

                    {detailError ? (
                      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-destructive">
                        <span>{detailError}</span>
                        <Button
                          size="xs"
                          variant="outline"
                          onClick={() => loadDetail(task.issue)}
                        >
                          <RotateCw className="h-3 w-3" />
                          重试
                        </Button>
                      </div>
                    ) : detailLoading && !detail ? (
                      <div className="mt-3 space-y-2">
                        <Skeleton className="h-5 w-2/3" />
                        <Skeleton className="h-16 w-full" />
                      </div>
                    ) : detail ? (
                      <div className="mt-3 space-y-3">
                        <div>
                          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                            成稿标题
                          </div>
                          <p className="mt-0.5 text-sm font-medium">
                            {detail.title || "（无标题）"}
                          </p>
                        </div>

                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[auto,1fr]">
                          {detail.cover_base64 && (
                            <div>
                              <div className="mb-1 flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                                <ImageIcon className="h-3 w-3" />
                                封面
                              </div>
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={`data:image/png;base64,${detail.cover_base64}`}
                                alt={`第 ${detail.issue} 期封面`}
                                className="h-28 w-auto rounded-lg border border-border object-cover"
                              />
                            </div>
                          )}
                          <div className="min-w-0">
                            <div className="mb-1 flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                              <FileText className="h-3 w-3" />
                              文章预览
                            </div>
                            {detail.article_preview ? (
                              <>
                                <div
                                  className={
                                    showArticle
                                      ? "max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-background/60 p-2.5 text-xs leading-relaxed"
                                      : "line-clamp-3 whitespace-pre-wrap rounded-lg border border-border bg-background/60 p-2.5 text-xs leading-relaxed"
                                  }
                                >
                                  {detail.article_preview}
                                </div>
                                <button
                                  type="button"
                                  onClick={() => setShowArticle((v) => !v)}
                                  className="mt-1 text-[11px] text-sky-400 hover:underline"
                                >
                                  {showArticle ? "收起" : "展开全文预览"}
                                </button>
                              </>
                            ) : (
                              <p className="text-xs text-muted-foreground">
                                未找到正文文件
                              </p>
                            )}
                          </div>
                        </div>

                        {detail.dir_path && (
                          <p className="break-all text-[11px] text-muted-foreground">
                            产出目录：{detail.dir_path}
                          </p>
                        )}
                      </div>
                    ) : null}

                    <div className="mt-4 flex flex-wrap gap-2">
                      <LinkButton
                        href={`/tasks?issue=${task.issue}`}
                        size="sm"
                        variant="outline"
                      >
                        <FileText className="h-4 w-4" />
                        查看历史任务详情
                      </LinkButton>
                      <Button size="sm" variant="ghost" onClick={handleOpenDir}>
                        <FolderOpen className="h-4 w-4" />
                        打开产出目录
                      </Button>
                      <Button size="sm" variant="ghost" onClick={resetForNext}>
                        <Sparkles className="h-4 w-4" />
                        再选一个选题
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4">
                    <Badge variant="destructive">
                      <XCircle className="mr-1 h-3 w-3" /> 流水线失败
                    </Badge>
                    <p className="mt-2 text-xs text-muted-foreground">
                      可以调整补充要求后重试，或到「系统配置」检查密钥是否正确。
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setPhase("producing");
                          setTask(null);
                        }}
                      >
                        <RotateCw className="h-4 w-4" />
                        调整参数重试
                      </Button>
                      <LinkButton href="/config" size="sm" variant="ghost">
                        去系统配置
                      </LinkButton>
                      <Button size="sm" variant="ghost" onClick={resetForNext}>
                        再选一个选题
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {hotspots.length > 0 && (
              <div className="mt-3 text-xs text-muted-foreground">
                参考素材：
                {hotspots.map((h, i) => (
                  <span key={i} className="ml-1 inline-flex items-center gap-0.5">
                    <a
                      href={h.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sky-400 hover:underline"
                    >
                      {h.source}
                      <ExternalLink className="ml-0.5 inline h-3 w-3" />
                    </a>
                    {i < hotspots.length - 1 ? "、" : ""}
                  </span>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {phase === "ready" && topics.length === 0 && !genError && (
        <EmptyState
          className="mt-8"
          icon={Sparkles}
          title="还没有候选选题"
          description={
            hotspots.length > 0
              ? "已带入热点素材，点上方「生成选题」即可产出 5 个候选方向。"
              : "可以先去热点素材页挑几条，也可以直接点「生成选题」按账号定位生成。"
          }
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button size="sm" onClick={handleGenerate}>
                <Sparkles className="h-3.5 w-3.5" />
                生成选题
              </Button>
              {hotspots.length === 0 && (
                <LinkButton href="/hotspot" size="sm" variant="outline">
                  <Flame className="h-3.5 w-3.5" />
                  去挑热点
                </LinkButton>
              )}
            </div>
          }
        />
      )}
    </PageShell>
  );
}
