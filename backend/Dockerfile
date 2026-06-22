# ===========================================================================
# 后端多阶段构建 —— scanner / deps / api / worker
#   - scanner: 安全扫描二进制独立成层(极少变动,缓存稳定)
#   - deps:    uv + uv.lock 锁定依赖,与应用代码解耦
#   - api:     精简运行镜像(不带 scanner、非 root、不烤 config)
#   - worker:  在 api 基础上叠加 scanner 二进制 + semgrep
# 构建时通过 --target api / --target worker 选择目标。
# ===========================================================================

# --------------------------------------------------------------------------- #
# Stage A — scanner:仅下载 gitleaks / osv-scanner 二进制
# --------------------------------------------------------------------------- #
FROM debian:bookworm-slim AS scanner
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -sSL https://github.com/gitleaks/gitleaks/releases/download/v8.18.4/gitleaks_8.18.4_linux_x64.tar.gz \
        | tar -xz -C /usr/local/bin gitleaks \
    && curl -sSL -o /usr/local/bin/osv-scanner \
        https://github.com/google/osv-scanner/releases/download/v1.7.4/osv-scanner_linux_amd64 \
    && chmod +x /usr/local/bin/osv-scanner /usr/local/bin/gitleaks

# --------------------------------------------------------------------------- #
# Stage B — deps:用 uv 基于 pyproject.toml + uv.lock 装依赖到 /app/.venv
#   --no-install-project:仅装依赖,不装本项目自身 → 改代码不重装依赖
# --------------------------------------------------------------------------- #
FROM python:3.11-slim AS deps
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# --------------------------------------------------------------------------- #
# Stage C — api:精简运行镜像(默认目标)
# --------------------------------------------------------------------------- #
FROM python:3.11-slim AS api
# gitpython 运行时需要系统 git;ca-certificates 供 httpx/TLS
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# 拷入依赖虚拟环境
COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    CR_CONFIG=/config/config.yaml \
    PYTHONUNBUFFERED=1
# 应用代码(放在依赖之后 → 改代码不触发依赖层重建)
COPY backend/ ./
# 非 root 运行;storage 挂载点预建并授权
RUN useradd -m -u 10001 app \
    && mkdir -p /app/storage \
    && chown -R app:app /app
USER app
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

# --------------------------------------------------------------------------- #
# Stage D — worker:api + 扫描二进制 + semgrep(仅 worker 需要)
# --------------------------------------------------------------------------- #
FROM api AS worker
USER root
COPY --from=scanner /usr/local/bin/gitleaks /usr/local/bin/osv-scanner /usr/local/bin/
# semgrep 是 pip 包,单独装进 worker 的 venv(scanner.py 对缺失已做降级)
RUN pip install --no-cache-dir semgrep || true
USER app
CMD ["python", "-m", "app.queue.worker"]
