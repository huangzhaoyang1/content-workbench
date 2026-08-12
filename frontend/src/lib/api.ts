// 轻量 API 客户端：统一指向后端地址、处理 JSON 与错误。
// 后端地址通过 NEXT_PUBLIC_API_URL（或旧名 NEXT_PUBLIC_API_BASE）配置，
// 都没设置时默认 http://localhost:8000。
import type {
  AnalyticsDataset,
  AnalyticsImportResult,
  AnalyticsResult,
  AnalyticsSuggestionResult,
  ConnectionTestResult,
  HistoryDetail,
  HistoryPagedResult,
  HotspotSearchResult,
  OcrArticle,
  OcrRecognizeResult,
  OcrStatus,
  PipelineStartResult,
  PipelineStatus,
  QueueAddResult,
  QueueClearResult,
  QueueItemInput,
  QueueSkipResult,
  QueueSnapshot,
  QueueStartResult,
  RegenerateResult,
  ScheduleInput,
  ScheduleJob,
  ScheduleListResult,
  SearchQuota,
  TesseractDetectResult,
  DataInsight,
  TopicGenerateResult,
  WorkbenchConfig,
  BaiduDetectResult,
  DissectAnalyzeResult,
  DissectAnalyzeReq,
  DissectFetchResult,
  DissectRewriteOneReq,
  DissectRewriteOneResult,
  DissectSaveTopicReq,
  TopicLibraryItem,
  TopicLibraryListResult,
  TopicLibraryQuery,
  TopicLibraryUpdateReq,
  DouyinSyncState,
  DouyinSyncConfig,
  DouyinSyncRecordsResult,
  DouyinSyncRecord,
  DouyinSyncRunResult,
  DouyinSyncRun,
  DouyinSyncImportResult,
  HistoryTask,
  TrashTopic,
  TopicVersionListResult,
  TopicVersionDetail,
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

// ---------------------------------------------------------------------------
// 访问令牌（仅在后端开启鉴权时需要）。
// 用 localStorage 持久化，request 自动附带；401 时清空并广播事件让登录框弹出。
// ---------------------------------------------------------------------------
const TOKEN_KEY = "workbench_auth_token";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(t: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(TOKEN_KEY, t);
  } catch {
    /* 隐私模式等场景忽略 */
  }
}

export function clearAuthToken(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* 忽略 */
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
    if (err.status === 401) {
      return "登录已过期，请重新输入访问令牌";
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
      return `网络连接失败，请检查后端服务是否可用（当前后端：${API_BASE}）。云端免费实例休眠后首次唤醒约需 30–60 秒，可稍后重试。`;
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
  const tok = getAuthToken();
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        ...(isForm ? {} : { "Content-Type": "application/json" }),
        ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
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
    // 令牌失效 / 未登录：清空本地令牌并广播，让登录框重新弹出。
    // 多个并发请求同时收到 401 时，仅第一个真正持有令牌的请求负责广播，
    // 其余请求因令牌已被清空（getAuthToken()===null）而跳过，避免重复弹窗/重复 re-render。
    if (res.status === 401) {
      if (typeof window === "undefined" || getAuthToken() !== null) {
        clearAuthToken();
        if (typeof window !== "undefined") {
          window.dispatchEvent(new Event("workbench:unauthorized"));
        }
      }
    }
    throw new ApiError(res.status, msg || `请求失败 (${res.status})`, detail);
  }
  return data as T;
}

export const api = {
  // ---------- 健康检查 ----------
  health: () => request<{ status: string; version: string }>("/api/health"),

  // ---------- 鉴权状态 ----------
  authStatus: () =>
    request<{ enabled: boolean; token_set: boolean; realm: string }>(
      "/api/auth/status"
    ),

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
  /** 读历史数据，给出「3 个内容方向 + 3 种标题风格 + 建议」，供选题页顶部展示。 */
  topicDataInsight: () => request<DataInsight>("/api/topic/data-insight"),

  // ---------- 流水线 ----------
  startPipeline: (payload: {
    topic: string;
    angle?: string;
    extra?: string;
    references?: string;
    platform?: string;
    review?: boolean;
    autoRefs?: boolean;
  }) =>
    request<PipelineStartResult>("/api/pipeline/start", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /** 确认发布：把已存为待审核的某期推送到公众号。coverLabel 非空时作为封面期号标识覆盖默认「第N期」。 */
  publishPipeline: (issue: number, coverLabel = "") =>
    request<PipelineStartResult>("/api/pipeline/publish", {
      method: "POST",
      body: JSON.stringify({ issue, cover_label: coverLabel }),
    }),
  /** 仅重画封面（不推送），返回新封面 base64。用于确认发布对话框「生成封面预览」实时反映用户输入的封面期号。 */
  regenerateCover: (issue: number, coverLabel = "") =>
    request<{ ok: boolean; cover_base64?: string; reason?: string; stderr?: string }>(
      "/api/pipeline/regenerate-cover",
      {
        method: "POST",
        body: JSON.stringify({ issue, cover_label: coverLabel }),
      },
    ),
  /** 放弃待审核的某期（只改本地状态，不调微信）。 */
  discardPipeline: (issue: number) =>
    request<{ ok: boolean; reason?: string }>("/api/pipeline/discard", {
      method: "POST",
      body: JSON.stringify({ issue }),
    }),
  pipelineStatus: (taskId: string) =>
    request<PipelineStatus>(`/api/pipeline/status/${taskId}`),

  // ---------- 历史任务 ----------
  listTasks: (params: {
    keyword?: string;
    status?: string;
    platform?: string;
    time_range?: string;
    tag?: string;
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
  deleteTask: (issue: number) =>
    request<{ ok: boolean; issue: number; trashed?: string }>(
      `/api/tasks/${issue}`,
      { method: "DELETE" }
    ),
  /** 批量删除历史任务。 */
  taskBatchDelete: (issues: number[]) =>
    request<{ ok: boolean; removed: number[]; skipped: number[] }>(
      "/api/tasks/batch-delete",
      { method: "POST", body: JSON.stringify({ issues }) }
    ),
  /** 给某期任务设置标签（覆盖式）。 */
  taskSetTags: (issue: number, tags: string[]) =>
    request<{ ok: boolean; issue: number; tags: string[] }>(
      `/api/tasks/${issue}/tags`,
      { method: "PATCH", body: JSON.stringify({ tags }) }
    ),
  /** 所有任务标签（去重）。 */
  taskListTags: () =>
    request<{ tags: string[] }>("/api/tasks/tags"),
  /** 回收站里的历史任务。 */
  taskListTrash: () =>
    request<{ tasks: HistoryTask[]; total: number }>("/api/tasks/trash"),
  /** 从回收站恢复某期任务。 */
  taskRestore: (issue: number) =>
    request<{ ok: boolean; issue: number; restored: string }>("/api/tasks/restore", {
      method: "POST",
      body: JSON.stringify({ issue }),
    }),
  /** 从回收站彻底删除某期任务（不可恢复）。 */
  taskPurge: (issue: number) =>
    request<{ ok: boolean; issue: number }>("/api/tasks/purge", {
      method: "POST",
      body: JSON.stringify({ issue }),
    }),
  /** 清空回收站。 */
  taskEmptyTrash: () =>
    request<{ ok: boolean; removed: number }>("/api/tasks/empty-trash", {
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
  /** 删除单条数据记录（按标题+日期匹配），返回删除后的数据集摘要。 */
  deleteAnalyticsRecord: (payload: {
    dataset_id?: string | null;
    title: string;
    date?: string | null;
  }) =>
    request<AnalyticsDataset>("/api/analytics/record", {
      method: "DELETE",
      body: JSON.stringify({
        dataset_id: payload.dataset_id ?? null,
        title: payload.title,
        date: payload.date ?? null,
      }),
    }),

  // ---------- 截图识别导入 ----------
  /** 当前 OCR 方式是否可用（不发起真实识别，仅读配置/探测本地程序）。 */
  ocrStatus: () => request<OcrStatus>("/api/analytics/ocr-status"),
  /**
   * 检测本地 Tesseract 是否可用（可传入还没保存的路径，先测后存）。
   * 两个参数都留空则使用后端当前配置。
   */
  detectTesseract: (tesseract_cmd = "", tessdata_dir = "") =>
    request<TesseractDetectResult>("/api/analytics/ocr-detect", {
      method: "POST",
      body: JSON.stringify({ tesseract_cmd, tessdata_dir }),
    }),
  /**
   * 测试百度 OCR 密钥是否可用（可传入还没保存的密钥，先测后存）。
   * 两个参数都留空则使用后端当前配置。
   */
  detectBaidu: (api_key = "", secret_key = "") =>
    request<BaiduDetectResult>("/api/analytics/ocr-baidu-detect", {
      method: "POST",
      body: JSON.stringify({ api_key, secret_key }),
    }),
  /** 上传一张截图做识别，返回结构化数据（不入库）。一次一张，便于逐图展示状态。 */
  ocrUploadAnalytics: (file: File, signal?: AbortSignal) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<OcrRecognizeResult>("/api/analytics/ocr-upload", {
      method: "POST",
      body: fd,
      signal,
    });
  },
  /** 把确认后的识别数据导入数据集（后端按标题+日期去重）。 */
  importAnalytics: (articles: OcrArticle[]) =>
    request<AnalyticsImportResult>("/api/analytics/import", {
      method: "POST",
      body: JSON.stringify({ articles }),
    }),

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
        topic_id: payload.topic_id ?? "",
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
  skipQueue: () =>
    request<QueueSkipResult>("/api/queue/skip", { method: "POST" }),

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

  // ---------- 抖音爆款拆解与公众号迁移 ----------
  /** 只抓取不拆解：拿到结构化文案后先给用户预览 / 编辑 */
  dissectFetch: (url: string) =>
    request<DissectFetchResult>("/api/douyin-dissect/fetch", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  dissectAnalyze: (payload: DissectAnalyzeReq) =>
    request<DissectAnalyzeResult>("/api/douyin-dissect/analyze", {
      method: "POST",
      body: JSON.stringify({
        url: payload.url ?? "",
        text: payload.text ?? "",
        meta: payload.meta ?? null,
      }),
    }),
  /** 只重新生成某一个角度的文章，复用已有拆解结果 */
  dissectRewriteOne: (payload: DissectRewriteOneReq) =>
    request<DissectRewriteOneResult>("/api/douyin-dissect/rewrite-one", {
      method: "POST",
      body: JSON.stringify({
        angle_key: payload.angle_key,
        raw_text: payload.raw_text,
        dissect: payload.dissect ?? null,
      }),
    }),
  dissectSaveTopic: (payload: DissectSaveTopicReq) =>
    request<{ ok: boolean; item: TopicLibraryItem; total: number }>(
      "/api/douyin-dissect/save-topic",
      {
        method: "POST",
        body: JSON.stringify({
          title: payload.title,
          content: payload.content ?? "",
          theme: payload.theme ?? "",
          category: payload.category ?? "",
          priority: payload.priority ?? "",
          status: payload.status ?? "",
          angle_key: payload.angle_key ?? "",
        }),
      }
    ),
  dissectListTopics: (query: TopicLibraryQuery | number = 50) => {
    const q: TopicLibraryQuery =
      typeof query === "number" ? { limit: query } : query;
    const sp = new URLSearchParams({ limit: String(q.limit ?? 50) });
    // 「全部」等价于不筛选，不要发给后端
    if (q.category && q.category !== "全部") sp.set("category", q.category);
    if (q.priority && q.priority !== "全部") sp.set("priority", q.priority);
    if (q.status && q.status !== "全部") sp.set("status", q.status);
    if (q.keyword?.trim()) sp.set("keyword", q.keyword.trim());
    if (q.tag?.trim()) sp.set("tag", q.tag.trim());
    return request<TopicLibraryListResult>(
      `/api/douyin-dissect/topics?${sp.toString()}`
    );
  },
  dissectUpdateTopic: (id: string, patch: TopicLibraryUpdateReq) =>
    request<{ ok: boolean; item: TopicLibraryItem }>(
      `/api/douyin-dissect/topics/${encodeURIComponent(id)}`,
      { method: "PATCH", body: JSON.stringify(patch) }
    ),
  dissectDeleteTopic: (id: string) =>
    request<{ ok: boolean; total: number }>(
      `/api/douyin-dissect/topics/${encodeURIComponent(id)}`,
      { method: "DELETE" }
    ),
  /** 批量删除选题。 */
  dissectBatchDeleteTopics: (ids: string[]) =>
    request<{ ok: boolean; removed: number; total: number }>(
      "/api/douyin-dissect/topics/batch-delete",
      { method: "POST", body: JSON.stringify({ ids }) }
    ),
  /** 批量把选题送进队列。 */
  dissectBatchProduceTopics: (ids: string[]) =>
    request<QueueAddResult>(
      "/api/douyin-dissect/topics/batch-produce",
      { method: "POST", body: JSON.stringify({ ids }) }
    ),
  /** 选题库出现过的全部标签。 */
  dissectListTopicTags: () =>
    request<{ tags: string[] }>("/api/douyin-dissect/topics/tags"),
  /** 回收站里的选题。 */
  dissectListTrash: () =>
    request<{ items: TrashTopic[]; total: number }>("/api/douyin-dissect/topics/trash"),
  /** 从回收站恢复一条选题。 */
  dissectRestoreTopic: (id: string) =>
    request<{ ok: boolean; item: TopicLibraryItem }>("/api/douyin-dissect/topics/restore", {
      method: "POST",
      body: JSON.stringify({ id }),
    }),
  /** 从回收站彻底删除一条选题（不可恢复）。 */
  dissectPurgeTopic: (id: string) =>
    request<{ ok: boolean; total: number }>("/api/douyin-dissect/topics/purge", {
      method: "POST",
      body: JSON.stringify({ id }),
    }),
  /** 清空回收站。 */
  dissectEmptyTrash: () =>
    request<{ ok: boolean; total: number }>("/api/douyin-dissect/topics/empty-trash", {
      method: "POST",
    }),
  /** 某选题的版本历史列表。 */
  dissectListTopicVersions: (topicId: string) =>
    request<TopicVersionListResult>(
      `/api/douyin-dissect/topics/${topicId}/versions`
    ),
  /** 某条历史版本的完整内容。 */
  dissectGetTopicVersion: (topicId: string, versionId: string) =>
    request<{ topic_id: string; version: TopicVersionDetail }>(
      `/api/douyin-dissect/topics/${topicId}/versions/${versionId}`
    ),
  /** 回退到某个历史版本（当前内容会先自动存档）。 */
  dissectRestoreTopicVersion: (topicId: string, versionId: string) =>
    request<{ ok: boolean; item: TopicLibraryItem }>(
      `/api/douyin-dissect/topics/${topicId}/restore-version`,
      { method: "POST", body: JSON.stringify({ version_id: versionId }) }
    ),

  // ---------- 抖音收藏同步 ----------
  /** 首屏一次性数据：配置 + 统计 + 下次执行时间 */
  douyinSyncState: () => request<DouyinSyncState>("/api/douyin-sync/state"),
  douyinSyncConfig: () => request<DouyinSyncConfig>("/api/douyin-sync/config"),
  /** 保存配置（来源 / 频率 / cookie / 筛选条件） */
  douyinSyncSaveConfig: (config: Partial<DouyinSyncConfig>) =>
    request<DouyinSyncConfig>("/api/douyin-sync/config", {
      method: "POST",
      body: JSON.stringify(config),
    }),
  /** 立即跑一次；不传 urls 则跑配置里的来源，传了只处理这批手动链接 */
  douyinSyncRun: (urls: string[] = []) =>
    request<DouyinSyncRunResult>("/api/douyin-sync/run", {
      method: "POST",
      body: JSON.stringify({ urls }),
    }),
  douyinSyncRecords: (params: {
    status?: string;
    keyword?: string;
    source?: string;
    limit?: number;
  } = {}) => {
    const sp = new URLSearchParams();
    if (params.status) sp.set("status", params.status);
    if (params.keyword?.trim()) sp.set("keyword", params.keyword.trim());
    if (params.source?.trim()) sp.set("source", params.source.trim());
    if (params.limit) sp.set("limit", String(params.limit));
    const q = sp.toString();
    return request<DouyinSyncRecordsResult>(
      `/api/douyin-sync/records${q ? `?${q}` : ""}`
    );
  },
  douyinSyncUpdateRecord: (
    id: string,
    patch: { status?: string; note?: string; text?: string; title?: string }
  ) =>
    request<DouyinSyncRecord>(
      `/api/douyin-sync/records/${encodeURIComponent(id)}`,
      { method: "PATCH", body: JSON.stringify(patch) }
    ),
  douyinSyncDeleteRecord: (id: string) =>
    request<{ ok: boolean; total: number }>(
      `/api/douyin-sync/records/${encodeURIComponent(id)}`,
      { method: "DELETE" }
    ),
  douyinSyncClearRecords: (status = "") =>
    request<{ ok: boolean; removed: number }>("/api/douyin-sync/records/clear", {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
  /** 把勾选的记录选入选题库 */
  douyinSyncImport: (ids: string[], priority = "中") =>
    request<DouyinSyncImportResult>("/api/douyin-sync/import", {
      method: "POST",
      body: JSON.stringify({ ids, priority }),
    }),
  douyinSyncRuns: (limit = 20) =>
    request<{ items: DouyinSyncRun[]; total: number }>(
      `/api/douyin-sync/runs${limit ? `?limit=${limit}` : ""}`
    ),
};
