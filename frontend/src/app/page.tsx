"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Flame,
  Lightbulb,
  History,
  Settings,
  ArrowRight,
  Activity,
  AlertTriangle,
  CheckCircle2,
  ListChecks,
  BarChart3,
  Rocket,
  Play,
  Clock,
  Loader2,
} from "lucide-react";
import { api, friendlyMessage } from "@/lib/api";
import type { HistoryTask, QueueStats } from "@/lib/types";
import { PageShell, PageHeader } from "@/components/layout/PageShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button, LinkButton } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { TaskStatusBadge, fmtTime } from "@/components/tasks/TaskCard";

const QUICK_LINKS = [
  {
    href: "/hotspot",
    label: "热点素材",
    icon: Flame,
    desc: "搜索近期 AI 热点，获取智能洞察",
  },
  {
    href: "/analytics",
    label: "数据分析",
    icon: BarChart3,
    desc: "复盘往期数据，找到下一步方向",
  },
  {
    href: "/queue",
    label: "任务队列",
    icon: ListChecks,
    desc: "批量排期与定时自动出稿",
  },
  {
    href: "/tasks",
    label: "历史任务",
    icon: History,
    desc: "查看往期产出、封面与草稿状态",
  },
  {
    href: "/config",
    label: "系统配置",
    icon: Settings,
    desc: "配置 SerpAPI / DeepSeek 密钥与参数",
  },
];

export default function DashboardPage() {
  const [health, setHealth] = useState<{
    status: string;
    version: string;
  } | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  const [recent, setRecent] = useState<HistoryTask[] | null>(null);
  const [recentError, setRecentError] = useState<string | null>(null);

  const [queueStats, setQueueStats] = useState<QueueStats | null>(null);
  const [queueRunning, setQueueRunning] = useState(false);
  const [queueError, setQueueError] = useState<string | null>(null);

  const [reloading, setReloading] = useState(false);

  const loadHealth = useCallback(async () => {
    setHealthError(null);
    try {
      setHealth(await api.health());
    } catch (e) {
      setHealth(null);
      setHealthError(friendlyMessage(e, "后端不可用"));
    }
  }, []);

  const loadRecent = useCallback(async () => {
    setRecentError(null);
    try {
      const res = await api.listTasks({ page: 1, page_size: 3 });
      setRecent(res.tasks);
    } catch (e) {
      setRecent(null);
      setRecentError(friendlyMessage(e, "读取历史任务失败"));
    }
  }, []);

  const loadQueue = useCallback(async () => {
    setQueueError(null);
    try {
      const res = await api.getQueue();
      setQueueStats(res.stats);
      setQueueRunning(res.is_running);
    } catch (e) {
      setQueueStats(null);
      setQueueError(friendlyMessage(e, "读取队列失败"));
    }
  }, []);

  const loadAll = useCallback(async () => {
    setReloading(true);
    await Promise.all([loadHealth(), loadRecent(), loadQueue()]);
    setReloading(false);
  }, [loadHealth, loadRecent, loadQueue]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const waiting = queueStats?.waiting ?? 0;

  return (
    <PageShell>
      <PageHeader
        title="概览"
        description="AI 内容运营工作台 · 热点 → 选题 → 生产 → 复盘 的核心闭环"
        actions={
          healthError ? (
            <Badge variant="destructive">
              <AlertTriangle className="mr-1 h-3 w-3" /> 后端离线
            </Badge>
          ) : health ? (
            <Badge variant="success">
              <CheckCircle2 className="mr-1 h-3 w-3" /> 后端在线 v{health.version}
            </Badge>
          ) : (
            <Skeleton className="h-6 w-24" />
          )
        }
      />

      {healthError && (
        <div className="mt-4 animate-fade-in rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <div className="flex flex-wrap items-center gap-2">
            <Activity className="h-4 w-4 shrink-0" />
            <span>无法连接后端（http://localhost:8000）。请先启动后端：</span>
            <code className="rounded bg-black/30 px-1.5 py-0.5 text-xs">
              uvicorn backend.main:app --reload --port 8000
            </code>
            <Button
              size="xs"
              variant="outline"
              className="ml-auto border-destructive/40 text-destructive hover:bg-destructive/10"
              onClick={loadAll}
              disabled={reloading}
            >
              {reloading ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : null}
              重试
            </Button>
          </div>
        </div>
      )}

      {/* 醒目的主行动区 */}
      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card className="border-sidebar-primary/40 bg-sidebar-primary/5 transition-colors hover:border-sidebar-primary md:col-span-2">
          <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Rocket className="h-5 w-5 text-sidebar-primary" />
                <h2 className="text-base font-semibold">开始今天的内容生产</h2>
              </div>
              <p className="mt-1.5 text-sm text-muted-foreground">
                一句话主题即可生成候选选题，选一个直接跑完整流水线到公众号草稿。
              </p>
            </div>
            <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
              <LinkButton href="/topic" className="w-full sm:w-auto">
                <Lightbulb className="h-4 w-4" />
                去生成选题
              </LinkButton>
              <LinkButton
                href="/hotspot"
                variant="outline"
                className="w-full sm:w-auto"
              >
                <Flame className="h-4 w-4" />
                先看热点
              </LinkButton>
            </div>
          </CardContent>
        </Card>

        <Card className="transition-colors hover:border-muted-foreground/30">
          <CardContent className="flex h-full flex-col justify-between gap-3 p-5">
            <div>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <ListChecks className="h-4 w-4" />
                队列待执行
                {queueRunning && (
                  <Badge variant="warning" className="ml-auto">
                    <Play className="mr-1 h-3 w-3" />
                    执行中
                  </Badge>
                )}
              </div>
              {queueError ? (
                <p className="mt-2 text-xs text-destructive">{queueError}</p>
              ) : queueStats ? (
                <div className="mt-2 flex items-end gap-2">
                  <span className="text-3xl font-semibold tabular-nums">
                    {waiting}
                  </span>
                  <span className="pb-1 text-xs text-muted-foreground">
                    条等待中 · 共 {queueStats.total} 条
                  </span>
                </div>
              ) : (
                <Skeleton className="mt-3 h-9 w-24" />
              )}
            </div>
            {queueError ? (
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={loadQueue}
              >
                重试
              </Button>
            ) : (
              <LinkButton
                href="/queue"
                variant="outline"
                size="sm"
                className="w-full"
              >
                查看队列
                <ArrowRight className="h-3.5 w-3.5" />
              </LinkButton>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 最近 3 期 */}
      <Card className="mt-6">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">最近 3 期</CardTitle>
          <LinkButton href="/tasks" variant="ghost" size="xs">
            全部历史
            <ArrowRight className="h-3 w-3" />
          </LinkButton>
        </CardHeader>
        <CardContent>
          {recentError ? (
            <ErrorState
              variant="inline"
              message={recentError}
              onRetry={loadRecent}
            />
          ) : recent === null ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : recent.length === 0 ? (
            <EmptyState
              icon={History}
              title="还没有产出记录"
              description="跑完第一期流水线后，这里会显示最近的成稿。"
              action={
                <LinkButton href="/topic" size="sm">
                  <Lightbulb className="h-3.5 w-3.5" />
                  去生成第一期
                </LinkButton>
              }
              className="py-8"
            />
          ) : (
            <ul className="space-y-2">
              {recent.map((t) => (
                <li key={t.issue}>
                  <Link
                    href={`/tasks?issue=${t.issue}`}
                    className="group flex items-center gap-3 rounded-lg border border-border px-3 py-2.5 transition-colors hover:border-muted-foreground/40 hover:bg-muted/40"
                  >
                    <Badge variant="outline" className="shrink-0">
                      第 {t.issue} 期
                    </Badge>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium" title={t.title}>
                        {t.title || "（无标题）"}
                      </p>
                      <p className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {fmtTime(t.completed_at)}
                      </p>
                    </div>
                    <TaskStatusBadge status={t.status} />
                    <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* 快捷入口 */}
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {QUICK_LINKS.map((item) => {
          const Icon = item.icon;
          return (
            <Link key={item.href} href={item.href}>
              <Card className="group h-full transition-all duration-200 hover:-translate-y-0.5 hover:border-sidebar-primary hover:shadow-lg">
                <CardHeader className="flex-row items-center gap-3 space-y-0">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sidebar-accent text-sidebar-accent-foreground transition-colors group-hover:bg-sidebar-primary group-hover:text-sidebar-primary-foreground">
                    <Icon className="h-5 w-5" />
                  </div>
                  <CardTitle className="text-base">{item.label}</CardTitle>
                  <ArrowRight className="ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-1" />
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">
                  {item.desc}
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">推荐工作流</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-2 text-sm text-muted-foreground">
            <li>1. 在「系统配置」填入 SerpAPI / DeepSeek 密钥（不填则使用内置示例数据）。</li>
            <li>2. 到「热点素材」搜索近期热点，勾选感兴趣的几条。</li>
            <li>3. 在「选题与生产」一键生成候选选题，选一个启动流水线。</li>
            <li>4. 实时查看生产日志，完成后到「历史任务」查看成稿与封面。</li>
            <li>5. 定期在「数据分析」上传后台数据，让下一轮选题更有依据。</li>
          </ol>
        </CardContent>
      </Card>
    </PageShell>
  );
}
