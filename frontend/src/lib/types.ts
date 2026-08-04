// 工作台前后端共享的 TS 类型定义。
// 字段命名与后端 workbench_config.json / 各 API 返回结构保持一致。

export interface HotspotApiConfig {
  api_url: string;
  api_key: string;
  timeout: number;
  method: string;
}

export interface SearchApiConfig {
  type: "serpapi" | "custom" | "";
  api_key: string;
}

export interface DeepSeekConfig {
  base_url: string;
  api_key: string;
  model: string;
}

export interface WorkbenchConfig {
  project_root: string;
  python_path: string;
  account_name: string;
  positioning: string;
  style: string;
  visual_style: string;
  hotspot_api: HotspotApiConfig;
  scheduled_tasks: unknown[];
  search_api: SearchApiConfig;
  deepseek: DeepSeekConfig;
  daily_limit: number;
}

export interface HotspotItem {
  id: string;
  title: string;
  summary: string;
  source: string;
  published: string;
  hours_ago: number;
  url: string;
  ai_summary?: string;
}

export interface HotspotSearchResult {
  items: HotspotItem[];
  origin: string;
  insight: string;
}

/** 今日真实搜索额度（用满后热点搜索会回退示例数据） */
export interface SearchQuota {
  date: string;
  used: number;
  limit: number;
  remaining: number;
  exhausted: boolean;
}

export interface TopicCandidate {
  topic: string;
  angle: string;
  structure: string;
  background: string;
}

export interface TopicGenerateResult {
  topics: TopicCandidate[];
}

export interface ConnectionResult {
  ok: boolean;
  message: string;
}

export interface ConnectionTestResult {
  serpapi: ConnectionResult;
  deepseek: ConnectionResult;
}

export type TaskStatus = "pending" | "running" | "success" | "failed";

export interface PipelineStatus {
  task_id: string;
  issue: number;
  topic: string;
  angle: string;
  platform: string;
  status: TaskStatus;
  logs: string[];
  returncode: number | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface PipelineStartResult {
  task_id: string;
  issue: number;
}

export type HistoryStatus = "ok" | "error" | "unknown" | "running";

export interface HistoryTask {
  issue: number;
  status: HistoryStatus;
  title: string;
  topic: string;
  angle: string;
  platform: string;
  draft_status: string | null;
  error: string | null;
  article_rel: string | null;
  cover_rel: string | null;
  completed_at: string | null;
  duration_sec: number | null;
}

export interface HistoryStats {
  total: number;
  success: number;
  failed: number;
  rate: number | null;
  this_month: number;
  avg_duration: number | null;
}

export interface HistoryListResult {
  tasks: HistoryTask[];
  stats: HistoryStats;
  skipped: string[];
  total_filtered: number;
}

export interface HistoryDetail extends HistoryTask {
  article_preview: string | null;
  cover_base64: string | null;
  dir_path: string | null;
  result_path: string | null;
  started_at: string | null;
}

// ==========================================================================
// 数据分析
// ==========================================================================

/** 后端把用户表头映射到内部字段后的结果，值为原始列名（未识别则为 null）。 */
export interface AnalyticsMapping {
  title: string | null;
  date: string | null;
  reads: string | null;
  likes: string | null;
  shares: string | null;
}

export interface AnalyticsRecord {
  title: string;
  date: string | null;
  reads: number | null;
  likes: number | null;
  shares: number | null;
}

/** 上传 / 载入示例后返回的数据集摘要。 */
export interface AnalyticsDataset {
  dataset_id: string;
  filename: string | null;
  row_count: number;
  headers: string[];
  mapping: AnalyticsMapping;
  has_date: boolean;
  uploaded_at: string;
  is_sample: boolean;
  preview: AnalyticsRecord[];
}

export interface AnalyticsOverview {
  total_articles: number;
  total_reads: number;
  avg_reads: number | null;
  avg_likes: number | null;
  avg_shares: number | null;
  max_reads: number | null;
}

export interface AnalyticsTrendPoint {
  date: string;
  reads: number;
  likes: number;
  shares: number;
  count: number;
}

export interface AnalyticsRankItem {
  rank: number;
  title: string;
  date: string | null;
  reads: number | null;
  likes: number | null;
  shares: number | null;
  like_rate: number | null;
}

export type RankingKey = "reads" | "shares" | "like_rate";

export type AnalyticsRankings = Record<RankingKey, AnalyticsRankItem[]>;

export interface AnalyticsResult {
  dataset_id: string;
  filename: string | null;
  time_range: string;
  has_date: boolean;
  row_count: number;
  mapping: AnalyticsMapping;
  overview: AnalyticsOverview;
  trend: AnalyticsTrendPoint[];
  rankings: AnalyticsRankings;
}

/** 数据驱动的选题方向建议。 */
export interface AnalyticsSuggestion {
  name: string;
  evidence: string;
  angle: string;
}

export interface AnalyticsSuggestionResult {
  suggestions: AnalyticsSuggestion[];
  dataset_id: string;
}

// ==========================================================================
// 任务队列
// ==========================================================================

export type QueueItemStatus = "waiting" | "running" | "success" | "failed";

/** 队列任务来源，便于在 UI 上标注是谁加进来的。 */
export type QueueSource = "manual" | "topic" | "tasks" | "analytics" | "schedule";

export interface QueueItem {
  id: string;
  topic: string;
  angle: string;
  extra: string;
  platform: string;
  source: QueueSource | string;
  status: QueueItemStatus;
  issue: number | null;
  task_id: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface QueueStats {
  waiting: number;
  running: number;
  success: number;
  failed: number;
  total: number;
}

export interface QueueSnapshot {
  items: QueueItem[];
  stats: QueueStats;
  is_running: boolean;
}

export interface QueueAddResult extends QueueStats {
  added: number;
  items: QueueItem[];
}

export interface QueueStartResult extends QueueStats {
  started: boolean;
  reason?: string;
}

export interface QueueClearResult extends QueueStats {
  removed: number;
}

/** 队列任务的最小输入，批量加入时使用。 */
export interface QueueItemInput {
  topic: string;
  angle?: string;
  extra?: string;
  platform?: string;
}

// ==========================================================================
// 定时任务
// ==========================================================================

export type ScheduleFrequency = "daily" | "weekly" | "cron";

export interface ScheduleJob {
  id: string;
  name: string;
  topic: string;
  angle: string;
  extra: string;
  platform: string;
  frequency: ScheduleFrequency;
  time: string;
  weekday: number;
  cron: string;
  enabled: boolean;
  created_at: string;
  next_run: string | null;
  last_run: string | null;
  last_result: string | null;
  run_count: number;
  freq_label: string;
}

export interface ScheduleListResult {
  jobs: ScheduleJob[];
}

/** 新建 / 编辑定时任务时提交的表单数据。 */
export interface ScheduleInput {
  name: string;
  topic: string;
  angle?: string;
  extra?: string;
  platform?: string;
  frequency: ScheduleFrequency;
  time?: string;
  weekday?: number;
  cron?: string;
  enabled?: boolean;
}

// ==========================================================================
// 历史任务（分页版）
// ==========================================================================

export interface HistoryPagedResult extends HistoryListResult {
  page: number;
  page_size: number;
  pages: number;
}

export interface RegenerateResult {
  mode: "queue" | "now";
  item?: QueueItem;
  task_id?: string;
  issue?: number;
}

/** 跨页面传递的选题草稿（sessionStorage 载体）。 */
export interface TopicSeed {
  topic: string;
  angle?: string;
  note?: string;
  from: "hotspot" | "analytics" | "tasks";
}
