"use client";

import * as React from "react";
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  Flame,
  Video,
} from "lucide-react";
import { api, API_BASE } from "@/lib/api";
import type { HistoryTask } from "@/lib/types";
import { PageShell, PageHeader } from "@/components/layout/PageShell";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LinkButton } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const IS_LOCAL_BACKEND = /^https?:\/\/(localhost|127\.0\.0\.1)/.test(API_BASE);

// 两条真实流水线（主视觉两大卡，各五步）
const PIPELINES = [
  {
    key: "douyin",
    title: "抖音爆款 → 公众号",
    desc: "贴一条抖音爆款，拆成骨架，走完选题 / 生成 / 封面，进公众号草稿箱。",
    icon: Video,
    steps: ["拆解视频", "生成选题", "生成内容", "确认封面期数", "发布草稿箱"],
    href: "/dissect",
    cta: "去拆解",
  },
  {
    key: "hotspot",
    title: "热点 → 公众号",
    desc: "搜当前热点，挑一个方向，走完生成 / 封面，进公众号草稿箱。",
    icon: Flame,
    steps: ["搜索热点", "选择热点选题", "生成内容", "确认封面期数", "发布草稿箱"],
    href: "/hotspot",
    cta: "去搜热点",
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
        description="抖音爆款或热点，都能变成你的公众号文章"
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

      {/* 主视觉：两条真实流水线，两大卡横排，各五步流程徽标串联 */}
      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
        {PIPELINES.map((p) => {
          const Icon = p.icon;
          return (
            <Card
              key={p.key}
              className="flex flex-col border-sidebar-primary/20 bg-sidebar-primary/[0.03]"
            >
              <CardContent className="flex h-full flex-col gap-4 p-5">
                <div className="flex items-center gap-2">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-sidebar-primary/15 text-sidebar-primary">
                    <Icon className="h-5 w-5" />
                  </span>
                  <h3 className="text-base font-semibold">{p.title}</h3>
                </div>
                {/* 五步流程徽标：灰底小标签，→ 串联，一眼看到「五步走完」 */}
                <div className="flex flex-wrap items-center gap-x-1.5 gap-y-2">
                  {p.steps.map((s, i) => (
                    <React.Fragment key={s}>
                      <span className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
                        {s}
                      </span>
                      {i < p.steps.length - 1 && (
                        <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                      )}
                    </React.Fragment>
                  ))}
                </div>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {p.desc}
                </p>
                <LinkButton href={p.href} className="mt-auto w-full">
                  {p.cta}
                  <ArrowRight className="h-4 w-4" />
                </LinkButton>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* 两线归一：最终都在「出稿与审核」完成确认与发布 */}
      <p className="mt-4 text-center text-xs text-muted-foreground">
        两条线最终都在
        <LinkButton href="/tasks" variant="link" size="sm" className="px-1">
          出稿与审核
        </LinkButton>
        完成确认与发布。
      </p>

      {/* 历史产出：首页仅留一条细链接，避免首屏堆叠 */}
      <div className="mt-6 flex justify-end">
        <LinkButton href="/tasks" variant="ghost" size="sm">
          查看全部历史
          <ArrowRight className="h-3 w-3" />
        </LinkButton>
      </div>
    </PageShell>
  );
}
