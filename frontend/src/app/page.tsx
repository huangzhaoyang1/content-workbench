"use client";

import * as React from "react";
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  FileText,
  Lightbulb,
  ShieldCheck,
  Target,
} from "lucide-react";
import { api, API_BASE } from "@/lib/api";
import type { HistoryTask } from "@/lib/types";
import { PageShell, PageHeader } from "@/components/layout/PageShell";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LinkButton } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const IS_LOCAL_BACKEND = /^https?:\/\/(localhost|127\.0\.0\.1)/.test(API_BASE);

// 核心流程四步（横向等宽主视觉）
const FLOW_STEPS = [
  {
    n: 1,
    title: "拆解爆款",
    desc: "把抖音爆款结构拆出来，迁移成公众号骨架。",
    href: "/dissect",
    cta: "去拆解",
    icon: Target,
  },
  {
    n: 2,
    title: "选入选题",
    desc: "一句话主题生成候选选题，挑一个跑流水线。",
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

      // 历史任务：一条请求派生「待审核数 / 今日任务」
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
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const pendingReview =
    tasks?.filter((t) => t.draft_status === "PENDING_REVIEW").length ?? null;
  const todayTasks = tasks?.filter((t) => isSameDay(t.completed_at)).length ?? null;

  return (
    <PageShell>
      <PageHeader
        title={greeting ? `${greeting}，${name}` : `你好，${name}`}
        description="把抖音爆款拆成骨架，变成你的公众号文章"
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

      {/* 顶部紧凑指标（占位小，不抢主视觉） */}
      <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <span className="text-muted-foreground">
          待审核
          <span className="ml-1.5 font-semibold text-foreground">
            {pendingReview ?? "—"}
          </span>
        </span>
        <span className="text-muted-foreground">
          今日完成
          <span className="ml-1.5 font-semibold text-foreground">
            {todayTasks ?? "—"}
          </span>
        </span>
        <span className="text-muted-foreground">
          素材库
          <span className="ml-1.5 font-semibold text-foreground">
            {materialTotal ?? "—"}
          </span>
        </span>
      </div>

      {/* 主视觉：核心流程四步，横向等宽大卡 + → 串联 */}
      <div className="mt-6 flex flex-col gap-3 md:flex-row md:items-stretch">
        {FLOW_STEPS.map((s, i) => {
          const Icon = s.icon;
          return (
            <React.Fragment key={s.n}>
              <Card className="flex flex-1 flex-col border-sidebar-primary/20 bg-sidebar-primary/[0.03]">
                <CardContent className="flex h-full flex-col gap-3 p-5">
                  <div className="flex items-center gap-2">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-sidebar-primary/15 text-lg font-bold text-sidebar-primary">
                      {s.n}
                    </span>
                    <Icon className="h-5 w-5 text-sidebar-primary" />
                  </div>
                  <h3 className="text-base font-semibold">{s.title}</h3>
                  <p
                    className="truncate text-sm text-muted-foreground"
                    title={s.desc}
                  >
                    {s.desc}
                  </p>
                  <LinkButton href={s.href} className="mt-auto w-full">
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

      {/* 历史产出：首页仅留一条细链接，避免首屏堆叠 */}
      <div className="mt-8 flex justify-end">
        <LinkButton href="/tasks" variant="ghost" size="sm">
          查看全部历史
          <ArrowRight className="h-3 w-3" />
        </LinkButton>
      </div>
    </PageShell>
  );
}
