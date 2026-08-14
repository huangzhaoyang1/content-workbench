# 项目交接手册（供外部审阅工具 deepseek harness 使用）

> 生成时间：2026-08-14 ｜ 基于 `content-workbench` 仓库当前真实状态（commit 4fa9b32 + 385747b 之后）
> 用途：让外部审阅工具在不接触密钥/真实运行配置的前提下，快速建立全局认知并定位审阅重点。
> 约定：本手册只列路径与结构，不写任何密钥值；审阅时**禁止扫描** `.secrets.json`、真实 `.bat`、`data/` 目录。

---

## 1. 项目定位与两条业务流水线

**一句话定位**：面向「AI 内容运营」场景的全栈工作台——把抖音视频拆解 / 全网热点抓取，经 LLM 改写为可发布文章，并支持本地预览、待审核与一键发布到微信公众号草稿箱。

**两条流水线**（共享同一套后端「队列 + 流水线 + 选题库 + 三步发布」能力，仅前半段入口不同）：

| 流水线 | 前半段（采集/拆解） | 后半段（选题→生产→发布） |
|---|---|---|
| **抖音线** | `/dissect`：粘贴抖音链接 → `fetch_douyin`（yt-dlp 抓元数据）→ 文案过短自动 `transcribe_video`（yt-dlp+Whisper 转写口播）→ `dissect_analyze` 拆出 5 类素材 → 生成 3 篇改写 | 候选选题卡片 → 「选择并生产」就地表单（默认勾选「先存为待审核」）→ 内联日志轮询 → 进入待审核 → ConfirmPublishDialog 三步发布 |
| **热点线** | `/hotspot`：热点抓取（`SerpAPI` 实时 → 自定义接口 → 内置 mock 三级回退）→ 热点洞察 → 选题生成 | `/topic`：候选选题卡片 → 「选择并生产」就地表单（含「存为待审核」）→ 同页内联日志 → 待审核 → ConfirmPublishDialog 三步发布 |

> 后半段为**复用优先**设计：两条线共用 `services/system/queue.py` + `services/content/pipeline.py` + 选题库 + 发布弹窗，差异仅在前端卡片所在页面与默认平台。

---

## 2. 技术栈

- **后端**：Python + FastAPI（`fastapi>=0.110`，`uvicorn[standard]`，`pydantic>=2.5`），单仓库 `backend/`，入口 `backend/main.py`。
- **前端**：Next.js 14.2.35（App Router）+ React 18 + TypeScript 5 + Tailwind CSS 3.4 + shadcn/ui（暗黑主题），目录 `frontend/`。
- **外部流水线脚本**：`side-hustle` 项目的 `scripts/run_pipeline.py`（**不在本仓库**，后端经 `settings.scripts_dir` + `subprocess` 调用；云端部署无该脚本时自动降级提示）。
- **转写**：`yt-dlp` 抓流 + `imageio-ffmpeg`/`static-ffmpeg` 提供 ffmpeg+ffprobe + `openai-whisper` CPU 推理（中文口播约 15–30 分钟/15 分钟视频）。
- **检索**：`SQLite FTS5`（jieba 分词建 `title_seg`/`content_seg` 索引），见 `services/data/retrieval.py`。
- **登录态**：Playwright 持久化 Chromium 上下文扫码登录抖音（`services/data/douyin_session.py`），cookie 落 Netscape 文件供 yt-dlp 复用。
- **鉴权**：可选 Bearer（`WORKBENCH_AUTH_ENABLED` / `WORKBENCH_AUTH_TOKEN`，默认关闭）。

---

## 3. 目录地图

### backend/
- `main.py` — 应用入口（CORS、路由挂载、全局异常处理器）。
- `services/content/` — **业务核心**
  - `dissect.py` 抖音拆解（fetch/preview/analyze + 转写兜底）
  - `pipeline.py` 流水线调度（调外部 `run_pipeline.py`，后台执行+实时日志；`review` 参数控制待审核/直推）
  - `topic.py` 选题生成（LLM 优先、模板兜底）
  - `quality.py` 内容质量四阶打分 + 违禁词扫描
  - `validate.py` 拆解结果（dissect）结构硬校验
- `services/data/` — 数据层：`transcribe.py`(ASR)、`douyin_cookie.py` / `douyin_session.py`(抖音登录)、`retrieval.py`(FTS5)、`tasks.py` / `memory.py` / `preferences.py` / `analytics.py`、`ocr_*`(OCR 策略)、`vision.py`。
- `services/integration/` — `hotspot.py`(热点三级回退)、`douyin_sync.py`(抖音同步)。
- `services/system/` — `config.py`(配置)、`queue.py`(队列+review 透传)、`quota.py`、`schedule.py`、`llm_usage.py`。
- `routers/` — `dissect/ hotspot/ topic/ pipeline/ queue/ tasks/ douyin_sync/ analytics/ config/ schedule/ health/`。
- `prompts/` — 提示词外置（见下文）。
- `eval/` — `eval_run.py` 评估脚本；`tests/` — pytest（auth/config/dissect/validate/queue/forbidden_words…）；`data/` — 运行数据（**gitignored**）。

### frontend/src/
- `app/` — 页面：`page.tsx`(首页)、`dissect/` `hotspot/` `topic/` `tasks/` `queue/` `analytics/` `config/` `douyin-sync/` `layout.tsx`。
- `components/dissect/` — `DissectPanel`(本次改造主文件)、`InputSection`、`DissectAnalysis`、`RewritePreview`、`MaterialChecklist`、`TitleSwitcher`、`TopicLibraryDialog`、`QualityScoreCard`。
- `components/tasks/` — `ConfirmPublishDialog`(**三步发布**)、`TaskCard`、`TaskDetailDialog`。
- `components/queue/ analytics/ layout/ auth/ brand/ charts/ ui/` — 通用与业务组件。
- `lib/` — `api.ts`(前端→后端调用)、`types.ts`、`seed.ts`。

### prompts/（提示词全部外置，改文案无需动代码）
- `dissect/system.md` + `params.json`、`hotspot/system.md`、`topic/system.md`、`pipeline-external/{system,user,params}.md`、`quality/styles.json`、`ocr-shared/{system,user}.md`。

### docs/（按类型索引）
- **体检/诊断**：`项目体检报告.md`(根)、`frontend-diagnosis.md`、`startup-diagnosis.md`、`flow-broken-diagnosis.md`、`bat-hardening-report.md`、`douyin-line-back-half-diagnosis.md`。
- **验收**：`acceptance-2.md`、`final-e2e-report.md`、`verification-report.md`。
- **审计/基线**：`prompt-audit.md`、`prompts-inventory.md`、`auto-refs-report.md`、`preference-forward-report.md`、`eval-baseline-report.md`、`quality-calibration/`(目录)。
- **速查**：`功能与接口速查.md`。

---

## 4. 当前已知状态

**已闭环（可视为稳定）**
- 主链路：抖音线 / 热点线前半段 + 后半段均跑通；后端队列 `review` 透传已修（抖音线默认进待审核而非直推微信）。
- 质量门：`quality.py` 本地四阶打分 + `QUALITY_THRESHOLD=30`（基于 11 篇真实稿校准，2026-08-11），作决策支持不自动裁决；违禁词扫描命中即标记 `BLOCK`。
- 评估基线：`eval-baseline-report.md` 已建立可量化基线。
- 转写：yt-dlp + Whisper 链路打通，ffmpeg/ffprobe 三级回退 + whisper 加速（`beam_size=1` + 磁盘缓存同 URL 复用）已落地。
- 结构硬校验：`validate.py` 强制「非 full 必须披露 missing」+ 素材五清单非空校验。

**已知限制（审阅时标注，非 bug）**
- **SerpAPI 未配 → 热点线走内置 mock**：`hotspot.py` 三级回退，未配 Key 时返回「模拟数据」，不编造真实分析。
- **语料库小**：检索/选题依赖的本地语料规模有限，影响召回与选题多样性。
- **ASR 慢**：Whisper CPU 推理，15 分钟视频转写约 15–30 分钟（已加速，仍受 CPU 限制）。
- **微信 IP 白名单需用户侧配置**：公众号草稿箱推送要求 MP 后台配置调用方 IP 白名单，属用户侧运维动作，代码无法替代。
- **外部脚本依赖**：`run_pipeline.py` 在 `side-hustle` 项目，本仓库通过 `scripts_dir` 引用；云端无脚本时流水线不可用（已降级提示）。

---

## 5. 关键设计决策清单

1. **提示词外置**：所有 LLM 提示词放 `backend/prompts/`，改文案不动代码，便于审阅与迭代。
2. **素材强制引用 + missing 披露**：`validate.py` 要求拆解声明素材完整度；非 full 必须列出 `missing`（如「没抠到具体数字」），杜绝模型假装抠到素材。
3. **validate 结构硬校验**：拆解输出先做 JSON 结构与类型校验，不通过则回灌错误让模型重试一次，再 fallback。
4. **质量阈值 30 + 人在环**：`QUALITY_THRESHOLD=30` 仅作发布决策参考，不自动发布；发布仍需人在 ConfirmPublishDialog 确认。
5. **广告法复合词表**：违禁词只用「极限程度复合词」（如「全网第一」）做子串匹配，避免单字「最/第一」误 BLOCK（`quality.py:_FORBIDDEN_AD_LAW`）。
6. **双流水线结构**：抖音线/热点线前半段不同、后半段共享队列+流水线+选题库+发布，复用优先不重写。
7. **封面预览三步发布**：`ConfirmPublishDialog` 先预览封面 → 选期号 → 确认发布，避免误推。

---

## 6. 边界与安全

**密钥所在文件（只列路径，绝不写值）**
- `side-hustle/.secrets.json` —— 微信 `appid`/`appsecret`（**外部项目，不在本仓库**）。
- `.env` / `.env.local` —— `WORKBENCH_AUTH_TOKEN` 等（**gitignored**）。
- `backend/data/workbench_config.json` —— 第三方 Key（`hotspot_api.api_key` / `search_api.api_key` / `deepseek.api_key`，**gitignored**，默认空）。

**gitignored 目录/文件**（`.gitignore`）
- `.env`、`.env.*`（保留 `.env.example`）、`*.pem`、`*.key`
- `data/`、`backend/data/*`（保留 `.gitkeep`）
- `node_modules/`、`.next/`、`__pycache__/`、`*.log` 等

**审阅红线（禁止扫描）**
- ❌ `.secrets.json`（含微信 AppSecret，外部项目）
- ❌ 真实 `.bat`：`启动AI内容工作台.bat`、`修复前端缓存.bat`（均 **gitignored**，含本地路径/端口）
- ❌ `data/` 任何内容（含 `douyin_sync.json` / `queue.json` / `workbench_config.json` 真实运行数据）

---

## 7. 建议审阅重点

1. **后半段衔接缝隙**：抖音线（`DissectPanel.tsx`）与热点线（`topic/page.tsx`）的「候选卡片→选择并生产→内联日志→待审核」是否行为一致？抖音线是否仍漏某条路径（如直接生产 vs 待审核默认值的边界）。
2. **双线逻辑重复**：两条线前半段（dissect vs hotspot）与后端 `pipeline.start`/`queue` 是否有可合并的重复代码或漂移的配置。
3. **评估基线提升**：`eval-baseline-report.md` 的指标体系是否覆盖后半段（待审核→发布）质量？能否用真实稿扩样到 >11 篇校准 `QUALITY_THRESHOLD`。
4. **潜在债务模块**：
   - `dissect.py` / `transcribe.py` 的抖音 cookie/登录态链路（匿名 vs 登录判定、egress 依赖）；
   - `pipeline.py` 对外部 `run_pipeline.py` 的耦合与云端降级；
   - `retrieval.py` 语料规模与 jieba 分词在长文下的召回；
   - `validate.py` 仅校验「五清单是 list」的结构弱约束，未对元素内容做本地复核。
5. **安全复核**：确认密钥仅上述三处、且无硬编码值泄漏到 `services/` 或 `prompts/`；确认 gitignore 实际排除了 `data/` 与 `.env`。
