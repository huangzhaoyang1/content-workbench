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

/** 视觉模型（截图识别用）。base_url / api_key 留空时自动沿用 DeepSeek 配置。 */
export interface VisionConfig {
  base_url: string;
  api_key: string;
  model: string;
}

/**
 * OCR 识别方式：
 * - paddle_ocr   本地 PaddleOCR（默认，免配置，但依赖较重）
 * - tesseract    本地 Tesseract（独立 C++ 程序，与 Python 版本无关，最稳）
 * - baidu_ocr    百度智能云 OCR（通用文字识别·高精度版，中文准确率高、每天 1000 次免费）
 * - vision_model 云端视觉模型（需配 VL 端点）
 */
export type OcrMode = "paddle_ocr" | "tesseract" | "baidu_ocr" | "vision_model";

export interface OcrConfig {
  mode: OcrMode;
  /** tesseract.exe 完整路径，仅 tesseract 模式生效；留空则自动去 PATH 里找 */
  tesseract_cmd: string;
  /** 语言包（tessdata）目录，可选；留空用 Tesseract 默认目录 */
  tessdata_dir: string;
  /** 百度智能云 OCR 的 API Key，仅 baidu_ocr 模式生效 */
  baidu_api_key: string;
  /** 百度智能云 OCR 的 Secret Key，仅 baidu_ocr 模式生效 */
  baidu_secret_key: string;
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
  vision: VisionConfig;
  ocr: OcrConfig;
  daily_limit: number;
  custom_forbidden_words: string[];
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
  /** 学 / 用 / 赚（三大内容方向） */
  direction?: string;
  topic: string;
  angle: string;
  structure: string;
  background: string;
}

export interface TopicGenerateResult {
  topics: TopicCandidate[];
}

// ==========================================================================
// 选题数据洞察（/api/topic/data-insight）
// ==========================================================================

/** 洞察用到的数据集摘要。 */
export interface DataInsightDataset {
  filename: string | null;
  total_articles: number | null;
  avg_reads: number | null;
  max_reads: number | null;
}

/** 标题风格表现（按风格聚合的平均阅读）。 */
export interface DataInsightTitleStyle {
  name: string;
  count: number;
  avg_reads: number;
  /** 相对大盘平均阅读的倍数；null 表示无法计算 */
  lift: number | null;
  tip: string;
}

/**
 * 选题数据洞察区返回结构。
 * - available=false 时只有 reason（引导用户去数据分析页），其余为空。
 * - directions 复用 AnalyticsSuggestion（name/evidence/angle）。
 */
export interface DataInsight {
  available: boolean;
  reason: string;
  dataset: DataInsightDataset | null;
  directions: AnalyticsSuggestion[];
  title_styles: DataInsightTitleStyle[];
  advice: string[];
  summary: string;
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

export type HistoryStatus = "ok" | "error" | "unknown" | "running" | "waiting";

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
  tags?: string[];
  trashed?: boolean;
  quality?: QualityScore | null;
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
// 截图识别导入
// ==========================================================================

/** 视觉模型从截图里识别出的一篇文章数据。数字字段识别不到为 null，不会瞎编。 */
export interface OcrArticle {
  title: string;
  date: string | null;
  reads: number | null;
  /** 在看数 */
  likes: number | null;
  /** 点赞数（新版后台的「赞」，与在看分开统计） */
  wow: number | null;
  shares: number | null;
  collects: number | null;
}

/** 整体数据截图才会有的账号级指标；文章列表截图里全为 null。 */
export interface OcrSummary {
  followers_delta: number | null;
  new_followers: number | null;
  lost_followers: number | null;
  total_reads: number | null;
  date_range: string | null;
}

export type OcrConfidence = "high" | "medium" | "low";

/** 单张截图的识别结果（尚未入库）。 */
export interface OcrRecognizeResult {
  articles: OcrArticle[];
  summary: OcrSummary;
  confidence: OcrConfidence;
  note: string;
  model: string;
  filename: string;
}

/** 确认导入后的结果。 */
export interface AnalyticsImportResult {
  imported: number;
  skipped: number;
  duplicates: string[];
  dataset: AnalyticsDataset;
}

/** 当前 OCR 方式的可用性（进页面时探测，用于提前提示）。 */
export interface OcrStatus {
  configured: boolean;
  model: string;
  /** 云端模式是 API 地址；本地模式是「本地」或可执行文件路径 */
  endpoint: string;
  /** true 表示视觉端点沿用了 DeepSeek 配置，没有单独配 */
  inherited: boolean;
  hint: string;
  /** 当前生效的 OCR 策略（paddle_ocr / tesseract / vision_model） */
  mode?: string;
  /** 额外说明，如「首次识别会自动下载模型」 */
  note?: string;
}

/** Tesseract 可用性检测结果（配置页「检测」按钮）。 */
export interface TesseractDetectResult {
  ok: boolean;
  /** 实际用到的 tesseract 可执行文件路径 */
  cmd: string;
  /** 版本号，检测失败时为空串 */
  version: string;
  /** 已安装的语言包列表，如 ["chi_sim", "eng"] */
  languages: string[];
  /** 是否装了中文简体语言包（chi_sim） */
  has_chinese: boolean;
  /** 给用户看的一句话结论（失败时含安装指引） */
  message: string;
}

/** 百度 OCR 连接检测结果（配置页「测试连接」按钮）。 */
export interface BaiduDetectResult {
  /** 密钥能否正常换取 access_token */
  ok: boolean;
  /** 是否填写了 API Key 和 Secret Key */
  has_key: boolean;
  /** 给用户看的一句话结论（失败时含申请地址指引） */
  message: string;
}

/** 前端本地维护的单张截图状态。 */
export type ScreenshotStatus = "pending" | "recognizing" | "success" | "failed";

export interface ScreenshotItem {
  id: string;
  file: File;
  /** createObjectURL 生成的缩略图地址，卸载时需要 revoke */
  previewUrl: string;
  status: ScreenshotStatus;
  error: string | null;
  articles: OcrArticle[];
  summary: OcrSummary | null;
  confidence: OcrConfidence | null;
  note: string;
}

// ==========================================================================
// 任务队列
// ==========================================================================

export type QueueItemStatus =
  | "waiting"
  | "running"
  | "success"
  | "failed"
  | "skipped";

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
  topic_id?: string | null;
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

export interface QueueSkipResult extends QueueStats {
  ok: boolean;
  id?: string;
  reason?: string;
}

/** 队列任务的最小输入，批量加入时使用。 */
export interface QueueItemInput {
  topic: string;
  angle?: string;
  extra?: string;
  platform?: string;
  /** 关联选题库条目 id，用于生产完成后自动翻转选题状态。 */
  topic_id?: string;
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

// ==========================================================================
// 抖音爆款拆解与公众号迁移
// ==========================================================================

/** 选题类型标签（与后端 TYPE_TAGS 白名单一致）。 */
export type DissectTypeTag = "反常识" | "痛点" | "干货" | "故事" | "经验";

/** 选题主题分类（与后端 _THEMES 一致）。 */
export type DissectTheme = "AI工具" | "AI副业" | "学习方法" | "行业观察" | "个人成长";

export interface DissectBasics {
  title: string;
  summary: string;
  topic: string;
  duration_sec: number | null;
  word_count: number | null;
  type_tags: DissectTypeTag[];
}

export interface DissectHook {
  quote: string;
  technique: string;
  why: string;
  /** 1-10 钩子强度；模型没给则为 null */
  score: number | null;
}

export interface DissectStructureSeg {
  stage: string;
  seconds: string;
  label: string;
  content: string;
  role: string;
}

export interface DissectBoom {
  core: string;
  reasons: string[];
  emotion: string;
}

export interface DissectAudience {
  who: string;
  pain: string;
  scene: string;
}

export interface DissectPortable {
  point: string;
  how: string;
}

export interface DissectMigration {
  titles: string[];
  opening: string;
  expand: string[];
  ending: string;
}

/** 核心素材清单：拆解阶段从原文逐条抠出来的硬料，改写必须消费它 */
export interface DissectMaterialView {
  point: string;
  detail: string;
}
export interface DissectMaterialCase {
  what: string;
  detail: string;
}
export interface DissectMaterialNumber {
  value: string;
  context: string;
}
export interface DissectMaterialMethod {
  name: string;
  usage: string;
}
export type MaterialCompletenessLevel = "full" | "partial" | "thin";

export interface DissectMaterials {
  views: DissectMaterialView[];
  cases: DissectMaterialCase[];
  numbers: DissectMaterialNumber[];
  quotes: string[];
  logic_chain: string[];
  methods: DissectMaterialMethod[];
  completeness: {
    level: MaterialCompletenessLevel;
    missing: string[];
    note: string;
  };
  counts: {
    views: number;
    cases: number;
    numbers: number;
    quotes: number;
    logic_chain: number;
    methods: number;
  };
}

export interface DissectResult {
  basics: DissectBasics;
  hook: DissectHook;
  structure: DissectStructureSeg[];
  boom: DissectBoom;
  audience: DissectAudience;
  portable: DissectPortable[];
  migration: DissectMigration;
  materials?: DissectMaterials;
}

/** 内容质量四维评分（后端本地计算，不额外调模型） */
export interface QualityDimension {
  key: "format" | "substance" | "emotion" | "spread";
  label: string;
  score: number;
  full: number;
}
export interface QualityScore {
  total: number;
  grade: "优秀" | "合格" | "待打磨" | "不合格" | "BLOCK" | string;
  block: boolean;
  forbidden_words: Array<{ word: string; category: string; line?: number }>;
  dimensions: QualityDimension[];
  weakest: string;
  advice: string[];
  threshold: number;
  meets_threshold: boolean;
}

export type RewriteAngleKey = "pitfall" | "howto" | "insight";

export interface RewriteResult {
  angle_key?: RewriteAngleKey | "";
  angle_label?: string;
  angle_desc?: string;
  titles: string[];
  theme: DissectTheme;
  digest: string;
  content: string;
  word_count: number | null;
  changes: string[];
  materials_used?: string[];
  quality?: QualityScore;
}

export interface DissectStats {
  digg: number | null;
  comment: number | null;
  collect: number | null;
  share: number | null;
}

/** 抖音链接抓取到的结构化信息（抓不到的字段保留 key，值为空） */
export interface DissectSource {
  origin: "manual" | "url" | "transcribe";
  url: string;
  note: string;
  complete?: boolean;
  video_id?: string;
  title?: string;
  desc?: string;
  author?: string;
  create_time?: string;
  duration_sec?: number | null;
  stats?: DissectStats;
  hashtags?: string[];
  cover?: string;
  /** 没抓到的字段中文名清单，前端据此提示手动补 */
  missing?: string[];
  strategy?: string;
}

/** POST /api/douyin-dissect/fetch —— 只抓取不拆解 */
export interface DissectFetchResult {
  text: string;
  /** 抓取成功才有结构化信息；反爬/验证页拦截时返回 null（同时 needs_transcribe=true） */
  source?: DissectSource | null;
  hints: string[];
  note: string;
  complete: boolean;
  /** 视频时长（秒），用来决定是否要触发自动转写。抓不到时为 null。 */
  duration_sec?: number | null;
  /** 抓取被反爬/验证页拦截：前端应自动触发「视频转写」兜底 */
  needs_transcribe?: boolean;
  /** 拦截时的原始错误信息（兜底失败后才展示给用户） */
  transcribe_error?: string;
}

/** POST /api/douyin-dissect/transcribe —— 视频音频 → 文字（Whisper） */
export interface DissectTranscribeResult {
  ok: boolean;
  text?: string;
  duration_sec?: number | null;
  engine?: string;
  model?: string;
  /**
   * 失败原因分类（前端据此显示不同引导）：
   * - need_login      平台要求登录态（典型：抖音 Fresh cookies）
   * - network         网络层失败（DNS / 防火墙 / 断网）
   * - unsupported     链接不被识别或平台不支持
   * - format          视频格式不支持
   * - timeout         下载或转写超时
   * - too_long        超过 30 分钟上限（_MAX_DURATION_SEC）
   * - transcribe_failed whisper 自身失败
   * - invalid_input   缺少链接
   * - unknown         其它（参考 error 字符串）
   */
  error_key?:
    | "need_login"
    | "network"
    | "unsupported"
    | "format"
    | "timeout"
    | "too_long"
    | "transcribe_failed"
    | "invalid_input"
    | "unknown";
  /** 用户可读的中文原因；ok=false 时包含如何操作 */
  error?: string;
}

export interface DissectAnalyzeResult {
  dissect: DissectResult;
  /** 兼容字段，等于 rewrites[0] */
  rewrite: RewriteResult;
  /** 三种角度：踩坑经历 / 干货总结 / 认知升级 */
  rewrites?: RewriteResult[];
  warnings?: string[];
  source: DissectSource;
  model: string;
  elapsed_sec: number;
  raw_text: string;
}

export interface DissectAnalyzeReq {
  url?: string;
  text?: string;
  /** 上一步抓取拿到的 source，用户改过文案时用来保留视频元信息 */
  meta?: DissectSource | null;
  /** 会话 ID；填了则后端把最近 6 轮对话拼进拆解上下文，并把本次输入输出存回记忆 */
  session_id?: string;
}

export interface DissectRewriteOneReq {
  angle_key: string;
  raw_text: string;
  dissect?: DissectResult | null;
}

export interface DissectRewriteOneResult {
  rewrite: RewriteResult;
  angle_key: string;
  model: string;
  elapsed_sec: number;
}

export interface DissectRewriteWithAdviceReq {
  angle_key: string;
  raw_text: string;
  content: string;
  advice: string[];
  dissect?: DissectResult | null;
}

export interface DissectRewriteWithAdviceResult {
  rewrite: RewriteResult;
  /** 改进前打分（对当前正文本地计算） */
  quality_before: QualityScore;
  /** 改进后打分（新正文的 quality 字段） */
  quality_after: QualityScore;
  angle_key: string;
  model: string;
  elapsed_sec: number;
}

export type TopicCategory = "踩坑类" | "干货类" | "复盘类" | "工具类" | "其他";
export type TopicPriority = "高" | "中" | "低";
export type TopicStatus = "待生产" | "生产中" | "已完成";

export interface DissectSaveTopicReq {
  title: string;
  content?: string;
  theme?: string;
  category?: string;
  priority?: string;
  status?: string;
  angle_key?: string;
  tags?: string[];
}

export interface TopicLibraryItem {
  id: string;
  title: string;
  content: string;
  theme: string;
  source: string;
  category: TopicCategory | string;
  priority: TopicPriority | string;
  status: TopicStatus | string;
  angle_key?: string;
  created_at: string;
  updated_at?: string;
  tags?: string[];
}

export interface TopicLibraryListResult {
  items: TopicLibraryItem[];
  total: number;
  filtered?: number;
  facets?: {
    categories: string[];
    priorities: string[];
    statuses: string[];
  };
}

export interface TopicLibraryQuery {
  limit?: number;
  category?: string;
  priority?: string;
  status?: string;
  keyword?: string;
  tag?: string;
}

export interface TopicLibraryUpdateReq {
  title?: string;
  content?: string;
  theme?: string;
  category?: string;
  priority?: string;
  status?: string;
  tags?: string[];
}

export interface TrashTopic extends TopicLibraryItem {
  deleted_at?: string;
}

export interface TopicVersion {
  version_id: string;
  saved_at: string;
  title: string;
  theme?: string;
  category?: string;
  content_len: number;
}

export interface TopicVersionListResult {
  topic_id: string;
  versions: TopicVersion[];
  total: number;
}

export interface TopicVersionDetail extends TopicVersion {
  content: string;
  tags?: string[];
}

// ---------------------------------------------------------------------------
// 抖音收藏同步
// ---------------------------------------------------------------------------
export type DouyinSyncSourceKind = "favorite" | "profile" | "manual";
export type DouyinSyncFrequency = "daily" | "weekly" | "cron";
export type DouyinSyncRecordStatus = "new" | "imported" | "ignored";

export interface DouyinSyncSource {
  id: string;
  name: string;
  url: string;
  kind: DouyinSyncSourceKind;
  enabled: boolean;
}

export interface DouyinSyncFilters {
  min_digg: number;
  min_text_len: number;
  keywords: string[];
  exclude_keywords: string[];
}

export interface DouyinSyncConfig {
  enabled: boolean;
  sources: DouyinSyncSource[];
  /** 永远不回传明文 cookie，只给布尔 */
  cookie: string;
  cookie_set: boolean;
  frequency: DouyinSyncFrequency;
  time: string;
  weekday: number;
  cron: string;
  max_per_run: number;
  filters: DouyinSyncFilters;
  freq_label?: string;
  next_run?: string | null;
  last_run?: string | null;
  last_result?: string;
  run_count?: number;
}

export interface DouyinSyncRecord {
  id: string;
  video_id: string;
  url: string;
  title: string;
  desc: string;
  text: string;
  author: string;
  create_time: string;
  duration_sec: number | null;
  stats: DissectStats;
  hashtags: string[];
  cover: string;
  missing: string[];
  complete: boolean;
  source_name: string;
  fetched_at: string;
  status: DouyinSyncRecordStatus;
  topic_id: string;
  note: string;
}

export interface DouyinSyncRun {
  id: string;
  trigger: string;
  started_at: string;
  elapsed_sec: number;
  added: number;
  skipped: number;
  filtered: number;
  failed: number;
  messages: string[];
}

export interface DouyinSyncState {
  config: DouyinSyncConfig;
  counts: Record<DouyinSyncRecordStatus, number>;
  total: number;
  last_run?: string | null;
  last_result?: string;
  next_run?: string | null;
  run_count: number;
  running: boolean;
}

export interface DouyinSyncRecordsResult {
  items: DouyinSyncRecord[];
  total: number;
  total_all: number;
  counts: Record<DouyinSyncRecordStatus, number>;
}

export interface DouyinSyncRunResult {
  ok?: boolean;
  run?: DouyinSyncRun;
  summary?: string;
  records?: DouyinSyncRecord[];
  imported?: number;
  failed?: number;
  messages?: string[];
}

export interface DouyinSyncImportResult {
  ok: boolean;
  imported: number;
  failed: number;
  messages: string[];
}
