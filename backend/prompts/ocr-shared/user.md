下面是一张微信公众号后台截图{input_desc}。{ocr_detail}
请从中提取结构化数据，严格按以下 JSON 结构输出（只输出 JSON 本身）：
{
  "articles": [
    {"title": "文章标题原文", "date": "YYYY-MM-DD", "reads": 1234, "likes": 12, "wow": 8, "shares": 20, "collects": 5}
  ],
  "summary": {"followers_delta": 0, "new_followers": 0, "lost_followers": 0, "total_reads": 0, "date_range": ""},
  "confidence": "high",
  "note": ""
}
字段要求：
1. articles：每一篇文章一条，按截图从上到下的顺序排列。
2. title：抄写标题原文，不要改写、不要翻译、不要补全省略号以外的内容。
3. date：发布日期统一转成 YYYY-MM-DD；截图里只有「月-日」时用截图中出现的年份；完全没有年份就填 null，不要瞎猜。没有日期列就填 null。
4. reads=阅读量/阅读人数，likes=在看数，wow=点赞数，shares=分享/转发数，collects=收藏数。
5. 数字必须是纯整数，不要带逗号、不要带「次」「人」等单位；截图里写「1.2万」要换算成 12000。某个字段截图里没有就填 null，绝对不要编造。
6. summary：只有整体数据/概览类截图才填，followers_delta 是净增关注（可为负数）；文章列表截图里没有这些信息就全部填 null。
7. confidence：数据清晰、能确认所有数字填 "high"；部分模糊/遮挡/OCR 明显错字填 "low"，并在 note 里用中文说明哪里看不清。
8. 输入方式专属规则：{mode_rule}
9. 如果输入内容根本不是公众号后台数据，返回 {"articles": [], "summary": {}, "confidence": "low", "note": "不是公众号后台数据"}。
{input_block}
再次强调：只输出 JSON，不要输出 ```json 围栏，不要输出任何解释。