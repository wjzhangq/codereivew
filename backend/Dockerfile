FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# 安全扫描 CLI(失败不阻断构建)
RUN curl -sSL https://github.com/gitleaks/gitleaks/releases/download/v8.18.4/gitleaks_8.18.4_linux_x64.tar.gz \
        | tar -xz -C /usr/local/bin gitleaks || true
RUN pip install --no-cache-dir semgrep || true
RUN curl -sSL -o /usr/local/bin/osv-scanner \
        https://github.com/google/osv-scanner/releases/download/v1.7.4/osv-scanner_linux_amd64 \
    && chmod +x /usr/local/bin/osv-scanner || true
WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic pydantic-settings pyyaml \
        sqlite-vec duckdb gitpython httpx argon2-cffi pyjwt cryptography python-multipart
COPY backend/ ./
COPY config/ /config/
ENV CR_CONFIG=/config/config.yaml
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
