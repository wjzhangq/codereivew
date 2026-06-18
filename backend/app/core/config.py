"""core/config.py — 配置加载

用 pydantic 把 config/config.yaml(plan §9)解析为强类型 settings。
凭据走 *_env 间接引用环境变量,密钥永不落配置文件明文。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 子配置模型
# --------------------------------------------------------------------------- #
class ServerCfg(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class StorageCfg(BaseModel):
    root: str = "./storage"
    meta_db: str = "./storage/meta.sqlite"
    vectors_dir: str = "./storage/vectors"
    graphs_dir: str = "./storage/graphs"
    analytics_dir: str = "./storage/analytics"
    repos_dir: str = "./storage/repos"
    reports_dir: str = "./storage/reports"


class SessionCfg(BaseModel):
    jwt_secret_env: str = "JWT_SECRET"
    ttl_hours: int = 12

    @property
    def jwt_secret(self) -> str:
        return os.getenv(self.jwt_secret_env, "dev-insecure-secret-change-me")


class AdminCfg(BaseModel):
    username: str = "admin"
    password_hash_env: str = "ADMIN_PASSWORD_HASH"
    password: str | None = None  # 仅本地测试

    @property
    def password_hash(self) -> str | None:
        return os.getenv(self.password_hash_env)


class ApiKeyCfg(BaseModel):
    enabled: bool = True


class AuthCfg(BaseModel):
    api_key: ApiKeyCfg = Field(default_factory=ApiKeyCfg)
    session: SessionCfg = Field(default_factory=SessionCfg)
    admin: AdminCfg = Field(default_factory=AdminCfg)
    password_hashing: str = "argon2"


class PlatformEntry(BaseModel):
    enabled: bool = False
    base_url: str | None = None
    token_env: str | None = None

    @property
    def token(self) -> str | None:
        return os.getenv(self.token_env) if self.token_env else None


class PlatformCfg(BaseModel):
    gitlab: PlatformEntry = Field(default_factory=PlatformEntry)
    github: PlatformEntry = Field(default_factory=PlatformEntry)


class BranchesCfg(BaseModel):
    mode: str = "whitelist"
    include_default: str = "forced"


class GitCfg(BaseModel):
    worktree_per_branch: bool = True
    branches: BranchesCfg = Field(default_factory=BranchesCfg)
    exclude_globs: list[str] = Field(default_factory=list)


class QueueCfg(BaseModel):
    workers: int = 4
    llm_workers: int = 1
    poll_interval_s: float = 1.5
    max_attempts: int = 3
    backoff_base_s: int = 5


class SecurityCfg(BaseModel):
    gitleaks: bool = True
    semgrep: bool = True
    sca: bool = True
    llm_review: bool = True


class BackfillCfg(BaseModel):
    mode: str = "max_of"
    last_days: int = 30
    last_count: int = 100


class AnalysisCfg(BaseModel):
    commit_granularity: str = "commit"
    backfill: BackfillCfg = Field(default_factory=BackfillCfg)
    use_commit_message: bool = False
    detect_message_drift: bool = True


class EmbeddingsCfg(BaseModel):
    granularity: str = "signature_plus_body"
    index_commit_summaries: bool = True


class ProviderCfg(BaseModel):
    type: str = "openai_compatible"
    base_url: str
    api_key_env: str | None = None
    api_key_value: str | None = None  # 明文密钥(可选);优先级高于 api_key_env

    @property
    def api_key(self) -> str | None:
        # 1) 明文优先:config 直接写 api_key_value
        if self.api_key_value:
            return self.api_key_value
        # 2) 间接引用:api_key_env 是环境变量名
        if self.api_key_env:
            return os.getenv(self.api_key_env)
        return None


class ModelRef(BaseModel):
    provider: str
    model: str
    dim: int | None = None


class ModelsCfg(BaseModel):
    providers: dict[str, ProviderCfg] = Field(default_factory=dict)
    llm: dict[str, ModelRef] = Field(default_factory=dict)
    embedding: dict[str, ModelRef] = Field(default_factory=dict)
    routing: dict[str, str] = Field(default_factory=dict)


class Settings(BaseModel):
    server: ServerCfg = Field(default_factory=ServerCfg)
    storage: StorageCfg = Field(default_factory=StorageCfg)
    auth: AuthCfg = Field(default_factory=AuthCfg)
    platform: PlatformCfg = Field(default_factory=PlatformCfg)
    git: GitCfg = Field(default_factory=GitCfg)
    queue: QueueCfg = Field(default_factory=QueueCfg)
    security: SecurityCfg = Field(default_factory=SecurityCfg)
    analysis: AnalysisCfg = Field(default_factory=AnalysisCfg)
    embeddings: EmbeddingsCfg = Field(default_factory=EmbeddingsCfg)
    models: ModelsCfg = Field(default_factory=ModelsCfg)

    # --- 便捷路径解析 ---
    def ensure_dirs(self) -> None:
        for p in (
            self.storage.root, self.storage.vectors_dir, self.storage.graphs_dir,
            self.storage.analytics_dir, self.storage.repos_dir, self.storage.reports_dir,
        ):
            Path(p).mkdir(parents=True, exist_ok=True)


def _config_path() -> Path:
    env = os.getenv("CR_CONFIG")
    if env:
        return Path(env)
    # 默认在 repo 根的 config/config.yaml,回落 example
    here = Path(__file__).resolve()
    root = here.parents[3]  # backend/app/core/config.py -> code-review/
    cfg = root / "config" / "config.yaml"
    if cfg.exists():
        return cfg
    return root / "config" / "config.example.yaml"


@lru_cache
def get_settings() -> Settings:
    path = _config_path()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    settings = Settings(**(data or {}))
    settings.ensure_dirs()
    return settings
