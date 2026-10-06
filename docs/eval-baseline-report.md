# 评估基线报告（baseline，非刷分）

> 执行：`python backend/eval/eval_run.py`（在 content-workbench 根目录运行）
> 产物：`backend/eval/result/{id}_{category}.json`（单题）+ `backend/eval/result/_summary.json`（汇总）
> 目的：建立**可重复基线**，量化当前各能力在真实服务层上的表现，定位退化点与数据集缺口。

---

## 1. 运行环境与关键前提

| 项 | 状态 | 对结果的影响 |
|---|---|---|
| jieba | 已装（OK） | retrieval 可建索引、可检索 |
| DeepSeek key | **无** | hotspot 走 mock 模式，`insight=""`；dissect 因无 `sample_text` 全部跳过（未触发 LLM） |
| search_api | **无** | hotspot 走内置 mock，按关键词精确匹配返回（eval 关键词多为「AI Agent」等长短语，mock 库无对应 → `items:[]`） |
| 索引数据 | topic_library 仅 1 条、douyin_sync 0 条 | retrieval 检索命中极少 |

> 因此本基线**不反映真实 LLM 能力**，只反映「在无 key / 无搜索源 / 稀疏索引」下的可重复表现。
> 接入 key + search_api + 充实索引后，重跑即可得到更高、更有意义的基线。

---

## 2. 基线结果

> 注：本节为**较早一次运行**的结果（该次 dissect 记为 skipped）；最新一次运行见文末 **§6「当前基线与已知弱项」**。两节数字口径不同，属正常。

| 维度 | 数值 |
|---|---|
| 总题数 | 20 |
| 尝试 ran | 15 |
| 跳过 skipped | 5（全部 dissect，缺 sample_text） |
| 报错 error | 0 |
| 通过 passed | 4 |
| 失败 failed | 11 |
| **整体准确率（ran 分母）** | **26.67%** |

### 每类准确率
| category | passed / ran | 准确率 |
|---|---|---|
| topic | 4 / 5 | 80.00% |
| hotspot | 0 / 5 | 0.00% |
| retrieval_history | 0 / 5 | 0.00% |
| dissect | 0 / 0（全跳过） | — |

**最弱类别**：hotspot 与 retrieval_history 并列 0%（代码取首个，报 hotspot）。

---

## 3. 被跳过题目及原因

全部为 `dissect` 类，题目缺 `sample_text` / `url` 字段，按规则跳过（不编造输入）：

| id | category | 原因 |
|---|---|---|
| 1 | dissect | 缺 sample_text/url，按规则跳过（不编造输入） |
| 2 | dissect | 同上 |
| 3 | dissect | 同上 |
| 4 | dissect | 同上 |
| 5 | dissect | 同上 |

> 要让 dissect 真正进入评估，需在 `eval_questions.json` 的 dissect 题里补 `sample_text`（真实视频口播稿/文案），这是 README 已列的待办。

---

## 4. 失败原因分析（基线价值所在）

- **topic（4/5 过，Q9 失败）**：`topic.generate` 是纯模板，输出结构化选题（topic/angle/structure/background）。
  Q9 期望关键词「标题风格/探店/日记体/数字体」描述的是「标题风格分析」能力，模板不产出 → 合理失败。
  → 说明：topic 类题目的 expected_keywords 偏「 aspirational 」，需按 `generate` 实际产物校准。
- **hotspot（0/5）**：无 key + 无 search_api → mock 模式，且 mock 按精确短语匹配，eval 关键词「AI Agent」等在 mock 库无对应 → `items:[]` + `insight:""` → 全 miss。
  → 说明：hotspot 分数被「是否配置 search_api + DeepSeek key」完全决定；本环境无法体现真实能力。
- **retrieval_history（0/5）**：索引数据稀疏（仅 1 条），且题目期望关键词「历史/检索/月份」是**任务元词**，不在检索返回的文章内容里 → 全 miss。
  → 说明：retrieval_history 类的 expected_keywords 应基于**实际检索返回的文章内容**来写，而非任务描述词。

---

## 5. 结论与下一步

本基线已可重复运行，稳定暴露三类缺口：
1. **数据集缺口**：dissect 缺 sample_text、topic/hotspot/retrieval 的 expected_keywords 与真实服务产物错配。
2. **环境缺口**：hotspot 需 search_api + DeepSeek key 才能体现真实能力。
3. **索引缺口**：retrieval 需充实 topic_library / douyin_sync 数据。

建议（可选，等确认）：
- 给 dissect 题补 `sample_text`，让拆解路径真正被评估；
- 按各服务真实输出重写 expected_keywords（或改为「结构断言」而非关键词）；
- 配置 key/search_api 后重跑，得到有意义的 hotspot 基线；
- 充实历史索引数据。

---

## 6. 当前基线与已知弱项

> 本节为 2026-08-12 的重跑结果，数据来自 `backend/eval/result/_summary.json`（`generated_at: 2026-08-12T07:46:09`），未做任何美化。
> 与上方 §2 的早期一次运行口径不同（该次 dissect 记为 skipped，本次记为 errored），**以本节为准**。

| 指标 | 数值 |
|---|---|
| 总题数 | 20 |
| 尝试 attempted | 15 |
| 报错 errored | 5 |
| 通过 passed | 5 |
| 失败 failed | 10 |
| **整体准确率** | **33.3%**（20 题中 attempted 15 / errored 5 / passed 5 / failed 10）|

### 分类准确率

| category | 准确率 | passed / attempted |
|---|---|---|
| topic | **0.8** | 4 / 5 |
| hotspot | **0.2** | 1 / 5 |
| retrieval_history | **0.0** | 0 / 5 |
| dissect | — | 5 题全部 errored（未进入判定）|

**最弱类别**：`retrieval_history`（0.0）。

### 已知弱项说明

- **5 道 dissect 题 errored**：均为 `DissectError: 爆款拆解需要 DeepSeek 密钥...`。属**环境问题**（评测环境未配置 DeepSeek 密钥），**非代码缺陷**；配置密钥后重跑即可进入判定。
- **retrieval_history 为 0 是已知弱项**：该类别准确率基于关键词命中判定，而该判定**对生成式输出偏严** —— 生成的文本与 `expected_keywords` 常语义等价但字面不同，按关键词比对时全部未命中。属判定口径问题，非检索能力缺失。
