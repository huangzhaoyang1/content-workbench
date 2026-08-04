"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  Loader2,
  Flame,
  ArrowRight,
  ExternalLink,
  Sparkles,
  CheckCircle2,
  Newspaper,
  X,
  ListPlus,
} from "lucide-react";
import { api, friendlyMessage } from "@/lib/api";
import type { HotspotItem, HotspotSearchResult, SearchQuota } from "@/lib/types";
import { useToast } from "@/components/ui/toast";
import { PageShell, PageHeader } from "@/components/layout/PageShell";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Button, LinkButton } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";

const TIME_RANGES = ["近1天", "近7天", "近30天"];

export default function HotspotPage() {
  const { toast } = useToast();
  const router = useRouter();
  const [keywords, setKeywords] = useState("");
  const [timeRange, setTimeRange] = useState("近7天");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<HotspotSearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<HotspotItem[]>([]);
  const [enqueuing, setEnqueuing] = useState(false);
  // 今日真实搜索额度：用满后会自动回退示例数据，需要让用户看得见
  const [quota, setQuota] = useState<SearchQuota | null>(null);
  const [resetting, setResetting] = useState(false);

  const loadQuota = useCallback(async () => {
    try {
      setQuota(await api.getSearchQuota());
    } catch {
      setQuota(null); // 额度只是辅助信息，失败静默，不打扰主流程
    }
  }, []);

  useEffect(() => {
    void loadQuota();
  }, [loadQuota]);

  const handleResetQuota = async () => {
    setResetting(true);
    try {
      setQuota(await api.resetSearchQuota());
      toast("已重置今日额度，后续搜索将真实调用 API", "success");
    } catch (e) {
      toast(friendlyMessage(e, "重置额度失败"), "error");
    } finally {
      setResetting(false);
    }
  };

  const handleSearch = async () => {
    setLoading(true);
    setError(null);
    try {
      const kws = keywords
        .split(/[\n,，]/)
        .map((k) => k.trim())
        .filter(Boolean);
      const res = await api.searchHotspots(kws, timeRange, 15);
      setResult(res);
      toast(`搜到 ${res.items.length} 条热点`, "success");
      void loadQuota(); // 搜索会消耗额度，刷新展示
    } catch (e) {
      setError(friendlyMessage(e, "搜索热点失败"));
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (item: HotspotItem) => {
    setSelected((prev) => {
      const exists = prev.find((p) => p.id === item.id);
      if (exists) return prev.filter((p) => p.id !== item.id);
      return [...prev, item];
    });
  };

  const clearSelected = () => {
    setSelected([]);
    sessionStorage.removeItem("selected_hotspots");
    toast("已清空选中素材", "success");
  };

  const selectAll = () => {
    if (!result) return;
    setSelected(result.items);
  };

  const persistSelected = () => {
    sessionStorage.setItem(
      "selected_hotspots",
      JSON.stringify(
        selected.map((s) => ({
          id: s.id,
          title: s.title,
          summary: s.summary,
          source: s.source,
          url: s.url,
        }))
      )
    );
  };

  const goTopic = () => {
    if (selected.length === 0) {
      toast("请至少勾选一条热点素材", "warning");
      return;
    }
    persistSelected();
    router.push("/topic");
  };

  /** 直接把选中的热点标题排进队列，跳过选题生成 */
  const enqueueSelected = async () => {
    if (selected.length === 0) {
      toast("请至少勾选一条热点素材", "warning");
      return;
    }
    setEnqueuing(true);
    try {
      await api.addQueueBatch(
        selected.map((s) => ({
          topic: s.title,
          angle: s.ai_summary || s.summary?.slice(0, 60) || "",
          extra: s.url ? `参考来源：${s.url}` : "",
        })),
        "hotspot"
      );
      toast(`已把 ${selected.length} 条热点加入队列`, {
        type: "success",
        action: { label: "去队列", onClick: () => router.push("/queue") },
      });
    } catch (e) {
      toast(friendlyMessage(e, "加入队列失败"), "error");
    } finally {
      setEnqueuing(false);
    }
  };

  return (
    <PageShell width="md">
      <PageHeader
        title="热点素材"
        description="搜索近期 AI 热点，获取智能洞察，勾选素材带入选题环节。"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {quota && (
              <Badge variant={quota.exhausted ? "warning" : "muted"}>
                今日真实搜索 {quota.used}/{quota.limit}
              </Badge>
            )}
            {selected.length > 0 && (
              <Badge variant="success">
                <CheckCircle2 className="mr-1 h-3 w-3" />
                已选 {selected.length} 条
              </Badge>
            )}
          </div>
        }
      />

      {quota?.exhausted && (
        <Alert variant="warning" className="mt-4">
          <AlertTitle>今日搜索额度已用完，当前返回示例数据</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center gap-2">
            <span>
              已用 {quota.used}/{quota.limit} 次。这是防止 API 超额扣费的本地保护，
              重置后搜索会真实调用 SerpAPI 并产生费用。
            </span>
            <Button
              variant="outline"
              size="xs"
              onClick={handleResetQuota}
              disabled={resetting}
            >
              {resetting ? "重置中…" : "重置今日额度"}
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <Card className="mt-5">
        <CardContent className="space-y-4 p-4 sm:p-6">
          <div className="space-y-1.5">
            <Label htmlFor="kw">关键词（每行 / 逗号分隔）</Label>
            <Textarea
              id="kw"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder={"如：\nAI 副业\n智能体\n大模型价格战"}
              rows={3}
            />
            <p className="text-xs text-muted-foreground">
              留空则按账号定位使用默认关键词。
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="space-y-1.5">
              <Label htmlFor="range">时间范围</Label>
              <Select
                id="range"
                className="sm:w-40"
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value)}
              >
                {TIME_RANGES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </Select>
            </div>
            <Button
              onClick={handleSearch}
              disabled={loading}
              className="w-full sm:w-auto"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              {loading ? "搜索中…" : "搜索热点"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && !loading && (
        <ErrorState
          className="mt-5"
          title="搜索失败"
          message={error}
          onRetry={handleSearch}
        />
      )}

      {loading && (
        <div className="mt-5 space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      )}

      {result && !loading && (
        <div className="mt-5 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="muted">
              <Newspaper className="mr-1 h-3 w-3" />
              {result.origin}
            </Badge>
            <Badge variant="secondary">搜到 {result.items.length} 条</Badge>
            {selected.length > 0 && (
              <>
                <Badge variant="success">
                  <CheckCircle2 className="mr-1 h-3 w-3" />
                  已选 {selected.length} 条
                </Badge>
                <Button variant="ghost" size="xs" onClick={clearSelected}>
                  <X className="h-3 w-3" />
                  清空已选
                </Button>
              </>
            )}
            {result.items.length > 0 &&
              selected.length < result.items.length && (
                <Button
                  variant="ghost"
                  size="xs"
                  className="ml-auto"
                  onClick={selectAll}
                >
                  全选本页
                </Button>
              )}
          </div>

          {result.insight && (
            <Alert variant="info" className="animate-fade-in">
              <Sparkles className="h-4 w-4" />
              <AlertTitle>智能洞察</AlertTitle>
              <AlertDescription>{result.insight}</AlertDescription>
            </Alert>
          )}

          {result.items.length === 0 ? (
            <EmptyState
              icon={Search}
              title="没有命中热点"
              description="试试放宽关键词、换个时间范围，或直接去选题页按账号定位生成。"
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  <Button size="sm" variant="outline" onClick={handleSearch}>
                    重新搜索
                  </Button>
                  <LinkButton href="/topic" size="sm">
                    直接去选题
                    <ArrowRight className="h-3.5 w-3.5" />
                  </LinkButton>
                </div>
              }
            />
          ) : (
            <div className="space-y-3">
              {result.items.map((item) => {
                const isSel = !!selected.find((s) => s.id === item.id);
                return (
                  <Card
                    key={item.id}
                    role="button"
                    tabIndex={0}
                    aria-pressed={isSel}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        toggleSelect(item);
                      }
                    }}
                    className={`cursor-pointer transition-all duration-150 hover:border-muted-foreground/40 ${
                      isSel
                        ? "border-emerald-500/60 bg-emerald-500/5"
                        : ""
                    }`}
                    onClick={() => toggleSelect(item)}
                  >
                    <CardContent className="p-4 sm:p-5">
                      <div className="flex items-start gap-3">
                        <div
                          className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors ${
                            isSel
                              ? "border-emerald-500 bg-emerald-500 text-white"
                              : "border-muted-foreground/40"
                          }`}
                        >
                          {isSel && <CheckCircle2 className="h-4 w-4" />}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="outline">{item.source}</Badge>
                            <span className="text-xs text-muted-foreground">
                              {item.published}
                            </span>
                            {item.ai_summary && (
                              <Badge variant="warning">AI 角度</Badge>
                            )}
                          </div>
                          <h3 className="mt-2 font-medium leading-snug">
                            {item.title}
                          </h3>
                          <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">
                            {item.summary}
                          </p>
                          {item.ai_summary && (
                            <p className="mt-2 rounded-md bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-300">
                              {item.ai_summary}
                            </p>
                          )}
                          {item.url && (
                            <a
                              href={item.url}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="mt-2 inline-flex items-center gap-1 text-xs text-sky-400 hover:underline"
                            >
                              <ExternalLink className="h-3 w-3" />
                              查看来源
                            </a>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}

          {result.items.length > 0 && (
            <>
              <Separator />
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <span className="text-sm text-muted-foreground">
                  已选 <b className="text-foreground">{selected.length}</b>{" "}
                  条素材
                  {selected.length === 0 && "（勾选后可带入选题或直接排队）"}
                </span>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Button
                    variant="outline"
                    onClick={enqueueSelected}
                    disabled={selected.length === 0 || enqueuing}
                    className="w-full sm:w-auto"
                  >
                    {enqueuing ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <ListPlus className="h-4 w-4" />
                    )}
                    直接加入队列
                  </Button>
                  <Button
                    onClick={goTopic}
                    disabled={selected.length === 0}
                    className="w-full sm:w-auto"
                  >
                    去选题
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {!result && !loading && !error && (
        <EmptyState
          className="mt-8"
          icon={Flame}
          title="还没有搜索热点"
          description="输入关键词点「搜索热点」，或留空直接搜索账号定位相关的近期资讯。"
          action={
            <Button size="sm" onClick={handleSearch}>
              <Search className="h-3.5 w-3.5" />
              立即搜索
            </Button>
          }
        />
      )}
    </PageShell>
  );
}
