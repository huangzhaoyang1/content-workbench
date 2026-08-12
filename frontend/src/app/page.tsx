"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  FileText,
  Flame,
  Layers,
  Lightbulb,
  ShieldCheck,
  Target,
} from "lucide-react";
import { api, API_BASE } from "@/lib/api";
import type { HistoryTask } from "@/lib/types";
import { PageShell, PageHeader } from "@/components/layout/PageShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button, LinkButton } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/ui/stat-card";
import { EmptyState } from "@/components/ui/empty-state";
import { TaskStatusBadge, fmtTime } from "@/components/tasks/TaskCard";

const IS_LOCAL_BACKEND = /^https?:\/\/(localhost|127\.0\.0\.1)/.test(API_BASE);

// 核心流程四步引导
const FLOW_STEPS = [
  {
    n: 1,
    title: "拆解爆款",
    desc: "把抖音爆款结构拆出来，迁移成公众号可写的骨架。",
    href: "/dissect",
    cta: "去拆解",
    icon: Target,
  },
  {
    n: 2,
    title: "选入选题",
    desc: "一句话主题生成候选选题，挑一个直接跑流水线。",
    href: "/topic",
    cta: "去选题",
    icon: Lightbulb,
  },
  {
    n: 3,
    title: "生成文章",
    desc: "一键跑完整流水线，产出成稿、封面与草稿。",
    href: "/tasks",
    cta: "发起出稿",
    icon: FileText,
  },
  {
    n: 4,
    title: "审核发布",
    desc: "对待审核成稿做最终确认，再推送到公众号。",
    href: "/tasks?review=1",
    cta: "去审核",
    icon: ShieldCheck,
  },
] as const;

function isSameDay(v: string | null): boolean {
  if (!v) return false;
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

export default function DashboardPage() {
  const [name, setName] = React.useState("内容运营");
  const [greeting, setGreeting] = React.useState<string | null>(null);

  const [tasks, setTasks] = React.useState<HistoryTask[] | null>(null);
  const [materialTotal, setMaterialTotal] = React.useState<number | null>(null);
  const [online, setOnline] = React.useState<boolean | null>(null);

  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    const h = new Date().getHours();
    setGreeting(h < 11 ? "早上好" : h < 14 ? "中午好" : h < 18 ? "下午好" : "晚上好");
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      // 账号名（鉴权开启时取 realm，否则用默认）
      try {
        const auth = await api.authStatus();
        if (auth.realm) setName(auth.realm);
      } catch {
        /* 取不到就用默认名 */
      }

      // 历史任务：一条请求派生「待审核数 / 今日任务 / 最近 5 个」
      try {
        const res = await api.listTasks({ page: 1, page_size: 20 });
        if (!cancelled) setTasks(res.tasks);
      } catch {
        if (!cancelled) setTasks(null);
      }

      // 素材库（选题库）总条数
      try {
        const lib = await api.dissectListTopics(1);
        if (!cancelled) setMaterialTotal(lib.total);
      } catch {
        if (!cancelled) setMaterialTotal(null);
      }

      // 后端在线状态（轻量探测）
      try {
        await api.health();
        if (!cancelled) setOnline(true);
      } catch {
        if (!cancelled) setOnline(false);
      }

      if (!cancelled) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const pendingReview =
    tasks?.filter((t) => t.draft_status === "PENDING_REVIEW").length ?? null;
  const todayTasks = tasks?.filter((t) => isSameDay(t.completed_at)).length ?? null;
  const recent = tasks ? tasks.slice(0, 5) : null;

  return (
    <PageShell>
      <PageHeader
        title={
          greeting ? `${greeting}，${name}` : `你好，${name}`
        }
        description="本地生活短视频内容生产流水线 · 拆 → 选 → 写 → 审 一气呵成"
        actions={
          online === null ? (
            <Skeleton className="h-6 w-20" />
          ) : online ? (
            <Badge variant="success">
              <CheckCircle2 className="mr-1 h-3 w-3" /> 后端在线
            </Badge>
          ) : (
            <Badge variant="destructive">
              <Clock className="mr-1 h-3 w-3" /> 后端离线
            </Badge>
          )
        }
      />

      {online === false && (
        <div className="mt-4 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          无法连接后端（{API_BASE}）。
          {IS_LOCAL_BACKEND ? (
            <span> 请先启动后端：运行「启动AI内容工作台.bat」。</span>
          ) : (
            <span> 免费实例休眠后首次唤醒约需 30–60 秒，稍后刷新即可。</span>
          )}
        </div>
      )}

      {/* 今日核心数据卡片 */}
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label="待审核"
          value={pendingReview ?? "—"}
          hint="需确认后发布的成稿"
          icon={ShieldCheck}
          tone={pendingReview && pendingReview > 0 ? "warning" : "default"}
        />
        <StatCard
          label="今日完成"
          value={todayTasks ?? "—"}
          hint="今天跑完的任务期数"
          icon={CheckCircle2}
        />
        <StatCard
          label="素材库"
          value={materialTotal ?? "—"}
          hint="选题库已积累的素材"
          icon={Layers}
        />
      </div>

      {/* 核心流程四步引导（主视觉） */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">核心流程</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-3 md:flex-row md:items-stretch">
            {FLOW_STEPS.map((s, i) => {
              const Icon = s.icon;
              return (
                <React.Fragment key={s.n}>
                  <Card className="flex flex-1 flex-col border-sidebar-primary/20 bg-sidebar-primary/[0.03]">
                    <CardContent className="flex h-full flex-col gap-3 p-5">
                      <div className="flex items-center gap-2.5">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-sidebar-primary/15 text-sm font-semibold text-sidebar-primary">
                          {s.n}
                        </span>
                        <Icon className="h-5 w-5 text-sidebar-primary" />
                        <span className="text-base font-semibold">{s.title}</span>
                      </div>
                      <p className="flex-1 text-sm leading-relaxed text-muted-foreground">
                        {s.desc}
                      </p>
                      <LinkButton href={s.href} className="mt-auto w-full sm:w-auto">
                        {s.cta}
                        <ArrowRight className="h-4 w-4" />
                      </LinkButton>
                    </CardContent>
                  </Card>
                  {i < FLOW_STEPS.length - 1 && (
                    <div className="flex items-center justify-center md:px-1">
                      <ArrowRight className="h-5 w-5 rotate-90 text-muted-foreground/50 md:rotate-0" />
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* 最近 5 个任务状态 */}
      <Card className="mt-6">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">最近任务</CardTitle>
          <LinkButton href="/tasks" variant="ghost" size="xs">
            全部历史
            <ArrowRight className="h-3 w-3" />
          </LinkButton>
        </CardHeader>
        <CardContent>
          {tasks === null && loading ? (
            <div className="space-y-2">
              {[0, 1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : recent && recent.length > 0 ? (
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
          ) : (
            <EmptyState
              icon={Flame}
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
          )}
        </CardContent>
      </Card>
    </PageShell>
  );
}
