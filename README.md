# AI 内容运营工作台（全栈）

一个面向「AI 内容运营」场景的全栈工作台。**前端**用 Next.js 14 + TypeScript + Tailwind CSS + shadcn/ui（暗黑主题），**后端**用 Python FastAPI，并**复用**现有 Streamlit 项目里的 Python 流水线脚本（`scripts/run_pipeline.py` 等）。

> 本仓库是「全栈重构」的第一阶段：先把工程骨架、页面框架、后端基础架子与前后端联调跑通；后续逐步把现有 Streamlit 各模块（热点素材 / 数据分析 / 历史任务 / 任务队列）的能力迁移到 API + 页面。

## 目录结构

```
content-workbench/
├─ frontend/                 # Next.js 14 前端（App Router + TypeScript + Tailwind + shadcn/ui）
│  ├─ src/
│  │  ├─ app/                # 路由与页面（6 个一级页面）
│  │  ├─ components/         # 通用组件（ui = shadcn 组件，layout = 布局组件）
│  │  ├─ lib/                # 工具函数（cn 等）
│  │  └─ ...
│  ├─ tailwind.config.ts
│  ├─ components.json        # shadcn/ui 配置
│  └─ package.json
├─ backend/                  # FastAPI 后端
│  ├─ main.py                # 应用入口（CORS、路由挂载）
│  ├─ config.py              # 配置管理（读取现有 Streamlit 项目配置、脚本目录）
│  ├─ routers/               # 路由（health 等）
│  ├─ services/              # 业务逻辑（pipeline 调用脚本）
│  └─ requirements.txt
├─ .gitignore
└─ README.md
```

## 快速开始

### 1. 后端（FastAPI）

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

- 健康检查：`GET http://localhost:8000/api/health`
- 联调测试：`POST http://localhost:8000/api/test/echo` `{"message":"hi"}`
- 接口文档：http://localhost:8000/docs

> 后端默认读取现有 Streamlit 项目的 `workbench_config.json` 与 `scripts/` 目录（默认路径 `C:\Users\黄朝扬\WorkBuddy\简约风格`）。可用环境变量 `STREAMLIT_PROJECT_ROOT` 覆盖。

### 2. 前端（Next.js 14）

```bash
cd frontend
npm install
npm run dev
```

- 访问：http://localhost:3000
- 前端通过 `next.config.mjs` 的 rewrite 把 `/api/*` 代理到后端 `http://localhost:8000/api/*`，开发时无需额外处理跨域。

### 3. 前后端联调

先启动后端（8000），再启动前端（3000）。前端默认首页会调用 `/api/health` 验证后端连通性，并在页面上显示结果。

## 技术约定

- 前端组件优先使用 **shadcn/ui**，不重复造轮子。
- 暗黑主题为默认主题（与现有 Streamlit 版本风格一致）。
- 所有 API 响应使用 `application/json`，路径统一以 `/api` 为前缀。
- 类型安全：前端全面 TypeScript；后端用 Pydantic 做请求/响应校验。

## 现有流水线脚本（被后端复用）

位于 `C:\Users\黄朝扬\WorkBuddy\简约风格\scripts\`（可通过 `STREAMLIT_PROJECT_ROOT` 配置）：

- `run_pipeline.py` —— 选题生产主流水线（后端 `/api/pipeline/run` 调用）。
- 其他脚本（热点搜索、数据分析、历史任务归档等）将在后续阶段接入。

## 部署说明

- 出稿（流水线）功能依赖本机 side-hustle 脚本（`run_pipeline.py`），云端部署仅支持热点搜索与选题生成，不支持出稿。完整功能请在本机使用启动器运行。
- 前端核心链路（发布三步弹窗、队列轮询）已覆盖 Vitest 冒烟测试，本地回归执行 `npm run test` 即可。
