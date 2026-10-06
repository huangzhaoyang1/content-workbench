"""热点搜索逻辑（复用现有 Streamlit 工作台的搜索/智能分析算法）。

统一入口 search() 返回 (items, origin, insight)：
  - 优先级：SerpAPI 实时搜索 → 自定义接口(hotspot_api.api_url) → 内置 mock
  - 任何异常都回退 mock，不影响主链路；未配置 Key 时自动用 mock
  - 每日额度保护（见 services/system/quota.py）
DeepSeek 智能分析仅在配置了 Key 时调用，失败静默降级。
"""
from __future__ import annotations

import json as _json

from ..system.llm_usage import call as llm_call

TIME_RANGES = {"近1天": 24, "近7天": 24 * 7, "近30天": 24 * 30}

# data_source 取值：用于热点洞察提示词模板的 {data_source} 占位符。
# 真实用 SerpAPI / 自定义接口数据时为「真实搜索」；回退到内置示例数据时为「模拟数据...」。
DATA_SOURCE_REAL = "真实搜索"
DATA_SOURCE_MOCK = "模拟数据（未配置真实搜索源）"

HOTSPOT_MOCK: list[dict] = [
    {"id": "h01", "hours_ago": 3, "source": "机器之心", "url": "https://www.jiqizhixin.com/articles/hot-01",
     "title": "OpenAI 发布 GPT-5.5:上下文窗口翻倍,推理成本降到三分之一",
     "summary": "新模型把长文本上下文从 128K 提到 256K,同时把每百万 token 的定价砍到原来的三分之一。"
                "官方给出的实测里,复杂多步推理任务的正确率提升约 18%,而延迟基本持平。"
                "对个人开发者来说,最大的变化是长文档问答终于不用再折腾切片和向量库了。"},
    {"id": "h02", "hours_ago": 7, "source": "量子位", "url": "https://www.qbitai.com/articles/hot-02",
     "title": "Claude Code 正式支持本地 Skill 市场,一句话装插件",
     "summary": "Anthropic 上线技能市场,允许把常用工作流打包成 Skill 分发,安装只需一条命令。"
                "早期数据显示,装了 3 个以上 Skill 的用户,单任务平均工具调用次数下降了四成。"},
    {"id": "h03", "hours_ago": 11, "source": "36氪", "url": "https://36kr.com/p/hot-03",
     "title": "AI 副业调研:70% 的人卡在「有工具但没交付物」",
     "summary": "针对 2000 名 AI 副业从业者的调研显示,真正月入过万的不到 8%,绝大多数人停在学工具阶段。"
                "报告指出,能持续变现的人有个共同点:把能力固化成了可重复交付的标准流程,而不是靠灵感接单。"},
    {"id": "h04", "hours_ago": 20, "source": "InfoQ", "url": "https://www.infoq.cn/article/hot-04",
     "title": "多智能体框架大洗牌:LangGraph、AutoGen、CrewAI 实测对比",
     "summary": "同一套客服工单任务分别在三个框架上跑通,从开发耗时、稳定性、可观测性三个维度做了横评。"
                "结论是复杂状态流转选 LangGraph,快速原型选 CrewAI,企业级审计需求选 AutoGen。"},
    {"id": "h05", "hours_ago": 30, "source": "新智元", "url": "https://www.aiera.com.cn/hot-05",
     "title": "国产大模型价格战再升级:主流厂商推理价格集体腰斩",
     "summary": "近一周内多家国内厂商密集调价,主力模型的输入价格普遍下调 50% 以上,部分轻量模型直接免费。"
                "行业分析认为,竞争焦点正在从跑分转向落地场景和工程化能力。"},
    {"id": "h06", "hours_ago": 44, "source": "少数派", "url": "https://sspai.com/post/hot-06",
     "title": "我用 AI 把公众号日更压缩到 20 分钟:一条可复制的流水线",
     "summary": "作者拆解了自己的内容流水线:定时抓热点 → 模型出稿 → 人工补一段真实体感 → 自动推草稿箱。"
                "关键经验是别追求全自动,把人的判断留在最值钱的那一步,其余全部脚本化。"},
    {"id": "h07", "hours_ago": 58, "source": "虎嗅", "url": "https://www.huxiu.com/article/hot-07",
     "title": "企业 AI 落地的真实困境:买了工具,没人会用",
     "summary": "多家企业采购 AI 工具后使用率不足两成,核心问题不是模型能力,而是没人把业务流程翻译成 AI 能接的输入。"
                "这也是 FDE(前向部署工程师)这个岗位在过去半年需求暴涨的直接原因。"},
    {"id": "h08", "hours_ago": 80, "source": "GitHub Trending", "url": "https://github.com/trending/hot-08",
     "title": "开源项目一周暴涨 2 万 Star:把任意网页一键转成 Agent 可调用工具",
     "summary": "项目通过解析页面结构自动生成工具描述和调用代码,省掉了手写 API 封装的环节。"
                "目前已支持主流电商、资讯、文档站点,社区正在补充中文站点的适配规则。"},
    {"id": "h09", "hours_ago": 110, "source": "钛媒体", "url": "https://www.tmtpost.com/hot-09",
     "title": "AI 短视频工厂跑通:单人日产 30 条,成本不到 5 块钱",
     "summary": "团队用脚本串联选题、文案、TTS、动态图形和成片导出,把本地生活类短视频的生产成本压到极低。"
                "瓶颈已经从生产端转移到分发端,账号权重和投放策略成了新的关键变量。"},
    {"id": "h10", "hours_ago": 140, "source": "爱范儿", "url": "https://www.ifanr.com/hot-10",
     "title": "本地小模型能力跃迁:7B 模型在消费级显卡上跑出可用体验",
     "summary": "新一轮量化和蒸馏方案让 7B 级模型在 8G 显存设备上稳定推理,常见办公任务的完成度接近云端中杯模型。"
                "对数据敏感的中小企业来说,本地部署的门槛第一次降到可接受范围。"},
    {"id": "h11", "hours_ago": 190, "source": "极客公园", "url": "https://www.geekpark.net/hot-11",
     "title": "提示词工程正在消亡?结构化上下文成为新共识",
     "summary": "随着模型指令遵循能力增强,靠咒语堆砌的提示词收益快速衰减,业界转向把上下文组织成结构化文档。"
                "实践表明,一份写清楚约束和示例的规范文档,效果远胜反复调试的长提示词。"},
    {"id": "h12", "hours_ago": 260, "source": "雷锋网", "url": "https://www.leiphone.com/hot-12",
     "title": "AI 编程助手渗透率过半,但代码审查耗时同步上升 35%",
     "summary": "调研显示超过半数开发者日常使用 AI 编程助手,产出速度明显提升,但审查和返工的时间也在增加。"
                "受访团队普遍反馈,建立 AI 生成代码的验收标准比引入工具本身更重要。"},
    {"id": "h13", "hours_ago": 380, "source": "第一财经", "url": "https://www.yicai.com/news/hot-13",
     "title": "知识付费转向:通用 AI 课程遇冷,垂直行业方案受追捧",
     "summary": "泛 AI 入门课程的完课率和复购率同步下滑,而针对具体行业的落地方案客单价上涨了近三倍。"
                "买单方看重的不再是学会用工具,而是能不能直接搬回自己的业务里跑。"},
    {"id": "h14", "hours_ago": 520, "source": "CSDN", "url": "https://blog.csdn.net/hot-14",
     "title": "RAG 已死?长上下文与检索增强的边界之争有了新结论",
     "summary": "多组对照实验表明,长上下文在小规模知识集上完胜检索方案,但语料超过一定规模后成本和延迟迅速失控。"
                "务实做法是两者混合:高频核心知识直接进上下文,长尾知识仍走检索。"},
]


def _clean_source(val) -> str:
    """把来源字段归一化为可读名称。兼容 字符串 / {'name':...} 字典 / 其他类型。"""
    if val is None or val == "":
        return "未知来源"
    if isinstance(val, dict):
        for k in ("name", "title", "display", "site", "domain"):
            v = val.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        for v in val.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
        return "未知来源"
    return str(val).strip()


def _normalize_hotspot_item(raw: dict, idx: int) -> dict:
    """把任意接口返回的一条记录归一化成统一结构（兼容常见字段命名）。"""
    def pick(*names, default=""):
        for n in names:
            v = raw.get(n)
            if v not in (None, ""):
                return v
        return default

    hours = pick("hours_ago", "hoursAgo", default=0)
    try:
        hours = int(float(hours))
    except (TypeError, ValueError):
        hours = 0
    return {
        "id": str(pick("id", "uuid", "doc_id", default=f"api_{idx}")),
        "title": str(pick("title", "headline", "name", default="(无标题)")).strip(),
        "summary": str(pick("summary", "digest", "description", "content", default="")).strip(),
        "source": _clean_source(pick("source", "site", "platform", "media", default="未知来源")),
        "published": str(pick("published", "publish_time", "date", "time", default="")).strip(),
        "hours_ago": hours,
        "url": str(pick("url", "link", "origin_url", default="")).strip(),
    }


def _fmt_published(hours_ago: int) -> str:
    if hours_ago < 1:
        return "刚刚"
    if hours_ago < 24:
        return f"{hours_ago} 小时前"
    return f"{hours_ago // 24} 天前"


def _search_mock(keywords: list[str], max_hours: int) -> list[dict]:
    kws = [k.lower() for k in keywords if k]
    out = []
    for item in HOTSPOT_MOCK:
        if item["hours_ago"] > max_hours:
            continue
        if kws:
            blob = (item["title"] + item["summary"] + item["source"]).lower()
            if not any(k in blob for k in kws):
                continue
        row = dict(item)
        row["published"] = _fmt_published(row["hours_ago"])
        out.append(row)
    out.sort(key=lambda x: x["hours_ago"])
    return out


def _search_api(api: dict, keywords: list[str], time_label: str, max_hours: int) -> list[dict]:
    """调用自定义真实接口（仅在 api_url 非空时触发）。"""
    import requests  # 懒加载

    params = {"keywords": ",".join(keywords), "time_range": time_label, "hours": max_hours}
    headers = {"Accept": "application/json"}
    if api.get("api_key"):
        headers["Authorization"] = f"Bearer {api['api_key']}"
    if api.get("method") == "POST":
        resp = requests.post(api["api_url"], json=params, headers=headers, timeout=api["timeout"])
    else:
        resp = requests.get(api["api_url"], params=params, headers=headers, timeout=api["timeout"])
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("data") or data.get("items") or data.get("results") or []
        if isinstance(rows, dict):
            rows = rows.get("items") or rows.get("list") or []
    else:
        rows = []

    out = []
    for i, r in enumerate(rows):
        if isinstance(r, dict):
            item = _normalize_hotspot_item(r, i)
            if not item["published"]:
                item["published"] = _fmt_published(item["hours_ago"])
            out.append(item)
    return out


def _probe_serpapi(api_key: str) -> tuple[bool, str]:
    """测试 SerpAPI 连通性。返回 (是否成功, 说明)。"""
    import requests  # 懒加载
    try:
        r = requests.get("https://serpapi.com/search.json",
                          params={"engine": "google_news", "q": "AI", "api_key": api_key, "num": 1},
                          timeout=10)
    except Exception as e:
        return False, f"网络错误 {type(e).__name__}"
    if r.status_code == 200:
        return True, "返回 200,Key 有效"
    if r.status_code in (401, 403):
        return False, "401/403 鉴权失败(检查 API Key)"
    return False, f"HTTP {r.status_code}"


def _probe_deepseek(ds: dict) -> tuple[bool, str]:
    """测试 DeepSeek 连通性。返回 (是否成功, 说明)。"""
    import requests  # 懒加载
    url = (ds.get("base_url") or "https://api.deepseek.com/v1").rstrip("/") + "/chat/completions"
    try:
        r = requests.post(url,
                          headers={"Authorization": f"Bearer {ds.get('api_key', '')}",
                                   "Content-Type": "application/json"},
                          json={"model": ds.get("model", "deepseek-chat"),
                                "messages": [{"role": "user", "content": "ping"}],
                                "max_tokens": 5},
                          timeout=15)
    except Exception as e:
        return False, f"网络错误 {type(e).__name__}"
    if r.status_code == 200:
        return True, "返回 200,Key 有效"
    if r.status_code in (401, 403):
        return False, "401/403 鉴权失败(检查 API Key)"
    return False, f"HTTP {r.status_code}"


def _search_serpapi(api_key: str, keywords: list[str], max_hours: int, daily_limit: int) -> list[dict]:
    """调用 SerpAPI(google_news)返回归一化热点列表。"""
    import requests  # 懒加载
    # 默认查询词贴合账号定位（非技术小白学 AI / 搞副业），避免搜出与定位无关的泛新闻
    if keywords:
        q = " OR ".join(keywords)
    else:
        q = "AI 副业 OR AI 工具 OR AI 学习 OR 大模型 普通人"
    params = {
        "engine": "google_news",
        "q": q,
        "api_key": api_key,
        "hl": "zh-cn",
        "gl": "cn",
        "num": min(20, max(1, int(daily_limit or 20))),
    }
    r = requests.get("https://serpapi.com/search.json", params=params, timeout=15)
    r.raise_for_status()
    news = (r.json() or {}).get("news_results") or []
    out = []
    for i, n in enumerate(news):
        if not isinstance(n, dict):
            continue
        item = _normalize_hotspot_item({
            "title": n.get("title"),
            "summary": n.get("snippet"),
            "source": n.get("source") or n.get("site"),
            "url": n.get("link"),
            "published": n.get("date") or n.get("when"),
            "hours_ago": n.get("age"),
        }, i)
        if not item["published"]:
            item["published"] = _fmt_published(item["hours_ago"])
        out.append(item)
    filtered = [o for o in out if o["hours_ago"] <= max_hours]
    return filtered if filtered else out


def _deepseek_enrich(ds: dict, rows: list[dict], data_source: str = DATA_SOURCE_REAL) -> tuple[list[dict], str]:
    """用 DeepSeek 对搜索结果做智能分析。返回 (列表[含 ai_summary], 整体洞察)。

    data_source: DATA_SOURCE_REAL / DATA_SOURCE_MOCK，注入提示词模板，
    让模型区分真实热点与占位演示数据（mock 模式下只返回演示提示，不编造分析）。
    """
    if not ds.get("api_key"):
        return rows, ""
    top = rows[:15]
    titles = "\n".join(f"{i+1}. {r['title']}" for i, r in enumerate(top))
    from ..prompts import load_hotspot
    # 用 .replace 渲染：模板里 JSON 示例含字面 { }，.format 会把它误当占位符而报错。
    prompt = load_hotspot().replace("{titles}", titles).replace("{data_source}", data_source)

    try:
        r = llm_call(
            base_url=ds.get("base_url") or "https://api.deepseek.com/v1",
            api_key=ds["api_key"],
            module="hotspot",
            payload={"model": ds.get("model", "deepseek-chat"),
                     "messages": [{"role": "user", "content": prompt}],
                     "response_format": {"type": "json_object"},
                     "max_tokens": 700},
            timeout=30,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    except Exception:
        return rows, ""
    try:
        data = _json.loads(content)
    except Exception:
        return rows, content.strip() if isinstance(content, str) else ""
    insight = (data.get("insight") or "").strip()
    angles = data.get("angles") or []
    if isinstance(angles, list):
        for i, row in enumerate(top[:len(angles)]):
            row["ai_summary"] = str(angles[i]).strip()
    return rows, insight


def search(cfg: dict, keyword_text: str, time_label: str, limit: int = 15) -> dict:
    """统一搜索入口（后端版）。返回 {items, origin, insight}。

    优先级:SerpAPI 实时搜索 → 自定义接口 → 内置 mock。任何异常回退 mock。
    """
    from ..system.quota import quota_ok, quota_inc

    keywords = [ln.strip() for ln in (keyword_text or "").splitlines() if ln.strip()]
    max_hours = TIME_RANGES.get(time_label, TIME_RANGES["近7天"])
    sa = cfg.get("search_api") or {}
    ds = cfg.get("deepseek") or {}
    daily_limit = int(cfg.get("daily_limit", 50) or 50)
    limit = int(limit or 15)

    # 1) SerpAPI 真实搜索
    if sa.get("type") == "serpapi" and sa.get("api_key"):
        if quota_ok(daily_limit):
            try:
                rows = _search_serpapi(sa["api_key"], keywords, max_hours, daily_limit)
                quota_inc(1)  # 每次真实搜索计 1 次，对应 1 次 SerpAPI 调用
                rows, insight = _deepseek_enrich(ds, rows, data_source=DATA_SOURCE_REAL)
                rows = rows[:limit]
                return {"items": rows, "origin": f"SerpAPI 实时搜索 · 命中 {len(rows)} 条", "insight": insight}
            except Exception as e:
                rows = _search_mock(keywords, max_hours)[:limit]
                return {"items": rows, "origin": f"SerpAPI 调用失败已回退示例数据({type(e).__name__})", "insight": ""}
        rows = _search_mock(keywords, max_hours)[:limit]
        return {"items": rows, "origin": "已达每日搜索上限,回退示例数据(mock)", "insight": ""}

    # 2) 自定义接口（沿用 hotspot_api.api_url）
    api = cfg.get("hotspot_api") or {}
    if sa.get("type") == "custom" and api.get("api_url"):
        try:
            rows = _search_api(api, keywords, time_label, max_hours)
            rows, insight = _deepseek_enrich(ds, rows, data_source=DATA_SOURCE_REAL)
            rows = rows[:limit]
            return {"items": rows, "origin": f"真实接口 · {api['api_url']}", "insight": insight}
        except Exception as e:
            rows = _search_mock(keywords, max_hours)[:limit]
            return {"items": rows, "origin": f"接口调用失败已回退示例数据({type(e).__name__})", "insight": ""}

    # 3) 内置 mock 示例数据（演示模式：把 data_source 标为模拟，让模型只回演示提示不编造）
    rows = _search_mock(keywords, max_hours)[:limit]
    rows, insight = _deepseek_enrich(ds, rows, data_source=DATA_SOURCE_MOCK)
    rows = rows[:limit]
    return {"items": rows, "origin": "示例数据(mock)", "insight": insight}
