# 自动补充历史素材（检索 → references）接线报告

> 范围：content-workbench 出稿链路。目标：启动流水线前用 topic 检索选题库 / 抖音同步，
>       把命中结果的「标题+摘要」追加进 references 作为写作参考；开关默认开，关闭则不追加；
>       检索失败 / 无命中一律静默降级，绝不阻塞出稿。

---

## 1. 接线位置（文件:行号）

### 后端 `backend/services/content/pipeline.py`
| 位置 | 改动 |
|---|---|
| L21 | `from ..data.retrieval import search as retrieval_search`（新增 import） |
| L134-159 | `def _supplement_refs_with_retrieval(references, topic, top_k=5)`（新增）：调 `retrieval_search(query=topic, top_k=5)`；命中结果按「标题+摘要」逐行拼成 block；用户已传 references 时用空行分隔后拼接；抛错 / 空结果 → 返回原 references |
| L172 | `start()` 签名新增 `auto_supplement_refs: bool = True`（默认开） |
| L201 | `if auto_supplement_refs: references = _supplement_refs_with_retrieval(references, topic)`（**构造命令之前**） |
| L154-166 | `start()` 文档字符串补充自动补充说明 |

### 后端 `backend/routers/pipeline.py`
| 位置 | 改动 |
|---|---|
| L23 | `PipelineStartReq` 新增 `auto_refs: bool = True` |
| L54 | `pipeline.start(..., auto_supplement_refs=body.auto_refs)` |

### 前端 `frontend/src/lib/api.ts`
| 位置 | 改动 |
|---|---|
| L267 | `startPipeline` 请求体新增 `autoRefs?: boolean` |

### 前端 `frontend/src/app/topic/page.tsx`
| 位置 | 改动 |
|---|---|
| L231 | `const [formAutoRefs, setFormAutoRefs] = useState(true)`（开关，默认开） |
| L409 | `startPipeline({ ..., autoRefs: formAutoRefs })` |
| L960-971 | 生产表单新增「自动补充历史素材」开关（青色 checkbox，位于「待审核」开关下方） |

---

## 2. 一次带检索的 references 拼装样例

假设用户带入了 1 条热点素材 URL，且 topic=`用 AI 写公众号摘要` 命中 2 条历史素材，
最终传给 `--references` 的字符串为：

```
https://news.example.com/ai-summary-tips

【历史素材补充（自动检索，仅供写作引用）】
1. 【选题库】用 AI 写公众号摘要的 3 个技巧：实测可省 70% 整理时间，重点在模块化拆稿。
2. 【抖音同步】AI 副业避坑指南：新手最常见的 5 个误区，先想清楚再花钱。
```

要点：
- 用户原有 references（热点 URL 串）**原样保留在开头**，与补充块用**一个空行**分隔；
- 补充块以 `【历史素材补充（自动检索，仅供写作引用）】` 开头，逐行列出 `序号. 【来源】标题：摘要`；
- 来源中文映射：`topic_library → 选题库`、`douyin_sync → 抖音同步`；
- 该字符串最终经 `--references` 进入 `generate_issue.py` 的 `<!-- 素材：... -->` 注释，作为写作参考（读者看不到）。

---

## 3. 降级与边界（已离线验证）
| 场景 | 行为 |
|---|---|
| 用户已传 references | 空行分隔后拼接，原值不丢 |
| 用户未传 references | references 直接等于补充 block |
| `retrieval_search` 抛错（如 jieba 未装 / SQLite 异常） | `print` 记日志 + 返回原 references，不阻塞出稿 |
| 检索返回空 | 返回原 references |
| `auto_refs=False`（前端关开关） | 完全跳过检索，references 仅含热点 URL |

---

## 4. 验证
- `py_compile` 通过：`backend/services/content/pipeline.py`、`backend/routers/pipeline.py`
- 前端 `tsc --noEmit` 通过（无类型错误）
- 离线端到端（stub 掉 `retrieval_search` / `availability` / `_run_sync` / `_persist`）：
  - `start(topic=..., references="https://x.com/a")` → 构造的 cmd 中 `--references` 含用户 URL + 历史素材 header + 命中标题，且带 `--no-publish`
  - `start(..., auto_supplement_refs=False)` → `--references` 仅含用户 URL，不补充
- 4 项检索降级单测全 PASS（已传/未传/抛错/空结果）
