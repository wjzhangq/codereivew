"""llm/client.py — 统一 chat 调用(OpenAI 兼容)

带重试/超时;源码只发给 config 白名单 provider。
provider 不可达时回落到离线 stub(保证 M0/M1 流水线可端到端跑通)。
"""
from __future__ import annotations

import json

import httpx

from app.core.logging import get_logger
from app.llm.registry import resolve_llm, tier_for_task

log = get_logger("llm.client")


def chat(task: str, system: str, user: str, *, json_mode: bool = False,
         max_tokens: int = 1500, timeout: float = 60.0) -> str:
    tier = tier_for_task(task)
    rm = resolve_llm(tier)
    payload = {
        "model": rm.model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if rm.api_key:
        headers["Authorization"] = f"Bearer {rm.api_key}"
    try:
        with httpx.Client(timeout=timeout) as cli:
            r = cli.post(f"{rm.base_url}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        log.warning("LLM provider 不可达(%s),使用离线 stub: %s", rm.provider_name, e)
        return _stub(task, json_mode)


def chat_json(task: str, system: str, user: str, **kw) -> dict:
    raw = chat(task, system, user, json_mode=True, **kw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 抽取第一个 { ... }
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass
        return {}


def _stub(task: str, json_mode: bool) -> str:
    """离线占位:provider 未配置时让流水线跑通。"""
    if not json_mode:
        return "（LLM provider 未配置,此为占位回答。配置 config.models 后生效。）"
    if task == "commit_analyze":
        return json.dumps({
            "summary": "（占位)本次改动的概述待 LLM 生成。",
            "problem": "（占位)解决的问题待 LLM 生成。",
            "approach": "（占位)采用的思路待 LLM 生成。",
        }, ensure_ascii=False)
    return "{}"
