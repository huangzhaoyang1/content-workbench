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
  QrCode,
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

/** 客户端纯 JS 的 Cookie 头解析（与后端 _parse_cookie_header 行为一致）。
 *  用于「用户在输入框粘贴时实时诊断」，不上行。
 *
 * 关键优化：识别 Set-Cookie 单条格式（带 Domain/Path/Expires/HttpOnly 等
 * 属性），那是 Response Headers 里的，不是请求头 Cookie 行。
 */
const SET_COOKIE_ATTR_NAMES = new Set([
  "Domain",
  "Path",
  "Expires",
  "Max-Age",
  "SameSite",
  "Priority",
  "Partitioned",
]);
// 登录态的「关键字段」—— 粘的 Cookie 里有 ≥ 1 才有可能是登录态。
const LOGIN_KEY_FIELDS = [
  "sessionid",
  "msToken",
  "sid_tt",
  "uid_tt",
  "passport_csrf_token",
  "odin_tt",
] as const;

function parseCookieHeader(raw: string): {
  count: number;
  names: string[];
  looksLikeSetCookie: boolean;
} {
  const s = (raw || "").trim();
  if (!s) return { count: 0, names: [], looksLikeSetCookie: false };
  // 检测「Set-Cookie 单条」特征：含 Domain= 或 Path= 或裸 HttpOnly/Secure
  const looksLikeSetCookie =
    /(?:\b|;)\s*(Domain|Path|Expires|Max-Age|SameSite|Priority)\s*=/i.test(s) ||
    /;\s*(Secure|HttpOnly)\s*(?:;|$)/i.test(s);
  const names: string[] = [];
  // 还原后端的过滤逻辑：
  //   name=value 才进；name ∈ SET_COOKIE_ATTR_NAMES 跳过；裸 Secure/HttpOnly 跳过
  // 用字符串 split + indexOf 实现，避开 tsconfig target=es5 不能迭代 RegExpStringIterator 的限制
  for (const part of s.split(";")) {
    const eq = part.indexOf("=");
    if (eq <= 0) continue;
    const name = part.slice(0, eq).trim();
    let val = part.slice(eq + 1).trim();
    if (val.startsWith('"') && val.endsWith('"') && val.length >= 2) {
      val = val.slice(1, -1);
    }
    if (!name || !val) continue;
    if (SET_COOKIE_ATTR_NAMES.has(name)) continue;
    if (names.includes(name)) continue;
    names.push(name);
  }
  return { count: names.length, names, looksLikeSetCookie };
}

function CookieDiagnostics({ value }: { value: string }) {
  const { count, names, looksLikeSetCookie } = React.useMemo(
    () => parseCookieHeader(value),
    [value]
  );
  if (!value.trim()) return null;
  const nameSet = new Set(names.map((n) => n.toLowerCase()));
  const hitLoginFields = LOGIN_KEY_FIELDS.filter((f) =>
    nameSet.has(f.toLowerCase())
  );
  // 等级：
  //   - looksLikeSetCookie → 红色：八成复制错了
  //   - count < 3 → 黄色：登录态 cookie 通常 ≥ 5 条
  //   - count >= 3 且 hitLoginFields → 绿色：看起来完整
  const errLevel: "error" | "warn" | "ok" = looksLikeSetCookie
    ? "error"
    : count < 3
      ? "warn"
      : hitLoginFields.length === 0
        ? "warn"
        : "ok";
  const wrapClass =
    errLevel === "error"
      ? "border-destructive/40 bg-destructive/10 text-destructive"
      : errLevel === "warn"
        ? "border-warning/40 bg-warning/10 text-warning-foreground"
        : "border-success/40 bg-success/10 text-success";
  return (
    <div className={`rounded-md border px-2.5 py-1.5 text-[11px] ${wrapClass}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-medium">
        <span>解析出 {count} 条 cookie</span>
        <span>·</span>
        <span>长度 {value.length} 字符</span>
        {hitLoginFields.length > 0 && (
          <>
            <span>·</span>
            <span>命中登录关键字段：{hitLoginFields.join(", ")}</span>
          </>
        )}
      </div>
      {errLevel !== "ok" && (
        <div className="mt-1 text-[11px] leading-relaxed opacity-90">
          {looksLikeSetCookie
            ? "⚠ 这看起来是「Response Headers → Set-Cookie」单条 cookie（含 Domain/Path/Expires 等属性），不是「Request Headers → Cookie」整段。请重新复制：Network 面板 → 任意请求 → 找 Cookie: 那一整行（每条 k=v，用 ; 空格分隔）。"
            : count < 3
              ? "⚠ 太短了：登录态 Cookie 通常 ≥ 5 条；当前很可能只粘了单条 cookie，请去 Network → Cookie 行复制完整内容。"
              : "⚠ 还没有 sessionid / msToken / odin_tt 这些关键登录字段，登录态可能无效，建议去 Network → Cookie 行再复制一次。"}
        </div>
      )}
      {errLevel === "ok" && (
        <div className="mt-1 text-[11px] leading-relaxed opacity-90">
          ✓ 看起来是完整的登录态 Cookie，按下面保存即可。
        </div>
      )}
    </div>
  );
}

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

  // 抖音扫码持久登录（Playwright）状态
  const [sessionStatus, setSessionStatus] = React.useState<{
    exists: boolean;
    logged_in: boolean;
    cookie_count: number;
    markers: string[];
    note?: string;
    error?: string;
  } | null>(null);
  const [loggingIn, setLoggingIn] = React.useState(false);
  const [loginError, setLoginError] = React.useState<string | null>(null);

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

  // 读取扫码登录状态（是否已登录 / cookie 数 / 命中哪些登录标记）
  const refreshSessionStatus = React.useCallback(async () => {
    try {
      const s = await api.douyinSyncSessionStatus();
      setSessionStatus(s);
    } catch {
      /* 后端没装 playwright 时会失败，忽略（手动 cookie 仍可用） */
    }
  }, []);

  // 触发扫码登录：弹出真实浏览器窗口等用户手机扫码（阻塞到扫码或超时）
  const handleLogin = async () => {
    setLoggingIn(true);
    setLoginError(null);
    try {
      const r = await api.douyinSyncLogin(300);
      if (r.ok) {
        toast(r.already ? "已是登录态，无需重扫" : "扫码登录成功，会话已保存（自动续期）", "success");
        await refreshSessionStatus();
      } else {
        setLoginError(r.error || "登录失败");
        toast(r.error || "登录失败，请重试", "error");
      }
    } catch (e) {
      const msg = friendlyMessage(e, "登录请求失败（需在本机运行后端）");
      setLoginError(msg);
      toast(msg, "error");
    } finally {
      setLoggingIn(false);
    }
  };

  React.useEffect(() => {
    void refreshState();
    void refreshRecords();
    void refreshRuns();
    void refreshSessionStatus();
  }, [refreshState, refreshRecords, refreshRuns, refreshSessionStatus]);

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
      const savedCookie = !!saved.cookie_set;
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
      // 区分 toast：保存了 cookie → 给引导跳回拆解；普通配置保存 → 一句话。
      if (savedCookie) {
        toast("Cookie 已保存，现在可以回去拆解视频了", {
          type: "success",
          action: {
            label: "去拆解视频",
            // 优先切到本页的「即时拆解」outer tab（不离开页面），
            // 用 router 作为兜底（页面销毁也能跳过去）
            onClick: () => {
              try {
                setOuterTab("dissect");
              } catch {
                /* noop */
              }
              router.push("/dissect");
            },
          },
        });
      } else {
        toast("配置已保存", "success");
      }
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
                        抖音网页端反爬很严，收藏夹 / 主页一般要登录。推荐用上方「抖音登录（扫码）」
                        一次扫码、自动续期；不想扫码也能用「手动粘贴 Cookie」或只用「手动粘贴链接」。
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

                  {/* 抖音登录（扫码，主路径）：扫码一次，会话持久化 + 自动续期，告别手动复制 */}
                  <div className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <Label className="text-sm font-medium">
                        抖音登录
                        <span className="ml-2 text-xs font-normal text-muted-foreground">
                          推荐：扫码一次，会话自动续期，再也不用手动复制 Cookie
                        </span>
                      </Label>
                      {sessionStatus?.logged_in ? (
                        <Badge variant="success">
                          <CheckCircle2 className="mr-1 h-3 w-3" /> 已登录（自动续期）
                        </Badge>
                      ) : sessionStatus?.exists ? (
                        <Badge variant="warning">
                          <XCircle className="mr-1 h-3 w-3" /> 会话已过期
                        </Badge>
                      ) : (
                        <Badge variant="muted">未登录</Badge>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      {loggingIn ? (
                        <Button size="sm" disabled className="gap-1.5">
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          正在等待扫码…（请在弹出的浏览器窗口用手机扫码）
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          className="gap-1.5"
                          onClick={handleLogin}
                          disabled={savingCfg}
                        >
                          <QrCode className="h-3.5 w-3.5" />
                          {sessionStatus?.logged_in ? "重新登录" : "抖音登录（扫码）"}
                        </Button>
                      )}
                      <p className="text-xs text-muted-foreground">
                        点一下会弹出抖音网页，手机扫码登录后窗口自动关闭。
                      </p>
                    </div>

                    {loginError && (
                      <p className="text-xs text-destructive">
                        登录失败：{loginError}（需在「本机」运行后端才能弹窗扫码）
                      </p>
                    )}
                    {sessionStatus?.logged_in && (
                      <p className="text-xs text-muted-foreground">
                        已读取到 {sessionStatus.cookie_count} 条 cookie，命中登录标记：
                        {sessionStatus.markers.join("、") || "（无）"}。会话过期时点「重新登录」即可续期。
                      </p>
                    )}
                    {!sessionStatus && (
                      <p className="text-xs text-muted-foreground">
                        后端未启用 Playwright 扫码登录（可选）；不影响下面「手动粘贴 Cookie」方式。
                      </p>
                    )}
                  </div>

                  {/* Cookie（手动粘贴，备选路径） */}
                  <div className="space-y-2 rounded-lg border border-border p-3">
                    <div className="flex items-center justify-between gap-2">
                      <Label className="text-sm font-medium">
                        手动粘贴 Cookie
                        <span className="ml-2 text-xs font-normal text-muted-foreground">
                          （备选）扫码登录用不了时，才用这个：复制浏览器 Cookie 整段粘贴
                        </span>
                      </Label>
                      {config?.cookie_set ? (
                        <Badge variant="success">已保存</Badge>
                      ) : (
                        <Badge variant="muted">未配置</Badge>
                      )}
                    </div>
                    <Textarea
                      value={cookieDraft}
                      placeholder={
                        config?.cookie_set
                          ? "已配置 Cookie；留空表示不修改，要更新就粘贴新的"
                          : "粘贴这里（建议选 Network 面板第一个请求 → Request Headers → cookie: 冒号后面的整段，多对 k=v 用「; 」分隔）"
                      }
                      rows={3}
                      className="font-mono text-xs"
                      onChange={(e) => {
                        setCookieDraft(e.target.value);
                        setDirtyCfg(true);
                      }}
                    />
                    {/* 实时诊断：粘贴即判，避免「保存后发现没用」再来回试 */}
                    <CookieDiagnostics value={cookieDraft} />
                    {cookieDraft && (
                      <div className="flex justify-end">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setCookieDraft("");
                            setDirtyCfg(true);
                          }}
                          className="h-6 text-[11px] text-muted-foreground"
                        >
                          清空
                        </Button>
                      </div>
                    )}
                    <p className="text-xs text-muted-foreground">
                      出于安全，保存后前端只回传「是否已配置」状态，不回传明文；失效时需重新粘贴。
                    </p>
                    {/* 5 步式引导（核心解决「用户不会复制 Cookie」的卡点） */}
                    <details className="group rounded-md bg-muted/50">
                      <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium text-foreground">
                        如何获取抖音 Cookie？点开看 5 步走
                      </summary>
                      <ol className="space-y-1.5 px-3 pb-3 pl-7 pt-1 text-xs text-muted-foreground">
                        <li>
                          <span className="font-semibold text-foreground">①</span>{" "}
                          Chrome / Edge 浏览器打开{" "}
                          <a
                            href="https://www.douyin.com"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary underline underline-offset-2"
                          >
                            https://www.douyin.com
                          </a>{" "}
                          并登录你自己的账号
                        </li>
                        <li>
                          <span className="font-semibold text-foreground">②</span>{" "}
                          按 <kbd className="rounded border bg-background px-1">F12</kbd>{" "}
                          打开「开发者工具」，切到{" "}
                          <span className="font-medium text-foreground">Network（网络）</span>{" "}
                          标签
                        </li>
                        <li>
                          <span className="font-semibold text-foreground">③</span>{" "}
                          刷新页面（<kbd className="rounded border bg-background px-1">F5</kbd>），
                          点击列表里第一个请求（如 aweme / www.douyin.com）
                        </li>
                        <li>
                          <span className="font-semibold text-foreground">④</span>{" "}
                          在右侧{" "}
                          <span className="font-medium text-foreground">Request Headers（请求头）</span>{" "}
                          里找到 <code className="rounded bg-background px-1">cookie:</code>{" "}
                          那一整行，<span className="font-semibold text-foreground">只复制冒号后面的值</span>
                          ；
                          <span className="text-destructive"> 别选 Response 那边的 Set-Cookie（只有一两条）</span>
                        </li>
                        <li>
                          <span className="font-semibold text-foreground">⑤</span>{" "}
                          粘贴到上方文本框 → 看到「解析出 ≥ 5 条 + 命中 sessionid/msToken」绿色提示
                          → 点「保存配置」→ 看到{" "}
                          <span className="font-medium text-foreground">「Cookie 已保存」</span>{" "}
                          后即可去「即时拆解」自动转写视频
                        </li>
                      </ol>
                      <div className="space-y-1 px-3 pb-3 text-[11px] text-muted-foreground">
                        <p className="font-medium text-foreground/70">✅ 正确示例：</p>
                        <pre className="overflow-x-auto rounded border border-success/30 bg-success/5 px-2 py-1 font-mono leading-snug text-success">
{`ttwid=1%7Cabc...; sessionid=abc...; msToken=def...; odin_tt=ghi...; sid_tt=jkl...; uid_tt=mno...; webid=pqr...`}
                        </pre>
                        <p className="pt-1 font-medium text-destructive/70">❌ 错误示例（复制的是 Response 的 Set-Cookie 单条）：</p>
                        <pre className="overflow-x-auto rounded border border-destructive/30 bg-destructive/5 px-2 py-1 font-mono leading-snug text-destructive">
{`ttwid=1%7Cabc...; Domain=.douyin.com; Path=/; Expires=...; HttpOnly; Secure; SameSite=None`}
                        </pre>
                        <p>
                          Cookie 一般几小时到几天会过期；只要「即时拆解」又开始频繁报「需要登录态」，
                          重新来一次这 5 步就行。
                        </p>
                      </div>
                    </details>
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
