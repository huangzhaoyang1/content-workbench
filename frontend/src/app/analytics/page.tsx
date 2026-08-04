"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  Eye,
  FileText,
  Flame,
  Heart,
  Lightbulb,
  Loader2,
  Plus,
  Share2,
  TrendingUp,
  Trophy,
  ArrowRight,
  RefreshCw,
} from "lucide-react";
import { api, friendlyMessage } from "@/lib/api";
import { topicSeeds } from "@/lib/seed";
import type {
  AnalyticsDataset,
  AnalyticsRankItem,
  AnalyticsResult,
  AnalyticsSuggestion,
  RankingKey,
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
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatCard } from "@/components/ui/stat-card";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PageShell, PageHeader } from "@/components/layout/PageShell";
import { BarChart, LineChart, type ChartPoint } from "@/components/charts/mini-charts";
import { UploadZone } from "@/components/analytics/UploadZone";
import { RankingTable } from "@/components/analytics/RankingTable";

const TIME_RANGES = ["近7天", "近30天", "全部"] as const;
type TimeRange = (typeof TIME_RANGES)[number];

const RANK_TABS: Array<{ key: RankingKey; label: string }> = [
  { key: "reads", label: "阅读量 TOP10" },
  { key: "shares", label: "分享量 TOP10" },
  { key: "like_rate", label: "在看率 TOP10" },
];

function num(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("zh-CN");
}

export default function AnalyticsPage() {
  const { toast } = useToast();
  const router = useRouter();

  const [dataset, setDataset] = useState<AnalyticsDataset | null>(null);
  const [result, setResult] = useState<AnalyticsResult | null>(null);
  const [suggestions, setSuggestions] = useState<AnalyticsSuggestion[]>([]);
  const [range, setRange] = useState<TimeRange>("全部");

  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [seedCount, setSeedCount] = useState(0);

  useEffect(() => {
    setSeedCount(topicSeeds.all().length);
  }, []);

  const runAnalyze = useCallback(
    async (datasetId: string, tr: TimeRange) => {
      setAnalyzing(true);
      setError(null);
      try {
        const [res, sug] = await Promise.all([
          api.analyzeAnalytics(datasetId, tr),
          api.analyticsSuggestions(datasetId),
        ]);
        setResult(res);
        setSuggestions(sug.suggestions);
      } catch (e) {
        const msg = friendlyMessage(e, "分析失败");
        setError(msg);
        toast(msg, "error");
      } finally {
        setAnalyzing(false);
      }
    },
    [toast]
  );

  // 进页面先看看后端有没有上次的数据集，有就直接恢复
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await api.analyzeAnalytics(null, "全部");
        if (!alive) return;
        setResult(res);
        setDataset({
          dataset_id: res.dataset_id,
          filename: res.filename,
          row_count: res.row_count,
          headers: [],
          mapping: res.mapping,
          has_date: res.has_date,
          uploaded_at: "",
          is_sample: (res.filename ?? "").includes("示例"),
          preview: [],
        });
        const sug = await api.analyticsSuggestions(res.dataset_id);
        if (alive) setSuggestions(sug.suggestions);
      } catch {
        /* 没有历史数据集属于正常情况，静默忽略 */
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const ds = await api.uploadAnalytics(file);
      setDataset(ds);
      setRange("全部");
      toast(`已解析 ${ds.row_count} 条数据`, "success");
      await runAnalyze(ds.dataset_id, "全部");
    } catch (e) {
      const msg = friendlyMessage(e, "上传失败");
      setError(msg);
      toast(msg, "error");
    } finally {
      setUploading(false);
    }
  };

  const handleSample = async () => {
    setUploading(true);
    setError(null);
    try {
      const ds = await api.loadAnalyticsSample();
      setDataset(ds);
      setRange("全部");
      toast("已载入示例数据", "success");
      await runAnalyze(ds.dataset_id, "全部");
    } catch (e) {
      const msg = friendlyMessage(e, "载入示例失败");
      setError(msg);
      toast(msg, "error");
    } finally {
      setUploading(false);
    }
  };

  const doClear = async () => {
    try {
      await api.clearAnalytics();
      setDataset(null);
      setResult(null);
      setSuggestions([]);
      setError(null);
      toast("已清空当前分析", "success");
    } catch (e) {
      toast(friendlyMessage(e, "清空失败"), "error");
    } finally {
      setConfirmClear(false);
    }
  };

  const switchRange = async (tr: TimeRange) => {
    setRange(tr);
    if (dataset) await runAnalyze(dataset.dataset_id, tr);
  };

  // 出错后一键重试：有数据集就重跑分析，没有就重新载入示例
  const handleRetry = () => {
    if (dataset) void runAnalyze(dataset.dataset_id, range);
    else void handleSample();
  };

  const addSeed = (topic: string, angle: string, note?: string) => {
    const n = topicSeeds.add({ topic, angle, note, from: "analytics" });
    setSeedCount(n);
    toast(`已加入选题参考（共 ${n} 条）`, "success");
  };

  const pickRank = (it: AnalyticsRankItem) => {
    addSeed(
      it.title,
      "参考这篇的高表现结构，换一个视角重写",
      `历史数据：阅读 ${num(it.reads)} · 在看 ${num(it.likes)} · 分享 ${num(it.shares)}`
    );
  };

  const trendPoints: ChartPoint[] =
    result?.trend.map((t) => ({ label: t.date, values: [t.reads] })) ?? [];
  const engagePoints: ChartPoint[] =
    result?.trend.map((t) => ({ label: t.date, values: [t.likes, t.shares] })) ?? [];

  const ov = result?.overview;

  return (
    <PageShell width="xl">
      <PageHeader
        title="数据分析"
        description="导入公众号后台数据，看清哪类内容真的有效，再把结论直接变成下一期选题。"
        actions={
          seedCount > 0 ? (
            <Button variant="outline" size="sm" onClick={() => router.push("/topic")}>
              <Lightbulb className="h-4 w-4" />
              选题参考 {seedCount} 条
              <ArrowRight className="h-4 w-4" />
            </Button>
          ) : undefined
        }
      />

      <div className="mt-6">
        <UploadZone
          dataset={dataset}
          uploading={uploading}
          onUpload={handleUpload}
          onSample={handleSample}
          onClear={() => setConfirmClear(true)}
        />
      </div>

      {error && (
        <Alert variant="destructive" className="mt-4">
          <AlertTitle>出错了</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
          <div className="mt-3">
            <Button
              size="sm"
              variant="outline"
              onClick={handleRetry}
              disabled={analyzing || uploading}
            >
              {analyzing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              重试
            </Button>
          </div>
        </Alert>
      )}

      {analyzing && !result && (
        <div className="mt-6 space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {!dataset && !analyzing && (
        <EmptyState
          className="mt-8"
          icon={BarChart3}
          title="还没有数据"
          description="上传公众号后台导出的表格（标题 / 日期 / 阅读量 / 在看 / 分享），或者先点「使用示例数据」看看这一页长什么样。"
          action={
            <Button size="sm" onClick={handleSample} disabled={uploading}>
              {uploading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Flame className="h-4 w-4" />
              )}
              先用示例数据看看
            </Button>
          }
        />
      )}

      {result && ov && (
        <>
          {/* 数据概览 */}
          <section className="mt-8">
            <div className="mb-3 flex items-center gap-2">
              <h2 className="text-lg font-semibold">数据概览</h2>
              {analyzing && (
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              )}
              <Badge variant="muted">{result.time_range}</Badge>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
              <StatCard label="总文章数" value={ov.total_articles} icon={FileText} />
              <StatCard
                label="总阅读量"
                value={num(ov.total_reads)}
                icon={Eye}
                tone="info"
              />
              <StatCard label="平均阅读量" value={num(ov.avg_reads)} icon={TrendingUp} />
              <StatCard label="平均在看数" value={num(ov.avg_likes)} icon={Heart} />
              <StatCard label="平均分享数" value={num(ov.avg_shares)} icon={Share2} />
              <StatCard
                label="最高阅读量"
                value={num(ov.max_reads)}
                icon={Trophy}
                tone="success"
              />
            </div>
          </section>

          {/* 趋势分析 */}
          <section className="mt-8">
            <Card>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <div>
                  <CardTitle className="text-base">趋势分析</CardTitle>
                  <CardDescription>阅读量走势与互动表现</CardDescription>
                </div>
                <div className="inline-flex items-center rounded-lg bg-muted p-1">
                  {TIME_RANGES.map((tr) => (
                    <button
                      key={tr}
                      type="button"
                      disabled={analyzing || !result.has_date}
                      onClick={() => switchRange(tr)}
                      className={
                        "rounded-md px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50 " +
                        (range === tr
                          ? "bg-background text-foreground shadow"
                          : "text-muted-foreground hover:text-foreground")
                      }
                    >
                      {tr}
                    </button>
                  ))}
                </div>
              </CardHeader>
              <CardContent>
                {!result.has_date ? (
                  <Alert>
                    <AlertTitle>没有识别到日期列</AlertTitle>
                    <AlertDescription>
                      这份数据里没有找到「发表时间 / 日期 / date」之类的列，所以画不了趋势图。
                      概览和榜单不受影响，仍然可以正常使用。
                    </AlertDescription>
                  </Alert>
                ) : trendPoints.length === 0 ? (
                  <EmptyState
                    icon={TrendingUp}
                    title="当前时间范围内没有数据"
                    description="换成「全部」再看看，或者确认导出文件的日期格式是否正确。"
                  />
                ) : (
                  <div className="space-y-6">
                    <LineChart
                      data={trendPoints}
                      series={["阅读量"]}
                      colors={["#38bdf8"]}
                      height={220}
                    />
                    <div className="border-t border-border pt-5">
                      <BarChart
                        data={engagePoints}
                        series={["在看", "分享"]}
                        colors={["#a78bfa", "#34d399"]}
                        height={200}
                      />
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </section>

          {/* 内容榜单 */}
          <section className="mt-8">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">内容榜单</CardTitle>
                <CardDescription>
                  点列头可以换排序方式；看到合适的直接「加入选题参考」，去选题页一起生成。
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Tabs defaultValue="reads">
                  <TabsList>
                    {RANK_TABS.map((t) => (
                      <TabsTrigger key={t.key} value={t.key}>
                        {t.label}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                  {RANK_TABS.map((t) => (
                    <TabsContent key={t.key} value={t.key}>
                      <RankingTable
                        items={result.rankings[t.key] ?? []}
                        metric={t.key}
                        onPick={pickRank}
                      />
                    </TabsContent>
                  ))}
                </Tabs>
              </CardContent>
            </Card>
          </section>

          {/* 选题建议 */}
          <section className="mt-8">
            <div className="mb-3 flex items-center gap-2">
              <h2 className="text-lg font-semibold">选题建议</h2>
              <Badge variant="secondary">{suggestions.length} 条</Badge>
            </div>
            {suggestions.length === 0 ? (
              <EmptyState
                icon={Lightbulb}
                title="暂时给不出建议"
                description="数据样本太少或缺少关键列，先攒够 5 篇以上带阅读量的数据再看。"
              />
            ) : (
              <div className="space-y-3">
                {suggestions.map((s, i) => (
                  <Card key={i}>
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between gap-3">
                        <CardTitle className="text-base">{s.name}</CardTitle>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => addSeed(s.name, s.angle, s.evidence)}
                        >
                          <Plus className="h-4 w-4" />
                          加入选题参考
                        </Button>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      <div className="rounded-md bg-muted/50 px-2.5 py-1.5 text-xs text-muted-foreground">
                        依据：{s.evidence}
                      </div>
                      <div>
                        <span className="text-muted-foreground">切入角度：</span>
                        {s.angle}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      <ConfirmDialog
        open={confirmClear}
        title="清空当前分析？"
        description="会移除已上传的数据集与分析结果，已加入的选题参考不受影响。"
        confirmText="清空"
        onConfirm={doClear}
        onCancel={() => setConfirmClear(false)}
      />
    </PageShell>
  );
}
