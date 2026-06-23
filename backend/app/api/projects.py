"""api/projects.py — 项目接入/列表/详情 + 分支白名单 + 图谱"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import current_user
from app.auth.users import user_can_access
from app.core.logging import audit
from app.core.security import encrypt_secret
from app.db.session import get_conn_ro, tx
from app.queue import queue

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectReq(BaseModel):
    name: str
    git_url: str
    org: str | None = None
    platform: str | None = None
    deploy_key: str | None = None
    description: str | None = None


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("/", "-")


@router.get("")
def list_projects(user: dict = Depends(current_user)):
    conn = get_conn_ro()
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY created_at DESC")]
    finally:
        conn.close()
    if user.get("role") not in ("admin", "machine"):
        rows = [r for r in rows if user_can_access(user, r["id"])]
    return {"data": [_project_card(r) for r in rows]}


@router.post("")
def create_project(req: CreateProjectReq, user: dict = Depends(current_user)):
    if user.get("role") not in ("admin", "machine"):
        raise HTTPException(403, "仅管理员可接入仓库")
    pid = _slug(req.name)
    with tx() as conn:
        if conn.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone():
            raise HTTPException(409, "项目已存在")
        conn.execute("""
            INSERT INTO projects(id,name,org,git_url,platform,deploy_key_enc,description,status)
            VALUES (?,?,?,?,?,?,?,'pending')
        """, (pid, req.name, req.org, req.git_url, req.platform,
              encrypt_secret(req.deploy_key) if req.deploy_key else None, req.description))
    audit("create_project", project=pid, url=req.git_url)
    jid = queue.enqueue("index_build", pid, priority=queue.PRIORITY_BACKFILL,
                        detail="首次克隆 + 全量索引")
    return {"id": pid, "jobId": jid}


@router.get("/{pid}")
def get_project(pid: str, user: dict = Depends(current_user)):
    _check_access(user, pid)
    conn = get_conn_ro()
    try:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "项目不存在")
        branches = conn.execute("SELECT COUNT(*) AS n FROM branches WHERE project_id=?",
                              (pid,)).fetchone()["n"]
        findings = conn.execute(
            "SELECT COUNT(*) AS n FROM findings WHERE project_id=? AND status='new'",
            (pid,)).fetchone()["n"]
    finally:
        conn.close()
    d = dict(row)
    d["branches"] = branches
    d["openFindings"] = findings
    return d


# --------------------------------------------------------------------------- #
# 分支白名单
# --------------------------------------------------------------------------- #
@router.get("/{pid}/branches")
def get_branches(pid: str, user: dict = Depends(current_user)):
    _check_access(user, pid)
    conn = get_conn_ro()
    try:
        rows = conn.execute("SELECT * FROM branches WHERE project_id=? ORDER BY is_default DESC, name",
                          (pid,)).fetchall()
    finally:
        conn.close()
    return {"data": [{
        "name": r["name"], "isDefault": bool(r["is_default"]),
        "whitelisted": bool(r["whitelisted"]), "ahead": r["ahead"], "behind": r["behind"],
        "lastCommit": r["last_commit"], "lastCommitMsg": r["last_commit_msg"],
        "author": r["author"], "when": r["committed_at"], "indexed": bool(r["indexed"]),
        "version": r["graph_version"],
    } for r in rows]}


class WhitelistReq(BaseModel):
    whitelisted: bool


@router.put("/{pid}/branches/{name:path}/whitelist")
def set_whitelist(pid: str, name: str, req: WhitelistReq, user: dict = Depends(current_user)):
    _check_access(user, pid)
    with tx() as conn:
        row = conn.execute("SELECT is_default FROM branches WHERE project_id=? AND name=?",
                          (pid, name)).fetchone()
        if not row:
            raise HTTPException(404, "分支不存在")
        if row["is_default"] and not req.whitelisted:
            raise HTTPException(409, "默认分支强制纳入,不可取消")
        conn.execute("UPDATE branches SET whitelisted=? WHERE project_id=? AND name=?",
                     (int(req.whitelisted), pid, name))
    if req.whitelisted:
        queue.enqueue("index_incremental", pid, branch=name,
                      priority=queue.PRIORITY_MANUAL, detail=f"索引新纳入分支 {name}")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# 模块图谱
# --------------------------------------------------------------------------- #
@router.get("/{pid}/graph")
def get_graph(pid: str, branch: str | None = None, user: dict = Depends(current_user)):
    _check_access(user, pid)
    from app.parsing.graph_store import GraphStore
    branch = branch or _default_branch(pid)
    try:
        gs = GraphStore(pid, branch)
        info = gs.graph_info()
        findings_by_mod = _findings_by_module(pid)
        gs.close()
    except FileNotFoundError:
        return {"modules": [], "edges": []}
    return {
        "modules": [{
            "id": m.id, "name": m.name, "files": m.files, "loc": m.loc,
            "x": m.x, "y": m.y, "cat": m.cat, "health": m.health,
            "churn": m.churn, "owner": m.owner, "desc": m.description,
            "findings": findings_by_mod.get(m.name, 0),
        } for m in info.modules],
        "edges": info.edges,
    }


# --------------------------------------------------------------------------- #
# 重新索引
# --------------------------------------------------------------------------- #
@router.post("/{pid}/reindex")
def reindex(pid: str, user: dict = Depends(current_user)):
    _check_access(user, pid)
    jid = queue.enqueue("index_build", pid, priority=queue.PRIORITY_MANUAL,
                        detail="手动重新索引")
    return {"jobId": jid}


# --------------------------------------------------------------------------- #
# 主动同步远程
# --------------------------------------------------------------------------- #
@router.post("/{pid}/sync")
def sync_remote(pid: str, user: dict = Depends(current_user)):
    _check_access(user, pid)
    conn = get_conn_ro()
    try:
        row = conn.execute("SELECT deploy_key_enc FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "项目不存在")
    finally:
        conn.close()

    from app.core.security import decrypt_secret
    from app.git.repo import fetch, bare_path
    from app.queue.handlers import _sync_branches

    deploy_key = decrypt_secret(row["deploy_key_enc"]) if row["deploy_key_enc"] else None
    bare = bare_path(pid)
    if not bare.exists():
        raise HTTPException(409, "仓库尚未克隆,请先触发索引")

    try:
        fetch(pid, deploy_key)
    except RuntimeError as e:
        raise HTTPException(502, f"git fetch 失败: {e}")

    _sync_branches(pid)
    audit("sync_remote", project=pid)
    return {"ok": True}


# --------------------------------------------------------------------------- #
def _project_card(r: dict) -> dict:
    return {
        "id": r["id"], "name": r["name"], "org": r["org"], "url": r["git_url"],
        "platform": r["platform"], "lang": r["lang"], "license": r["license"],
        "desc": r["description"], "version": r["version"], "files": r["files"],
        "loc": r["loc"], "openFindings": 0, "status": r["status"],
        "indexProgress": r["index_progress"], "health": r["health"],
        "lastIndexed": r["last_indexed_at"], "defaultBranch": r["default_branch"],
    }


def _findings_by_module(pid: str) -> dict[str, int]:
    conn = get_conn_ro()
    try:
        rows = conn.execute(
            "SELECT module, COUNT(*) AS n FROM findings WHERE project_id=? AND status='new' "
            "GROUP BY module", (pid,)).fetchall()
        return {r["module"]: r["n"] for r in rows if r["module"]}
    finally:
        conn.close()


def _default_branch(pid: str) -> str:
    conn = get_conn_ro()
    try:
        r = conn.execute("SELECT default_branch FROM projects WHERE id=?", (pid,)).fetchone()
        return (r["default_branch"] if r else None) or "main"
    finally:
        conn.close()


def _check_access(user: dict, pid: str):
    if user.get("role") == "machine":
        if user.get("project_id") and user["project_id"] != pid:
            raise HTTPException(403, "Key 无权访问该项目")
        return
    if not user_can_access(user, pid):
        raise HTTPException(403, "无权访问该项目")
