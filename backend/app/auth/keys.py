"""auth/keys.py — API Key 生成/校验/吊销"""
from __future__ import annotations

import uuid

from app.core.logging import audit
from app.core.security import generate_api_key, hash_api_key
from app.db.session import get_conn_ro, tx


def create_key(project_id: str, name: str = "", scope: str = "read") -> dict:
    raw, hashed = generate_api_key()
    kid = str(uuid.uuid4())[:8]
    with tx() as conn:
        conn.execute("INSERT INTO api_keys(id,project_id,name,key_hash,scope) VALUES (?,?,?,?,?)",
                     (kid, project_id, name, hashed, scope))
    audit("create_api_key", project=project_id, key_id=kid)
    return {"id": kid, "key": raw, "scope": scope}


def validate_key(raw_key: str) -> dict | None:
    """校验 API Key → 返回 {project_id, scope} 或 None。"""
    hashed = hash_api_key(raw_key)
    conn = get_conn_ro()
    try:
        row = conn.execute("SELECT * FROM api_keys WHERE key_hash=? AND revoked_at IS NULL",
                          (hashed,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def revoke_key(key_id: str) -> bool:
    with tx() as conn:
        cur = conn.execute(
            "UPDATE api_keys SET revoked_at=datetime('now') WHERE id=? AND revoked_at IS NULL "
            "RETURNING id", (key_id,))
        ok = cur.fetchone() is not None
    if ok:
        audit("revoke_api_key", key_id=key_id)
    return ok


def list_keys(project_id: str) -> list[dict]:
    conn = get_conn_ro()
    try:
        cur = conn.execute("SELECT id,project_id,name,scope,created_at,revoked_at "
                          "FROM api_keys WHERE project_id=?", (project_id,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
