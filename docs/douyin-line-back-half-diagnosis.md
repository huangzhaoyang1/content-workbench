# 抖音线后半部分诊断报告（对比热点线基准）

> 调查日期：2026-08-13
> 方法：仅读代码，未修改任何文件。热点线基准页 = `frontend/src/app/topic/page.tsx`；抖音线主页面 = `frontend/src/app/dissect/page.tsx`（内嵌 `DissectPanel.tsx`）。
> 行号已抽样复核（关键结论行号以本报告的复核值为准）。

---

## 〇、结论速览（先给决策层看）

抖音线后半部分**底层执行器（队列 + 流水线）完全复用热点线同一套**，没有另起炉灶；但**用户可见的"选题 → 确认 → 待审核"体验严重缺失**。相比热点线，抖音线最大的 3 个差距是：

1. **没有"生成候选选题卡片 → 一键选择并生产"这一步**（缺页面/衔接逻辑）——抖音线只有「直接生产（单篇直发）」和「加入选题库（手动存）」，用户无法像热点线那样从一组候选里挑。
2. **没有"存为待审核"开关**（缺接口衔接）——抖音线所有生产入口经队列调用 `pipeline.start` 时**未传 `review`**，默认 `review=False` 直接推送微信，正常路径根本不进"待审核"，审核/发布三步闭环对抖音线是缺失的（仅推送失败兜底可达）。
3. **没有内联生产日志/进度体验**（缺页面）——热点线在 `/topic` 页就地显示生产日志与队列进度；抖音线「直接生产」后跳 `/queue`→`/tasks`，日志不在拆解页就地看。

根因总结：不是"缺生产引擎"，而是**抖音线的前端衔接层（候选选题卡片、待审核开关、内联日志）没有像 `/topic` 页那样接好**——属于"缺页面/缺衔接逻辑"，不是"缺接口/缺后端能力"。

---

## 一、热点线后半部分（基准）

### 1.1 步骤流（生成选题 → 待审核，主路径 A 线）

```
[素材来源] ──sessionStorage 中转──▶ /topic 页
   ├─ 热点页勾选 selected_hotspots (hotspot/page.tsx:121-143)
   ├─ 数据分析/历史任务带入 topic_seeds (analytics:391 / tasks:248)
   └─ 后端实时 data-insight (topic.py:162)
        │
        ▼
[① 生成选题] 按钮 topic/page.tsx:976(handleGenerate:492)
   → api.generateTopics (api.ts:248) → POST /api/topic/generate
   → routers/topic.py:30 → services/content/topic.py:394(generate)
   → 返回 {topics:[{topic,angle,structure,background}]}
        │
        ▼
[② 候选卡片] topic/page.tsx 约1021-1100 渲染；每张卡 4 字段
   ├─ 「加入队列」按钮 :1061(onClick addToQueue) / 文字:1069
   └─ 「选择并生产」按钮 :1074(onClick pickTopic) / 文字:1076
        │
        ▼
[③ 生产参数表单] phase==="producing" 时显示，约1113-1223
   ├─ 选题/角度/补充要求/平台/「先存为待审核」勾选(:1178)/「自动补史料」(:1187)
   └─ 「启动流水线」:1201 → startPipeline:569 → api.startPipeline(api.ts:261)
        │
        ▼
[④ 生产执行 + 就地日志] 同页"生产日志"卡片 约1225-1547
   ├─ 阶段进度 PIPELINE_STAGES(:76) + 实时日志框
   └─ 轮询 api.pipelineStatus(api.ts:295)，每1500ms(:710-725)
        │
        ▼
[⑤ 到达待审核] 轮询到 success → loadDetail(api.taskDetail:320)
   → detail.draft_status==="PENDING_REVIEW" 时显示审核区(:1431)
   → 「确认发布」:1450 → ConfirmPublishDialog(期数→封面→发布)
```

### 1.2 候选选题卡片展示字段（已核实）

`TopicCandidate` 类型（`types.ts:93-98`），卡片渲染：
- `t.topic`（标题）— `topic/page.tsx:1052` 左右（CardTitle）
- `t.angle`（切入角度）— 卡片内"切入角度：" 文案附近
- `t.structure`（建议结构）— "建议结构：{t.structure}"
- `t.background`（背景/依据）— 条件渲染

两个按钮（已核实行号）：
- **「加入队列」** `:1061`（onClick `addToQueue`）→ `api.addQueue` → `POST /api/queue/add` → `queue.add`（仅入队占位，不自动执行，需到 `/queue` 页点"开始执行"）
- **「选择并生产」** `:1074`（onClick `pickTopic`）→ 填生产表单 + `setPhase("producing")`，就地滚到生产表单

### 1.3 从生成选题到待审核：主路径 A 线共 5 步 UI + 接口
1. 生成选题（`/api/topic/generate`）
2. 候选卡片 + 选择（`pickTopic`）
3. 确认参数 + 勾"存为待审核"（`/api/pipeline/start`，带 `--no-publish`）
4. 生产执行 + 就地轮询日志（`GET /pipeline/status/{task_id}`）
5. 到达待审核（读 `result.json` 的 `draft_status`）

> 关键开关：**「先存为待审核」勾选框 `topic/page.tsx:1178`** → `formReview` 传给 `api.startPipeline`（`:586`）→ `pipeline.start(review=True)`（`pipeline.py:229-230` 追加 `--no-publish`）→ 外部 `run_pipeline.py` 把该期 `draft_status` 写为 `PENDING_REVIEW`。这是热点线能主动走"审核→发布"闭环的前提。

---

## 二、抖音线后半部分（待检查）

### 2.1 拆解结果展示什么（问题 a）

`DissectPanel.tsx` 内分两个 Tab（`DissectPanel.tsx:405-450`）：

- **「公众号文章」Tab**：`RewritePreview.tsx` —— 3 篇改写，每篇含质量分（`QualityScoreCard` 四维：格式/有料/共鸣/传播，各25分）、备选标题、主题/字数/摘要、正文预览、用到的素材、改动说明。
- **「拆解分析」Tab**：`MaterialChecklist.tsx`（5 类核心素材清单：观点/案例/数据/金句/方法 + 完整度徽标）+ `DissectAnalysis.tsx`（钩子/受众/爆点/结构/可迁移/迁移建议）。

> 结论 a：拆解结果**展示很丰富**（素材清单 + 3 篇改写预览 + 质量分 + 拆解分析），**不缺展示**。

### 2.2 拆解完成后的衔接（问题 b）—— 操作栏 4 个按钮（已核实）

`DissectPanel.tsx:452-488` 操作栏：
- `N 篇全存` `:466`（handleSaveAll:236）→ 逐篇 `api.dissectSaveTopic`，`status:"待生产"`，**只存选题库，不生产**
- `加入选题库` `:471`（handleSaveTopic:214）→ 当前篇 `api.dissectSaveTopic`，**只存选题库，不生产**
- `复制文案` `:481`
- `直接生产` `:483`（handleProduce:272）→ 把当前篇 `topic/angle/extra` 写入 `queueDraft`（`seed.ts:70-87`，`:274`）→ `router.push("/queue")`（`:280`）

> 结论 b：
> - **没有"一键生成选题"按钮**（全仓搜 `dissect` 目录：只有「加入选题库 / 直接生产 / 拿去生产 / 批量生产」，无"生成选题""选择并生产""加入队列"）。
> - 不会"到此为止"——有两条衔接：① 加入选题库（手动存，之后可批量/单条生产）；② 直接生产（手动，把改写正文带草稿跳 `/queue` 自动入队开跑）。
> - **不会自动进入"待审核"**：两条路径都不传 review 概念。

### 2.3 抖音线走哪条生产路径（问题 c）

**完全复用热点线背后的全局队列 `queue.json` + 流水线 `pipeline.start`，不是另一套。**

- 抖音线所有生产入口 → 汇入 `task_queue`（`services/system/queue.py`）：
  - 「直接生产」→ `/queue` 页 `addQueue(source:"manual")` → `queue.add`
  - 选题库「拿去生产」→ `queueDraft` + `/queue`（`DissectPanel.tsx:301-310`）
  - 选题库「批量生产」→ `api.dissectBatchProduceTopics`（`routers/dissect.py:269-296` 调 `task_queue.add(source="topic", topic_id=...)`）
- 队列 worker `_run_loop`（`queue.py:211-290`）调 **同一个** `pipeline.start`（`:231`）。

**与热点线唯一差异（已核实根因）**：
- 热点线 `/topic`「选择并生产」的生产表单有「先存为待审核」勾选（`topic/page.tsx:1178`），`formReview` 传给 `api.startPipeline` → `pipeline.start(review=True)`。
- 队列 worker 调 `pipeline.start`（`queue.py:231`）**未传 `review`** → 落到 `pipeline.py:172` 默认值 `review=False` → 不追加 `--no-publish` → **直接推送微信，不进待审核**。

> 结论 c：抖音线**不是另一套流程**，底层执行器相同；它缺的是"存为待审核"开关（接口参数没传，不是接口不存在）。候选选题卡片 UI 流程也没走（抖音线用「直接生产」跳过候选卡片这一步）。

### 2.4 从拆解素材到"进入待审核"共几步（问题 d）

**正常路径根本不经过"待审核"——该环节缺失/未实现。**

| 步 | 前端 UI（文件:行号，已核实） | 后端接口 | 数据流 |
|---|---|---|---|
| 1. 拿拆解素材（结果区就绪） | `DissectPanel.tsx:357-490`（articles/dissect 两 Tab） | 无（本地 state） | 用户已看 3 篇改写 + 素材清单 |
| 2. 点「直接生产」 | `:483`→`handleProduce:272` | 写 `queueDraft`(`seed.ts:70-87`)，跳 `/queue` | topic/angle/extra 进 sessionStorage |
| 3. /queue 自动入队并启动 | `queue/page.tsx` | `POST /queue/add` + `POST /queue/start` → 跳 `/tasks` | 任务入 `queue.json`，worker 启动 |
| 4. 队列 worker 跑流水线 | 无（后台线程） | `_run_loop:211` → `pipeline.start(review=False)`(`:231`) | **直接推送公众号** |
| ★ 进入待审核 | **缺失/未实现（正常路径）** | `pipeline.start` 默认 `review=False`（`pipeline.py:172,229-230`）；队列调用未传 review（`queue.py:231`） | 正常不产生 `PENDING_REVIEW` |
| （兜底）5. 推送失败→PENDING_REVIEW | `/tasks?review=1` 审核模式 + `ConfirmPublishDialog` | `run_pipeline.py` 置 `PENDING_REVIEW`；`POST /pipeline/publish` | 失败后用户到 /tasks 审核 |

> 结论 d：正常共 **4 步**到"完成（直发微信）"，中间**没有"待审核"环节**。唯一能落到待审核的是微信推送失败的兜底，此时在 `/tasks` 审核模式可见并发布。**抖音线后半段没有内联队列/进度/日志**——日志在 `/queue`、`/tasks` 页看，不在拆解页就地显示（热点线在 `/topic` 页就地显示，见 1.1 第④步）。

### 2.5 抖音线到审核/发布闭环（问题 e）

三步弹窗 `ConfirmPublishDialog`（期号 → 生成封面预览 → 确认发布）是**全局复用组件**（`components/tasks/ConfirmPublishDialog.tsx`），`/topic`、`/tasks`、`/`（首页）三处都引用。

- **作为设计路径：不能。** 抖音线所有生产入口经队列，`review=False` 默认直推，**不会置 `PENDING_REVIEW`**，因此不会主动弹出"期数→封面→发布"三步框。
- **作为失败兜底：能。** 微信推送失败但文章+封面已生成时，该期被置 `PENDING_REVIEW`（`pipeline.py:420` 附近注释），用户可在 `/tasks?review=1` 审核模式看到，并复用同一 `ConfirmPublishDialog` 走三步发布。
- **对比热点线**：热点线有"先存为待审核"勾选（`topic/page.tsx:1178`），可**主动**走 review 路径，正常就能在三步弹窗里审封面再发布。抖音线 UI **没有等价开关**。

> 结论 e：三步弹窗**代码存在且可复用**，但抖音线正常（直发）路径**根本不进待审核**，故"审核→发布"闭环对抖音线是**缺失/未实现为设计链路**，仅推送失败兜底可达。

---

## 三、逐环节对比表（核心交付）

| 环节 | 热点线做法（基准） | 抖音线做法 | 差距/缺失 | 严重度 |
|---|---|---|---|---|
| **素材 → 带入** | 热点页勾选 / 数据分析 / 历史任务 经 sessionStorage + 后端实时 insight 带入 `/topic`（`hotspot:121-143`、`topic:394-429`） | 拆解结果在 `DissectPanel` 本地 state，靠「加入选题库」手动存 或「直接生产」带正文 | 抖音线素材不自动带入选题流；需手动 | **中** |
| **选题生成** | 「生成选题」按钮 `topic:976` → 出 N 个候选卡片（标题/角度/结构/背景）让你挑 | **无"生成候选选题"步骤**；只有 3 篇改写结果（每篇带备选标题），等于"选题即改写" | 缺候选选题卡片 + 选择环节 | **高** |
| **选题确认** | 候选卡片「选择并生产」`topic:1074` 填表单就地生产；或「加入队列」`topic:1061` | 无"选择并生产"卡片；「直接生产」`:483` 跳过确认直接进队列；「加入选题库」`:471` 手动存 | 缺"选择并生产"就地确认 UI | **高** |
| **生产参数** | 生产表单含平台/补充要求/**「先存为待审核」勾选(:1178)**/自动补史料 | 无生产参数表单（「直接生产」直接跳队列）；review 概念缺失 | 缺待审核开关（根因见下） | **高** |
| **生产执行 / 日志** | 同页"生产日志"卡片 `topic:1225-1547` + 内联队列进度卡 `:1102`，就地轮询 | 「直接生产」跳 `/queue`→`/tasks`，日志在别页看，**不在拆解页内联** | 缺内联日志/进度体验 | **中** |
| **待审核** | `review=True` → `--no-publish` → `PENDING_REVIEW`，审核区 `topic:1431` | 队列调 `pipeline.start` 未传 review（`queue.py:231`），默认 `review=False`（`pipeline.py:172`）；正常**不进待审核**，仅推送失败兜底 | **正常路径缺失"待审核"环节**（缺接口衔接，非缺接口） | **高** |
| **封面发布闭环** | 审核区「确认发布」`:1450` → `ConfirmPublishDialog`（期数→封面→发布）主动可达 | 三步弹窗代码复用，但抖音线正常直发不触发；**仅推送失败兜底在 `/tasks` 走通** | 主动审核/发布闭环缺失（仅兜底） | **高** |

---

## 四、5 个核心问题回答（逐条）

**a. 抖音线拆解完后，能否像热点线一样「看到候选选题卡片 → 一键选择并生产 → 就地看日志」？**
→ **不能。** 抖音线没有"生成候选选题卡片"这一步（全仓无此 UI）；只有「直接生产」（单篇直发，跳过候选）和「加入选题库」后批量生产。也没有"选择并生产"就地确认表单，更没有在拆解页就地看生产日志（日志在 `/queue`、`/tasks` 页）。

**b. 抖音线是否缺少「生成具体选题标题」这一步？**
→ **缺"候选选题"这一步。** 抖音线拆解已直接产出 3 篇改写（每篇带 `rewrite.titles` 备选标题），但这是"改写结果"不是"选题候选"。热点线那种"生成 N 个候选选题标题让你挑、再决定生产哪条"的流程，抖音线没有——选题概念是用户手动从 3 篇改写里挑一篇直接生产。

**c. 抖音线的选题是否进了选题库？还是生产完就丢了？**
→ **有「加入选题库」按钮**（`:471`），手动存入 `dissect` 来源选题库（`routers/dissect.py:145-162`），存了就能批量/单条生产，**不会丢**。但「直接生产」（不经选题库）的产出进全局队列→`/tasks`，也不丢，只是不进选题库。注意：选题库入库是**手动逐篇触发**，不是自动。

**d. 抖音线后半段是否有「内联队列/进度/日志」体验？**
→ **没有在拆解页内联。** 热点线在 `/topic` 页就地显示"生产日志"卡片 + 内联队列进度；抖音线「直接生产」后跳 `/queue`→`/tasks`，日志在队列页/任务页看，不在 `DissectPanel` 就地显示。

**e. 抖音线到审核三步弹窗是否闭环？**
→ **三步弹窗代码存在且全局复用，但抖音线正常路径不触发。** 根因：队列 worker 调 `pipeline.start`（`queue.py:231`）未传 `review`，默认 `review=False`（`pipeline.py:172`）→ 不追加 `--no-publish` → 直推微信，不置 `PENDING_REVIEW`。仅微信推送失败兜底才在 `/tasks` 走通三步发布。热点线因有"先存为待审核"勾选（`:1178`）可主动触发。

---

## 五、三大差距与根因（3 句话总结）

1. **最大差距一：抖音线缺"候选选题卡片 + 选择并生产"这一步**——根因是缺页面/缺衔接逻辑：`DissectPanel` 只有「直接生产/加入选题库」，没有像 `/topic` 那样的"生成候选→挑一条→就地生产"UI 流。
2. **最大差距二：抖音线正常路径不进"待审核"**——根因是缺接口衔接（不是缺接口）：队列 worker 调 `pipeline.start`（`queue.py:231`）未传 `review`，导致默认直推微信，审核/发布三步闭环对抖音线缺失（仅推送失败兜底可达）。
3. **最大差距三：抖音线缺内联生产日志/进度体验**——根因是缺页面：`DissectPanel` 拆解后"直接生产"跳走，不在原地显示队列进度与日志，而热点线在 `/topic` 页就地显示。

> 整体判断：**后端能力（队列 + 流水线 + 选题库 + 三步发布弹窗）抖音线已全部复用，无需重写；问题集中在抖音线前端"衔接层"——把 `/topic` 页那套"候选卡片 → 选择并生产 → 待审核开关 → 内联日志"的体验，接到 `DissectPanel` 拆解结果之后即可补齐。** 属于"缺页面/缺衔接逻辑"，修复成本集中在前端。

---

## 六、被引用文件清单（绝对路径）

**前端**
- `<repo-root>/frontend/src/app/topic/page.tsx`（基准）
- `<repo-root>/frontend/src/app/hotspot/page.tsx`（素材来源入口）
- `<repo-root>/frontend/src/app/dissect/page.tsx`（抖音线主页）
- `<repo-root>/frontend/src/components/dissect/DissectPanel.tsx`（抖音线操作栏/衔接）
- `<repo-root>/frontend/src/components/dissect/RewritePreview.tsx`
- `<repo-root>/frontend/src/components/dissect/MaterialChecklist.tsx`
- `<repo-root>/frontend/src/components/dissect/DissectAnalysis.tsx`
- `<repo-root>/frontend/src/components/tasks/ConfirmPublishDialog.tsx`（三步发布弹窗）
- `<repo-root>/frontend/src/lib/api.ts`
- `<repo-root>/frontend/src/lib/types.ts`
- `<repo-root>/frontend/src/lib/seed.ts`（queueDraft）

**后端**
- `<repo-root>/backend/routers/topic.py`
- `<repo-root>/backend/services/content/topic.py`
- `<repo-root>/backend/routers/dissect.py`
- `<repo-root>/backend/services/content/pipeline.py`
- `<repo-root>/backend/services/system/queue.py`
- `<repo-root>/backend/routers/pipeline.py`
- `<repo-root>/backend/routers/queue.py`

**外部依赖（不在本仓）**
- `<streamlit_root>/scripts/run_pipeline.py`：写 `PENDING_REVIEW` / 处理 `--no-publish`，本仓只读取其结果。
