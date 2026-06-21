"""api/deps.py — 鉴权依赖(JWT for Web / API Key for 机器)"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from app.auth import keys
from app.core.security import decode_token
from app.db.session import get_conn_ro


def _user_by_id(uid: str) -> dict | None:
    conn = get_conn_ro()
    try:
        row = conn.execute("SELECT id,username,name,role,disabled FROM users WHERE id=?",
                          (uid,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


async def current_user(authorization: str | None = Header(None),
                       x_api_key: str | None = Header(None)) -> dict:
    """两条鉴权线:Bearer JWT(Web)或 X-API-Key(机器)。"""
    if authorization and authorization.startswith("Bearer "):
        payload = decode_token(authorization[7:])
        if payload:
            user = _user_by_id(payload["sub"])
            if user and not user["disabled"]:
                return user
    if x_api_key:
        k = keys.validate_key(x_api_key)
        if k:
            return {"id": "apikey", "role": "machine", "scope": k["scope"],
                    "project_id": k["project_id"]}
    raise HTTPException(401, "未认证")


async def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user
