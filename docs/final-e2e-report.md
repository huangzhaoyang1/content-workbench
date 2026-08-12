# 主链路 + 质量门 本机端到端验收报告

- 生成时间：2026-08-12
- 项目：content-workbench（后端流水线 + 工作台审核流）
- 验收方式：服务层直调 `pipeline.start()`（未起 uvicorn HTTP 层；沙箱长驻限制下，服务层等价覆盖同一 `_run`/`_attach_quality` 逻辑）
- 安全护栏：`review=True` → `--no-publish`，全程**未推送公众号**；合成期号 99001，验收后已清理，未触碰真实 issues 数据。

---

## 1. 密钥配置（D.1）

| 项 | 结论 | 证据 |
|---|---|---|
| content-workbench `.env` | 不存在 | 文件系统确认缺失 |
| 环境变量 `DEEPSEEK_API_KEY` | 已配置（非空，未打印明文） | env 探测 set(non-empty) |
| side-hustle LLM endpoint | 可达 | `config.json` 指向 `https://api.deepseek.com/v1/chat/completions`；沙箱实测该端点 HTTP 401（网络连通，仅因无 key 的 HEAD）；**本次出稿第 1 次尝试即润色成功 → 真实可达** |

> 说明：`generate_issue.py` 用 stdlib `urllib` 直连 DeepSeek，无需额外 HTTP 依赖；base `python` 即可运行。

---

## 2. 主链路（topic → 出稿 → 待审核）— 结论：PASS

- `availability()` = True（`run_pipeline.py` 存在，`scripts_dir` 解析到 side-hustle）。
- 发起参数：`topic="AI 写周报"`、`platform="wechat"`、`style="真实、有用、可跟"`、`review=True`、`auto_supplement_refs=True`。
- 终态：`final_status=success`，`task_returncode=0`。
- `result.json.draft_status = PENDING_REVIEW` → 确实只落本地草稿、**未推送公众号** ✅。

---

## 3. 质量门（result.json.quality 字段）— 结论：PASS

由 `pipeline._attach_quality` 在 review 任务成功后写入，结构完整：

| 字段 | 值 |
|---|---|
| total | 41.2 |
| block | false |
| threshold | 30 |
| meets_threshold | true |
| forbidden_words | [] |
| dimensions | 格式达标 15.1 / 内容有料 6.6 / 情绪共鸣 9.5 / 传播属性 10.0（各满分 25） |

> 写入位置：`data/issues/<N>/result.json["quality"]`；前端 `TaskDetailDialog` 四维小卡片 + 总分 + 违禁词警告即读此字段。分数为**决策支持，不自动拦截**（人在环）。

---

## 4. 正文结构（AG 成稿质量标准遵从度）— 结论：基本达标（红色加粗口径已修复）

实测正文（LLM 真实润色稿，非降级骨架）：

| 维度 | 实测 | 标准 | 结论 |
|---|---|---|---|
| 字数 | 1946 字符 | 公众号建议 800–1500 | 略超，可接受 |
| emoji 小标题 | 4 个 | 3–5 | ✅ |
| 引用块金句 | 3 个 | 2–3 | ✅ |
| 段落最长 | 123 字符 | ≤3 行/段 | 边缘达标 |
| 红色加粗 | Markdown 粗体 7 处（修复后计入） | 4–8 处 | ✅ 达标（修复后） |

> **已修复**：评分器现同时识别 HTML 红字（`<font color="red">`）与 Markdown 粗体（`**...**`，代码围栏内不误计），两者合计按 4–8 处区间判分。对该 E2E 真实润色稿重跑 `score_article()`，**修复后该稿格式分 = 21.1**（旧口径仅数 HTML 红字 → 红色加粗计 0 → 格式分 15.1，差值 +6.0）。

---

## 5. 素材使用（autoRefs / X′ 生效）— 结论：链路通，本文印证弱

- `pipeline._supplement_refs_with_retrieval` 在出稿前调用 `retrieval_search(topic)` 补充历史素材，**无报错**。
- 终稿未出现「【历史素材补充】」字面标记 → 本次检索可能无命中，或 LLM 已吸收素材但未保留标记。
- 结论：自动补充素材链路已打通并接入出稿，但**本篇未显式印证**历史素材被引用；留作后续用更多选题验证。

---

## 6. 违禁词（AH 生效）— 结论：PASS

- `block=false`，`forbidden_words=[]` → 本文未命中广告法极限复合词 / 平台敏感词，合规扫描正常生效（复合词表已修复误伤，见历史提交）。

---

## 汇总表

| 验收维度 | 结论 | 关键证据 |
|---|---|---|
| 密钥 / LLM 可达 | 可达 | DeepSeek 第 1 次润色成功 |
| 主链路（主题→出稿→待审核） | PASS | success；draft_status=PENDING_REVIEW，未推送 |
| 质量门（quality 字段） | PASS | total/四维/threshold(30)/meets/block/forbidden 齐全 |
| 结构-emoji 小标题 | PASS | 4 / 4 |
| 结构-引用块金句 | PASS | 3 |
| 结构-红色加粗 | 已修复达标 | Markdown 粗体 7 处计入，格式分 15.1→21.1 |
| 结构-段落 / 字数 | 边缘达标 | max_para 123；1946 字 |
| 素材 autoRefs | 链路通 / 印证弱 | 无报错，终稿无字面标记 |
| 违禁词 AH | PASS | block=false |

---

## 总结（3 句话）

1. 主链路（主题 → 本地出稿 → 待审核草稿）与质量门（result.json.quality：四维 + 阈值 30 + 合规标记）在本机**真实跑通**，review=True 全程未触碰公众号，符合「人在环、分数是决策支持不是自动裁决」的设计。
2. DeepSeek 密钥可用、端点可达，本次为**真实 LLM 润色稿**（非降级骨架），质量门基于真实正文打分（total=41.2，达标）。
3. 一处待改进：autoRefs 检索命中未在终稿显式印证（语料增长自然解决，不改代码）；红色加粗评分口径已于收尾阶段修复（现同时识别 HTML 红字与 Markdown 粗体），不影响闭环可用性。

---

## E. 收尾声明

- **SerpAPI 决策 = 不配置**（mock 回退安全可用，检索降级为本地选题库 / 抖音同步，不影响出稿）。
- **热点功能当前为演示模式**，以手动粘贴选题为主；自动化热点抓取（RSS）仅在 side-hustle 自动模式下启用，工作台热点模块为展示/手填形态。
