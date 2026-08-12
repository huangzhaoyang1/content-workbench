"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  FileText,
  History,
  Layers,
  ListChecks,
  RefreshCw,
  Search,
  ShieldCheck,
  Tag,
  Timer,
  Trash2,
  Undo2,
} from "lucide-react";
import { api, friendlyMessage } from "@/lib/api";
import { topicSeeds } from "@/lib/seed";
import type { HistoryDetail, HistoryPagedResult, HistoryTask } from "@/lib/types";
import { useToast } from "@/components/ui/toast";
import { PageShell, PageHeader } from "@/components/layout/PageShell";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button, LinkButton } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { StatCard } from "@/components/ui/stat-card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  TaskCard,
  fmtDuration,
  TaskStatusBadge,
  platformLabel,
  fmtTime,
} from "@/components/tasks/TaskCard";
import { TaskDetailDialog } from "@/components/tasks/TaskDetailDialog";
import { ConfirmPublishDialog } from "@/components/tasks/ConfirmPublishDialog";

const STATUSES = ["全部", "成功", "失败", "运行中", "等待中"];
const PLATFORMS = ["全部", "微信公众号", "小红书", "抖音", "其他"];
const TIMES = ["全部", "近7天", "近30天", "本月", "上月"];
const PAGE_SIZE = 10;

export default function TasksPage() {
  const { toast } = useToast();
  const router = useRouter();

  const [data, setData] = useState<HistoryPagedResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState("全部");
  const [platform, setPlatform] = useState("全部");
  const [timeRange, setTimeRange] = useState("全部");
  const [tag, setTag] = useState("全部");
  const [allTags, setAllTags] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [pendingBatchDelete, setPendingBatchDelete] = useState(false);
  const [page, setPage] = useState(1);

  const [tab, setTab] = useState<"active" | "trash">("active");
  const [trashTasks, setTrashTasks] = useState<HistoryTask[]>([]);
  const [trashTotal, setTrashTotal] = useState(0);
  const [trashLoading, setTrashLoading] = useState(false);
  const [pendingTrashDelete, setPendingTrashDelete] = useState<HistoryTask | null>(null);
  const [purging, setPurging] = useState(false);
  const [pendingEmptyTrash, setPendingEmptyTrash] = useState(false);

  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [openingDir, setOpeningDir] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [enqueuingId, setEnqueuingId] = useState<number | null>(null);

  // 审核模式：从侧边栏「审核」入口（/tasks?review=1）进入时，仅显示待审核任务。
  const [review, setReview] = useState(false);

  // 轮询发布态期间若组件卸载，停止 setState / 清掉定时器，避免内存泄漏与控制台告警。
  const mountedRef = useRef(true);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    return () => {
      mountedRef.current = false;
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, []);

  const load = useCallback(
    async (override?: Partial<{
      keyword: string;
      status: string;
      platform: string;
      time_range: string;
      tag: string;
      page: number;
      page_size: number;
    }>) => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.listTasks({
          keyword: override?.keyword ?? keyword,
          status: override?.status ?? status,
          platform: override?.platform ?? platform,
          time_range: override?.time_range ?? timeRange,
          tag: override?.tag ?? tag,
          page: override?.page ?? page,
          page_size: override?.page_size ?? PAGE_SIZE,
        });
        setData(res);
        if (res.page !== (override?.page ?? page)) setPage(res.page);
      } catch (e) {
        setError(friendlyMessage(e, "加载历史任务失败"));
      } finally {
        setLoading(false);
      }
    },
    [keyword, status, platform, timeRange, tag, page]
  );

  const loadTags = useCallback(async () => {
    try {
      const res = await api.taskListTags();
      setAllTags(res.tags || []);
    } catch {
      /* 标签列表失败不影响主流程 */
    }
  }, []);

  const loadTrash = useCallback(async () => {
    setTrashLoading(true);
    try {
      const res = await api.taskListTrash();
      setTrashTasks(res.tasks || []);
      setTrashTotal(res.total || 0);
    } catch (e) {
      toast(friendlyMessage(e, "读取回收站失败"), "error");
    } finally {
      setTrashLoading(false);
    }
  }, [toast]);

  const restoreTrashItem = async (task: HistoryTask) => {
    try {
      await api.taskRestore(task.issue);
      toast(`已恢复第 ${task.issue} 期`, "success");
      void loadTrash();
      void load();
      void loadTags();
    } catch (e) {
      toast(friendlyMessage(e, "恢复失败"), "error");
    }
  };

  const confirmPurge = async () => {
    if (!pendingTrashDelete) return;
    setPurging(true);
    try {
      await api.taskPurge(pendingTrashDelete.issue);
      toast(`已彻底删除第 ${pendingTrashDelete.issue} 期`, "success");
      setPendingTrashDelete(null);
      void loadTrash();
    } catch (e) {
      toast(friendlyMessage(e, "彻底删除失败"), "error");
    } finally {
      setPurging(false);
    }
  };

  const confirmEmptyTrash = async () => {
    try {
      await api.taskEmptyTrash();
      toast("回收站已清空", "success");
      setPendingEmptyTrash(false);
      void loadTrash();
    } catch (e) {
      toast(friendlyMessage(e, "清空失败"), "error");
    }
  };

  useEffect(() => {
    const reviewParam =
      new URLSearchParams(window.location.search).get("review") === "1";
    setReview(reviewParam);
    // 审核模式多拉一些，尽量把待审核任务收进首屏；否则按默认分页。
    void load({ page: 1, page_size: reviewParam ? 50 : PAGE_SIZE });
    void loadTags();
    // 只在首次挂载时拉一次，之后由筛选动作触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 支持 /tasks?issue=12 深链：从概览页/选题页跳过来时直接打开详情
  useEffect(() => {
    const raw = new URLSearchParams(window.location.search).get("issue");
    const issue = raw ? Number(raw) : NaN;
    if (!Number.isFinite(issue)) return;
    void openDetail(issue);
    // 打开后清掉 query，避免刷新重复弹窗
    window.history.replaceState(null, "", "/tasks");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyFilter = (patch: Partial<{
    status: string;
    platform: string;
    time_range: string;
    keyword: string;
    tag: string;
  }>) => {
    setPage(1);
    void load({ ...patch, page: 1 });
  };

  const openDetail = async (issue: number) => {
    setDetailOpen(true);
    setDetailLoading(true);
    setDetail(null);
    try {
      setDetail(await api.taskDetail(issue));
    } catch (e) {
      toast(friendlyMessage(e, "详情加载失败"), "error");
      setDetailOpen(false);
    } finally {
      setDetailLoading(false);
    }
  };

  const reuseTopic = (task: HistoryTask) => {
    if (!task.topic) return;
    const n = topicSeeds.add({
      topic: task.topic,
      angle: task.angle,
      note: `复用第 ${task.issue} 期：${task.title}`,
      from: "tasks",
    });
    toast(`已加入选题参考（共 ${n} 条），正在前往选题页`, "success");
    router.push("/topic");
  };

  const enqueue = async (task: HistoryTask) => {
    if (!task.topic) return;
    setEnqueuingId(task.issue);
    try {
      await api.addQueue({
        topic: task.topic,
        angle: task.angle,
        source: "tasks",
      });
      toast(`已把第 ${task.issue} 期的选题加入队列`, {
        type: "success",
        action: { label: "去队列", onClick: () => router.push("/queue") },
      });
    } catch (e) {
      toast(friendlyMessage(e, "加入队列失败"), "error");
    } finally {
      setEnqueuingId(null);
    }
  };

  const regenerate = async (mode: "queue" | "now") => {
    if (!detail) return;
    setRegenerating(true);
    try {
      const res = await api.regenerateTask(detail.issue, mode);
      if (res.mode === "now") {
        toast(`已启动第 ${res.issue} 期流水线`, "success");
        setDetailOpen(false);
        router.push("/queue");
      } else {
        toast("已加入队列，去任务队列页点「开始执行」", {
          type: "success",
          action: { label: "去队列", onClick: () => router.push("/queue") },
        });
        setDetailOpen(false);
      }
    } catch (e) {
      toast(friendlyMessage(e, "重新生成失败"), "error");
    } finally {
      setRegenerating(false);
    }
  };

  const openDir = async () => {
    if (!detail) return;
    setOpeningDir(true);
    try {
      await api.openTaskDir(detail.issue);
      toast("已在文件管理器中打开", "success");
    } catch (e) {
      toast(friendlyMessage(e, "打开目录失败"), "error");
    } finally {
      setOpeningDir(false);
    }
  };

  /** 确认发布前的二次确认弹窗（让用户手动指定封面期号标识） */
  const [confirmOpen, setConfirmOpen] = useState(false);

  /** 待审核 → 确认发布：推送到公众号并轮询发布任务状态。 */
  const confirmPublish = async (coverLabel = "") => {
    if (!detail) return;
    setReviewBusy(true);
    try {
      const r = await api.publishPipeline(detail.issue, coverLabel);
      await new Promise<void>((resolve) => {
        pollTimerRef.current = setInterval(async () => {
          try {
            const st = await api.pipelineStatus(r.task_id);
            if (st.status === "success" || st.status === "failed") {
              if (pollTimerRef.current) clearInterval(pollTimerRef.current);
              pollTimerRef.current = null;
              resolve();
            }
          } catch {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
            resolve();
          }
        }, 1500);
      });
      // 轮询期间组件已卸载：不再更新已卸载组件状态 / 弹 toast，防止内存泄漏与控制台报错。
      if (!mountedRef.current) return;
      await openDetail(detail.issue);
      toast("已推送到公众号草稿箱", "success");
    } catch (e) {
      toast(friendlyMessage(e, "发布失败"), "error");
    } finally {
      setReviewBusy(false);
    }
  };

  /** 待审核 → 放弃：只改本地状态，不调微信。 */
  const discardIssue = async () => {
    if (!detail) return;
    setReviewBusy(true);
    try {
      await api.discardPipeline(detail.issue);
      await openDetail(detail.issue);
      toast("已标记为放弃（未推送）", "success");
    } catch (e) {
      toast(friendlyMessage(e, "操作失败"), "error");
    } finally {
      setReviewBusy(false);
    }
  };

  const handleDeleteTask = async (task: HistoryTask) => {
    try {
      await api.deleteTask(task.issue);
      toast(`已把第 ${task.issue} 期移入回收站`, "success");
      void load();
      void loadTags();
    } catch (e) {
      toast(friendlyMessage(e, "删除失败"), "error");
    }
  };

  const toggleSelect = (issue: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(issue)) next.delete(issue);
      else next.add(issue);
      return next;
    });
  };

  const runBatchDelete = async () => {
    const issues = Array.from(selected);
    if (issues.length === 0) return;
    try {
      await api.taskBatchDelete(issues);
      toast(`已把 ${issues.length} 期移入回收站`, "success");
      setSelected(new Set());
      void load();
      void loadTags();
    } catch (e) {
      toast(friendlyMessage(e, "批量删除失败"), "error");
    } finally {
      setPendingBatchDelete(false);
    }
  };

  const stats = data?.stats;
  const pages = data?.pages ?? 1;

  // 审核模式：仅展示待审核（PENDING_REVIEW）的任务。
  const visibleTasks = review
    ? (data?.tasks ?? []).filter((t) => t.draft_status === "PENDING_REVIEW")
    : (data?.tasks ?? []);

  return (
    <PageShell>
      <PageHeader
        title="历史任务"
        description="往期产出一览。看到跑得好的选题，可以直接复用或再排一期。"
        actions={
          <>
            <LinkButton href="/topic" size="sm">
              <FileText className="h-4 w-4" />
              发起出稿
            </LinkButton>
            <LinkButton href="/queue" variant="ghost" size="sm">
              <ListChecks className="h-4 w-4" />
              任务队列
            </LinkButton>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void load()}
              disabled={loading}
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              刷新
            </Button>
          </>
        }
      />

      {/* 审核模式：从侧边栏「审核」进入，仅显示待审核任务 */}
      {review && (
        <Alert variant="warning" className="mt-4">
          <ShieldCheck className="h-4 w-4" />
          <AlertDescription className="flex flex-1 flex-wrap items-center gap-2">
            <span>审核模式：当前仅显示待审核任务，确认后一键发布或放弃。</span>
            <Button
              size="xs"
              variant="outline"
              className="ml-auto"
              onClick={() => {
                setReview(false);
                router.push("/tasks");
              }}
            >
              退出审核模式
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Tab 切换：历史任务 / 回收站 */}
      <div className="mt-4 flex w-fit items-center gap-1 rounded-lg border border-border bg-muted/20 p-1">
        <button
          type="button"
          onClick={() => setTab("active")}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            tab === "active"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <History className="h-3.5 w-3.5" />
          历史任务
        </button>
        <button
          type="button"
          onClick={() => {
            setTab("trash");
            void loadTrash();
          }}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            tab === "trash"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Trash2 className="h-3.5 w-3.5" />
          回收站
          <span className="text-[10px] text-muted-foreground">{trashTotal}</span>
        </button>
      </div>

      {/* 统计概览 */}
      {tab === "active" && (
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {loading && !data ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))
        ) : (
          <>
            <StatCard label="总任务" value={stats?.total ?? 0} icon={Layers} />
            <StatCard
              label="成功 / 成功率"
              value={
                <span>
                  {stats?.success ?? 0}
                  <span className="ml-1 text-base font-normal text-muted-foreground">
                    /{" "}
                    {stats?.rate === null || stats?.rate === undefined
                      ? "—"
                      : `${Math.round(stats.rate * 100)}%`}
                  </span>
                </span>
              }
              hint={stats ? `失败 ${stats.failed} 期` : undefined}
              icon={CheckCircle2}
              tone="success"
            />
            <StatCard
              label="本月任务"
              value={stats?.this_month ?? 0}
              icon={CalendarDays}
            />
            <StatCard
              label="平均耗时"
              value={fmtDuration(stats?.avg_duration ?? null)}
              icon={Timer}
            />
          </>
        )}
      </div>
      )}

      {/* 筛选 */}
      {tab === "active" && (
      <Card className="mt-6">
        <CardContent className="flex flex-wrap items-center gap-2 p-4 sm:gap-3">
          <div className="relative w-full min-w-[200px] sm:flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="搜索标题 / 选题"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") applyFilter({ keyword });
              }}
            />
          </div>
          <Select
            className="w-[calc(50%-0.25rem)] sm:w-32"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              applyFilter({ status: e.target.value });
            }}
          >
            {STATUSES.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </Select>
          <Select
            className="w-[calc(50%-0.25rem)] sm:w-36"
            value={platform}
            onChange={(e) => {
              setPlatform(e.target.value);
              applyFilter({ platform: e.target.value });
            }}
          >
            {PLATFORMS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </Select>
          <Select
            className="w-[calc(50%-0.25rem)] sm:w-32"
            value={timeRange}
            onChange={(e) => {
              setTimeRange(e.target.value);
              applyFilter({ time_range: e.target.value });
            }}
          >
            {TIMES.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </Select>
          <Select
            className="w-[calc(50%-0.25rem)] sm:w-32"
            value={tag}
            onChange={(e) => {
              setTag(e.target.value);
              applyFilter({ tag: e.target.value });
            }}
          >
            <option value="全部">全部标签</option>
            {allTags.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
          <Button
            variant="outline"
            className="w-[calc(50%-0.25rem)] sm:w-auto"
            onClick={() => applyFilter({ keyword })}
          >
            查询
          </Button>
        </CardContent>
      </Card>
      )}

      {/* 批量操作条 */}
      {tab === "active" && selected.size > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-primary/40 bg-primary/5 px-3 py-2 text-xs">
          <span className="font-medium">已选 {selected.size} 期</span>
          <div className="ml-auto flex gap-2">
            <Button
              size="xs"
              variant="destructive"
              onClick={() => setPendingBatchDelete(true)}
            >
              <Trash2 className="mr-1 h-3 w-3" />
              批量删除
            </Button>
            <Button
              size="xs"
              variant="ghost"
              onClick={() => setSelected(new Set())}
            >
              取消选择
            </Button>
          </div>
        </div>
      )}

      {error && (
        <ErrorState
          className="mt-4"
          variant="inline"
          message={error}
          retrying={loading}
          onRetry={() => void load()}
        />
      )}

      {/* 任务列表 */}
      {tab === "active" && (
      <Card className="mt-4">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">
            任务列表
            {data && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                {review
                  ? `待审核 ${visibleTasks.length} 条`
                  : `共 ${data.total_filtered} 条`}
              </span>
            )}
          </CardTitle>
          {pages > 1 && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Button
                size="xs"
                variant="outline"
                disabled={page <= 1 || loading}
                onClick={() => {
                  const p = page - 1;
                  setPage(p);
                  void load({ page: p });
                }}
              >
                上一页
              </Button>
              <span>
                {page} / {pages}
              </span>
              <Button
                size="xs"
                variant="outline"
                disabled={page >= pages || loading}
                onClick={() => {
                  const p = page + 1;
                  setPage(p);
                  void load({ page: p });
                }}
              >
                下一页
              </Button>
            </div>
          )}
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-28 w-full" />
              ))}
            </div>
          ) : !data || visibleTasks.length === 0 ? (
            <EmptyState
              icon={History}
              title={
                review
                  ? "没有待审核的任务"
                  : data && data.stats.total > 0
                  ? "当前筛选条件下没有任务"
                  : "还没有任何产出记录"
              }
              description={
                review
                  ? "所有成稿都已处理，去「选题」再生产几期吧。"
                  : data && data.stats.total > 0
                  ? "把状态或时间范围调回「全部」再看看。"
                  : "去「选题与生产」跑一次流水线，或者在「任务队列」里排几期。"
              }
              action={
                review ? (
                  <LinkButton href="/topic" size="sm">
                    去生产新一期
                  </LinkButton>
                ) : data && data.stats.total > 0 ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setKeyword("");
                      setStatus("全部");
                      setPlatform("全部");
                      setTimeRange("全部");
                      setTag("全部");
                      setPage(1);
                      void load({
                        keyword: "",
                        status: "全部",
                        platform: "全部",
                        time_range: "全部",
                        tag: "全部",
                        page: 1,
                      });
                    }}
                  >
                    重置筛选
                  </Button>
                ) : (
                  <div className="flex flex-wrap justify-center gap-2">
                    <LinkButton href="/topic" size="sm">
                      去生成第一期
                    </LinkButton>
                    <LinkButton href="/queue" size="sm" variant="outline">
                      去排期
                    </LinkButton>
                  </div>
                )
              }
            />
          ) : (
            <div className="space-y-3">
              {visibleTasks.map((t) => (
                <TaskCard
                  key={t.issue}
                  task={t}
                  onView={openDetail}
                  onReuse={reuseTopic}
                  onEnqueue={enqueue}
                  onDelete={handleDeleteTask}
                  enqueuing={enqueuingId === t.issue}
                  selected={selected.has(t.issue)}
                  onToggle={toggleSelect}
                />
              ))}
            </div>
          )}

          {data && data.skipped.length > 0 && (
            <Alert className="mt-4" variant="warning">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                已跳过 {data.skipped.length} 个损坏项：
                {data.skipped.slice(0, 2).join("；")}
                {data.skipped.length > 2 ? "…" : ""}
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
      )}

      {/* 回收站 */}
      {tab === "trash" && (
      <Card className="mt-4">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">
            回收站
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              共 {trashTotal} 期
            </span>
          </CardTitle>
          {trashTotal > 0 && (
            <Button
              size="xs"
              variant="destructive"
              onClick={() => setPendingEmptyTrash(true)}
            >
              <Trash2 className="mr-1 h-3 w-3" />
              清空回收站
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {trashLoading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-28 w-full" />
              ))}
            </div>
          ) : trashTasks.length === 0 ? (
            <EmptyState
              icon={Trash2}
              title="回收站是空的"
              description="删除的历史任务会先到这里，可随时恢复或彻底删除。"
            />
          ) : (
            <div className="space-y-3">
              {trashTasks.map((t) => (
                <Card key={t.issue} className="transition-colors">
                  <CardContent className="p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="outline">第 {t.issue} 期</Badge>
                          <TaskStatusBadge status={t.status} />
                          <Badge variant="secondary">{platformLabel(t.platform)}</Badge>
                          {t.tags && t.tags.length > 0 && (
                            <span className="inline-flex flex-wrap gap-1 align-middle">
                              {t.tags.map((tt) => (
                                <Badge key={tt} variant="outline" className="text-[10px]">
                                  {tt}
                                </Badge>
                              ))}
                            </span>
                          )}
                        </div>
                        <p className="mt-2 truncate text-sm font-medium">{t.title || "（无标题）"}</p>
                        <div className="mt-2 text-[11px] text-muted-foreground">
                          完成 {fmtTime(t.completed_at)}
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-1.5">
                        <Button
                          size="xs"
                          variant="outline"
                          onClick={() => void restoreTrashItem(t)}
                        >
                          <Undo2 className="h-3 w-3" />
                          恢复
                        </Button>
                        <Button
                          size="xs"
                          variant="ghost"
                          className="text-destructive hover:bg-destructive/10"
                          onClick={() => setPendingTrashDelete(t)}
                        >
                          <Trash2 className="h-3 w-3" />
                          彻底删除
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
      )}

      <TaskDetailDialog
        open={detailOpen}
        loading={detailLoading}
        detail={detail}
        regenerating={regenerating}
        openingDir={openingDir}
        reviewBusy={reviewBusy}
        onClose={() => setDetailOpen(false)}
        onRegenerate={regenerate}
        onOpenDir={openDir}
        onConfirmPublish={() => setConfirmOpen(true)}
        onDiscard={discardIssue}
        onTagsSaved={(issue) => {
          void openDetail(issue);
          void loadTags();
        }}
      />

      <ConfirmPublishDialog
        open={confirmOpen}
        issue={detail?.issue ?? 0}
        onClose={() => setConfirmOpen(false)}
        onConfirm={confirmPublish}
      />

      <ConfirmDialog
        open={pendingBatchDelete}
        title={`批量删除 ${selected.size} 期任务？`}
        description="将连同整期产出目录一并移入回收站，可在回收站里恢复。"
        confirmText="批量删除"
        onConfirm={runBatchDelete}
        onCancel={() => setPendingBatchDelete(false)}
      />

      <ConfirmDialog
        open={!!pendingTrashDelete}
        title="彻底删除这个任务？"
        description={
          pendingTrashDelete
            ? `将永久删除第 ${pendingTrashDelete.issue} 期，不可恢复。`
            : ""
        }
        confirmText="彻底删除"
        destructive
        loading={purging}
        onConfirm={confirmPurge}
        onCancel={() => setPendingTrashDelete(null)}
      />

      <ConfirmDialog
        open={pendingEmptyTrash}
        title="清空回收站？"
        description="回收站里的所有历史任务都会被永久删除，不可恢复。"
        confirmText="清空"
        onConfirm={confirmEmptyTrash}
        onCancel={() => setPendingEmptyTrash(false)}
      />
    </PageShell>
  );
}
