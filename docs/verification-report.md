# Content-Workbench 集中验收报告

- **日期**：2026-08-11
- **范围**：对 10 项既有指令（F / U / 2–9）做一次集中验收
- **更正说明（2026-08-11）**：第 7、8 项初版基于「外部脚本只认 `--force`、整条契约错位、references 被下游丢弃」的误判撰写；后经出稿对接项目契约核查（Segment V）核对 `side-hustle/scripts/run_pipeline.py` 与 `generate_issue.py` 的真实 CLI 契约，确认外部脚本通过自定义 argv 解析器（`get_arg`/`has_flag`）接收并转发 `--topic/--angle/--references/--platform` 等参数、`references` 实际进入 `build_topic_draft`，真实缺口仅为 4 个偏好参数（`--style/--word-count/--domains/--forbidden-topics`）未透传。现据此更正第 7、8 项证据与备注。
- **验收方法说明**：
  - 能直接调函数/脚本的，优先在**隔离的临时 `DATA_DIR`**（系统临时目录 + 仅拷入真实源数据 `topic_library.json` / `douyin_sync.json`）里跑，跑完 `shutil.rmtree` 自清理，**不触碰 `backend/data` 下任何生产文件**。
  - 需读代码确认的，给出 `文件:行号`；需运行时行为的，给出**真实调用输出**。
  - 凡是「无法验证」的，明确写原因，不写「正常 / 没问题」这类无证据结论。
  - `tasks.json` / `llm_usage.jsonl` / `preferences.json` / `memory.db` / 真实 `retrieval.db` 均为**懒创建**（首次运行时才落盘），当前生产目录里这些文件缺失是预期行为，不算缺陷。

---

## 1. 任务持久化（tasks.json）

- **结论：PASS**
- **证据**：
  - 动态验证（隔离目录）：构造 1 条 `status=running` 任务 → `_persist()` 原子写入 `tasks.json`（文件生成、含该 task_id）；模拟服务重启 `_load_tasks()` + `_reconcile()` 后，该任务 `status` 由 `running` 翻转为 `failed`，`error="服务重启导致该任务中断（原后台进程已终止）"`；再次 `_persist()` + 重新读取，`status` 仍为 `failed`。
  - 代码：`services/content/pipeline.py:23-26`（`_TASKS` 热数据 + `TASKS_PATH = DATA_DIR/"tasks.json"`）；`:83-91`（`_persist()` 用 `atomic_write_json` 原子写，`:89`）；`:59-71`（`_reconcile()` 把 `pending/running` 标 `failed`）；`:94-106`（`_ensure_loaded()` 启动时从磁盘恢复并 reconcile）。
- **备注**：文件懒创建，生产目录暂无 `tasks.json` 属正常；重启中断态的「兜底标记」逻辑已验证有效，不会让前端看到永久 `running`。

## 2. 违禁词检测

- **结论：PASS**
- **证据**：
  - 动态验证：对含「最 / 第一 / 百分百 / 国家级」的 ~140 字正文调 `quality.score_article()` → `block=True`、`grade="BLOCK"`、`forbidden_words` 命中含有「最 / 第一 / 百分百 / 国家级」，分类均为「广告法极限词」；对一篇干净短文本调用 → `block=False`（不误杀）。
  - 代码：`services/content/quality.py:86-91`（`_FORBIDDEN_AD_LAW` 含「最 / 第一 / 国家级」等 24 条广告法极限词）；`:94-98`（`_FORBIDDEN_PLATFORM` 平台敏感词 20 条）；`:107-143`（`_load_custom_forbidden_words()` 读配置里的用户自定义词）；`:126-144`（`_check_forbidden_words()` 子串匹配）；`:291-333`（`score_article` 命中即 `grade="BLOCK"`，`:321`）。
- **备注**：三类词（广告法极限词 / 平台敏感词 / 用户自定义）均已接好；「最 / 第一 / 国家级」确属广告法极限词并被正确拦截。

## 3. 会话记忆（memory.db）

- **结论：PASS**
- **证据**：
  - 动态验证：连续 `save_turn` 两条（`user` → `assistant`，session=`verify_acc_20260811`）→ `get_recent(limit=6)` 返回 2 条，顺序为升序 `[user, assistant]`；测试结束后直接 SQL `DELETE` 该 session，残留 0 行。
  - 代码：`services/data/memory.py:30-39`（表 `conversation_turns(id, session_id, role, content, created_at)`）；`:54-83`（`save_turn`）；`:86-104`（`get_recent` 按时间 `DESC` 取后 `reversed`，`:104`，即自然对话升序）。
- **备注**：`memory.db` 懒创建，生产目录暂无属正常；升降序、清理均无残留，机制可靠。

## 4. 偏好记忆（preferences）

- **结论：PASS**
- **证据**：
  - 动态验证：`save_preferences({default_platform:"douyin", style_key:"humor", word_count:"800-1200", domains:["AI","副业","AI"], forbidden_topics:["政治"]})` → `load_preferences()` 往返一致，`domains` 去重为 `["AI","副业"]`；再写回出厂默认后 `load_preferences()` 恢复为 `DEFAULT_PREFS`。
  - 代码：`services/data/preferences.py:27-33`（`DEFAULT_PREFS`）；`:39-69`（`_normalize` 字符串/列表归一、列表去空去重保序）；`:72-81`（`load_preferences` 缺文件/损坏回退默认）；`:84-97`（`save_preferences` 用 `atomic_write_json`）。
- **备注**：`preferences.json` 懒创建，目前生产目录缺失属正常；后续 `pipeline.start()` 会读它作默认值（见第 8 项）。

## 5. FTS5 中文检索

- **结论：PARTIAL**
- **证据**：
  - 动态验证（隔离目录，源数据 = 真实 `topic_library.json`+`douyin_sync.json`）：`build_index(force=True)` 仅索引出 **1 篇文档**（因为 `topic_library.json` 的 `items` 是长度为 **1** 的列表，`douyin_sync.json` 的 `records` 是**空列表 0 条**——这是源数据现状，非索引 bug）。
  - 检索机制本身可用：对命中正文的分词 `search("别")` → 正确召回该文档（`jieba` 分词 `jieba OK=True`，FTS5 AND 匹配正常）。
  - 但 3 个真实业务查询 `search("AI 写作")` / `search("公众号 爆款")` / `search("小红书 选题")` 全部返回 **空**——当前语料只有 1 篇关于「Codex 看板」的主题，不包含这些词。
  - 真实 `backend/data/retrieval.db` 现有 **1 行**，与源数据一致（即「1 行」并非脏数据/陈旧索引，而是源本身就这么少——修正了此前「预期 ~3 行」的假设）。
  - 代码：`services/data/retrieval.py:43-56`（FTS5 虚拟表，`title_seg/content_seg` 为真正索引列）；`:78-84`（`_seg` jieba 分词）；`:120-177`（`_collect_docs`：`items` 取列表、`records` 取列表）；`:195-222`（`build_index`）；`:242-296`（`search` 把 query 也 jieba 分词后 AND 匹配）。
- **备注**：**机制正确，但语料枯竭**，检索当前几乎无实用价值。建议先充实 `topic_library.items`（多积累选题/知识点）与 `douyin_sync.records`（真实同步记录），再 `build_index(force=True)` 重建。

## 6. 成本埋点（llm_usage）

- **结论：PASS**
- **证据**：
  - 动态验证（隔离目录）：连调 `_record("dissect",...)`、`_record("pipeline",...)` 两次 → `llm_usage.jsonl` 生成、共 2 行，schema 字段 = `{time, module, model, prompt_tokens, completion_tokens, cost_est, duration_ms}`（7 字段齐全），首行样例 `{"time":"2026-08-11T...","module":"dissect","model":"deepseek-chat","prompt_tokens":1200,"completion_tokens":800,"cost_est":0.0044,"duration_ms":1234.5}`。
  - 代码：`services/system/llm_usage.py:25`（`USAGE_PATH`）；`:49-75`（`_record` 追加 JSONL）；`:78-117`（`call()` 在 `:105` `if r.status_code < 400` 时才记账，错误响应不记——符合「DeepSeek 错误不返回 usage」）。
- **备注**：`llm_usage.jsonl` 懒创建，沙箱无真实 LLM 调用故生产目录暂无，属正常；记账路径与字段已验证。

## 7. 检索接入生成流

- **结论：FAIL**
- **证据**：
  - `services/content/pipeline.py` 全文 grep `retrieval|use_reference_search|search(` → **无任何匹配**：`start()` 从未调用 `retrieval.search()`，不存在「自动补充历史素材」开关或 `use_reference_search` 参数。
  - `start()` 把 `references`（热点 URL 串）作为 `--references` CLI 标志透传（`:169`）；外部 `side-hustle/run_pipeline.py` 实际**接收**该参数并经由 `generate_issue.py` 的 `build_topic_draft` 进入正文（见第 8 项，契约已核对），`references` 并未被丢弃。本项 FAIL 的唯一原因是 `start()` **从未调用 `retrieval.search()``，即检索库没有被接入生成流。
  - 前端 `frontend/src/app/topic/page.tsx:399` 用 `hotspots.map(h => h.url)` 拼 `refs`，`:404` 仅 `references: refs` 透传给 `api.startPipeline`；全局 grep 前端无「自动补充历史素材 / 检索补充」任何开关。
- **备注**：检索能力（第 5 项）已具备机制，但**完全没有被接入出稿流程**——`start()` 从未调用 `retrieval.search()`；热点的 `references` 虽被正确透传到 `side-hustle` 并进入 `build_topic_draft`，但与检索库无联动。

## 8. 偏好接入默认值

- **结论：PARTIAL**
- **证据**：
  - 后端接线**正确且已验证**：`pipeline.start()` 读偏好作默认值（`services/content/pipeline.py:152` `prefs = load_preferences()`；`:154-158` 把 `platform/style_key/word_count/domains/forbidden_topics` 回退到偏好）；非空时追加对应 CLI 标志（`:175-182` `--style/--word-count/--domains/--forbidden-topics`）。
  - 外部脚本契约**已核对（非错位）**：`side-hustle/scripts/run_pipeline.py` 用自定义 argv 解析器 `get_arg()`（L102）/`has_flag()`（L98），**并非只认 `--force`**；`run_manual`（L200）在 `--topic` 存在时切「手动主题模式」，把 `--topic/--angle/--extra/--references/--platform/--out` 转发给 `generate_issue.py`（后者用 `_argv_has`/`_argv_val` 消费）。即主题/选题/`references` 均能传到生成脚本，主契约满足。
  - **唯一真实缺口**：后端注入的 `--style/--word-count/--domains/--forbidden-topics` 这 **4 个偏好参数**，`run_pipeline.py` 与 `generate_issue.py` 都**不消费**（`build_topic_draft` 签名只含 `topic/angle/extra/references/platform`）。故偏好实际不生效，但**仅限这 4 个参数**，并非整条契约错位。
- **备注**：后端接线完成；外部脚本主契约（主题/选题/`references`）已打通，**仅 4 个偏好参数未透传**。要让偏好生效，只需在 `run_pipeline.py`/`generate_issue.py` 接住这 4 个参数并转发即可（范围明确、改动小）。

## 9. 评估基线（eval）

- **结论：FAIL（未实现）**
- **证据**：
  - `backend/eval/eval_questions.json` 存在：20 道题，id 1–20，分 4 类各 5 道（dissect / topic / hotspot / retrieval_history）。
  - `backend/eval/eval_run.py` → **不存在**；`backend/eval/result/` → **不存在**。
  - `backend/eval/README.md` 明确写「执行脚本待实现」，TODO 列表含 `run_eval.py`。
- **备注**：问题集已就绪，但**没有执行器、没有结果目录**，评估流程无法跑起来；属于「基线已定义、runner 未实现」。

## 10. 外部流水线提示词快照

- **结论：PASS**
- **证据**：
  - `backend/prompts/pipeline-external/` 三件套齐全：`system.md`（4 个 `[[[PROMPT:...]]]` 段：NEWSLETTER_POLISH_SYSTEM @generate_issue.py:328、TOPIC_ARTICLE_SYSTEM @:498、ANTI_AI_RULES @writer.py:77、FEW_SHOT_SEEDS @writer.py:103，均带 `file:line` 溯源）、`user.md`（2 个出稿骨架 NEWSLETTER_DRAFT_SKELETON / TOPIC_DRAFT_SKELETON）、`params.json`（`banned_words` 36、`negative_markers` 22、`common_adverbs` 16、各项 `code_constants` 等，附 `provenance`）。
  - 提取方式：AST 扫描外部 `generate_issue.py` + `writer.py`（`run_pipeline.py` 仅编排、无提示词），由 `backend/_archive_junk/_extract_pipeline_prompts.py` 生成。
  - 外部项目 `side-hustle` 经 `git rev-parse --is-inside-work-tree` 确认 **NOT-A-REPO**（不在 git 中）；此前已建议对其执行 `git init` + 首次提交，**按你的要求未执行、待你确认**。
- **备注**：快照完整可追溯；外部项目未入版本控制是一处风险点（配置无密钥、data/ 为生成物，可安全提交）。

---

## 汇总表

| # | 项目 | 结论 | 一句话说明 |
|---|------|------|-----------|
| 1 | 任务持久化 | **PASS** | `tasks.json` 原子写 + 重启 `reconcile` 均验证通过，落盘与恢复无误 |
| 2 | 违禁词检测 | **PASS** | 含「最/第一/国家级」命中广告法极限词并标 BLOCK，机制正确不误杀 |
| 3 | 会话记忆 | **PASS** | `memory.db` 存 2 取 2、顺序升序、清理无残留，schema 正确 |
| 4 | 偏好记忆 | **PASS** | `preferences` 读写往返 + 列表去重 + 还原出厂值全部通过 |
| 5 | FTS5 中文检索 | **PARTIAL** | 分词/检索机制可用（命中词能召回），但语料仅 1 条、3 个真实查询全空 |
| 6 | 成本埋点 | **PASS** | `llm_usage.jsonl` 写入 7 字段、仅成功响应记账，路径验证通过 |
| 7 | 检索接入生成流 | **FAIL** | `pipeline` 全程未调用 `retrieval`，`references` 实际被 side-hustle 接收并进入 `build_topic_draft`；FAIL 仅因检索库未被调用 |
| 8 | 偏好接入默认值 | **PARTIAL** | 后端已把偏好注入命令行；外部脚本主契约（主题/选题/references）已打通，仅 `--style/--word-count/--domains/--forbidden-topics` 4 个偏好参数未透传 |
| 9 | 评估基线 | **FAIL** | 20 道题已定义，但 `eval_run.py` / `result/` 均缺失，无法执行 |
| 10 | 外部流水线提示词快照 | **PASS** | `pipeline-external/` 三件套齐全且带 `file:line` 溯源，外部项目尚未入 git |

---

## 总结（3 句话）

- **最健康的 3 项**：任务持久化、违禁词检测、会话记忆——均通过函数级动态验证，机制正确、落盘/恢复/清理均无误，可直接信赖。
- **最需要继续做的 3 项**：检索接入生成流（FAIL，根本没接进出稿）、评估基线（FAIL，runner 未实现）、偏好接入默认值（PARTIAL，仅 4 个偏好参数未透传）；此外 FTS5 检索虽机制可用但语料枯竭，也需补数据才能产生价值。
- **方案里没预期到的意外问题（已更正）**：后端 `pipeline.start()` 与真实外部 `run_pipeline.py` 的契约**并非完全错位**——外部脚本用自定义 argv 解析器（`get_arg`/`has_flag`），`run_manual` 会转发 `--topic/--angle/--references/--platform/--out` 给 `generate_issue.py`，主题/选题/`references` 均能传到生成脚本，**主契约满足**。经契约核查（见第 8 项），**唯一真实缺口是 `--style/--word-count/--domains/--forbidden-topics` 这 4 个偏好参数未透传**，并非整条契约错位（另：真实 `retrieval.db` 的「1 行」并非脏数据，而是源数据本身 `topic_library` 仅 1 条、`douyin_sync.records` 为空，索引与源一致）。
