# Prompt 审计报告（终稿）

> 依据：24 处提示词全文审阅（含 R 升级后的 hotspot）。评分维度：引用约束 / 缺失披露 / 数据禁令 / 输出格式 / 语气一致，各 0-2 分，满分 10。

## 评分总表

| 模块 | 引用约束 | 缺失披露 | 数据禁令 | 输出格式 | 语气一致 | 总分 | 状态 |
|---|---|---|---|---|---|---|---|
| dissect 拆解（_DISSECT_*） | 2 | 2 | 2 | 2 | 2 | 10 | 教科书级，勿动 |
| dissect 改写（_REWRITE_* + ANGLES） | 2 | 2 | 2 | 2 | 2 | 10 | 教科书级，勿动 |
| quality 四阶标准 | 2 | 1 | 1 | 2 | 2 | 8 | 缺「结论追溯素材来源」字段 |
| vision / ocr（合并后 ocr-shared） | 2 | 2 | 2 | 2 | 1 | 9 | 反幻觉优秀，人设通用 |
| hotspot（R 升级后） | 2 | 2 | 2 | 2 | 2 | 10 | 已从 1 分升至满分 |
| pipeline-external（side-hustle 出稿） | 1 | 1 | 2 | 1 | 1 | 6 | 最低分模块，W 已补约束段但仍薄弱 |

## 各模块要点
- dissect：M0-M7 素材提取规则、禁止编造、missing 披露、非文案 fallback、素材硬性原料、materials_used 自证——六项最佳实践齐备。
- quality：四阶标准扎实；缺口是「每个结论应能指回素材来源 id」，便于人工审核追溯。
- vision/ocr：null 不编造 + confidence 分级 + 非目标图 fallback，反幻觉到位。
- hotspot：R 升级后具备 data_source 识别、角度须附标题依据、演示模式不编造。
- pipeline-external：是**唯一仍低于 8 分的模块**。理由：① 素材引用约束弱（无「数字必须原样出现」级硬约束，W 已补）；② 无 missing 披露机制；③ 无 persona 一致性约束；④ 输出格式约束弱于工作台侧。**建议后续把工作台 QUALITY_SPEC 的四阶标准注入 external 出稿 prompt**（可参考 W 的注入方式）。

## 结论
- 最健康：dissect 拆解与改写（10/10，双满分）。
- 最需改进：pipeline-external（6/10）——它是真实出稿主链路，建议下阶段把 QUALITY_SPEC 注入其中。
- 无需改动：dissect / hotspot / vision / ocr（保持现状）。（写盘结束）
