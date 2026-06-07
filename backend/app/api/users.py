"""api/users.py — 用户管理(admin)+ 身份映射"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import current_user, require_admin
from app.api.projects import _check_access
from app.auth import identity, users

router = APIRouter(prefix="/api", tags=["users"])


class CreateUserReq(BaseModel):
    username: str
    password: str
    name: str = ""
    role: str = "user"
    projects: list[str] = []


@router.get("/users")
def get_users(admin: dict = Depends(require_admin)):
    return {"data": users.list_users()}


@router.post("/users")
def add_user(req: CreateUserReq, admin: dict = Depends(require_admin)):
    return users.create_user(req.username, req.password, req.name, req.role, req.projects)


class UpdateUserReq(BaseModel):
    disabled: bool | None = None
    projects: list[str] | None = None


@router.patch("/users/{uid}")
def update_user(uid: str, req: UpdateUserReq, admin: dict = Depends(require_admin)):
    if req.disabled is not None:
        users.set_disabled(uid, req.disabled)
    if req.projects is not None:
        users.set_access(uid, req.projects)
    return {"ok": True}


# ---------- 身份映射 ---------- #
@router.get("/projects/{pid}/identities")
def get_identities(pid: str, user: dict = Depends(current_user)):
    _check_access(user, pid)
    return {"data": identity.list_identities(pid)}


@router.post("/projects/{pid}/identities/resolve")
def resolve(pid: str, user: dict = Depends(current_user)):
    _check_access(user, pid)
    n = identity.resolve_project_identities(pid)
    return {"resolved": n}


class MergeReq(BaseModel):
    source_id: int
    target_id: int


@router.post("/projects/{pid}/identities/merge")
def merge(pid: str, req: MergeReq, admin: dict = Depends(require_admin)):
    identity.merge_identities(pid, req.source_id, req.target_id)
    return {"ok": True}
