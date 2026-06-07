"""llm/embedder.py — embedding 调用(维度锁定)

provider 不可达时回落到确定性 hash 伪向量(保证 M0 向量流水线可跑通)。
换模型 = 全量重嵌(config 显式标注 dim)。
"""
from __future__ import annotations

import hashlib
import struct

import httpx

from app.core.logging import get_logger
from app.llm.registry import resolve_embedding

log = get_logger("llm.embedder")


def embed_texts(texts: list[str], timeout: float = 60.0) -> list[list[float]]:
    if not texts:
        return []
    rm = resolve_embedding()
    headers = {"Content-Type": "application/json"}
    if rm.api_key:
        headers["Authorization"] = f"Bearer {rm.api_key}"
    try:
        with httpx.Client(timeout=timeout) as cli:
            r = cli.post(f"{rm.base_url}/embeddings",
                         json={"model": rm.model, "input": texts}, headers=headers)
            r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            return [d["embedding"] for d in data]
    except Exception as e:  # noqa: BLE001
        log.warning("embedding provider 不可达,使用 hash 伪向量: %s", e)
        return [_hash_vec(t, rm.dim or 1024) for t in texts]


def embed_one(text: str) -> list[float]:
    return embed_texts([text])[0]


def _hash_vec(text: str, dim: int) -> list[float]:
    """确定性伪向量:同文本同向量,可用于离线相似度近似。"""
    out: list[float] = []
    i = 0
    while len(out) < dim:
        h = hashlib.sha256(f"{i}:{text}".encode()).digest()
        for j in range(0, len(h) - 3, 4):
            if len(out) >= dim:
                break
            v = struct.unpack("i", h[j:j + 4])[0]
            out.append((v % 2000) / 1000.0 - 1.0)
        i += 1
    return out
