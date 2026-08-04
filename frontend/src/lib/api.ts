// 轻量 API 客户端：统一指向后端地址、处理 JSON 与错误。
// 后端地址通过 NEXT_PUBLIC_API_BASE 配置，默认 http://localhost:8000。
import type {
  AnalyticsDataset,
  AnalyticsResult,
  AnalyticsSuggestionResult,
  ConnectionTestResult,
  HistoryDetail,
  HistoryPagedResult,
  HotspotSearchResult,
  PipelineStartResult,
  PipelineStatus,
  QueueAddResult,
  QueueClearResult,
  QueueItemInput,
  QueueSnapshot,
  QueueStartResult,
  RegenerateResult,
  ScheduleInput,
  ScheduleJob,
  ScheduleListResult,
  SearchQuota,
  TopicGenerateResult,
  WorkbenchConfig,
} from "./types";

// 后端地址：两个变量名都支持（NEXT_PUBLIC_API_BASE 是历史名字，
// NEXT_PUBLIC_API_URL 是部署文档里用的名字），任填其一即可，都没填走本地。
// 注意：Next.js 在构建时做静态替换，必须写成完整字面量，不能拼字符串取值。
const RAW_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || process.env.NEXT_PUBLIC_API_URL || "";

export const API_BASE = RAW_API_BASE.trim().replace(/\/+$/, "") || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** 网络层失败（fetch 直接抛错，通常是后端没起来 / 断网 / CORS） */
export class NetworkError extends Error {
  constructor(message = "网络连接失败") {
    super(message);
    this.name = "NetworkError";
  }
}

/**
 * 把任意异常转换成给用户看的一句话。
 * 规则：
 *  - 连不上后端 → 提示检查后端服务
 *  - 5xx → 服务器开小差
 *  - 4xx → 直接用后端返回的 detail
 */
export function friendlyMessage(err: unknown, fallback = "操作失败，请重试"): string {
  if (err instanceof NetworkError) {
    return `网络连接失败，请检查后端服务是否可用（当前后端：${API_BASE}）。云端免费实例休眠后首次唤醒约需 30–60 秒，可稍后重试。`;
  }
  if (err instanceof ApiError) {
    if (err.status === 0) {
      return `网络连接失败，请检查后端服务是否可用（当前后端：${API_BASE}）`;
    }
    if (err.status === 503) {
      // 功能在当前环境不可用（例如云端没有本地流水线脚本），后端已给出人话说明
      return err.message || "该功能在当前环境不可用";
    }
    if (err.status >= 500) {
      return `服务器开小差了（${err.status}）：${err.message || "请稍后重试"}`;
    }
    if (err.status === 404) {
      return err.message || "请求的资源不存在";
    }
    if (err.status === 422) {
      return `参数有误：${err.message}`;
    }
    return err.message || fallback;
  }
  if (err instanceof Error) {
    if (/failed to fetch|networkerror|load failed/i.test(err.message)) {
      return "网络连接失败，请检查后端服务是否已启动（默认 http://localhost:8000）";
    }
    return err.message || fallback;
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  // FormData 必须让浏览器自己带 boundary，不能手动设 Content-Type
  const isForm =
    typeof FormData !== "undefined" && init?.body instanceof FormData;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        ...(isForm ? {} : { "Content-Type": "application/json" }),
        ...(init?.headers || {}),
      },
      cache: "no-store",
    });
  } catch {
    // fetch 本身失败：后端没起来 / 断网 / 被拦截
    throw new NetworkError();
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    const detail =
      (data as { detail?: unknown })?.detail ??
      (typeof data === "string" ? data : res.statusText);
    const msg =
      typeof detail === "string"
        ? detail
        : JSON.stringify(detail);
    throw new ApiError(res.status, msg || `请求失败 (${res.status})`, detail);
  }
  return data as T;
}

export const api = {
  // ---------- 健康检查 ----------
  health: () => request<{ status: string; version: string }>("/api/health"),

  // ---------- 配置 ----------
  getConfig: () => request<WorkbenchConfig>("/api/config"),
  putConfig: (config: WorkbenchConfig) =>
    request<WorkbenchConfig>("/api/config", {
      method: "PUT",
      body: JSON.stringify({ config }),
    }),
  testConnection: (search_api: object, deepseek: object) =>
    request<ConnectionTestResult>("/api/config/test", {
      method: "POST",
      body: JSON.stringify({ search_api, deepseek }),
    }),

  // ---------- 热点搜索 ----------
  searchHotspots: (keywords: string[], time_range: string, limit = 15) =>
    request<HotspotSearchResult>("/api/hotspot/search", {
      method: "POST",
      body: JSON.stringify({ keywords, time_range, limit }),
    }),
  getSearchQuota: () => request<SearchQuota>("/api/hotspot/quota"),
  resetSearchQuota: () =>
    request<SearchQuota>("/api/hotspot/quota/reset", { method: "POST" }),

  // ---------- 选题生成 ----------
  generateTopics: (payload: {
    hotspots?: object[];
    data_insight?: string | null;
    data_suggestions?: object[];
  }) =>
    request<TopicGenerateResult>("/api/topic/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // ---------- 流水线 ----------
  startPipeline: (payload: {
    topic: string;
    angle?: string;
    extra?: string;
    references?: string;
    platform?: string;
  }) =>
    request<PipelineStartResult>("/api/pipeline/start", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  pipelineStatus: (taskId: string) =>
    request<PipelineStatus>(`/api/pipeline/status/${taskId}`),

  // ---------- 历史任务 ----------
  listTasks: (params: {
    keyword?: string;
    status?: string;
    platform?: string;
    time_range?: string;
    page?: number;
    page_size?: number;
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.keyword) qs.set("keyword", params.keyword);
    if (params.status && params.status !== "全部") qs.set("status", params.status);
    if (params.platform && params.platform !== "全部")
      qs.set("platform", params.platform);
    if (params.time_range && params.time_range !== "全部")
      qs.set("time_range", params.time_range);
    if (params.page) qs.set("page", String(params.page));
    if (params.page_size) qs.set("page_size", String(params.page_size));
    const q = qs.toString();
    return request<HistoryPagedResult>(`/api/tasks${q ? `?${q}` : ""}`);
  },
  taskDetail: (issue: number) => request<HistoryDetail>(`/api/tasks/${issue}`),
  regenerateTask: (issue: number, mode: "queue" | "now" = "queue", extra = "") =>
    request<RegenerateResult>(`/api/tasks/${issue}/regenerate`, {
      method: "POST",
      body: JSON.stringify({ mode, extra }),
    }),
  openTaskDir: (issue: number) =>
    request<{ ok: boolean; path: string }>(`/api/tasks/${issue}/open-dir`, {
      method: "POST",
    }),

  // ---------- 数据分析 ----------
  uploadAnalytics: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<AnalyticsDataset>("/api/analytics/upload", {
      method: "POST",
      body: fd,
    });
  },
  loadAnalyticsSample: () =>
    request<AnalyticsDataset>("/api/analytics/sample", { method: "POST" }),
  analyzeAnalytics: (dataset_id?: string | null, time_range = "全部") =>
    request<AnalyticsResult>("/api/analytics/analyze", {
      method: "POST",
      body: JSON.stringify({ dataset_id: dataset_id || null, time_range }),
    }),
  analyticsSuggestions: (dataset_id?: string | null) => {
    const q = dataset_id ? `?dataset_id=${encodeURIComponent(dataset_id)}` : "";
    return request<AnalyticsSuggestionResult>(`/api/analytics/suggestions${q}`);
  },
  clearAnalytics: () =>
    request<{ ok: boolean }>("/api/analytics", { method: "DELETE" }),

  // ---------- 任务队列 ----------
  getQueue: () => request<QueueSnapshot>("/api/queue"),
  addQueue: (payload: QueueItemInput & { source?: string }) =>
    request<QueueAddResult>("/api/queue/add", {
      method: "POST",
      body: JSON.stringify({
        topic: payload.topic,
        angle: payload.angle ?? "",
        extra: payload.extra ?? "",
        platform: payload.platform ?? "wechat",
        source: payload.source ?? "manual",
      }),
    }),
  addQueueBatch: (items: QueueItemInput[], source = "manual") =>
    request<QueueAddResult>("/api/queue/add", {
      method: "POST",
      body: JSON.stringify({ items, source }),
    }),
  startQueue: () =>
    request<QueueStartResult>("/api/queue/start", { method: "POST" }),
  removeQueueItem: (id: string) =>
    request<QueueClearResult>(`/api/queue/${id}`, { method: "DELETE" }),
  clearQueue: (onlyFinished = false) =>
    request<QueueClearResult>(
      `/api/queue${onlyFinished ? "?only_finished=true" : ""}`,
      { method: "DELETE" }
    ),

  // ---------- 定时任务 ----------
  listSchedules: () => request<ScheduleListResult>("/api/schedule"),
  createSchedule: (payload: ScheduleInput) =>
    request<ScheduleJob>("/api/schedule", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateSchedule: (id: string, payload: Partial<ScheduleInput>) =>
    request<ScheduleJob>(`/api/schedule/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  toggleSchedule: (id: string, enabled: boolean) =>
    request<ScheduleJob>(`/api/schedule/${id}`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  deleteSchedule: (id: string) =>
    request<{ ok: boolean }>(`/api/schedule/${id}`, { method: "DELETE" }),
};
