"""api/webhook.py — 平台 webhook → 入队自动分析"""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.logging import get_logger
from app.db.session import get_conn
from app.queue import queue

router = APIRouter(prefix="/api/webhook", tags=["webhook"])
log = get_logger("api.webhook")


@router.post("/{provider}")
async def webhook(provider: str, request: Request,
                  x_hub_signature_256: str | None = Header(None),
                  x_gitlab_token: str | None = Header(None)):
    body = await request.body()
    payload = await request.json()

    # 解析仓库 + 分支
    if provider == "github":
        repo_url = payload.get("repository", {}).get("ssh_url", "")
        ref = payload.get("ref", "")
    elif provider == "gitlab":
        repo_url = payload.get("project", {}).get("git_ssh_url", "")
        ref = payload.get("ref", "")
    else:
        raise HTTPException(400, "未知 provider")
    branch = ref.replace("refs/heads/", "")

    project = _find_project(repo_url)
    if not project:
        log.warning("webhook 未匹配项目: %s", repo_url)
        return {"matched": False}

    # 校验 secret
    secret = _webhook_secret(project["id"])
    if secret:
        if provider == "github":
            expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            if not x_hub_signature_256 or not hmac.compare_digest(expected, x_hub_signature_256):
                raise HTTPException(401, "签名校验失败")
        elif provider == "gitlab" and x_gitlab_token != secret:
            raise HTTPException(401, "token 校验失败")

    # 仅白名单分支触发
    if not _is_whitelisted(project["id"], branch):
        return {"matched": True, "triggered": False, "reason": "分支未纳入白名单"}

    queue.enqueue("fetch", project["id"], priority=queue.PRIORITY_WEBHOOK,
                  detail="webhook fetch")
    queue.enqueue("index_incremental", project["id"], branch=branch,
                  priority=queue.PRIORITY_WEBHOOK, detail=f"webhook 增量索引 {branch}")
    queue.enqueue("commit_analyze", project["id"], branch=branch,
                  priority=queue.PRIORITY_WEBHOOK, detail=f"webhook commit 分析 {branch}")
    return {"matched": True, "triggered": True, "branch": branch}


def _find_project(repo_url: str) -> dict | None:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT id, git_url FROM projects").fetchall()
        for r in rows:
            if _normalize(r["git_url"]) == _normalize(repo_url):
                return dict(r)
        return None
    finally:
        conn.close()


def _normalize(url: str) -> str:
    return url.replace(".git", "").split(":")[-1].strip("/").lower()


def _webhook_secret(pid: str) -> str | None:
    conn = get_conn()
    try:
        r = conn.execute("SELECT webhook_secret FROM project_settings WHERE project_id=?",
                       (pid,)).fetchone()
        return r["webhook_secret"] if r else None
    finally:
        conn.close()


def _is_whitelisted(pid: str, branch: str) -> bool:
    conn = get_conn()
    try:
        r = conn.execute("SELECT whitelisted FROM branches WHERE project_id=? AND name=?",
                       (pid, branch)).fetchone()
        return bool(r and r["whitelisted"])
    finally:
        conn.close()
