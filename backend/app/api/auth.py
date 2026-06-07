"""api/auth.py — 登录"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth import users
from app.core.security import create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginReq(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginReq):
    user = users.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(401, "用户名或密码错误")
    token = create_token(user["id"], user["role"])
    return {"token": token, "user": user}
