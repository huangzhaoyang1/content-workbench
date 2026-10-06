"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Coins, Loader2, RefreshCw, Timer, Zap } from "lucide-react";
import { api, friendlyMessage } from "@/lib/api";
import type { LlmCostBucket, LlmCostSummary, LlmUsageRecord } from "@/lib/types";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { StatCard } from "@/components/ui/stat-card";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageShell, PageHeader } from "@/components/layout/PageShell";
import { BarChart, type ChartPoint } from "@/components/charts/mini-charts";

/** 后端 llm_usage 写入的 module 取值 → 中文名。 */
const MODULE_LABEL: Record<string, string> = {
  hotspot: "热点搜索",
  topic: "选题生成",
  dissect: "爆款拆解",
  ocr_structure: "截图识别",
  vision: "视觉模型",
};

const MODULE_COLOR: Record<string, string> = {
  hotspot: "#38bdf8",
  topic: "#a78bfa",
  dissect: "#34d399",
  ocr_structure: "#fbbf24",
  vision: "#f472b6",
};

const moduleLabel = (m: string) => MODULE_LABEL[m] ?? m;

function fmtInt(v: number | null | undefined): string {
  return (v ?? 0).toLocaleString("zh-CN");
}

/** 费用都是「分」级别的量级，小于 1 元保留 4 位才有信息量。 */
function fmtCost(v: number | null | undefined): string {
  const n = v ?? 0;
  if (n <= 0) return "¥0";
  if (n < 1) return `¥${n.toFixed(4)}`;
  return `¥${n.toFixed(2)}`;
}

function fmtDuration(ms: number | null | undefined): string {
  const v = ms ?? 0;
  if (v <= 0) return "—";
  if (v < 1000) return `${Math.round(v)}ms`;
  if (v < 60000) return `${(v / 1000).toFixed(1)}s`;
  const min = Math.floor(v / 60000);
  const sec = Math.round((v % 60000) / 1000);
  return `${min}分${sec}秒`;
}

/** 2026-10-06T17:33:24 → 10-06 17:33 */
function fmtTime(iso: string): string {
  if (!iso || iso.length < 16) return iso || "—";
  return `${iso.slice(5, 10)} ${iso.slice(11, 16)}`;
}

const BUCKETS: Array<{ key: "today" | "week" | "month" | "all"; label: string; hint: string }> = [
  { key: "today", label: "今日费用", hint: "自然日" },
  { key: "week", label: "本周费用", hint: "本周一起算" },
  { key: "month", label: "本月费用", hint: "自然月" },
  { key: "all", label: "累计费用", hint: "有记录以来" },
];

export default function LlmCostPage() {
  const [data, setData] = useState<LlmCostSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.llmCost());
    } catch (e) {
      setError(friendlyMessage(e, "加载失败，请确认后端已启动"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // 模块按费用从高到低排，最花钱的排最上面
  const modules = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.by_module)
      .map(([name, b]: [string, LlmCostBucket]) => ({ name, ...b }))
      .sort((a, b) => b.cost_est - a.cost_est || b.calls - a.calls);
  }, [data]);

  const totalCost = data?.all.cost_est ?? 0;

  const tokenPoints: ChartPoint[] = modules.map((m) => ({
    label: moduleLabel(m.name),
    values: [m.prompt_tokens, m.completion_tokens],
  }));

  const hasAnyCall = (data?.all.calls ?? 0) > 0;

  return (
    <PageShell width="xl">
      <PageHeader
        title="调用与成本"
        description="每一次模型调用都落一条记录：调用次数、token 消耗与费用估算，用来判断这条内容线跑起来到底花多少钱。"
        actions={
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            刷新
          </Button>
        }
      />

      {error && (
        <Alert variant="destructive" className="mt-6">
          <AlertTitle>出错了</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
          <div className="mt-3">
            <Button size="sm" variant="outline" onClick={() => void load()} disabled={loading}>
              <RefreshCw className="h-4 w-4" />
              重试
            </Button>
          </div>
        </Alert>
      )}

      {loading && !data && (
        <div className="mt-6 space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
          <Skeleton className="h-72 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {data && !hasAnyCall && (
        <EmptyState
          className="mt-8"
          icon={Coins}
          title="还没有调用记录"
          description="跑一次热点搜索、选题生成或爆款拆解，这里就会出现第一条记录。数据来自 backend/data/llm_usage.jsonl。"
        />
      )}

      {data && hasAnyCall && (
        <>
          {/* 费用概览 */}
          <section className="mt-8">
            <div className="mb-3 flex items-center gap-2">
              <h2 className="text-lg font-semibold">费用概览</h2>
              <Badge variant="muted">{data.currency}</Badge>
            </div>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {BUCKETS.map((b) => {
                const bucket = data[b.key];
                return (
                  <StatCard
                    key={b.key}
                    label={b.label}
                    value={fmtCost(bucket.cost_est)}
                    icon={Coins}
                    tone={b.key === "all" ? "info" : "default"}
                    hint={`${b.hint} · ${fmtInt(bucket.calls)} 次调用 · ${fmtInt(
                      bucket.total_tokens
                    )} tokens`}
                  />
                );
              })}
            </div>
          </section>

          {/* 按模块分布 */}
          <section className="mt-8">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">按模块分布</CardTitle>
                <CardDescription>
                  输入 / 输出 token 对比，以及每个模块占累计费用的比例。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <BarChart
                  data={tokenPoints}
                  series={["输入 token", "输出 token"]}
                  colors={["#38bdf8", "#a78bfa"]}
                  height={200}
                />

                <div className="border-t border-border pt-5">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>模块</TableHead>
                        <TableHead className="text-right">调用次数</TableHead>
                        <TableHead className="text-right">输入 token</TableHead>
                        <TableHead className="text-right">输出 token</TableHead>
                        <TableHead className="text-right">费用</TableHead>
                        <TableHead className="w-[160px]">占比</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {modules.map((m) => {
                        const pct = totalCost > 0 ? (m.cost_est / totalCost) * 100 : 0;
                        return (
                          <TableRow key={m.name}>
                            <TableCell className="font-medium">
                              <span className="inline-flex items-center gap-2">
                                <span
                                  className="inline-block h-2 w-2 rounded-full"
                                  style={{
                                    background: MODULE_COLOR[m.name] ?? "#9AA5B5",
                                  }}
                                />
                                {moduleLabel(m.name)}
                              </span>
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {fmtInt(m.calls)}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {fmtInt(m.prompt_tokens)}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {fmtInt(m.completion_tokens)}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {fmtCost(m.cost_est)}
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-2">
                                <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                                  <div
                                    className="h-full rounded-full"
                                    style={{
                                      width: `${Math.min(100, pct)}%`,
                                      background: MODULE_COLOR[m.name] ?? "#9AA5B5",
                                    }}
                                  />
                                </div>
                                <span className="text-xs tabular-nums text-muted-foreground">
                                  {pct.toFixed(1)}%
                                </span>
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </section>

          {/* 最近调用 */}
          <section className="mt-8">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">最近调用</CardTitle>
                <CardDescription>最新的 10 次，按时间倒序。</CardDescription>
              </CardHeader>
              <CardContent>
                {data.recent.length === 0 ? (
                  <EmptyState
                    icon={Activity}
                    title="没有明细记录"
                    description="汇总有数据但读不到明细行，检查一下 llm_usage.jsonl 是否完整。"
                  />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[130px]">时间</TableHead>
                        <TableHead>模块</TableHead>
                        <TableHead>模型</TableHead>
                        <TableHead className="text-right">输入</TableHead>
                        <TableHead className="text-right">输出</TableHead>
                        <TableHead className="text-right">费用</TableHead>
                        <TableHead className="text-right">耗时</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.recent.map((r: LlmUsageRecord, i: number) => (
                        <TableRow key={`${r.time}-${i}`}>
                          <TableCell className="whitespace-nowrap text-muted-foreground">
                            {fmtTime(r.time)}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">{moduleLabel(r.module)}</Badge>
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {r.model || "—"}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {fmtInt(r.prompt_tokens)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {fmtInt(r.completion_tokens)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {fmtCost(r.cost_est)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums text-muted-foreground">
                            {fmtDuration(r.duration_ms)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}

                <div className="mt-4 flex items-start gap-2 rounded-md bg-muted/50 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                  <Zap className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>
                    {data.note}
                    <br />
                    说明：输入 / 输出 token 由调用方按返回的 usage 字段累计；耗时为单次请求的端到端时间。
                  </span>
                </div>
              </CardContent>
            </Card>
          </section>

          {/* 口径说明 */}
          <section className="mt-6 grid gap-3 md:grid-cols-3">
            <Card>
              <CardContent className="flex items-start gap-3 p-4">
                <Activity className="mt-0.5 h-4 w-4 shrink-0 text-info" />
                <div className="text-xs leading-relaxed text-muted-foreground">
                  <div className="mb-1 text-sm font-medium text-foreground">数据来源</div>
                  每次模型调用由后端写一行 JSON 到 <code>llm_usage.jsonl</code>，本页只读汇总，不做二次统计。
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="flex items-start gap-3 p-4">
                <Coins className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                <div className="text-xs leading-relaxed text-muted-foreground">
                  <div className="mb-1 text-sm font-medium text-foreground">为什么是估算</div>
                  缓存命中 / 未命中等复杂计费被合并为单一定价，只用来判断量级，不能当账单核对。
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="flex items-start gap-3 p-4">
                <Timer className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                <div className="text-xs leading-relaxed text-muted-foreground">
                  <div className="mb-1 text-sm font-medium text-foreground">怎么用</div>
                  拆解单次最贵（长文案 + 3 篇改写），先看它占了多少比例，再决定要不要缩减改写篇数。
                </div>
              </CardContent>
            </Card>
          </section>
        </>
      )}
    </PageShell>
  );
}
