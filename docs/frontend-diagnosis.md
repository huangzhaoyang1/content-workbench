# 前端 + 后端 + 链路 全面诊断报告

> 诊断时间：2026-08-12 12:19（GMT+8）
> 诊断方式：**只读**——未修改任何文件、未改动代码。仅读取配置/日志/源码，并对当前正在运行的服务做只读探测（HTTP 探针、端口探测、静态 chunk 探测）。
> 项目根：`C:\Users\黄朝扬\WorkBuddy\content-workbench`

## 一句话结论（先看这个）

**当前两端都在正常运行**：后端 54321、前端 3000 均返回 200，所有核心接口冒烟测试全绿，前端静态资源当前可加载。
用户之前看到的「报错 / 流程跑不通」对应的是 **`frontend.log` 里记录的 2026-08-04 那次损坏的构建缓存（stale `.next`）**——当时浏览器拿到 HTML 后，JS 静态块全部 404、整页白屏崩溃。该 `.next` 目录已在 **今天 12:17 被重建**，现在已恢复健康。

---

## 1. 后端启动

| 检查项 | 结论 | 证据 / 报错原文 |
|---|---|---|
| 启动器启动什么 | 后端：`uvicorn backend.main:app --reload --port 54321`；前端：`npm run dev`（默认 3000）；两个服务各自开一个 `cmd /k` 窗口 | `启动AI内容工作台.bat` 第 25、31 行 |
| 后端端口 | **54321**（bat 显式指定，非默认 8000） | bat 第 25 行 `--port 54321` |
| 端口当前是否在听 | **在听（LISTENING）** | `socket.connect(127.0.0.1:54321)` → LISTENING |
| 后端当前是否健康 | **健康**，所有探针接口 200 | 见第 4 节链路自测 |
| 后端日志有无崩溃 | 无崩溃。`backend.log`（mtime 2026-08-05 20:29）仅有正常 `200 OK`、少量预期的 `422`（参数校验）、`404`（查不存在的资源） | 见下方日志片段 |

`backend.log` 关键片段（全部正常，无 traceback / 无红色异常）：
```
INFO: ... "GET /api/health HTTP/1.1" 200 OK
INFO: ... "POST /api/pipeline/start HTTP/1.1" 200 OK
INFO: ... "GET /api/tasks/13 HTTP/1.1" 200 OK
INFO: ... "POST /api/pipeline/start HTTP/1.1" 422 Unprocessable Entity   # 缺必填参数，属正常校验
INFO: ... "GET /api/tasks/99999 HTTP/1.1" 404 Not Found                   # 查不存在，属正常
```

**结论：后端启动正常，不是故障点。** 注意 bat 用裸 `uvicorn` 命令，依赖该 `cmd` 窗口的 PATH 上有 `uvicorn`（当前环境解析到 managed venv 的 `uvicorn.EXE`）。若未来在干净环境双击 bat 而 PATH 无 `uvicorn`，后端会起不来——这是潜在风险，但**不是本次故障原因**（当前进程健在）。

---

## 2. 前端启动

| 检查项 | 结论 | 证据 / 报错原文 |
|---|---|---|
| dev/build 命令 | `dev`: `next dev`；`build`: `next build`；`start`: `next start` | `frontend/package.json` scripts |
| node_modules 是否装齐 | **装齐**。next / react / @base-ui/react / class-variance-authority / clsx / lucide-react / tailwind-merge 均存在 | `ls frontend/node_modules/<pkg>` 全部 OK |
| `.next` 是否存在 | **存在**，且 mtime = **2026-08-12 12:17**（今天刚重建） | `stat frontend/.next` |
| 前端端口 | 当前在 **3000** 监听；3001 未占用（无端口冲突） | `socket.connect(127.0.0.1:3000)` → LISTENING；3001 → 未监听 |
| 当前页面/资源是否可加载 | **可加载**。所有页面 HTML 200，静态 chunk 全部 200 | 见下方探测片段 |

当前运行态探测（2026-08-12 12:19）：
```
GET /topic            -> 200 (HTML, len 7005)
GET /tasks            -> 200
GET /analytics        -> 200
GET /dissect          -> 200
GET /hotspot          -> 200
静态块:
  /_next/static/chunks/main-app.js               -> 200
  /_next/static/chunks/app/topic/page.js         -> 200
  /_next/static/chunks/app/layout.js             -> 200
  /_next/static/chunks/webpack.js                 -> 200
```

**结论：前端当前启动正常、资源可加载，不是当前故障点。** 但本次故障的「真凶」记录在 `frontend.log` 里（见第 3 节）。

---

## 3. 真实报错（重点）

`frontend.log` 最后 100 行暴露了**最初那次跑不通**的真实原因（mtime 2026-08-04 19:27，对应损坏的 `.next` 构建缓存）。原样关键报错如下：

**(a) 模块找不到（MODULE_NOT_FOUND）—— 整页 JS 加载失败的根因**
```
Error: Cannot find module './vendor-chunks/class-variance-authority'
  code: 'MODULE_NOT_FOUND',
  requireStack: [
    '...frontend/.next/server/webpack-runtime.js',
    '...frontend/.next/server/app/topic/page.js',
    ...
  ],
  page: '/analytics'
```
webpack 缓存策略同样报错：
```
[webpack.cache.PackFileCacheStrategy] Caching failed for pack: Error: ENOENT: no such file or
directory, lstat '...frontend/.next/server/vendor-chunks/class-variance-authority.js'
Resolving './vendor-chunks/class-variance-authority' ... doesn't lead to expected result
'...vendor-chunks/class-variance-authority.js', but to 'Error: Can't resolve ...' instead.
（同款错误还出现在 @floating-ui / @base-ui / clsx 等 vendor-chunks）
```

**(b) 静态资源 404 —— 浏览器拿到 HTML 后白屏**
```
GET /_next/static/css/app/layout.css?v=...          404
GET /_next/static/chunks/main-app.js?v=...          404
GET /_next/static/chunks/app/hotspot/page.js        404
GET /_next/static/chunks/app/page.js                404
```

**这串报错说明什么**：浏览器成功拿到 HTML 外壳（所以「页面打开」了），但后续加载的 JS 静态块（main-app.js、各路由 page.js、layout.css）全部 404，且 webpack-runtime 在 `.next/server` 里找不到 `vendor-chunks/*`。结果是**整页 JavaScript 没加载 → 页面白屏或点击任何按钮/流程都无反应**，正是用户描述的「报错、流程跑不通」。

**为什么会出现这种损坏**：`.next` 是 Next.js 的构建缓存目录。当 `node_modules` 依赖发生过变化（安装/升级/换分支/从别处拷贝），而 `.next` 还是旧依赖时期生成的，**dev 模式会复用这个过期缓存**，于是在 `webpack-runtime.js` 里硬编码引用的 `vendor-chunks` 已不存在 → MODULE_NOT_FOUND + 静态块 404。这是 Next.js 的经典「缓存与依赖不一致」问题。

**源码层面扫描（dissect / topic / tasks / analytics 主流程）**
- 4 个主流程页面均使用统一的 `api` 客户端（`frontend/src/lib/api.ts`），**未发现**硬编码错误地址（`localhost:8000`、`/api/v1`、裸 `fetch(` 直连等均为 0 命中）。
- `api.ts` 的 `API_BASE` 来自 `.env.local` 的 `NEXT_PUBLIC_API_URL`，与后端端口一致（见第 4 节）。
- 当前构建产物可正常编译并服务（chunk 200），说明这 4 个页面**没有导致编译失败的 TS 错误**；运行时崩溃类 bug 不在本次故障证据中。

---

## 4. 链路自测

后端当前健在，逐个调用页面依赖的核心接口（只读 GET/POST，不改动数据）：

| 接口 | 方法 | 结果 |
|---|---|---|
| `/api/health` | GET | **200** `{"status":"ok","version":"0.3.0",...}` |
| `/api/auth/status` | GET | **200** `{"enabled":false,...}` |
| `/api/config` | GET | **200** |
| `/api/tasks?page=1&page_size=3` | GET | **200** 返回真实任务列表 |
| `/api/tasks/99002` | GET | **200** 返回任务详情（status=error，属该任务自身执行失败，非平台故障） |
| `/api/hotspot/quota` | GET | **200** |
| `/api/queue` | GET | **200** |
| `/api/queue/start` | POST | **200** `{"started":false,"reason":"队列中没有等待执行的任务"}` |
| `/api/topic/data-insight` | GET | **200** |
| `/api/analytics/sample` | POST | **200** |
| `/api/analytics/analyze` | POST | **200** |
| `/api/douyin-dissect/topics?limit=3` | GET | **200** |
| `/api/douyin-sync/state` | GET | **200** |
| `/api/config/test` | POST | **200** `{"serpapi":{"ok":false,"message":"未填写 API Key"},"deepseek":{...}}`（未配 Key，属正常） |
| `/api/pipeline/start`（空 body） | POST | **422** `参数校验失败：topic Field required`（缺参校验，属正常） |

**API 地址一致性核对**
- 前端 `.env.local`：`NEXT_PUBLIC_API_URL=http://localhost:54321`
- `api.ts`：`API_BASE = process.env.NEXT_PUBLIC_API_URL || ... || "http://localhost:8000"` → 实际取 **54321**
- 后端实际监听：**54321**
- ✅ 前后端地址**完全一致**，无错位。
- CORS：后端 `allow_origin_regex = ^(http://(localhost|127\.0\.0\.1)(:\d+)?|https://...\.vercel\.app)$`，**放行 localhost 任意端口**，前端在 3000/3001 都不会被浏览器拦截。

**结论：链路（前端 → 后端 → 接口）当前完全通畅，不是故障点。**

---

## 5. 总结（3 句话）

1. **哪一步跑不通**：最初是「前端页面加载」这一步跑不通——浏览器拿到 HTML 外壳后，JS 静态块（`/_next/static/chunks/...`）全部 404、webpack-runtime 找不到 `vendor-chunks`，整页 JS 没加载，于是任何「流程」点不动、页面白屏。
2. **根因是什么**：`frontend/.next` 是一份**过时/损坏的 Next.js 构建缓存**（依赖已变但缓存未重建），Next 启动时在 `webpack-runtime.js` 里引用了已不存在的 `vendor-chunks`（class-variance-authority / @base-ui / clsx 等），导致静态资源 404 与 MODULE_NOT_FOUND——这是 `frontend.log`（2026-08-04）记录的全部报错来源。
3. **最可能的一处修复**：**删除 `frontend/.next` 并重新 `npm run dev`**（依赖有变动时先 `npm install`）即可；本次诊断时该目录已在今天 12:17 被重建，当前后端（54321）与前端（3000）均已恢复健康、所有接口 200。若你重启后**仍**报错，那会是另一类问题（如浏览器控制台运行时异常），可再把实时控制台报错贴给我做二次定位。

---

### 附：潜在风险（非本次故障，但建议留意）
- **bat 依赖 PATH 上的 `uvicorn`/`npm`**：若未来在干净环境双击 `启动AI内容工作台.bat` 而 PATH 无 `uvicorn`，后端会起不来（前端会报「网络连接失败」）。当前环境解析正常，非本次原因。
- **端口错位**：`next dev` 默认 3000，若被占会自动顺延到 3001，但 bat 提示用户固定开 `http://localhost:3000`。若你曾有多份前端实例，可能开错端口看到旧/空页面。当前 3000 为唯一健康实例，无冲突。
