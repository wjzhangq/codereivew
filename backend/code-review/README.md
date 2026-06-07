# 代码 Review 平台

自动化代码 Review 平台:接入仓库后持续做**结构图谱解析、逐 commit 理解、安全扫描、贡献/周期汇总、代码问答、项目 Wiki**。

> 后端 FastAPI + SQLite(WAL)+ sqlite-vec + DuckDB + SQLite 自建队列(无 Redis);前端 React + Vite + Ant Design v5。按 `dev.md` 的 M0–M5 里程碑实现。

---

## 架构一览

```
API (FastAPI) ──入队──▶ SQLite 队列 ──claim──▶ Worker 池
  │ JWT/APIKey 鉴权                              │
  ▼                                              ▼
Web (React+AntD)              ① Git 包装  ② 解析(图谱+向量)
                              ③ commit 理解  ④ 安全扫描  ⑤ 模型管理
                              ⑥ 用户汇总 / 问答 / Wiki
存储:meta.sqlite(OLTP) · vectors/<pid>.sqlite(sqlite-vec)
      graphs/<pid>/<branch>.sqlite(图谱) · analytics/(DuckDB+Parquet)
```

各模块与 `dev.md` 章节对应:`app/git`(M0.1)、`app/parsing`(M0.2-3)、`app/queue`(M1.2)、
`app/api`(M1.3)、`app/llm`+`app/analysis`(M2)、`app/security`(M3)、
`app/auth`+`app/analytics`+`app/qa`+`app/wiki`(M4)。

---

## 本地开发

### 后端

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .                       # 或 pip install -e ".[dev]"

# 配置
cp ../config/config.example.yaml ../config/config.yaml
export JWT_SECRET="$(openssl rand -hex 32)"
# 管理员密码:示例 config 内置 password: admin12345(仅本地);生产用 ADMIN_PASSWORD_HASH

# 起 API(自动 init schema + 引导 admin)
uvicorn app.main:app --reload --port 8080

# 另开终端起 worker 池
python -m app.queue.worker
```

API 文档:http://localhost:8080/docs

### 前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173,/api 代理到 :8080
```

默认登录:`admin` / `admin12345`(见 config.example.yaml)。

### 测试

```bash
cd backend
CR_CONFIG=../config/config.example.yaml python -m pytest app/tests/ -o testpaths= -o addopts= -q
```

覆盖:队列原子领取/写类串行/退避重试、解析流水线(clone→图谱→向量)、
commit 理解 + drift 检测、API 鉴权。

---

## Docker 部署

```bash
export JWT_SECRET="$(openssl rand -hex 32)"
export CR_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
docker compose up --build
```

- `api`(:8080)+ `worker`(2 副本)+ `web`(:5173)
- `storage/` 持久卷;无 Redis、无独立 DB 服务

---

## 接入第一个仓库

1. 登录(admin)→ 工作台 →「接入仓库」,填 git URL + deploy key。
2. 平台自动入队 `index_build`:clone → 建 worktree → 跑图谱 → 切块嵌入。
3. 默认分支强制纳入白名单;在项目详情勾选其余分支。
4. 触发逐 commit 分析 / 安全扫描 / Wiki 生成(或配 webhook 自动触发)。

---

## ⚠️ 集成注意(见 dev.md 附录 C)

- **图谱引擎 `code-review-graph`**:`app/parsing/engine.py` 用适配器模式 —— 引擎安装后调其 API,
  未安装时回落内置最小解析(目录即模块),保证流水线可端到端跑通。
  引擎就位后按 spike 笔记更新 `engine.py` 与 `graph_store.py` 的 schema。
- **LLM / embedding provider 未配置**时:`llm/client.py` 与 `llm/embedder.py` 自动回落到
  离线 stub / hash 伪向量,流水线不报错(但内容为占位)。配 `config.models` 后生效。
- **安全扫描 CLI**(gitleaks/semgrep/osv-scanner)未安装时该项静默跳过;Docker 镜像已预装。
