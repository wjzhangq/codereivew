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
│  部署  Docker Compose(多阶段镜像 · 数据/配置外置)→ k8s              │
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

### 2. Docker 预构建镜像(推荐)

镜像托管于 Docker Hub，版本号与 git tag 保持一致：

| 镜像 | 地址 | 说明 |
|---|---|---|
| API | [`wjzhangq/codereview-api`](https://hub.docker.com/r/wjzhangq/codereview-api) | FastAPI 服务，不含扫描器 |
| Worker | [`wjzhangq/codereview-worker`](https://hub.docker.com/r/wjzhangq/codereview-worker) | 任务工作进程，含 gitleaks / semgrep / osv-scanner |
| Web | [`wjzhangq/codereview-web`](https://hub.docker.com/r/wjzhangq/codereview-web) | nginx 静态前端 |

**一键启动（无需构建）：**

```bash
# 1. 准备配置
cp config/config.example.yaml config/config.yaml
# 按需编辑 config/config.yaml（LLM provider、admin 密码等）

# 2. 生成密钥
export JWT_SECRET="$(openssl rand -hex 32)"
export CR_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"

# 3. 拉取指定版本并启动（TAG 与 git tag 一致，如 v1.0.2）
TAG=v1.0.2 docker compose -f docker-compose.hub.yml up -d
# api(:8080) + worker(2 副本) + web(:5173)
```

`docker-compose.hub.yml` 直接引用预构建镜像，无需本地源码：

```yaml
services:
  api:
    image: wjzhangq/codereview-api:${TAG:-latest}
    ports: ["8080:8080"]
    environment:
      CR_CONFIG: /config/config.yaml
      JWT_SECRET: ${JWT_SECRET}
      CR_ENCRYPTION_KEY: ${CR_ENCRYPTION_KEY:-}
      ADMIN_PASSWORD_HASH: ${ADMIN_PASSWORD_HASH:-}
      GL_TOKEN: ${GL_TOKEN:-}
      GH_TOKEN: ${GH_TOKEN:-}
      MODELGATE_KEY: ${MODELGATE_KEY:-}
      VLLM_KEY: ${VLLM_KEY:-}
    volumes: ["storage:/app/storage", "./config:/config"]
  worker:
    image: wjzhangq/codereview-worker:${TAG:-latest}
    command: python -m app.queue.worker
    deploy: { replicas: 2 }
    environment:
      CR_CONFIG: /config/config.yaml
      JWT_SECRET: ${JWT_SECRET}
      CR_ENCRYPTION_KEY: ${CR_ENCRYPTION_KEY:-}
      GL_TOKEN: ${GL_TOKEN:-}
      GH_TOKEN: ${GH_TOKEN:-}
      MODELGATE_KEY: ${MODELGATE_KEY:-}
      VLLM_KEY: ${VLLM_KEY:-}
    volumes: ["storage:/app/storage", "./config:/config"]
  web:
    image: wjzhangq/codereview-web:${TAG:-latest}
    ports: ["5173:80"]
    depends_on: ["api"]
volumes:
  storage:
```

### 3. Docker 本地构建

```bash
# 配置外置:复制模板到 ./config,容器通过 volume 挂载读取(明文密钥不进镜像)
cp config/config.example.yaml config/config.yaml

export JWT_SECRET="$(openssl rand -hex 32)"
export CR_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
docker compose up --build
# api(:8080) + worker(2 副本) + web(:5173)
```

**镜像构建优化(多阶段)** —— 后端 `backend/Dockerfile` 拆成 4 个 stage，api/worker 各取所需:

| Stage | 作用 |
|---|---|
| `scanner` | 仅下载 gitleaks / osv-scanner 二进制,独立成层(极少变动,缓存稳定) |
| `deps` | `uv sync --frozen`(基于 `pyproject.toml` + `uv.lock`)锁定依赖到独立层 |
| `api` | 精简运行镜像:依赖 + 应用代码,非 root(uid 10001),**不带 scanner、不烤 config** |
| `worker` | 在 `api` 基础上 `COPY --from=scanner` 叠加扫描二进制 + semgrep |

**数据与配置全部映射到外部**(`docker-compose.yml` volumes):

| 宿主 / 卷 | 容器路径 | 用途 |
|---|---|---|
| `storage`(named volume) | `/app/storage` | 运行时数据:仓库镜像 / 图谱 / 向量 / 报告 / OLAP |
| `./config`(bind mount) | `/config` | 外部配置目录,`CR_CONFIG=/config/config.yaml` |

> 优化要点:`.dockerignore` 排除 `storage/`、`node_modules/`、`config.yaml` 等(密钥不进构建上下文);改应用代码只重跑代码层、不重装依赖;前端用 `npm ci` 锁定 `package-lock.json` 可复现构建。

构建/校验:

```bash
docker compose build                                       # 首次全量
docker compose run --rm worker which gitleaks osv-scanner  # worker 内应都有
docker compose run --rm api which gitleaks || echo "api 无扫描器(预期)"
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

## 运维 CLI(`cr`)

后端内置一个命令行工具,用于**验证环境**、**查看项目状态**、**强制重建索引**。安装后即可用 `cr <命令>`(或不安装直接 `python -m app.cli <命令>`)。

```bash
cd backend
uv pip install -e .          # 注册 `cr` 入口(或 pip install -e .)
# 未安装也可:python -m app.cli <命令>
```

| 命令 | 作用 |
|---|---|
| `cr doctor` | 综合体检:配置加载 · 存储目录可写 · meta.sqlite 读写 · 图谱引擎 · LLM Chat · Embedding(逐项 ✓/✗) |
| `cr check-llm` | **真实**发一次 chat + embedding 请求,验证 provider 连通(非占位 stub / hash 伪向量回落),并校验向量维度 |
| `cr check-graph` | 在临时 git 仓库上**真实**跑 code-review-graph 构建一次,验证引擎可产出图谱 |
| `cr projects` | 列出所有项目(id / name / status / files / loc / 最后索引时间) |
| `cr status <project_id>` | 单个项目详情 + 分支白名单/索引状态 + 最近 10 条 job(含失败原因) |
| `cr reindex <project_id>` | **前台同步**强制全量重建索引(clone→worktree→图谱→向量),进度实时打印到终端 |

```bash
cr doctor                          # 部署后第一件事:确认环境就绪
cr check-llm                       # 单独排查 LLM / embedding 是否连通
cr status memory-lancedb-pro-skill # 查看某项目分支与任务状态
cr reindex memory-lancedb-pro-skill# 图谱/向量异常时强制重建
```

> `doctor` 仅当**配置 / 存储 / 数据库**任一失败才返回非零退出码;图谱引擎或 LLM 处于降级回落时只告警(`!`),便于在无外部依赖的开发环境照常使用。

---

## 目录结构

```
code-review/
├── config/config.example.yaml        # 统一配置示例
├── backend/
│   ├── pyproject.toml
│   └── app/
│       ├── main.py                   # FastAPI 入口
│       ├── cli.py                    # 运维 CLI(doctor/check-llm/check-graph/projects/status/reindex)
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
├── docker-compose.yml                # api + worker + web(本地构建,按 target 分配镜像)
├── docker-compose.hub.yml            # 使用 Docker Hub 预构建镜像(无需构建,TAG=版本号)
├── .dockerignore                     # 排除 storage/node_modules/config.yaml/缓存
├── backend/Dockerfile                # 多阶段:scanner / deps / api / worker
├── frontend/Dockerfile               # node 构建(npm ci)→ nginx 静态服务
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
