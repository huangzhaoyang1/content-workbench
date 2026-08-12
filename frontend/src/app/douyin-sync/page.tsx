"use client";

import * as React from "react";
import {
  Bookmark,
  Loader2,
  Play,
  Trash2,
  Download,
  Plus,
  RefreshCw,
  AlertTriangle,
  Clock,
  CheckCircle2,
  XCircle,
  Filter,
  Library,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { PageShell, PageHeader } from "@/components/layout/PageShell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { useRouter } from "next/navigation";
import { api, friendlyMessage } from "@/lib/api";
import { DissectPanel } from "@/components/dissect/DissectPanel";
import type {
  DouyinSyncState,
  DouyinSyncConfig,
  DouyinSyncRecord,
  DouyinSyncSource,
  DouyinSyncSourceKind,
  DouyinSyncRecordStatus,
  DouyinSyncRun,
  TopicLibraryItem,
} from "@/lib/types";

const STATUS_LABEL: Record<DouyinSyncRecordStatus, string> = {
  new: "待入库",
  imported: "已入库",
  ignored: "已忽略",
};
const STATUS_VARIANT: Record<DouyinSyncRecordStatus, "muted" | "success" | "warning"> = {
  new: "muted",
  imported: "success",
  ignored: "warning",
};

function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  if (n >= 10000) return `${(n / 10000).toFixed(1)}w`;
  return String(n);
}

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
      <span>{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </span>
  );
}

export default function DouyinSyncPage() {
  const { toast } = useToast();
  const router = useRouter();
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [state, setState] = React.useState<DouyinSyncState | null>(null);
  const [tab, setTab] = React.useState("config");
  const [outerTab, setOuterTab] = React.useState("dissect");

  // 配置编辑态
  const [cfg, setCfg] = React.useState<Partial<DouyinSyncConfig>>({});
  const [cookieDraft, setCookieDraft] = React.useState("");
  const [savingCfg, setSavingCfg] = React.useState(false);
  const [dirtyCfg, setDirtyCfg] = React.useState(false);

  // 立即同步（手动）
  const [manualUrls, setManualUrls] = React.useState("");
  const [running, setRunning] = React.useState(false);

  // 素材池
  const [records, setRecords] = React.useState<DouyinSyncRecord[]>([]);
  const [recLoading, setRecLoading] = React.useState(false);
  const [recError, setRecError] = React.useState<string | null>(null);
  const [filterStatus, setFilterStatus] = React.useState("");
  const [filterKeyword, setFilterKeyword] = React.useState("");
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const [confirmClear, setConfirmClear] = React.useState<null | "" | "ignored">(null);
  const [clearing, setClearing] = React.useState(false);

  // 运行历史
  const [runs, setRuns] = React.useState<DouyinSyncRun[]>([]);
  const [expandedRun, setExpandedRun] = React.useState<string | null>(null);

  // 抖音选题库（素材池沉淀进 topic_library、source=douyin_sync 的条目）
  const [dyTopics, setDyTopics] = React.useState<TopicLibraryItem[]>([]);
  const [dyLoading, setDyLoading] = React.useState(false);
  const loadDyTopics = React.useCallback(async () => {
    setDyLoading(true);
    try {
      const r = await api.dissectListTopics({ limit: 200 });
      setDyTopics(r.items.filter((i) => i.source === "douyin_sync"));
    } catch (e) {
      toast(friendlyMessage(e, "读取抖音选题库失败"), "error");
    } finally {
      setDyLoading(false);
    }
  }, [toast]);
  const dyStatusVariant = (s: string): "secondary" | "warning" | "success" => {
    if (s === "已完成") return "success";
    if (s === "生产中") return "warning";
    return "secondary";
  };

  const refreshState = React.useCallback(async () => {
    try {
      const s = await api.douyinSyncState();
      setState(s);
      setCfg({
        enabled: s.config.enabled,
        sources: s.config.sources,
        frequency: s.config.frequency,
        time: s.config.time,
        weekday: s.config.weekday,
        cron: s.config.cron,
        max_per_run: s.config.max_per_run,
        filters: s.config.filters,
      });
      setDirtyCfg(false);
    } catch (e) {
      setError(friendlyMessage(e, "读取抖音收藏同步状态失败"));
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshRecords = React.useCallback(async () => {
    setRecLoading(true);
    setRecError(null);
    try {
      const r = await api.douyinSyncRecords({
        status: filterStatus,
        keyword: filterKeyword,
        limit: 300,
      });
      setRecords(r.items);
      setSelected(new Set());
    } catch (e) {
      setRecError(friendlyMessage(e, "读取爬取记录失败"));
    } finally {
      setRecLoading(false);
    }
  }, [filterStatus, filterKeyword]);

  const refreshRuns = React.useCallback(async () => {
    try {
      const r = await api.douyinSyncRuns(20);
      setRuns(r.items);
    } catch {
      /* 非关键，忽略 */
    }
  }, []);

  React.useEffect(() => {
    void refreshState();
    void refreshRecords();
    void refreshRuns();
  }, [refreshState, refreshRecords, refreshRuns]);

  React.useEffect(() => {
    if (tab === "library") void loadDyTopics();
  }, [tab, loadDyTopics]);

  // ---- 配置编辑 ----
  const patchCfg = (patch: Partial<DouyinSyncConfig>) => {
    setCfg((c) => ({ ...c, ...patch }));
    setDirtyCfg(true);
  };

  const patchFilters = (patch: Partial<DouyinSyncConfig["filters"]>) => {
    const base: DouyinSyncConfig["filters"] = cfg.filters ?? {
      min_digg: 0,
      min_text_len: 0,
      keywords: [],
      exclude_keywords: [],
    };
    patchCfg({ filters: { ...base, ...patch } });
  };

  const addSource = () => {
    const src: DouyinSyncSource = {
      id: Math.random().toString(36).slice(2, 10),
      name: "",
      url: "",
      kind: "profile",
      enabled: true,
    };
    patchCfg({ sources: [...(cfg.sources ?? []), src] });
  };
  const updateSource = (id: string, patch: Partial<DouyinSyncSource>) => {
    patchCfg({
      sources: (cfg.sources ?? []).map((s) => (s.id === id ? { ...s, ...patch } : s)),
    });
  };
  const removeSource = (id: string) => {
    patchCfg({ sources: (cfg.sources ?? []).filter((s) => s.id !== id) });
  };

  const saveConfig = async () => {
    setSavingCfg(true);
    try {
      const payload: Partial<DouyinSyncConfig> = {
        enabled: cfg.enabled ?? false,
        sources: cfg.sources ?? [],
        frequency: cfg.frequency ?? "daily",
        time: cfg.time ?? "09:00",
        weekday: cfg.weekday ?? 0,
        cron: cfg.cron ?? "0 9 * * *",
        max_per_run: cfg.max_per_run ?? 10,
        filters: cfg.filters ?? {
          min_digg: 0,
          min_text_len: 0,
          keywords: [],
          exclude_keywords: [],
        },
      };
      if (cookieDraft.trim()) payload.cookie = cookieDraft.trim();
      const saved = await api.douyinSyncSaveConfig(payload);
      setState((s) => (s ? { ...s, config: saved } : s));
      setCfg({
        enabled: saved.enabled,
        sources: saved.sources,
        frequency: saved.frequency,
        time: saved.time,
        weekday: saved.weekday,
        cron: saved.cron,
        max_per_run: saved.max_per_run,
        filters: saved.filters,
      });
      setCookieDraft("");
      setDirtyCfg(false);
      toast("配置已保存", "success");
    } catch (e) {
      toast(friendlyMessage(e, "保存配置失败"), "error");
    } finally {
      setSavingCfg(false);
    }
  };

  // ---- 立即同步 ----
  const runSync = async (urls: string[]) => {
    setRunning(true);
    try {
      const res = await api.douyinSyncRun(urls);
      toast(res.summary || "同步完成", "success");
      await refreshState();
      await refreshRecords();
      await refreshRuns();
    } catch (e) {
      toast(friendlyMessage(e, "同步失败，可能是抖音反爬或链接失效"), "error");
    } finally {
      setRunning(false);
    }
  };

  // ---- 素材池操作 ----
  const toggleSelect = (id: string) => {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };
  const toggleSelectAll = () => {
    setSelected((s) =>
      s.size === records.length ? new Set() : new Set(records.map((r) => r.id))
    );
  };

  const importSelected = async (priority: string) => {
    const ids = Array.from(selected);
    if (!ids.length) return;
    try {
      const res = await api.douyinSyncImport(ids, priority);
      toast(
        res.failed
          ? `已入库 ${res.imported} 条，失败 ${res.failed}`
          : `已入库 ${res.imported} 条到选题库`,
        {
          type: res.failed ? "warning" : "success",
          action: {
            label: "去选题库查看",
            onClick: () => router.push("/dissect"),
          },
        }
      );
      await refreshRecords();
      await refreshState();
    } catch (e) {
      toast(friendlyMessage(e, "选入选题库失败"), "error");
    }
  };

  const importSingle = async (id: string) => {
    try {
      const res = await api.douyinSyncImport([id], "中");
      if (res.imported) {
        toast("已加入选题库", {
          type: "success",
          action: {
            label: "去选题库查看",
            onClick: () => router.push("/dissect"),
          },
        });
      } else {
        toast("加入失败", "error");
      }
      await refreshRecords();
      await refreshState();
    } catch (e) {
      toast(friendlyMessage(e, "选入选题库失败"), "error");
    }
  };

  const deleteRecord = async (id: string) => {
    try {
      await api.douyinSyncDeleteRecord(id);
      setRecords((rs) => rs.filter((r) => r.id !== id));
      setSelected((s) => {
        const n = new Set(s);
        n.delete(id);
        return n;
      });
      await refreshState();
    } catch (e) {
      toast(friendlyMessage(e, "删除失败"), "error");
    }
  };

  const updateRecord = async (rec: DouyinSyncRecord, patch: { title?: string; note?: string; text?: string }) => {
    try {
      await api.douyinSyncUpdateRecord(rec.id, patch);
      setRecords((rs) => rs.map((r) => (r.id === rec.id ? { ...r, ...patch } : r)));
      toast("已保存修改", "success");
    } catch (e) {
      toast(friendlyMessage(e, "保存失败"), "error");
    }
  };

  const doClear = async () => {
    setClearing(true);
    try {
      await api.douyinSyncClearRecords(confirmClear ?? "");
      toast("已清空", "success");
      setConfirmClear(null);
      await refreshRecords();
      await refreshState();
    } catch (e) {
      toast(friendlyMessage(e, "清空失败"), "error");
    } finally {
      setClearing(false);
    }
  };

  const counts = state?.counts;
  const config = state?.config;

  return (
    <PageShell width="xl">
      <PageHeader
        title="抖音线"
        description="抖音爆款两条路：即时拆解爆款文案一键成稿，或把收藏夹沉淀成素材池。"
      />

      <Tabs defaultValue="dissect" value={outerTab} onValueChange={setOuterTab} className="mt-5">
        <TabsList className="flex-wrap">
          <TabsTrigger value="dissect">① 即时拆解</TabsTrigger>
          <TabsTrigger value="sync">② 收藏沉淀</TabsTrigger>
        </TabsList>

        <TabsContent value="dissect">
          <DissectPanel />
        </TabsContent>

        <TabsContent value="sync">
          {loading && (
        <div className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-border px-6 py-12 text-sm text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" /> 正在读取状态…
        </div>
      )}

      {!loading && error && <ErrorState message={error} title="加载失败" />}

      {!loading && !error && state && (
        <>
          {/* 状态条 + 立即同步 */}
          <Card className="mb-5">
            <CardContent className="flex flex-wrap items-center gap-4 p-4">
              <div className="flex flex-col">
                <span className="text-xs text-muted-foreground">素材总数</span>
                <span className="text-2xl font-semibold">{state.total}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="muted">待入库 {counts?.new ?? 0}</Badge>
                <Badge variant="success">已入库 {counts?.imported ?? 0}</Badge>
                <Badge variant="warning">已忽略 {counts?.ignored ?? 0}</Badge>
              </div>
              <div className="ml-auto flex flex-col items-end gap-2">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5" />
                    {config?.freq_label ?? "—"}
                  </span>
                  <span>下次：{state.next_run ?? "未启用"}</span>
                  <span>上次：{state.last_result ?? "—"}</span>
                </div>
                <Button onClick={() => runSync([])} disabled={running}>
                  {running ? (
                    <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="mr-1.5 h-4 w-4" />
                  )}
                  立即同步
                </Button>
              </div>
            </CardContent>
          </Card>

          <Tabs defaultValue="config" value={tab} onValueChange={setTab}>
            <TabsList className="flex-wrap">
              <TabsTrigger value="config">
                <Bookmark className="mr-1.5 h-3.5 w-3.5" />
                配置
              </TabsTrigger>
              <TabsTrigger value="pool">
                <Filter className="mr-1.5 h-3.5 w-3.5" />
                素材池（{state.total}）
              </TabsTrigger>
              <TabsTrigger value="history">
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                运行历史
              </TabsTrigger>
              <TabsTrigger value="library">
                <Library className="mr-1.5 h-3.5 w-3.5" />
                抖音选题库
              </TabsTrigger>
            </TabsList>

            {/* ----------------- 配置 ----------------- */}
            <TabsContent value="config">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>同步设置</CardTitle>
                      <CardDescription>
                        抖音网页端反爬很严，收藏夹 / 主页一般要登录。粘贴你自己的 Cookie 成功率更高；
                        也可以只用「手动粘贴链接」。
                      </CardDescription>
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                      启用定时
                      <Switch
                        checked={cfg.enabled ?? false}
                        onCheckedChange={(v) => patchCfg({ enabled: v })}
                      />
                    </label>
                  </div>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* 来源 */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label className="text-sm font-medium">抖音来源</Label>
                      <Button variant="outline" size="sm" onClick={addSource}>
                        <Plus className="mr-1 h-3.5 w-3.5" /> 添加来源
                      </Button>
                    </div>
                    {(cfg.sources ?? []).length === 0 && (
                      <p className="text-xs text-muted-foreground">
                        还没有来源。添加抖音主页 / 收藏夹链接，或直接在下方「手动粘贴链接」跑一次。
                      </p>
                    )}
                    {(cfg.sources ?? []).map((s) => (
                      <div key={s.id} className="rounded-lg border border-border p-3">
                        <div className="flex flex-wrap items-end gap-2">
                          <div className="flex-1 min-w-[160px]">
                            <Label className="text-xs text-muted-foreground">名称</Label>
                            <Input
                              value={s.name}
                              placeholder="如：我的收藏夹"
                              onChange={(e) => updateSource(s.id, { name: e.target.value })}
                            />
                          </div>
                          <div className="w-32">
                            <Label className="text-xs text-muted-foreground">类型</Label>
                            <Select
                              value={s.kind}
                              onChange={(e) => updateSource(s.id, { kind: e.target.value as DouyinSyncSourceKind })}
                            >
                              <option value="favorite">收藏夹</option>
                              <option value="profile">个人主页</option>
                            </Select>
                          </div>
                          <label className="flex items-center gap-2 pb-2 text-sm">
                            启用
                            <Switch
                              checked={s.enabled}
                              onCheckedChange={(v) => updateSource(s.id, { enabled: v })}
                            />
                          </label>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive"
                            onClick={() => removeSource(s.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                        <div className="mt-2">
                          <Label className="text-xs text-muted-foreground">链接</Label>
                          <Input
                            value={s.url}
                            placeholder="https://www.douyin.com/user/xxx 或 收藏夹链接"
                            onChange={(e) => updateSource(s.id, { url: e.target.value })}
                          />
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* 频率 */}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <Label className="text-sm font-medium">频率</Label>
                      <Select
                        value={cfg.frequency ?? "daily"}
                        onChange={(e) => patchCfg({ frequency: e.target.value as DouyinSyncConfig["frequency"] })}
                      >
                        <option value="daily">每天</option>
                        <option value="weekly">每周</option>
                        <option value="cron">自定义 cron</option>
                      </Select>
                    </div>
                    {cfg.frequency === "daily" && (
                      <div>
                        <Label className="text-sm font-medium">执行时间</Label>
                        <Input
                          type="time"
                          value={cfg.time ?? "09:00"}
                          onChange={(e) => patchCfg({ time: e.target.value })}
                        />
                      </div>
                    )}
                    {cfg.frequency === "weekly" && (
                      <>
                        <div>
                          <Label className="text-sm font-medium">星期几</Label>
                          <Select
                            value={String(cfg.weekday ?? 0)}
                            onChange={(e) => patchCfg({ weekday: Number(e.target.value) })}
                          >
                            {["周一", "周二", "周三", "周四", "周五", "周六", "周日"].map((w, i) => (
                              <option key={w} value={String(i)}>{w}</option>
                            ))}
                          </Select>
                        </div>
                        <div>
                          <Label className="text-sm font-medium">执行时间</Label>
                          <Input
                            type="time"
                            value={cfg.time ?? "09:00"}
                            onChange={(e) => patchCfg({ time: e.target.value })}
                          />
                        </div>
                      </>
                    )}
                    {cfg.frequency === "cron" && (
                      <div>
                        <Label className="text-sm font-medium">cron 表达式</Label>
                        <Input
                          value={cfg.cron ?? "0 9 * * *"}
                          placeholder="0 9 * * *"
                          onChange={(e) => patchCfg({ cron: e.target.value })}
                        />
                      </div>
                    )}
                    <div>
                      <Label className="text-sm font-medium">每次最多抓（条）</Label>
                      <Input
                        type="number"
                        min={1}
                        max={50}
                        value={cfg.max_per_run ?? 10}
                        onChange={(e) => patchCfg({ max_per_run: Number(e.target.value) || 10 })}
                      />
                    </div>
                  </div>

                  {/* Cookie */}
                  <div>
                    <Label className="text-sm font-medium">抖音登录 Cookie（选填，提高成功率）</Label>
                    <Textarea
                      value={cookieDraft}
                      placeholder={
                        config?.cookie_set ? "已配置 Cookie，留空表示不修改；要更新就粘贴新的" : "粘贴浏览器里抖音的 Cookie（在 DevTools → Network → 任意请求 → Request Headers 复制）"
                      }
                      rows={2}
                      onChange={(e) => {
                        setCookieDraft(e.target.value);
                        setDirtyCfg(true);
                      }}
                    />
                    {config?.cookie_set && (
                      <p className="mt-1 text-xs text-success">✓ 已保存 Cookie（出于安全不回传明文）</p>
                    )}
                  </div>

                  {/* 筛选 */}
                  <div className="space-y-3 rounded-lg border border-border p-3">
                    <Label className="text-sm font-medium">筛选条件（不满足的自动跳过）</Label>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <Label className="text-xs text-muted-foreground">最小点赞数</Label>
                        <Input
                          type="number"
                          min={0}
                          value={cfg.filters?.min_digg ?? 0}
                          onChange={(e) => patchFilters({ min_digg: Number(e.target.value) || 0 })}
                        />
                      </div>
                      <div>
                        <Label className="text-xs text-muted-foreground">最小文案字数</Label>
                        <Input
                          type="number"
                          min={0}
                          value={cfg.filters?.min_text_len ?? 0}
                          onChange={(e) => patchFilters({ min_text_len: Number(e.target.value) || 0 })}
                        />
                      </div>
                      <div>
                        <Label className="text-xs text-muted-foreground">包含关键词（逗号分隔）</Label>
                        <Input
                          value={(cfg.filters?.keywords ?? []).join("，")}
                          placeholder="AI，副业"
                          onChange={(e) =>
                            patchFilters({
                              keywords: e.target.value.split(/[，,]/).map((x) => x.trim()).filter(Boolean),
                            })
                          }
                        />
                      </div>
                      <div>
                        <Label className="text-xs text-muted-foreground">排除关键词（逗号分隔）</Label>
                        <Input
                          value={(cfg.filters?.exclude_keywords ?? []).join("，")}
                          placeholder="广告，带货"
                          onChange={(e) =>
                            patchFilters({
                              exclude_keywords: e.target.value.split(/[，,]/).map((x) => x.trim()).filter(Boolean),
                            })
                          }
                        />
                      </div>
                    </div>
                  </div>

                  {/* 手动粘贴链接 */}
                  <div className="space-y-2 rounded-lg border border-dashed border-border p-3">
                    <Label className="text-sm font-medium">手动粘贴链接，立即跑一次（100% 可用）</Label>
                    <Textarea
                      value={manualUrls}
                      placeholder="每行一条抖音链接，例如 https://v.douyin.com/xxxx/ 或 https://www.douyin.com/video/xxxxx"
                      rows={3}
                      onChange={(e) => setManualUrls(e.target.value)}
                    />
                    <Button
                      variant="outline"
                      onClick={() =>
                        runSync(manualUrls.split(/\s+/).map((x) => x.trim()).filter(Boolean))
                      }
                      disabled={running || !manualUrls.trim()}
                    >
                      {running ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Play className="mr-1.5 h-4 w-4" />}
                      抓取这些链接
                    </Button>
                  </div>

                  <div className="flex justify-end">
                    <Button onClick={saveConfig} disabled={savingCfg || !dirtyCfg}>
                      {savingCfg ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
                      保存配置
                    </Button>
                  </div>
                  {!dirtyCfg && (
                    <p className="text-right text-xs text-muted-foreground">配置无改动</p>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* ----------------- 素材池 ----------------- */}
            <TabsContent value="pool">
              <div className="space-y-4">
                {/* 筛选 + 批量操作 */}
                <div className="flex flex-wrap items-end gap-2">
                  <div className="w-32">
                    <Label className="text-xs text-muted-foreground">状态</Label>
                    <Select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
                      <option value="">全部</option>
                      <option value="new">待入库</option>
                      <option value="imported">已入库</option>
                      <option value="ignored">已忽略</option>
                    </Select>
                  </div>
                  <div className="flex-1 min-w-[180px]">
                    <Label className="text-xs text-muted-foreground">关键词</Label>
                    <Input
                      value={filterKeyword}
                      placeholder="标题 / 作者 / 文案"
                      onChange={(e) => setFilterKeyword(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") refreshRecords();
                      }}
                    />
                  </div>
                  <Button variant="outline" onClick={refreshRecords} disabled={recLoading}>
                    {recLoading ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-1.5 h-4 w-4" />}
                    刷新
                  </Button>
                  {records.length > 0 && (
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={selected.size === records.length} onChange={toggleSelectAll} />
                      全选
                    </label>
                  )}
                  <Button
                    variant="default"
                    onClick={() => importSelected("中")}
                    disabled={selected.size === 0}
                  >
                    <Download className="mr-1.5 h-4 w-4" />
                    选入选题库（{selected.size}）
                  </Button>
                  <Button
                    variant="ghost"
                    className="text-destructive"
                    onClick={() => setConfirmClear("")}
                  >
                    <Trash2 className="mr-1.5 h-4 w-4" /> 清空全部
                  </Button>
                </div>

                {recError && <ErrorState message={recError} title="读取失败" />}

                {!recError && records.length === 0 && (
                  <EmptyState
                    icon={Bookmark}
                    title="素材池还是空的"
                    description="先在「配置」里添加抖音主页 / 收藏夹并启用定时，或直接粘贴链接点「抓取这些链接」。定时任务到点会自动往这里灌素材。"
                  />
                )}

                <div className="space-y-3">
                  {records.map((r) => (
                    <Card key={r.id}>
                      <CardContent className="space-y-2 p-4">
                        <div className="flex items-start gap-3">
                          <input
                            type="checkbox"
                            className="mt-1.5"
                            checked={selected.has(r.id)}
                            onChange={() => toggleSelect(r.id)}
                          />
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-medium">{r.title || "（无标题）"}</span>
                              <Badge variant={STATUS_VARIANT[r.status]}>{STATUS_LABEL[r.status]}</Badge>
                              {r.author && <span className="text-xs text-muted-foreground">@{r.author}</span>}
                              <span className="text-xs text-muted-foreground">· {r.source_name}</span>
                              {r.complete === false && <Badge variant="warning">可能不完整</Badge>}
                            </div>
                            {r.desc && (
                              <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{r.desc}</p>
                            )}
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              <StatPill label="赞" value={fmtNum(r.stats.digg)} />
                              <StatPill label="评" value={fmtNum(r.stats.comment)} />
                              <StatPill label="藏" value={fmtNum(r.stats.collect)} />
                              <StatPill label="转" value={fmtNum(r.stats.share)} />
                              {(r.hashtags ?? []).slice(0, 4).map((t) => (
                                <Badge key={t} variant="muted">#{t}</Badge>
                              ))}
                            </div>

                            {expandedId === r.id && (
                              <div className="mt-3 space-y-2 rounded-lg border border-border bg-muted/40 p-3">
                                <div>
                                  <Label className="text-xs text-muted-foreground">标题</Label>
                                  <Input
                                    defaultValue={r.title}
                                    id={`title-${r.id}`}
                                  />
                                </div>
                                <div>
                                  <Label className="text-xs text-muted-foreground">笔记</Label>
                                  <Input
                                    defaultValue={r.note}
                                    id={`note-${r.id}`}
                                    placeholder="标注：准备什么时候用 / 适合什么选题"
                                  />
                                </div>
                                <Textarea
                                  defaultValue={r.text}
                                  rows={4}
                                  id={`text-${r.id}`}
                                  className="text-xs"
                                />
                                <div className="flex justify-end gap-2">
                                  <Button
                                    size="sm"
                                    onClick={() => {
                                      const title = (document.getElementById(`title-${r.id}`) as HTMLInputElement)?.value ?? r.title;
                                      const note = (document.getElementById(`note-${r.id}`) as HTMLInputElement)?.value ?? r.note;
                                      const text = (document.getElementById(`text-${r.id}`) as HTMLTextAreaElement)?.value ?? r.text;
                                      void updateRecord(r, { title, note, text });
                                    }}
                                  >
                                    保存修改
                                  </Button>
                                </div>
                              </div>
                            )}
                          </div>
                          <div className="flex shrink-0 flex-col items-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setExpandedId(expandedId === r.id ? null : r.id)}
                            >
                              {expandedId === r.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => void importSingle(r.id)}
                            >
                              <Download className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive"
                              onClick={() => void deleteRecord(r.id)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            </TabsContent>

            {/* ----------------- 运行历史 ----------------- */}
            <TabsContent value="history">
              {runs.length === 0 ? (
                <EmptyState
                  icon={RefreshCw}
                  title="还没有运行记录"
                  description="点「立即同步」或等定时任务触发后，这里会显示每次抓取的结果。"
                />
              ) : (
                <div className="space-y-3">
                  {runs.map((run) => (
                    <Card key={run.id}>
                      <CardContent className="space-y-2 p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={run.failed ? "warning" : "success"}>
                            {run.trigger === "schedule" ? "定时" : "手动"}
                          </Badge>
                          <span className="text-sm font-medium">{run.started_at}</span>
                          <span className="text-xs text-muted-foreground">耗时 {run.elapsed_sec}s</span>
                          <div className="ml-auto flex flex-wrap gap-1.5">
                            <StatPill label="新增" value={String(run.added)} />
                            <StatPill label="跳过" value={String(run.skipped)} />
                            <StatPill label="过滤" value={String(run.filtered)} />
                            <StatPill label="失败" value={String(run.failed)} />
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setExpandedRun(expandedRun === run.id ? null : run.id)}
                          >
                            {expandedRun === run.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                          </Button>
                        </div>
                        {expandedRun === run.id && (
                          <ul className="space-y-1 rounded-lg border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
                            {run.messages.length === 0 && <li>无详情</li>}
                            {run.messages.map((m, i) => (
                              <li key={i} className="flex gap-1.5">
                                {m.includes("失败") ? <XCircle className="mt-0.5 h-3.5 w-3.5 text-destructive" /> : <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 text-success" />}
                                <span>{m}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* ----------------- 抖音选题库 ----------------- */}
            <TabsContent value="library">
              <Card>
                <CardHeader>
                  <CardTitle>抖音选题库</CardTitle>
                  <CardDescription>
                    从「素材池」选入选题库、来源为抖音同步的选题会集中展示在这里，可直接拿去生产。
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {dyLoading ? (
                    <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
                    </div>
                  ) : dyTopics.length === 0 ? (
                    <EmptyState
                      icon={Bookmark}
                      title="还没有从抖音沉淀的选题"
                      description="在「素材池」勾选抖音视频，点「选入选题库」后，它们会出现在这里。"
                      action={
                        <Button size="sm" variant="outline" onClick={() => void loadDyTopics()}>
                          <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> 刷新
                        </Button>
                      }
                    />
                  ) : (
                    <div className="space-y-2">
                      {dyTopics.map((t) => (
                        <div
                          key={t.id}
                          className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-3 py-2"
                        >
                          <span className="min-w-0 flex-1 truncate text-sm font-medium">
                            {t.title}
                          </span>
                          <Badge variant="muted">抖音同步</Badge>
                          <Badge variant={dyStatusVariant(t.status)}>{t.status}</Badge>
                          <span className="text-xs text-muted-foreground">
                            {t.updated_at || t.created_at}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </>
      )}
        </TabsContent>
      </Tabs>

      {/* 清空确认 */}
      <ConfirmDialog
        open={confirmClear !== null}
        title="确认清空爬取记录？"
        description={
          confirmClear === "ignored"
            ? "将删除所有「已忽略」的记录，已入库的会保留。"
            : "将删除所有爬取记录（含已入库的）。此操作不可撤销。"
        }
        confirmText="清空"
        destructive
        loading={clearing}
        onConfirm={doClear}
        onCancel={() => setConfirmClear(null)}
      />

      {!loading && !error && state && state.total > 0 && (
        <Alert variant="warning" className="mt-5">
          <AlertDescription>
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                抖音反爬很严：收藏夹 / 主页很可能抓不到链接（需要登录 Cookie）。最稳的路子是「手动粘贴链接」——
                每条都能 100% 抓到结构化文案。定时任务适合在已配 Cookie 时用。
              </span>
            </div>
          </AlertDescription>
        </Alert>
      )}
    </PageShell>
  );
}
