"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  History,
  Layers,
  ListChecks,
  RefreshCw,
  Search,
  Timer,
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
import { Input } from "@/components/ui/input";
import { Button, LinkButton } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { StatCard } from "@/components/ui/stat-card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { TaskCard, fmtDuration } from "@/components/tasks/TaskCard";
import { TaskDetailDialog } from "@/components/tasks/TaskDetailDialog";

const STATUSES = ["全部", "成功", "失败", "进行中"];
const PLATFORMS = ["全部", "微信公众号", "其他"];
const TIMES = ["全部", "近7天", "近30天", "近90天"];
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
  const [page, setPage] = useState(1);

  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [openingDir, setOpeningDir] = useState(false);
  const [enqueuingId, setEnqueuingId] = useState<number | null>(null);

  const load = useCallback(
    async (override?: Partial<{
      keyword: string;
      status: string;
      platform: string;
      time_range: string;
      page: number;
    }>) => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.listTasks({
          keyword: override?.keyword ?? keyword,
          status: override?.status ?? status,
          platform: override?.platform ?? platform,
          time_range: override?.time_range ?? timeRange,
          page: override?.page ?? page,
          page_size: PAGE_SIZE,
        });
        setData(res);
        if (res.page !== (override?.page ?? page)) setPage(res.page);
      } catch (e) {
        setError(friendlyMessage(e, "加载历史任务失败"));
      } finally {
        setLoading(false);
      }
    },
    [keyword, status, platform, timeRange, page]
  );

  useEffect(() => {
    void load({ page: 1 });
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

  const stats = data?.stats;
  const pages = data?.pages ?? 1;

  return (
    <PageShell>
      <PageHeader
        title="历史任务"
        description="往期产出一览。看到跑得好的选题，可以直接复用或再排一期。"
        actions={
          <>
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

      {/* 统计概览 */}
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

      {/* 筛选 */}
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
          <Button
            variant="outline"
            className="w-[calc(50%-0.25rem)] sm:w-auto"
            onClick={() => applyFilter({ keyword })}
          >
            查询
          </Button>
        </CardContent>
      </Card>

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
      <Card className="mt-4">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">
            任务列表
            {data && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                共 {data.total_filtered} 条
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
          ) : !data || data.tasks.length === 0 ? (
            <EmptyState
              icon={History}
              title={
                data && data.stats.total > 0
                  ? "当前筛选条件下没有任务"
                  : "还没有任何产出记录"
              }
              description={
                data && data.stats.total > 0
                  ? "把状态或时间范围调回「全部」再看看。"
                  : "去「选题与生产」跑一次流水线，或者在「任务队列」里排几期。"
              }
              action={
                data && data.stats.total > 0 ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setKeyword("");
                      setStatus("全部");
                      setPlatform("全部");
                      setTimeRange("全部");
                      setPage(1);
                      void load({
                        keyword: "",
                        status: "全部",
                        platform: "全部",
                        time_range: "全部",
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
              {data.tasks.map((t) => (
                <TaskCard
                  key={t.issue}
                  task={t}
                  onView={openDetail}
                  onReuse={reuseTopic}
                  onEnqueue={enqueue}
                  enqueuing={enqueuingId === t.issue}
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

      <TaskDetailDialog
        open={detailOpen}
        loading={detailLoading}
        detail={detail}
        regenerating={regenerating}
        openingDir={openingDir}
        onClose={() => setDetailOpen(false)}
        onRegenerate={regenerate}
        onOpenDir={openDir}
      />
    </PageShell>
  );
}
