# Content-Workbench + side-hustle 集中验收报告（第 2 轮 / 11 项）

- **日期**：2026-08-11
- **范围**：对最近完成的 11 项工作（W / X′ / Y / Z / AC / AD / R / S / T / L / M）做一轮集中验收
- **方法**：能直接调函数/脚本的优先直接调（prefer 真实输出）；重启服务或真实发布只报告方案不执行；全程只读为主，临时验证文件验完即清。
- **原则**：拿不到证据写「无法验证 + 原因」，禁止写「正常 / 没问题」。

---

## 1. 指令 W — 偏好参数穿透（最重要）

- **结论：PASS**
- **证据**：
  - a. `side-hustle/scripts/generate_issue.py:467-468`：`build_topic_draft(topic, angle="", extra="", references="", platform="wechat", style=None, word_count=None, domains=None, forbidden_topics=None)` —— 4 个新参数已在签名中。
  - b. `side-hustle/scripts/run_pipeline.py`：`get_arg`(L102)/`has_flag`(L98) 自定义解析器；`run_manual` 在 L208-211 用 `get_arg` 读取 `style/word-count/domains/forbidden-topics`，L225-232 **仅非空时**追加进 `gen_cmd`；自动模式 L334-337 同样读取。
  - c. `ls side-hustle/scripts/*.bak` → `generate_issue.py.bak`、`run_pipeline.py.bak` 均存在。
  - d/e. 重跑离线验证 harness（`_archive_junk/_verify_sidehustle_forward.py`）→ **A 向后兼容一致 / B 约束注入 / C 禁区拒写 / D 透传 flag：ALL PASS**。注入段样例（L516-518，截取）：
    ```
    ## 本篇硬性约束（必须遵守）
    - **文风**：{style}
    - **字数范围**：{word_count} 字（成稿须落在此区间，偏短偏长都算不合格）
    - **领域聚焦**：仅限以下领域展开 —— {domains}；偏离则读者无感。
    - **禁写禁区**：以下话题一律不写 —— {forbidden_topics}；若主题命中任一，直接拒写，不得绕开。
    ```
    4 参数实际行为：`style`→文风；`word_count`→字数范围（带合格判定）；`domains`→领域聚焦；`forbidden_topics`→**双重**——既在 L480-485 做「标题命中即确定性拒写（不调模型）」，又在约束段写「禁写禁区」。
- **备注**：4 参数端到端透传已闭环，改造前后无参时输出字节一致（向后兼容）。

## 2. 指令 X′ — 检索接入出稿

- **结论：PASS**
- **证据**：
  - a. `backend/services/content/pipeline.py:21` `from ..data.retrieval import search as retrieval_search`；`:134` 定义 `_supplement_refs_with_retrieval`；`:141` 调用 `retrieval_search(query=topic, top_k=top_k)`；`:200-201` `start()` 在 `auto_supplement_refs=True`（默认）时调用。
  - b. 静默降级：`pipeline.py:142-144` 检索抛错 → `except` 返回原 `references`；`:145-146` 无命中 → 返回原值；`:159-160` 全部为空被跳过 → 返回原值。**绝不阻塞出稿**。
  - c. 前端开关：`frontend/src/lib/api.ts:267` `autoRefs?: boolean`；`frontend/src/app/topic/page.tsx:230` 注释「是否自动检索历史素材…默认开」、`:409` payload `autoRefs: formAutoRefs`、`:968-969` 开关文案「自动补充」+「历史素材」span（拆成两个节点，故整串 grep 搜不到）。
  - d. 拼装演示（topic="中国AI大模型"，不真实出稿）输出：
    ```
    https://news.example.com/hot-topic-123

    【历史素材补充（自动检索，仅供写作引用）】
    1. 【issue_seed】中国AI大模型周调用量连续十五周超美国：真实踩坑篇：<正文摘要…>
    2. 【issue_seed】中国AI大模型周调用量连续十五周超美国：真实踩坑篇
    ```
- **备注**：接线位置 `pipeline.py:134-161`（函数）+ `:200-201`（调用）；用户 references 保留，命中结果以空行分隔追加。

## 3. 指令 Y — 评估执行器

- **结论：PASS（基线已建立）**
- **证据**：
  - a. `backend/eval/eval_run.py` 存在且已运行，产出 `backend/eval/result/`。
  - b. `result/` 下 20 个 `{id}_{category}.json` + `_summary.json`。逐题结论：通过 #6/#7/#8/#10；失败 #9/#11-#20；跳过 #1-#5。
  - c. `_summary.json`：总 20 / 运行 15 / 跳过 5 / 报错 0 / 通过 4 → **整体准确率 26.67%**。分类：topic 80%（4/5，#9 因 expected_keywords 错配失败）、hotspot 0%（0/5）、retrieval_history 0%（0/5）。最弱：hotspot（与 retrieval_history 并列 0）。跳过 #1-#5 原因：`缺 sample_text/url，按规则跳过（不编造输入）`。
- **备注**：目的「可重复基线」已达成；低分是预期（语料稀疏 + expected_keywords 与服务产物错配 + 无 DeepSeek key/搜索源）。

## 4. 指令 Z — side-hustle 入 Git

- **结论：PASS**
- **证据**：
  - a. `cd side-hustle && git rev-parse --is-inside-work-tree` → `true`。
  - b. `git log -1` → `HEAD = a2927f8c0269967b4387baa22395163d528135cb`，提交信息「chore: 初始化 side-hustle 仓库（源码+配置，排除密钥与生成物）」；`git ls-tree -r --name-only HEAD | wc -l` → **28 个文件**；`git status --short` → **空（working tree clean）**。
- **备注**：精确 `git add` 显式清单提交；`.secrets.json`/`data/`/`.workbuddy/`/`*.bak`/`__pycache__` 均被 `.gitignore` 排除。

## 5. 指令 AC — 种子语料导入

- **结论：PASS**
- **证据**：
  - a. `retrieval.index_stats()` → `doc_count = 4`，`by_source = {'dissect':1, 'issue_seed':3}`。
  - b. `search("AI")` → 3 条（全部 `source=issue_seed`：AI实战×2 / AI课程×1）；`search("写作")` → 0 条（正文无字面「写作」token，属 FTS5 分词匹配的正常行为，非 bug）。
  - c. `ls content-workbench/_archive_junk/seed_retrieval.py` 存在（4587 字节）；`backend/scripts/` 已无活脚本（仅留空目录）。
- **备注**：3 篇 side-hustle 历史文章 + 1 条 topic_library 已进检索库；「写作」类查询需文章正文含该词才命中，建议用主题词（AI/大模型/斯坦福）检索。

## 6. 指令 AD — 验收报告修正

- **结论：PASS**
- **证据**：
  - a. `docs/verification-report.md` 第 7 项已改为「`references` 实际被 side-hustle 接收并进入 `build_topic_draft`；FAIL 仅因检索库未被调用」；第 8 项「整条契约错位」已改为「仅 4 个偏好参数未透传」，并补全 `run_pipeline.py` 自定义 argv 解析器 + `run_manual` 转发 `--topic/--angle/--references/--platform` 的真实契约证据。
  - b. 报告开头新增「**更正说明（2026-08-11）**」：含日期 + 更正原因（初版基于误判，经 Segment V 契约核查更正）。
- **备注**：本报告上一轮已按 Segment V 结论修正，本次核对无误。

## 7. 指令 R — hotspot 提示词升级

- **结论：PASS**
- **证据**：
  - a. `backend/prompts/hotspot/system.md` 已替换为新版：L3 `数据来源：{data_source}`；L14-18「数据来源规则」——模拟数据必须返回 `{"insight":"当前为演示模式…","angles":[]}` 且禁止编造；L10 角度必须附「依据：哪条标题的哪个点」；L19「不超过 8 条 angles」。
  - b. `backend/services/integration/hotspot.py`：L19-20 `DATA_SOURCE_REAL/MOCK` 常量；L266 `.replace("{data_source}", data_source)`；真实搜索 L315/L329 传 `DATA_SOURCE_REAL`，内置 mock L338 传 `DATA_SOURCE_MOCK`。
  - c. 模拟数据源实跑：`hotspot.search({}, "AI", "近7天")` → `insight=''`、`origin="示例数据(mock)"`、6 条 mock items。**未编造任何分析**。
- **备注**：安全属性（不编造）在无 DeepSeek key 沙箱下已满足（insight 为空而非虚构）；字面「演示模式」文本需配置 DeepSeek key 后由模型按 L16-18 生成——属预期（无 key 时 enrich 直接短路返回空，不崩）。

## 8. 指令 S — vision/ocr 提示词合并

- **结论：PASS**
- **证据**：
  - a. `backend/prompts/` 仅剩 `ocr-shared/`（另有 dissect/hotspot/quality/pipeline-external + `_baseline.json`）；旧 `vision/`、`ocr/` 目录已删除（ls 确认）。
  - b. `vision.py:128-130` `from ..prompts import load_ocr_shared` + `_SHARED = load_ocr_shared()`；`ocr_structure.py:29-31` 同。
  - c. `mode_rule` 注入区分正确：`vision.py:136-140` `input_desc="（图片）"`、`mode_rule="若为图片：图片清晰能确认所有数字填 high…"`；`ocr_structure.py:37-46` `input_desc="经本地 OCR（{engine}）识别出的文字"`、`mode_rule="若为 OCR 文字：OCR 可能把相似字认错…数字不要猜"`。
- **备注**：vision 与 ocr 共用同一 `ocr-shared` 模板，仅按模式注入不同 `input_desc/ocr_detail/mode_rule/input_block`，输出字段与合并前完全一致。

## 9. 指令 T — 默认文风收敛

- **结论：PARTIAL**
- **证据**：
  - grep 字符串 `"真实、有用、可跟；第一人称，像跟朋友聊天"` 在 `backend/` 命中 4 处：
    1. `backend/prompts/dissect/params.json:2` —— **单一真相源**（运行时，期望的 1 处）
    2. `backend/services/prompts.py:68` —— `_DEFAULT_STYLE_LITERAL` **兜底字面量**（运行时）
    3. `backend/prompts/_baseline.json:8` —— 审计基线副本（非运行时）
    4. `backend/_archive_junk/_tmp_default_style_check.py:8` —— 临时校验脚本（非运行时）
  - `dissect.py` / `config.py` 已不再硬编码该串（grep 未命中），改由 `load_dissect_default_style()` 读取 `params.json`。
- **备注**：单一真相源已建立、调用方收敛到位；但 `prompts.py:68` 仍保留一个兜底字面量（params.json 缺字段时回退），加 2 处非运行时副本，故未达成「仅 1 处」。

## 10. 指令 L — 提示词审计报告

- **结论：FAIL（文件缺失，无法验证）**
- **证据**：
  - `ls docs/ | grep -i audit` → 无；`Glob docs/prompt-audit.md` → **不存在**。
  - 相关产物为 `docs/prompts-inventory.md`（按模块列提示词清单 + 字数 + 重复/覆盖结论），但**不含「得分」维度**，也无「最需要改的模块」结论。
- **备注**：无法汇报各模块得分与最需改进模块，因 `prompt-audit.md` 未产出；现有 `prompts-inventory.md` 是清单而非审计评分。

## 11. 指令 M — 输出结构硬校验

- **结论：FAIL（未实现）**
- **证据**：
  - `Glob backend/services/content/validate.py` → **不存在**；`ls backend/services/content/` → 仅 `dissect.py/pipeline.py/quality.py/topic.py`（无 validate.py）。
  - `grep "validate" dissect.py` → **无匹配**，即 dissect 服务未在 LLM 输出后调用任何结构校验，也无重试逻辑。
- **备注**：dissect 产出目前无结构化硬校验与失败重试；该项指令尚未落地。

---

## 汇总表（11 项）

| # | 项 | 结论 | 一句话说明 |
|---|----|------|-----------|
| 1 | W 偏好参数穿透 | **PASS** | 4 参数入签名 + 透传 + .bak 备份 + 离线 harness 全 PASS（向后兼容/注入/拒写/透传） |
| 2 | X′ 检索接入出稿 | **PASS** | pipeline 调 retrieval.search 并拼 references，空/错静默降级；前端「自动补充历史素材」开关就位 |
| 3 | Y 评估执行器 | **PASS** | eval_run.py 可跑，20 题基线 26.67%（topic 80% / hotspot·retrieval 0%），#1-5 因缺 sample_text 跳过 |
| 4 | Z side-hustle 入 Git | **PASS** | 是仓库；HEAD a2927f8…，28 文件，status 干净 |
| 5 | AC 种子语料导入 | **PASS** | 索引 4 篇（dissect:1+issue_seed:3）；search("AI")→3 issue_seed，search("写作")→0（正常） |
| 6 | AD 验收报告修正 | **PASS** | 第 7/8 项已按 V 结论更正，开头有「更正说明（2026-08-11）」 |
| 7 | R hotspot 提示词升级 | **PASS** | system.md 含 data_source 规则/角度附依据/≤8 条；mock 实跑不编造（insight 空，安全满足） |
| 8 | S vision/ocr 合并 | **PASS** | prompts 仅 ocr-shared；vision/ocr 均从 ocr-shared 加载，mode_rule 图片 vs OCR 区分正确 |
| 9 | T 默认文风收敛 | **PARTIAL** | params.json 单一真相源 + 调用方收敛；但 prompts.py 仍留兜底字面量 + 2 处非运行时副本 |
| 10 | L 提示词审计报告 | **FAIL** | docs/prompt-audit.md 不存在，无法验证得分与最需改进模块 |
| 11 | M 输出结构硬校验 | **FAIL** | validate.py 不存在，dissect 无结构校验/重试逻辑，指令未实现 |

---

## 总结（3 句话）

- **真正闭环的 8 项**：W（偏好透传）、X′（检索接入出稿）、Y（评估基线）、Z（Git 化）、AC（种子导入）、AD（报告修正）、R（hotspot 升级）、S（vision/ocr 合并）——均已有代码/数据落地并通过函数级或运行级验证，可直接信赖。
- **仍有缺口的 3 项**：T（默认文风还差一处兜底字面量收敛 + 2 处非运行时副本）、L（`prompt-audit.md` 从未产出，缺评分结论）、M（`validate.py` 未实现，dissect 缺结构校验与重试）——这三项属于「做了但没收口」或「压根没做」。
- **新发现的意外问题**：无重大意外；但三点需注意——① 种子文章 `search("写作")→0` 说明检索召回依赖主题词而非泛词「写作」，补充历史素材时应用语义主题词；② hotspot 在沙箱无 DeepSeek key 时 mock 模式 `insight` 为空而非「演示模式」文本，安全（不编造）已满足，但「演示模式提示」需配 key 才由模型生成；③ 检索是 FTS5 AND 匹配，topic 须含命中 token 才补充素材，非主题词会静默跳过（设计如此，非缺陷）。
