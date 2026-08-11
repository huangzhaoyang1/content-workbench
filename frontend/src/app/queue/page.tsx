"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CalendarClock,
  CheckCircle2,
  Clock,
  Layers,
  Loader2,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  SkipForward,
  Trash2,
  XCircle,
} from "lucide-react";
import { api, friendlyMessage } from "@/lib/api";
import { queueDraft } from "@/lib/seed";
import type {
  QueueItem,
  QueueSnapshot,
  ScheduleInput,
  ScheduleJob,
} from "@/lib/types";
import { useToast } from "@/components/ui/toast";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label, FieldError } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/stat-card";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PageShell, PageHeader } from "@/components/layout/PageShell";
import { QueueItemCard } from "@/components/queue/QueueItemCard";
import { ScheduleDialog } from "@/components/queue/ScheduleDialog";

type PendingConfirm =
  | { kind: "clear-all" }
  | { kind: "clear-finished" }
  | { kind: "remove-item"; item: QueueItem }
  | { kind: "delete-job"; job: ScheduleJob }
  | null;

export default function QueuePage() {
  const { toast } = useToast();
  const router = useRouter();

  const [snap, setSnap] = useState<QueueSnapshot | null>(null);
  const [jobs, setJobs] = useState<ScheduleJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [skipping, setSkipping] = useState(false);
  const [adding, setAdding] = useState(false);
  const [savingJob, setSavingJob] = useState(false);
  const [confirmBusy, setConfirmBusy] = useState(false);

  // 手动添加表单
  const [topic, setTopic] = useState("");
  const [angle, setAngle] = useState("");
  const [extra, setExtra] = useState("");
  const [draftTopicId, setDraftTopicId] = useState("");
  const [topicError, setTopicError] = useState("");

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingJob, setEditingJob] = useState<ScheduleJob | null>(null);
  const [pending, setPending] = useState<PendingConfirm>(null);

  const topicRef = useRef<HTMLInputElement>(null);

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setRefreshing(true);
      try {
        const [q, s] = await Promise.all([api.getQueue(), api.listSchedules()]);
        setSnap(q);
        setJobs(s.jobs);
      } catch (e) {
        if (!silent) toast(friendlyMessage(e, "加载失败"), "error");
      } finally {
        setLoading(false);
        if (!silent) setRefreshing(false);
      }
    },
    [toast]
  );

  useEffect(() => {
    const init = async () => {
      await load();
      // 别的页面「加入队列」时可能带了草稿过来：自动入队并立即开始生产
      const d = queueDraft.take();
      if (d) {
        try {
          toast(`正在自动入队并开始生产：${d.topic}`, "info");
          await api.addQueue({
            topic: d.topic,
            angle: d.angle ?? "",
            extra: d.extra ?? "",
            source: "manual",
            topic_id: d.topic_id ?? "",
          });
          const startRes = await api.startQueue();
          if (startRes.started) {
            toast("已自动开始生产", "success");
          } else {
            toast("已加入队列，请手动点「开始执行」", "warning");
          }
          router.push("/tasks");
        } catch (e) {
          toast(friendlyMessage(e, "自动入队失败，请手动操作"), "error");
          setTopic(d.topic);
          setAngle(d.angle ?? "");
          setExtra(d.extra ?? "");
          setDraftTopicId(d.topic_id ?? "");
        }
      }
    };
    void init();
  }, [load]);

  // 队列在跑的时候自动轮询，跑完自动停
  useEffect(() => {
    if (!snap?.is_running) return;
    const timer = setInterval(() => void load(true), 2500);
    return () => clearInterval(timer);
  }, [snap?.is_running, load]);

  const handleAdd = async () => {
    if (!topic.trim()) {
      setTopicError("选题主题不能为空");
      topicRef.current?.focus();
      return;
    }
    setTopicError("");
    setAdding(true);
    try {
      await api.addQueue({
        topic: topic.trim(),
        angle: angle.trim(),
        extra: extra.trim(),
        source: "manual",
        topic_id: draftTopicId || undefined,
      });
      setTopic("");
      setAngle("");
      setExtra("");
      setDraftTopicId("");
      toast("已加入队列", {
        type: "success",
        action: { label: "去队列", onClick: () => router.push("/queue") },
      });
      await load(true);
    } catch (e) {
      toast(friendlyMessage(e, "加入失败"), "error");
    } finally {
      setAdding(false);
    }
  };

  const handleStart = async () => {
    setStarting(true);
    try {
      const res = await api.startQueue();
      if (res.started) toast("队列已开始执行", "success");
      else toast(res.reason ?? "队列没有可执行的任务", "warning");
      await load(true);
    } catch (e) {
      toast(friendlyMessage(e, "启动失败"), "error");
    } finally {
      setStarting(false);
    }
  };

  const handleSkip = async () => {
    setSkipping(true);
    try {
      const res = await api.skipQueue();
      if (res.ok) toast("已跳过当前任务", "success");
      else toast(res.reason ?? "跳过失败", "warning");
      await load(true);
    } catch (e) {
      toast(friendlyMessage(e, "跳过失败"), "error");
    } finally {
      setSkipping(false);
    }
  };

  const runConfirm = async () => {
    if (!pending) return;
    setConfirmBusy(true);
    try {
      if (pending.kind === "clear-all") {
        const r = await api.clearQueue(false);
        toast(`已清空 ${r.removed} 条任务`, "success");
      } else if (pending.kind === "clear-finished") {
        const r = await api.clearQueue(true);
        toast(`已清理 ${r.removed} 条已完成记录`, "success");
      } else if (pending.kind === "remove-item") {
        await api.removeQueueItem(pending.item.id);
        toast("已移除", "success");
      } else if (pending.kind === "delete-job") {
        await api.deleteSchedule(pending.job.id);
        toast("已删除定时任务", "success");
      }
      await load(true);
      setPending(null);
    } catch (e) {
      toast(friendlyMessage(e, "操作失败"), "error");
    } finally {
      setConfirmBusy(false);
    }
  };

  const submitJob = async (payload: ScheduleInput) => {
    setSavingJob(true);
    try {
      if (editingJob) {
        await api.updateSchedule(editingJob.id, payload);
        toast("定时任务已更新", "success");
      } else {
        await api.createSchedule(payload);
        toast("定时任务已创建", "success");
      }
      setDialogOpen(false);
      setEditingJob(null);
      await load(true);
    } catch (e) {
      toast(friendlyMessage(e, "保存失败"), "error");
    } finally {
      setSavingJob(false);
    }
  };

  const toggleJob = async (job: ScheduleJob, enabled: boolean) => {
    // 先本地切，失败再回滚，避免开关有延迟感
    setJobs((list) =>
      list.map((j) => (j.id === job.id ? { ...j, enabled } : j))
    );
    try {
      const updated = await api.toggleSchedule(job.id, enabled);
      setJobs((list) => list.map((j) => (j.id === job.id ? updated : j)));
      toast(enabled ? "已启用" : "已禁用", "success");
    } catch (e) {
      setJobs((list) =>
        list.map((j) => (j.id === job.id ? { ...j, enabled: !enabled } : j))
      );
      toast(friendlyMessage(e, "切换失败"), "error");
    }
  };

  const stats = snap?.stats;
  const items = snap?.items ?? [];
  const waitingCount = stats?.waiting ?? 0;

  const confirmText = (() => {
    if (!pending) return { title: "", desc: "" as React.ReactNode, ok: "确认" };
    switch (pending.kind) {
      case "clear-all":
        return {
          title: "清空整个队列？",
          desc: "所有等待中和已完成的记录都会被移除，正在执行的任务不受影响。此操作不可撤销。",
          ok: "清空队列",
        };
      case "clear-finished":
        return {
          title: "清理已完成记录？",
          desc: "只移除已完成和失败的记录，等待中的任务会保留。",
          ok: "清理",
        };
      case "remove-item":
        return {
          title: "移除这条任务？",
          desc: `「${pending.item.topic}」将从队列中移除。`,
          ok: "移除",
        };
      case "delete-job":
        return {
          title: "删除定时任务？",
          desc: `「${pending.job.name}」将被永久删除，之后不会再自动执行。`,
          ok: "删除",
        };
    }
  })();

  return (
    <PageShell width="lg">
      <PageHeader
        title="任务队列"
        description="一次排好几期选题，让它顺序跑完；也可以配成定时任务，到点自动出稿。"
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => void load()}
            disabled={refreshing}
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            刷新
          </Button>
        }
      />

      {/* 队列统计 */}
      <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))
        ) : (
          <>
            <StatCard label="等待中" value={stats?.waiting ?? 0} icon={Clock} />
            <StatCard
              label="执行中"
              value={stats?.running ?? 0}
              icon={Loader2}
              tone="warning"
            />
            <StatCard
              label="已完成"
              value={stats?.success ?? 0}
              icon={CheckCircle2}
              tone="success"
            />
            <StatCard
              label="失败"
              value={stats?.failed ?? 0}
              icon={XCircle}
              tone={(stats?.failed ?? 0) > 0 ? "danger" : "default"}
            />
          </>
        )}
      </div>

      {/* 队列列表 */}
      <Card className="mt-6">
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 space-y-0">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">队列</CardTitle>
            {snap?.is_running && (
              <Badge variant="warning">
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                执行中
              </Badge>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={handleStart}
              disabled={starting || snap?.is_running || waitingCount === 0}
            >
              {starting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              开始执行{waitingCount > 0 ? `（${waitingCount}）` : ""}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleSkip}
              disabled={skipping || !snap?.is_running}
              title={snap?.is_running ? "跳过正在执行的任务" : "当前没有正在执行的任务"}
            >
              {skipping ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <SkipForward className="h-4 w-4" />
              )}
              跳过当前任务
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={items.length === 0}
              onClick={() => setPending({ kind: "clear-finished" })}
            >
              清理已完成
            </Button>
            <Button
              size="sm"
              variant="destructive"
              disabled={items.length === 0}
              onClick={() => setPending({ kind: "clear-all" })}
            >
              <Trash2 className="h-4 w-4" />
              清空队列
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-28 w-full" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              icon={Layers}
              title="队列是空的"
              description="在下面手动加一条选题，或者从其他页面把选题送进来自动开始生产：热点素材页勾选后点「直接加入队列」、爆款拆解页点「直接生产」、选题页点「加入队列」、历史任务页点「加入队列」。"
            />
          ) : (
            <div className="space-y-3">
              {items.map((it) => (
                <QueueItemCard
                  key={it.id}
                  item={it}
                  onRemove={(item) => setPending({ kind: "remove-item", item })}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 手动添加 */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">手动添加</CardTitle>
          <CardDescription>临时想到一个选题，直接排进队列。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label required>选题主题</Label>
            <Input
              ref={topicRef}
              value={topic}
              error={!!topicError}
              onChange={(e) => {
                setTopic(e.target.value);
                if (topicError) setTopicError("");
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void handleAdd();
              }}
              placeholder="例如：我用 AI 做副业的第 30 天，真实收入公开"
            />
            {topicError && <FieldError>{topicError}</FieldError>}
          </div>
          <div className="space-y-1.5">
            <Label>切入角度</Label>
            <Textarea
              rows={2}
              value={angle}
              onChange={(e) => setAngle(e.target.value)}
              placeholder="例如：只讲数字和踩过的坑，不讲鸡汤"
            />
          </div>
          <div className="space-y-1.5">
            <Label>补充要求（可选）</Label>
            <Textarea
              rows={2}
              value={extra}
              onChange={(e) => setExtra(e.target.value)}
              placeholder="例如：开头用一个具体场景切入"
            />
          </div>
          <Button onClick={handleAdd} disabled={adding || !topic.trim()}>
            {adding ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            加入队列
          </Button>
        </CardContent>
      </Card>

      {/* 定时任务 */}
      <Card className="mt-6">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div className="flex items-center gap-2">
            <CalendarClock className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">定时任务</CardTitle>
            <Badge variant="muted">{jobs.length}</Badge>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setEditingJob(null);
              setDialogOpen(true);
            }}
          >
            <Plus className="h-4 w-4" />
            新增定时任务
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-24 w-full" />
          ) : jobs.length === 0 ? (
            <EmptyState
              icon={CalendarClock}
              title="还没有定时任务"
              description="配一个「每天早上 9 点自动出一期」，就不用每天手动点了。"
              action={
                <Button
                  size="sm"
                  onClick={() => {
                    setEditingJob(null);
                    setDialogOpen(true);
                  }}
                >
                  <Plus className="h-4 w-4" />
                  新增定时任务
                </Button>
              }
            />
          ) : (
            <div className="space-y-2">
              {jobs.map((job) => (
                <div
                  key={job.id}
                  className="flex flex-wrap items-center gap-3 rounded-lg border border-border px-3 py-2.5"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-medium">
                        {job.name}
                      </span>
                      <Badge variant="secondary">{job.freq_label}</Badge>
                      {!job.enabled && <Badge variant="muted">已禁用</Badge>}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
                      <span className="truncate">选题：{job.topic}</span>
                      <span>
                        下次执行：{job.enabled ? job.next_run ?? "—" : "已禁用"}
                      </span>
                      {job.last_run && (
                        <span>
                          上次：{job.last_run}
                          {job.last_result ? `（${job.last_result}）` : ""}
                        </span>
                      )}
                      {job.run_count > 0 && <span>累计 {job.run_count} 次</span>}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <Switch
                      checked={job.enabled}
                      onCheckedChange={(v) => void toggleJob(job, v)}
                    />
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      title="编辑"
                      onClick={() => {
                        setEditingJob(job);
                        setDialogOpen(true);
                      }}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      title="删除"
                      onClick={() => setPending({ kind: "delete-job", job })}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <ScheduleDialog
        open={dialogOpen}
        job={editingJob}
        saving={savingJob}
        onSubmit={submitJob}
        onClose={() => {
          setDialogOpen(false);
          setEditingJob(null);
        }}
      />

      <ConfirmDialog
        open={pending !== null}
        title={confirmText.title}
        description={confirmText.desc}
        confirmText={confirmText.ok}
        loading={confirmBusy}
        onConfirm={runConfirm}
        onCancel={() => setPending(null)}
      />
    </PageShell>
  );
}
