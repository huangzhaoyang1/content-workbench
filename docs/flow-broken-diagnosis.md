# 流程断裂诊断报告

> **诊断对象**：content-workbench / side-hustle 端到端链路
> **诊断时间**：2026-08-12 21:00–21:30（仅只读，未修改任何文件）
> **诊断结论**：①②③ 是**同一条链路断裂**——根因是**微信公众号凭证未配置**，导致所有「选择并生产 / 加入队列」的任务走到 push 步骤时全部失败 → result.json `status: "error"` → 永远进不了「待审核 / 封面预览 / 确认期数」链路；④⑤⑥ 为设计未落地，本报告**只诊断，不实施修复**。

---

## A. 前端按钮诊断（问题 ①②）

### A.1 「选择并生产」按钮

| 项 | 内容 |
|---|---|
| 文件 | `frontend/src/app/topic/page.tsx` |
| 行号 | L857–L864 |
| 代码 | `onClick={() => pickTopic(t)}`（**不调任何 API**） |
| 实际行为 | `pickTopic`（L373–L380）只设置 `setPicked(t)` / `setFormTopic(t.topic)` / `setFormAngle(t.angle)` / `setPhase("producing")`，**无网络请求** |
| 视觉反馈 | 被选中卡片 `border-emerald-500/60` + 按钮变 secondary（L834–836、L859） |
| 副作用 | **下方远距离** 渲染「生产参数」表单（L886–L996，含选题/角度/补充要求/平台/待审核/启动流水线按钮） |
| 问题 | **点击后页面无自动滚动到表单**，且 toast 只在「启动流水线」后才弹；用户停在候选列表区域就以为「无反应」 |

### A.2 「加入队列」按钮

| 项 | 内容 |
|---|---|
| 文件 | `frontend/src/app/topic/page.tsx` |
| 行号 | L843–L856 |
| 代码 | `onClick={() => addToQueue(t)}` |
| 实际行为 | `addToQueue`（L353–L371）调 `api.addQueue({topic, angle, extra, source: "topic"})` |
| 后端接口 | `POST /api/queue/add`（`api.ts` L438–L449） |
| 参数结构 | `{topic: string, angle: string, extra: string, platform?: "wechat"|"other", source?: string, topic_id?: string}` |
| Loading / 禁用态 | `disabled={enqueuing === t.topic}` + 加载中显示 `<Loader2 animate-spin>`（L846、L850） |
| 错误捕获 | try/catch + `friendlyMessage` 友好化错误 + toast 弹出（L366–L367）；按钮本身**不会被吞错** |
| 成功提示 | `toast("已加入任务队列", {type: "success", action: {label: "去队列", onClick: () => router.push("/queue")}})`（L362–L365） |
| 结论 | **onClick 真接了，无死按钮**；执行链路完整；问题在于**任务执行后用户看不到执行进展（详见 ④）** |

### A.3 后端接口映射总表（问题 ①② 涉及）

| 前端按钮 | 调用的 API（`frontend/src/lib/api.ts`） | 后端路由 |
|---|---|---|
| 生成选题（顶部卡片 L769） | `api.generateTopics()` L247 | `POST /api/topic/generate` |
| 数据洞察（自动） | `api.topicDataInsight()` L257 | `GET /api/topic/data-insight` |
| 加入队列（L847） | `api.addQueue()` L438 | `POST /api/queue/add` |
| 启动流水线（L975） | `api.startPipeline()` L260 | `POST /api/pipeline/start` |
| 流水线状态（轮询） | `api.pipelineStatus()` L285 | `GET /api/pipeline/status/{task_id}` |
| 拉取详情 | `api.taskDetail()` L310 | `GET /api/tasks/{issue}` |
| 打开目录 | `api.openTaskDir()` L316 | `POST /api/tasks/{issue}/open-dir` |

---

## B. 后端任务执行诊断（问题 ①② 的根源）

### B.1 result.json / article.md 完整内容（99004、99005）

#### `side-hustle/data/issues/99004/result.json`（完整）

```json
{
  "title": "为什么中国大模型便宜又好用？",
  "topic": "为什么中国大模型便宜又好用？",
  "angle": "大模型降本与商业化拐点——依据：标题6'大模型迭代降本！AI应用商业化拐点来临？热门大牛股13天9板'及标题4'港股通重塑AI资产估值中枢 大模型从价格战迈向价值战'，可探讨成本下降如何推动应用爆发及价值重估。",
  "platform": "wechat",
  "status": "error",
  "error": "推送失败"
}
```

#### `side-hustle/data/issues/99005/result.json`（完整）

```json
{
  "title": "为什么中国大模型便宜又好用？：真实踩坑篇",
  "topic": "为什么中国大模型便宜又好用？：真实踩坑篇",
  "angle": "以我第一次实操翻车的真实经历切入,讲清楚踩了哪些坑、怎么填。 结合热点《为什么中国大模型便宜又好用？》(来源:新华网)展开。",
  "platform": "wechat",
  "status": "error",
  "error": "推送失败"
}
```

#### `side-hustle/data/issues/99004/article.md` 头部 20 行

```markdown
<!-- ✅ 已 AI 润色（20:47）。发布前请人工抽检。-->
## 昨天我差点被一条热搜唬住了

"**大模型迭代降本，AI应用商业化拐点来临？热门大牛股13天9板**"——刷到这条的时候我在吃早饭，差点被油条呛到。

13天9板是什么概念？**股票价格几乎翻倍**。普通人的第一反应肯定是：又来炒概念了？

但等等。有只股票的股价涨这么疯，背后一定有真实的东西在发生。好奇心压不住了，我花了一整天翻资料、问懂行的人，还真让我摸出点门道来。今天不讲虚的，就聊聊**为什么这波和以前不太一样**。

## "AI最花钱"的时代可能真的在松动

做个简单的类比。早年间手机刚出的时候，一台大哥大要两万块，十分钟能把一个月工资打光。那时候谁敢说人手一部？**但现在呢？** 千元机遍地走，连收废品的大爷都用上智能手机了。

大模型也是这个逻辑。
```

#### `side-hustle/data/issues/99005/article.md` 头部 20 行

```markdown
<!-- ✅ 已 AI 润色（20:47）。发布前请人工抽检。-->
讲真，我上次差点被一个AI工具坑到怀疑人生。

事情是这样的。上个月我想做个副业小项目——用AI帮我写点理财科普短文发到公众号。想法挺美，操作起来却一路翻车。我先是找了个号称"免费"的国外大模型，结果免费额度一天就烧完了，页面弹出个付款码，我盯着那串美元数字，半天没缓过神。

然后我换了另一家，倒是便宜，但生成的东西跟百度翻译腔似的，读起来浑身难受。

钱花了，时间搭进去，稿子没憋出来。

后来一个做技术的老同学看不过去，甩给我一句话："你换个思路，用国内的开源模型自己搭，成本几乎为零。"我当场愣住——**原来便宜又好用的东西，根本不用我满世界找。**

## 别急着用，先搞懂"为什么便宜"
```

> 两份 article.md 均已落地、内容完整、润色成功（文末 `<!-- ✅ 已 AI 润色 -->` 注释）。

### B.2 queue.json 中 99004/99005 的执行记录（截取关键期号）

```json
{
  "id": "c86964a110",
  "topic": "为什么中国大模型便宜又好用？",
  "source": "hotspot",
  "status": "failed",
  "issue": 99004,
  "task_id": "1d95e92bbd92",
  "error": "[2026-08-12 20:47:13] 已写 result.json：<源项目已脱敏>\\data\\issues\\99004\\result.json",
  "created_at": "2026-08-12 20:46:17",
  "started_at": "2026-08-12 20:46:59",
  "finished_at": "2026-08-12 20:47:15"
},
{
  "id": "f9eb7e71df",
  "topic": "为什么中国大模型便宜又好用？：真实踩坑篇",
  "source": "topic",
  "status": "failed",
  "issue": 99005,
  "task_id": "5bd1dd09140b",
  "error": "[2026-08-12 20:47:28] 已写 result.json：<源项目已脱敏>\\data\\issues\\99005\\result.json",
  "created_at": "2026-08-12 20:46:36",
  "started_at": "2026-08-12 20:47:15",
  "finished_at": "2026-08-12 20:47:29"
}
```

> `queue.json` 中 `status: "failed"` 是 content-workbench 后端的判定，**不是因为没产出，而是因为推送失败被整个标为失败**。queue.json 中 99002/99003/99006/99007/99008 同样 `status: failed`，**全部都是推送失败**（99001/99003 是早期 success 的样本）。

### B.3 pipeline.log 中 99004/99005 的执行链路（原文）

```
[2026-08-12 20:46:59] === pipeline start ===
[2026-08-12 20:46:59] 手动主题模式：topic='为什么中国大模型便宜又好用？' angle='大模型降本与商业化拐点……' platform=wechat style='' word_count=''（跳过发布日校验）
[2026-08-12 20:46:59] step1: generate_issue.py (topic mode) -> <源项目已脱敏>\data\issues\99004\article.md
[2026-08-12 20:47:12] step1 OK: 主题草稿已生成
[2026-08-12 20:47:13] 封面已生成（主题=概念学习，期号标识=第3期）：<源项目已脱敏>\data\cover_auto.png
[2026-08-12 20:47:13] 推送草稿箱：<Python 安装目录>\python.exe <源项目已脱敏>\scripts\publish_to_wechat.py … --new --cover …
[2026-08-12 20:47:13] 推送失败：publish_to_wechat.py exited 1
[2026-08-12 20:47:13] 已写 result.json：<源项目已脱敏>\data\issues\99004\result.json
```

99005 同链路（20:47:15 → 20:47:29），过程完全一致：`step1 OK` → `封面已生成` → `推送失败：publish_to_wechat.py exited 1`。

### B.4 结论

| 假设 | 真假 |
|---|---|
| 没执行 | ❌ 执行了（pipeline.log 有 start/step1 OK/封面/推送四步记录） |
| 执行失败 | ⚠️ **前半段（生成文章+封面）成功，后半段（推送公众号）失败** |
| 执行成功但产出为空 | ❌ article.md 完整且已 AI 润色，封面图也已生成 |

**真实情况**：流水线**实际跑通**了文章+封面，但**推送到公众号的子步骤因凭证缺失而失败**，整个流水线被标记为 `error` / `failed`。这就是用户感觉「执行无产出」「看不到期数/封面」的根本原因——产出**已经存在**，但状态码让前端把所有产出都藏起来。

---

## C. 审核/封面预览链路状态（问题 ③）

### C.1 实现现状

`ConfirmPublishDialog.tsx` 三步完整实现：

| 步骤 | 文件:行号 | 内容 |
|---|---|---|
| ① 填封面期号标识 | `components/tasks/ConfirmPublishDialog.tsx` L91–L107 | `<Input>` 默认「第 N 期」，回车在就绪时直接确认 |
| ② 生成封面预览 | 同上 L109–L157 | 调 `api.taskDetail(issue)` → 取 `detail.cover_base64` → `<img>` 展示；就绪前 disabled |
| ③ 确认发布 | 同上 L159–L177 | 「请先生成封面预览」灰按钮 / 失败给「直接发布（无预览）」兜底 |

**实现完整，三步全在**。但有一个**关键触发条件**：

### C.2 触发条件：必须 `draft_status === "PENDING_REVIEW"`

```tsx
// frontend/src/components/tasks/TaskDetailDialog.tsx:168
{detail.draft_status === "PENDING_REVIEW" && (
  <div className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
    ...
    <ConfirmPublishDialog ... />  // 三步弹窗
  </div>
)}
```

只有 `draft_status` 为 `PENDING_REVIEW` 时才会渲染「待审核」区块及三步弹窗。

### C.3 任务详情的质量评分是否显示

```tsx
// TaskDetailDialog.tsx:180
{detail.quality ? (
  <QualityScoreCard quality={detail.quality} />
  // + 门槛达标徽标 + 违禁词告警
) : (
  <div className="rounded-md border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
    该期未生成质量评分（可能是本次改动前产出的草稿）。请直接阅读正文判断。
  </div>
)}
```

`detail.quality` 存在则展示 `QualityScoreCard`，否则提示「未评分」。但 99004/99005 的 result.json 根本没 `quality` 字段（side-hustle 旧版未写入），所以即便能进入待审核也不会有质量卡。

### C.4 链路断裂原因

**`result.json` 的 `status` 是 `"error"`（因为 publish_to_wechat.py 失败），不是 `"PENDING_REVIEW"`**。整个 task list 看起来「全失败」，`TaskDetailDialog` 的待审核块永不渲染 → `ConfirmPublishDialog`（三步弹窗）**永远不会被打开** → 用户自然看不到期数、封面预览、确认发布按钮。

---

## D. 选题库现状（问题 ⑤）

### D.1 选题库数据结构

- 文件：`backend/data/topic_library.json`
- 类型：`{"items": [...]}` 字典
- `items` 数组长度：**1**（实测仅 1 条样本）

第一条样本：
```json
{
  "id": "bac9599899bb",
  "title": "别再刷Codex对话了，我搞了个看板来管它",
  "content": "嗨，我是扬。\n\n最近我干了件大事：把 Codex 的对话管理整个推倒重来了……",
  "theme": "（未填）",
  "category": "（未填）",
  "priority": "（未填）",
  "status": "（未填）",
  "version": 1,
  "tags": [],
  "created_at": "...",
  "updated_at": "..."
}
```

后端 API 完整（`api.ts` L513–L602 共 12 个接口）：`dissectSaveTopic` / `dissectListTopics` / `dissectUpdateTopic` / `dissectDeleteTopic` / `dissectBatchDeleteTopics` / `dissectBatchProduceTopics` / `dissectListTopicTags` / `dissectListTrash` / `dissectRestoreTopic` / `dissectPurgeTopic` / `dissectEmptyTrash` / `dissectListTopicVersions` / `dissectGetTopicVersion` / `dissectRestoreTopicVersion`。

### D.2 前端入口

| 位置 | 是否展示选题库 |
|---|---|
| `/topic` 选题与生产页 | ❌ **完全不展示**——仅在「自动补充历史素材」复选框描述里提了一句（L230、L970） |
| `/douyin-sync` Tab① 即时拆解（嵌 `DissectPanel`） | ✅ 「选题库（N）」按钮在右上角（L317–L320），点开 → `TopicLibraryDialog` |
| `/dissect` 独立路由（直接渲染 `DissectPanel`） | ✅ 同上 |
| 抖音线 Tab② 收藏沉淀 | ❌ 仅展示素材池/配置/运行历史，不展示选题库 |

### D.3 结论

**数据有（1 条）、接口全（12 个）、但前端只有 1 个入口（嵌在 DissectPanel 里的按钮）**。

`/topic` 页面（用户生成选题的主战场）**完全不渲染选题库**。用户从 /topic 进入，看不到任何「历史沉淀的选题」卡片或入口——这正是用户反馈「选题库没看到」的根因。

---

## E. 生成选题后的页面结构（问题 ⑥）

### E.1 `/topic` 页完整区块顺序（topic/page.tsx）

| 顺序 | 区块 | 行号 | 占比/特性 |
|---|---|---|---|
| 1 | `PageHeader`：标题 + 描述 + 顶部入口（热点素材 / 任务队列） | L634–L650 | 顶栏，紧凑 |
| 2 | **流程指示器**：5 步（准备素材 / 生成选题 / 确认参数 / 生产执行 / 完成） | L653–L662 | 横条，一行 |
| 3 | **数据洞察卡片**：自动拉历史数据，展示 3 内容方向 + 3 标题风格 + 建议 | L665–L676 | **视觉比重大**（三块 grid + 标题 + 副标题 + 徽标） |
| 4 | 选题参考 chips（数据分析/历史任务带入） | L679–L732 | 中等，有则展示 |
| 5 | 素材来源提示 + 「生成选题」按钮 | L735–L780 | 一行卡片 |
| 6 | **候选选题卡片**（生成后渲染） | L815–L883 | **页面下半部分**，每张含 title(CardTitle) + angle(CardDescription) + structure + background + 「加入队列」「选择并生产」按钮 |
| 7 | 生产参数表单（点「选择并生产」后才出现） | L886–L996 | 在 ⑥ 下方更远 |
| 8 | 实时日志 + 阶段进度（点「启动流水线」后才出现） | L999–L1320 | 页面最底部 |

### E.2 候选选题卡片字段完整性

```tsx
// topic/page.tsx:839-879
<CardHeader>
  <CardTitle>{t.topic}</CardTitle>            // 标题
  <CardDescription>{t.angle}</CardDescription>// 角度
</CardHeader>
<CardContent>
  <div>建议结构：{t.structure}</div>            // 建议结构
  {t.background && <div>{t.background}</div>}  // 背景（如果有）
</CardContent>
```

四字段齐全：标题 / 角度 / 建议结构 / 背景。每张卡片配「加入队列」「选择并生产」两按钮。

### E.3 结论

候选选题卡片**不是「思考方向 / 数据洞察」的小尾巴**——它是页面下半部分主体区块，标题就是「候选选题 (N)」，每张卡片 4 字段齐全。

**用户感知「没看到具体选题」的可能原因**：
- 「生成选题」按钮在 **L765–L778**（顶部素材卡里），而候选选题卡片在 **L815–L883**（下方远距离）。**点击后页面不自动滚动**，用户停在顶部看不到下面的卡片刷新。
- 数据洞察卡片（L665–L676）视觉比重大、覆盖整个上半屏，可能让用户误以为「这就是全部选题」——实际上它只是「3 个内容方向 + 3 种标题风格」，是抽象方向，**不是具体选题**。
- 候选选题卡片在桌面端每张约 130–180px 高、垂直堆叠 5–8 张，需要滚动 1–2 屏才能看完。视觉上确实「藏在下面」。

---

## F. 总览：链路断裂图（问题 ①②③ 是同一断裂）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 用户操作                                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                                   ▼
  [点击「选择并生产」]                 [点击「加入队列」]
   topic.tsx L857-864                    topic.tsx L843-856
   pickTopic()                          addQueue() → POST /api/queue/add
   仅切换 phase，不调 API               queue 启动 pipeline.start()
        │                                       │
        └─────────────────┬─────────────────────┘
                          ▼
                [queue 启动 pipeline.start]
                     pipeline.py
                          │
                          ▼
        ┌─────────────────────────────────────────┐
        │ subprocess: side-hustle generate_issue  │
        │ + cover                                  │
        │ + publish_to_wechat.py                   │
        └─────────────────────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────────┐
        │ 【断裂点 1】                              │
        │ workbench_config.json:36-39              │
        │ wechat.appid="" / secret=""（空）          │
        │ → publish_to_wechat.py exited 1          │
        │ → pipeline.log: "推送失败"                 │
        └─────────────────────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────────┐
        │ 【断裂点 2】                              │
        │ side-hustle 把整个流水线判为失败          │
        │ result.json:                              │
        │   status = "error"（不是 "PENDING_REVIEW"）│
        │   error   = "推送失败"                    │
        │   quality 字段缺失                        │
        └─────────────────────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────────┐
        │ 【断裂点 3】前端表现                       │
        │ /topic 页面 → 红色「流水线失败」块         │
        │   topic.tsx:1267-1295（status !== success）│
        │                                            │
        │ TaskDetailDialog 待审核块永不渲染          │
        │   TaskDetailDialog.tsx:168                │
        │   `detail.draft_status === "PENDING_REVIEW"│
        │   && ...`（永远 false）                   │
        │                                            │
        │ ConfirmPublishDialog 三步弹窗永不触发      │
        │   用户看不到期数 / 封面预览 / 确认发布      │
        └─────────────────────────────────────────┘
                          │
                          ▼
                [用户感知：执行无产出 + 看不到期数/封面]
```

### 关键断裂点（具体行号）

| 序号 | 文件:行号 | 现状 | 含义 |
|---|---|---|---|
| ① | `backend/data/workbench_config.json:36-39` | `wechat.appid=""` / `secret=""` | 推送凭证缺失，publish_to_wechat.py 必失败 |
| ② | `side-hustle/pipeline.log`（99004 20:47:13 / 99005 20:47:28） | `推送失败：publish_to_wechat.py exited 1` | 推送子步骤真实失败 |
| ③ | `side-hustle/data/issues/99004/result.json:6` & `99005/result.json:6` | `"status": "error"` | 整个流水线被标失败，**而非 `PENDING_REVIEW`** |
| ④ | `frontend/src/components/tasks/TaskDetailDialog.tsx:168` | `detail.draft_status === "PENDING_REVIEW" && (...)` | 待审核块 + 三步弹窗**永不渲染** |
| ⑤ | `frontend/src/app/topic/page.tsx:1267–1295` | `task?.status !== "success"` 显示红色失败块 | 实际有产出但被当失败展示 |

### 「执行成功但展示失败」的对照证据

| 维度 | 真实状态 | 用户感知 |
|---|---|---|
| 文章正文 | ✅ article.md 已生成、已落地、已 AI 润色（99004 L1: `<!-- ✅ 已 AI 润色（20:47）-->`） | ❌ 「执行无产出」 |
| 封面图片 | ✅ cover_auto.png 已生成（pipeline.log: `封面已生成`） | ❌ 「没看到封面预览」 |
| 期号 | ✅ queue.json 里有 issue=99004/99005 | ❌ 「确认期数没看到」 |
| 流水线状态 | ✅ step1 OK / 封面 OK / 推送 FAIL | ❌ 「整期显示失败」 |
| result.json quality | ❌ 字段缺失（side-hustle 旧版未写） | — |
| 任务列表 | ❌ 显示「失败」徽标（`TaskStatusBadge`） | ❌ 「看起来全部没成功」 |

---

## G. 设计未落地项（问题 ④⑤⑥，不在本轮修复范围）

| 问题 | 当前状态 | 用户期望 | 落地点位 |
|---|---|---|---|
| ④ 队列在选题→执行处内联 | ❌ `/topic` 页面**完全不展示队列进度**，仅在 toast 提供「去队列」跳转；用户在 /topic 跑队列时看不到队列状态 | 队列在 /topic 页面底部内联（轮询 + 进度条） | `topic/page.tsx` 增加内联队列区块，调 `api.getQueue()` 轮询 |
| ⑤ 选题库没看到 | ⚠️ 数据有（1 条），接口全（12 个），仅在 DissectPanel 嵌了「选题库（N）」按钮；`/topic` 页面**完全不显示** | 选题库作为 /topic 或独立页面可见入口 | `topic/page.tsx` 顶部加「选题库」按钮 → 弹 `TopicLibraryDialog`；或加 `/topic-library` 独立路由 |
| ⑥ 生成选题后应直接展示具体选题 | ⚠️ 候选选题卡片**已存在**（topic/page.tsx:815-883）且字段齐全，但**位置在页面下半部分**，点击生成后无自动滚动 | 点「生成选题」后自动滚动到候选选题卡片区域；视觉强化候选 vs 抽象方向（数据洞察） | `topic/page.tsx` handleGenerate 成功后加 `scrollIntoView`；候选选题卡片放大视觉权重 |

---

## H. 本轮结论与建议下一步

**已确诊（不动手）**：
- ①②③ 是**同一条根因**——**微信公众号凭证未配置（workbench_config.json:36-39）**，导致 pipeline 推到 wechat 步骤必败 → result.json status=error → 审核三步永不触发。
- ⑤⑥ 是**前端展示缺位**——选题库只在 DissectPanel 一处入口可见；候选选题卡片存在但藏在下半屏。

**修复路径（待用户拍板，本轮不实施）**：

1. **最小修复 ①②③**（推荐先做）：在 `/config` 或 `workbench_config.json` 填入真实的 `wechat.appid` + `secret`（用户需到微信公众平台拿）→ 流水线自然走通 → 99005 之类会进入 `PENDING_REVIEW` → 触发三步弹窗。
2. **如果暂不接 wechat**（仅做诊断 + 演示）：改 side-hustle 判定逻辑——`push 失败但 article+cover 都已生成`时，`result.status` 判为 `PENDING_REVIEW`（而非 `error`），让三步链路可见；用户可走「直接发布（无预览）」兜底确认路径体验完整。
3. **设计落地 ④⑤⑥**：独立工单，本报告只标记缺口位置、不实施。

---

**报告完**。本轮只读，所有结论均可在 ① `workbench_config.json:36-39` ② pipeline.log 20:47:13/28 ③ TaskDetailDialog.tsx:168 处手动复核。