# side-hustle 偏好透传实现报告（Segment E）

> 范围：`C:\Users\黄朝扬\WorkBuddy\2026-07-28-10-03-37\side-hustle`
> 目标：给出稿函数加 4 个可选偏好参数（style / word_count / domains / forbidden_topics），
>       由工作台经 `run_pipeline.py` 透传到 `generate_issue.py`，缺省时行为与改造前**完全一致**。
> 验证方式：离线 harness（不联网、不真实发布、不写 `data/issues`），对比改造后 vs `.bak` 改造前。

---

## 1. 备份
- `scripts/generate_issue.py.bak`（31794 字节）
- `scripts/run_pipeline.py.bak`（13410 字节）
- 位置：与源文件同目录 `side-hustle/scripts/`。

---

## 2. 改动的函数与行号

### `scripts/generate_issue.py`
| 函数 / 位置 | 改动 |
|---|---|
| `_as_list(v)` — 新增，L446 | 把 domains / forbidden_topics 统一成 list（支持 list 或逗号串） |
| `_refuse_draft(title, hits, today)` — 新增，L455 | 禁区命中时返回确定性拒写草稿（不调模型） |
| `build_topic_draft(...)` — 签名 L467-468 | 新增 4 个可选参数，默认 `None`：`style=None, word_count=None, domains=None, forbidden_topics=None` |
| 禁区预检 — L480-485 | `fb_list = _as_list(forbidden_topics)`；命中任一即 `return _refuse_draft(...)`（确定性，无需模型判断） |
| 约束段注入 — L504-518 | 仅当任一约束非空时，追加 `## 本篇硬性约束（必须遵守）` 段落；原有 prompt 骨架**不动** |
| `main_topic_mode(topic)` — L617 | L624-627 用 `_argv_val` 读 `--style/--word-count/--domains/--forbidden-topics`；L631-635 透传给 `build_topic_draft` |

### `scripts/run_pipeline.py`
| 函数 / 位置 | 改动 |
|---|---|
| `run_manual(force, no_publish, issue_arg)` — L200 | L208-211 用 `get_arg` 读 4 个偏好；L225-232 **仅非空时**追加 `--style/--word-count/--domains/--forbidden-topics` 到 `gen_cmd` |
| `main()`（自动模式）— L334-345 | L334-337 读 4 个偏好；L339-345 非空时追加进 `auto_flags` 后传给 `generate_issue.py` |

**向后兼容保证**：4 个参数全部默认空 / `None`，且「非空才追加」——不带参数时 `gen_cmd` 与改造前逐字节一致，prompt 不出现任何约束段。

---

## 3. 注入的 prompt 片段样例（含前后文）

调用：`build_topic_draft(topic="用 AI 做副业有哪些靠谱方向", angle="从上班族视角",
references="某报告提到 AI 摘要可省 70% 时间", platform="wechat",
style="口语化、像朋友聊天，少用术语", word_count="1200-1600",
domains=["AI副业","效率工具"], forbidden_topics=["股票","政治"])`

> `## 参考素材（仅供写作引用，读者看不到，成稿不得出现『素材：』字样）`
> `<!-- 素材：某报告提到 AI 摘要可省 70% 时间 -->`
>
> `## 本篇硬性约束（必须遵守）`
>
> `- **文风**：口语化、像朋友聊天，少用术语`
> `- **字数范围**：1200-1600 字（成稿须落在此区间，偏短偏长都算不合格）`
> `- **领域聚焦**：仅限以下领域展开 —— AI副业、效率工具；偏离则读者无感。`
> `- **禁写禁区**：以下话题一律不写 —— 股票、政治；若主题命中任一，直接拒写，不得绕开。`
>
> `> 以上约束与「绝不无中生有」铁律同等重要：未满足任一，成稿即不合格。`
>
> `## 正文`

关键点：原有「参考素材」「正文」骨架完全保留，约束段**仅追加在两者之间**；不带偏好时这一段根本不会出现。

---

## 4. 测试结果（离线，无发布 / 无写盘）

| 测试 | 场景 | 结果 |
|---|---|---|
| A 向后兼容 | 不带 4 参数，`build_topic_draft` 输出 vs `.bak` 改造前 | **PASS**（324 字节完全一致，无 diff） |
| B 约束注入 | 带 style+word_count（+domains+forbidden） | **PASS**（`**文风**`/`**字数范围**`/`**领域聚焦**`/`**禁写禁区**` 全部注入；仅带 style+word_count 时不出现 domains/forbidden 段，无污染） |
| C 禁区拒写 | forbidden=["股票","政治"] 命中主题"今天聊聊股票投资的入门" | **PASS**（出现 `⛔` 头 + `命中禁写清单` + `未调用生成模型`；未命中主题正常出稿，不含拒写头） |
| D 透传 flag | `run_manual` 经 `gen_cmd` 转发（subprocess 被拦截） | **PASS**（`--style/--word-count/--domains/--forbidden-topics` 及各自取值全部出现在子进程命令中） |

> 注：C 项最初用主题"炒股入门怎么选股"误判为未拒写——因"股票"不是"炒股入门怎么选股"的子串；
> 改用含"股票"子串的主题后确认拒写逻辑正确。判定符用 `⛔`/`命中禁写清单`（普通草稿约束段也会写"直接拒写"，故"拒写"二字不可作判别符）。

---

## 5. 结论
- 4 个偏好参数已实现端到端透传：工作台 → `run_pipeline.py` → `generate_issue.py` → prompt。
- 向后兼容：缺省行为零变化，已用 `.bak` 字节级比对证明。
- 禁区命中为确定性拒写，不消耗模型调用，安全且可离线验证。
- 改造前源码已 `.bak` 留存，可随时回滚。

---

## 6. 待办（可选，未执行）
- `content-workbench/docs/verification-report.md` 第 7、8 项含已被 Segment D 推翻的误判
  （"契约完全错位 / 外部只认 --force / references 被丢弃"）。如需，可将第 8 项原因收窄为
  "仅 4 个偏好参数未透传"，并删除第 7 项"references 被丢弃"一句（references 实际已透传）。
