"""llm/registry.py — 多 provider 加载 + 分级路由

config.models.providers 声明 provider(OpenAI 兼容);
llm.default/cheap、embedding.default 指定 provider+模型;routing 把任务映射到档位。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import ProviderCfg, get_settings


@dataclass
class ResolvedModel:
    provider_name: str
    base_url: str
    api_key: str | None
    model: str
    dim: int | None = None


def resolve_llm(tier: str) -> ResolvedModel:
    """tier: 'default' | 'cheap'。"""
    s = get_settings()
    ref = s.models.llm.get(tier) or s.models.llm.get("default")
    if not ref:
        raise RuntimeError("config.models.llm 未配置")
    prov = s.models.providers[ref.provider]
    return ResolvedModel(ref.provider, prov.base_url, prov.api_key, ref.model)


def resolve_embedding() -> ResolvedModel:
    s = get_settings()
    ref = s.models.embedding["default"]
    prov = s.models.providers[ref.provider]
    return ResolvedModel(ref.provider, prov.base_url, prov.api_key, ref.model, ref.dim)


def tier_for_task(task: str) -> str:
    """routing 表把任务映射到档位;默认 default。"""
    s = get_settings()
    return s.models.routing.get(task, "default")
