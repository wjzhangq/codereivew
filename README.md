# CodeReview 平台

> 接入代码仓库后,自动持续做:**结构图谱解析 · 逐 commit 理解(忽略 message,LLM 读真实 diff)· 安全扫描 · 贡献/周期汇总 · 代码问答 · 项目 Wiki**

```
┌─────────────── 技术栈 ───────────────────────────────────────────────────┐
│  后端  FastAPI · Python 3.11+                                            │
│  存储  SQLite(WAL)+ sqlite-vec(向量)+ DuckDB(OLAP)                    │
│  队列  SQLite 自建 claim 队列(无 Redis!)                                │
│  图谱  code-review-graph 引擎(Tree-sitter 24 语言)                      │
│  安全  gitleaks + Semgrep + osv-scanner + LLM 复审                       │
│  LLM   多 provider(OpenAI 兼容)+ 分级路由(cheap / default)             │
│  前端  React + Vite + Ant Design v5 + React Query + Zustand             │
│  部署  Docker Compose → k8s                                              │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 系统架构

```
 API (FastAPI)  ──入队──▶  SQLite 队列  ──claim──▶  Worker 池 (4 线程)
   │ JWT / APIKey 鉴权                  原子领取      │ LLM 信号量限流
   │                                    写类串行      │
   ▼                                                  ▼
 Web 管理台 (React)              ┌─────────────────────────────────┐
 10 页面 + 登录                  │ ① Git 包装(deploy key+worktree) │
 AntD v5 高保真复刻              │ ② 图谱解析(社区检测+blast-radius)│
                                 │ ③ commit 理解(忽略 msg,LLM 产出) │
                                 │ ④ 安全扫描(4 引擎 + LLM 复审)    │
                                 │ ⑤ 模型管理(多 provider 分级路由)  │
                                 │ ⑥ 问答 / Wiki / 用户汇总          │
                                 └─────────────────────────────────┘
存储布局:
  storage/meta.sqlite          — OLTP 主库(项目/分支/队列/Key/findings/…)
  storage/vectors/<pid>.sqlite — sqlite-vec 向量(代码块 + commit 摘要)
  storage/graphs/<pid>/<br>.sqlite — 图谱(节点/边/社区/blast-radius)
  storage/analytics/           — DuckDB + Parquet(贡献 OLAP)
```

---

## 功能页面(11 个)

| 页面 | 说明 |
|---|---|
| 登录 | 本地账号体系,admin 来自 config,管理员添加用户 |
| 工作台 | 项目卡片总览 + 快速接入仓库 |
| 概览 · 图谱 ⭐ | 分支白名单 + **模块依赖图谱**(SVG 边 + HTML 节点,悬停爆炸半径) |
| 安全面板 | 4 等级筛选 + findings 表 + 抽屉(证据/建议/标记处理) |
| 周期/贡献报告 | commit 卡(问题红/思路绿) + 贡献 by_log/by_blame + MiniBars |
| 代码问答 | 图谱+向量+演进史融合检索 → LLM 回答 + 证据 chips |
| 项目 Wiki | 社区结构+commit 理解 → LLM 增量刷新模块文档 |
| 任务中心 | SQLite 队列监控,原子领取 SQL 展示 |
| 用户管理 | 账号 CRUD + 平台身份解析映射(admin only) |
| 项目设置 | 仓库/Webhook/API Key/平台 Token/分析参数 |

---

## 快速开始

### 1. 本地开发(推荐)

```bash
# 后端
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings pyyaml \
    sqlite-vec duckdb gitpython httpx argon2-cffi pyjwt cryptography python-multipart

cp ../config/config.example.yaml ../config/config.yaml
export JWT_SECRET="$(openssl rand -hex 32)"

uvicorn app.main:app --reload --port 8080   # 自动建表 + 引导 admin
uv run uvicorn app.main:app --reload --port 8080
# 另开终端:
python -m app.queue.worker                   # 启动 worker 池
uv run -m app.queue.worker

# 前端
cd ../frontend
npm install && npm run dev                   # http://localhost:5173
```

**默认登录**:`admin` / `admin12345`(见 config.example.yaml)

**API 文档**:http://localhost:8080/docs (FastAPI 自动生成 OpenAPI)

### 2. Docker 一键部署

```bash
export JWT_SECRET="$(openssl rand -hex 32)"
export CR_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
docker compose up --build
# api(:8080) + worker(2 副本) + web(:5173),storage/ 持久卷
```

### 3. Kubernetes

```bash
kubectl apply -f deploy/k8s/codereview.yaml
# 提前替换 Secret 中的占位值
```

---

## 接入第一个仓库

1. 登录 admin → 工作台 → **接入仓库**(git URL + deploy key)
2. 系统自动入队 `index_build`:clone → worktree → 图谱 → 向量
3. 默认分支**强制纳入**白名单;在概览页勾选其余分支
4. 触发 commit 分析 / 安全扫描 / Wiki 生成
5. 配 webhook 后 push 到白名单分支自动增量分析

---

## 目录结构

```
code-review/
├── config/config.example.yaml        # 统一配置示例
├── backend/
│   ├── pyproject.toml
│   └── app/
│       ├── main.py                   # FastAPI 入口
│       ├── api/                      # 10 routers (auth/projects/analysis/security/qa/wiki/jobs/users/webhook/settings)
│       ├── core/                     # config(pydantic-settings) / security(JWT/argon2/加密) / logging(审计)
│       ├── auth/                     # users(账号) / keys(API Key) / identity(平台身份解析)
│       ├── git/                      # repo(clone/fetch) / worktree / history(log/blame/diff)
│       ├── parsing/                  # engine(引擎适配) / graph_store(只读图谱) / chunker / vectors(sqlite-vec)
│       ├── analysis/                 # commit_analyzer(忽略 msg,LLM 理解,drift 检测)
│       ├── security/                 # scanner(gitleaks+semgrep+osv+LLM 复审,基线对比)
│       ├── llm/                      # registry(多 provider) / client(chat) / embedder
│       ├── analytics/                # duck(DuckDB) / period_report / contributor(by_log+by_blame)
│       ├── qa/                       # retriever(图谱+向量+演进史→LLM)
│       ├── wiki/                     # generator(社区结构+commit 理解→增量 LLM)
│       ├── queue/                    # queue(原子 claim+写类串行+退避) / worker / handlers(8 类任务)
│       ├── db/                       # schema.sql + session(WAL)
│       └── tests/                    # 8 tests: 队列/流水线/API
├── frontend/
│   └── src/
│       ├── App.tsx + main.tsx        # 路由 + 入口
│       ├── theme.ts                  # AntD v5 token 映射
│       ├── layout/AppLayout.tsx      # Sidebar + Header + 外壳
│       ├── pages/ (10 个)            # Login/Dashboard/ProjectOverview/Security/Reports/QA/Wiki/Jobs/Users/Settings
│       ├── hooks/api.ts              # React Query hooks(全量 API 对接)
│       ├── components/widgets.tsx    # Health 环 / Sev / MiniBars / CatTag / Avatar
│       ├── store/auth.ts            # zustand(登录态/侧栏)
│       └── api/client.ts            # axios 统一拆包
├── docker-compose.yml                # api + worker + web
├── deploy/k8s/codereview.yaml        # Namespace + PVC + Secret + Deployments + Service
└── storage/                          # 运行时(.gitignore)
```

---

## 测试

```bash
cd backend
CR_CONFIG=../config/config.example.yaml python -m pytest app/tests/ -o testpaths= -o addopts= -q
```

| 测试 | 覆盖 |
|---|---|
| `test_queue.py` | 去抖合并、写类按 project 串行、退避重试 |
| `test_pipeline.py` | clone→图谱→向量 E2E;commit 分析 + drift 检测 |
| `test_api.py` | JWT 鉴权、RBAC、项目 CRUD |

---

## 关键设计决策

| 决策 | 理由 |
|---|---|
| **SQLite 队列(无 Redis)** | 单写场景足够;同一二进制;原子 claim SQL 保证写类串行 |
| **忽略 commit message** | 作者可伪造;LLM 读真实 diff 更准;detect_message_drift 抓"文不对题" |
| **sqlite-vec 暴力 KNN** | 免独立向量服务;按 (project,branch) 分区 + blast-radius 预过滤控扫描量 |
| **DuckDB 非持久库** | 是同一份 SQLite/Parquet 数据上的查询引擎,不另存数据 |
| **引擎适配器模式** | 未安装时回落内置最小解析,流水线照跑;就位后只换一行 import |
| **LLM 分级路由** | 逐 commit 走 cheap(省成本);Wiki/QA 走 default(要质量) |
| **默认分支强制纳入** | API 级拒绝取消(409),前端 disabled checkbox;webhook push 即触发 |

---

## ⚠️ 优雅降级(开发 / 演示 友好)

| 组件缺失 | 行为 |
|---|---|
| code-review-graph 未安装 | 回落内置解析(目录即模块,圆周布局) |
| LLM provider 未配 | 返回占位 stub 文本,流水线照跑 |
| embedding provider 未配 | 用 SHA-256 hash 伪向量(确定性) |
| gitleaks/semgrep/osv 未装 | 该扫描器静默跳过,其余正常 |
| 平台 token 未配 | 身份解析跳过,回落 git email + 标 unverified |

---

## 配置参考

见 `config/config.example.yaml`,对应 plan.md §9。关键环境变量:

| 变量 | 用途 |
|---|---|
| `JWT_SECRET` | JWT 签名密钥(≥32字节) |
| `ADMIN_PASSWORD_HASH` | argon2 哈希(生产);不填则用 config 明文(仅测试) |
| `CR_ENCRYPTION_KEY` | Fernet key,加密 deploy key/token 落库 |
| `GL_TOKEN` / `GH_TOKEN` | 平台 token(身份解析 + 可选仓库发现) |
| `MODELGATE_KEY` / `VLLM_KEY` | LLM provider API key |

---

## License

内部工具,按需授权。依赖的 `code-review-graph` 为 MIT;`gitleaks` MIT;`Semgrep` LGPL-2.1。
