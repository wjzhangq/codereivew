"""api/settings.py — 项目设置(webhook / API Key / 平台 token / 分析参数)"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import current_user, require_admin
from app.api.projects import _check_access
from app.auth import keys
from app.db.session import get_conn_ro, tx

router = APIRouter(prefix="/api/projects", tags=["settings"])


@router.get("/{pid}/settings")
def get_settings_(pid: str, user: dict = Depends(current_user)):
    _check_access(user, pid)
    conn = get_conn_ro()
    try:
        p = conn.execute("SELECT git_url, default_branch, platform FROM projects WHERE id=?",
                       (pid,)).fetchone()
        s = conn.execute("SELECT * FROM project_settings WHERE project_id=?", (pid,)).fetchone()
    finally:
        conn.close()
    return {
        "gitUrl": p["git_url"] if p else "",
        "defaultBranch": p["default_branch"] if p else "",
        "platform": p["platform"] if p else None,
        "webhookEnabled": bool(s["webhook_enabled"]) if s else True,
        "hasWebhookSecret": bool(s and s["webhook_secret"]),
        "analysis": json.loads(s["settings_json"]) if s and s["settings_json"] else {},
        "keys": keys.list_keys(pid),
    }


class WebhookReq(BaseModel):
    secret: str | None = None
    enabled: bool = True


@router.put("/{pid}/settings/webhook")
def set_webhook(pid: str, req: WebhookReq, user: dict = Depends(current_user)):
    _check_access(user, pid)
    with tx() as conn:
        conn.execute("""
            INSERT INTO project_settings(project_id,webhook_secret,webhook_enabled)
            VALUES (?,?,?)
            ON CONFLICT(project_id) DO UPDATE SET
                webhook_secret=COALESCE(excluded.webhook_secret, project_settings.webhook_secret),
                webhook_enabled=excluded.webhook_enabled
        """, (pid, req.secret, int(req.enabled)))
    return {"ok": True}


class AnalysisReq(BaseModel):
    settings: dict


@router.put("/{pid}/settings/analysis")
def set_analysis(pid: str, req: AnalysisReq, user: dict = Depends(current_user)):
    _check_access(user, pid)
    with tx() as conn:
        conn.execute("""
            INSERT INTO project_settings(project_id,settings_json) VALUES (?,?)
            ON CONFLICT(project_id) DO UPDATE SET settings_json=excluded.settings_json
        """, (pid, json.dumps(req.settings)))
    return {"ok": True}


class KeyReq(BaseModel):
    name: str = ""
    scope: str = "read"


@router.post("/{pid}/keys")
def create_key(pid: str, req: KeyReq, user: dict = Depends(current_user)):
    _check_access(user, pid)
    return keys.create_key(pid, req.name, req.scope)


@router.delete("/{pid}/keys/{kid}")
def revoke_key(pid: str, kid: str, user: dict = Depends(current_user)):
    _check_access(user, pid)
    return {"ok": keys.revoke_key(kid)}
