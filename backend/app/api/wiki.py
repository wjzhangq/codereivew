"""api/wiki.py — Wiki 页 + 增量刷新"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user
from app.api.projects import _check_access
from app.db.session import get_conn_ro
from app.queue import queue

router = APIRouter(prefix="/api/projects", tags=["wiki"])


@router.get("/{pid}/wiki")
def list_wiki(pid: str, user: dict = Depends(current_user)):
    _check_access(user, pid)
    conn = get_conn_ro()
    try:
        rows = conn.execute("SELECT page_key,title,page_group,fresh,updated_at "
                          "FROM wiki_pages WHERE project_id=? ORDER BY page_group", (pid,)).fetchall()
    finally:
        conn.close()
    return {"data": [{"id": r["page_key"], "title": r["title"], "group": r["page_group"],
                      "fresh": bool(r["fresh"]), "updated": r["updated_at"]} for r in rows]}


@router.get("/{pid}/wiki/{page}")
def get_wiki(pid: str, page: str, user: dict = Depends(current_user)):
    _check_access(user, pid)
    conn = get_conn_ro()
    try:
        r = conn.execute("SELECT * FROM wiki_pages WHERE project_id=? AND page_key=?",
                       (pid, page)).fetchone()
    finally:
        conn.close()
    if not r:
        raise HTTPException(404, "Wiki 页不存在")
    return {"title": r["title"], "group": r["page_group"], "updated": r["updated_at"],
            "fresh": bool(r["fresh"]),
            "sections": json.loads(r["sections"]) if r["sections"] else []}


@router.post("/{pid}/wiki/refresh")
def refresh_wiki(pid: str, user: dict = Depends(current_user)):
    _check_access(user, pid)
    jid = queue.enqueue("wiki_gen", pid, priority=queue.PRIORITY_MANUAL,
                        detail="增量刷新 Wiki")
    return {"jobId": jid}
