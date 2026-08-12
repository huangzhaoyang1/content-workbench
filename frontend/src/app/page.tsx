"use client";

import * as React from "react";
import { ArrowRight, CheckCircle2, Clock } from "lucide-react";
import { api, API_BASE } from "@/lib/api";
import type { HistoryTask } from "@/lib/types";
import { PageShell, PageHeader } from "@/components/layout/PageShell";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LinkButton } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { MarkDouyin, MarkHotspot, MarkEmpty } from "@/components/brand/marks";

const IS_LOCAL_BACKEND = /^https?:\/\/(localhost|127\.0\.0\.1)/.test(API_BASE);

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

/** 把任务状态映射成中文标签（含待审核）。 */
function statusLabel(t: HistoryTask): string {
  if (t.draft_status === "PENDING_REVIEW") return "审核中";
  switch (t.status) {
    case "ok":
      return "已完成";
    case "error":
      return "失败";
    case "running":
      return "生产中";
    case "waiting":
      return "排队中";
    default:
      return "未知";
  }
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
      try {
        const auth = await api.authStatus();
        if (auth.realm) setName(auth.realm);
      } catch {
        /* 取不到就用默认名 */
      }
      try {
        const res = await api.listTasks({ page: 1, page_size: 20 });
        if (!cancelled) setTasks(res.tasks);
      } catch {
        if (!cancelled) setTasks(null);
      }
      try {
        const lib = await api.dissectListTopics(1);
        if (!cancelled) setMaterialTotal(lib.total);
      } catch {
        if (!cancelled) setMaterialTotal(null);
      }
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
  const latest = tasks?.[0] ?? null;
  const firstRun =
    !tasks && materialTotal === null
      ? false
      : (tasks?.length ?? 0) === 0 && (materialTotal ?? 0) === 0;

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

      {/* 顶部紧凑指标（不抢主视觉） */}
      <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <span className="text-ink-2">
          待审核
          <span className="ml-1.5 font-semibold text-ink">{pendingReview ?? "—"}</span>
        </span>
        <span className="text-ink-2">
          今日完成
          <span className="ml-1.5 font-semibold text-ink">{todayTasks ?? "—"}</span>
        </span>
        <span className="text-ink-2">
          素材库
          <span className="ml-1.5 font-semibold text-ink">{materialTotal ?? "—"}</span>
        </span>
      </div>

      {/* 主视觉：两条真实流水线，左右两大卡等高 */}
      {firstRun ? (
        <Card className="mt-6 flex flex-col items-center gap-4 px-6 py-12 text-center">
          <MarkEmpty className="h-16 w-16 text-ink-3" />
          <div>
            <p className="text-base font-medium text-ink">库里还没货</p>
            <p className="mt-1 text-sm text-ink-2">
              先去拆一条抖音爆款，或搜一波热点，把素材攒起来。
            </p>
          </div>
          <LinkButton href="/dissect" className="mt-1">
            去拆解一条爆款
            <ArrowRight className="h-4 w-4" />
          </LinkButton>
        </Card>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* 卡A：抖音线 */}
          <Card className="flex flex-col border-subtle bg-surface">
            <CardContent className="flex h-full flex-col gap-4 p-5">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
                  <MarkDouyin className="h-6 w-6" />
                </span>
                <div>
                  <h3 className="text-base font-semibold text-ink">抖音线</h3>
                  <p className="text-xs text-ink-2">抖音爆款 → 公众号</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <LinkButton
                  href="/dissect"
                  variant="outline"
                  className="justify-start"
                >
                  即时拆解
                </LinkButton>
                <LinkButton
                  href="/douyin-sync"
                  variant="outline"
                  className="justify-start"
                >
                  收藏沉淀
                </LinkButton>
              </div>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                <span className="text-ink-2">
                  库内{" "}
                  <span className="font-semibold text-ink">
                    {materialTotal ?? "—"}
                  </span>{" "}
                  个选题
                </span>
                {latest && (
                  <span className="text-ink-2">
                    当前进度：
                    <span className="font-medium text-ink">
                      第{latest.issue}期 · {statusLabel(latest)}
                    </span>
                  </span>
                )}
              </div>

              <LinkButton href="/dissect" className="mt-auto w-full">
                去拆解
                <ArrowRight className="h-4 w-4" />
              </LinkButton>
            </CardContent>
          </Card>

          {/* 卡B：热点线（主用，琥珀金描边） */}
          <Card className="flex flex-col border-accent bg-surface ring-1 ring-accent/40">
            <CardContent className="flex h-full flex-col gap-4 p-5">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent/15 text-accent">
                  <MarkHotspot className="h-6 w-6" />
                </span>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-semibold text-ink">热点线</h3>
                    <span className="rounded-full border border-accent/50 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                      主用
                    </span>
                  </div>
                  <p className="text-xs text-ink-2">热点 → 公众号</p>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-2">
                <LinkButton href="/hotspot" variant="outline" className="justify-start">
                  搜索热点
                </LinkButton>
              </div>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                <span className="text-ink-2">本次热点选题状态</span>
                {latest && (
                  <span className="text-ink-2">
                    最新：
                    <span className="font-medium text-ink">
                      第{latest.issue}期 · {statusLabel(latest)}
                    </span>
                  </span>
                )}
              </div>

              <LinkButton href="/hotspot" className="mt-auto w-full">
                去搜热点
                <ArrowRight className="h-4 w-4" />
              </LinkButton>
            </CardContent>
          </Card>
        </div>
      )}

      {/* 两线归一：生产→审核→封面→发布 → 公众号草稿箱 */}
      <p className="mt-4 text-center text-xs text-ink-2">
        两条线共用「生产 → 审核 → 封面 → 发布」，最终进
        <LinkButton href="/tasks" variant="link" size="sm" className="px-1">
          出稿与审核
        </LinkButton>
      </p>

      {/* 历史产出：仅留一条细链接 */}
      <div className="mt-6 flex justify-end">
        <LinkButton href="/tasks" variant="ghost" size="sm">
          查看全部历史
          <ArrowRight className="h-3 w-3" />
        </LinkButton>
      </div>
    </PageShell>
  );
}
