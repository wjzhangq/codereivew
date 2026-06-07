"""api/security.py — findings + 触发扫描"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import current_user
from app.api.projects import _check_access, _default_branch
from app.db.session import get_conn
from app.queue import queue

router = APIRouter(prefix="/api/projects", tags=["security"])


@router.get("/{pid}/findings")
def get_findings(pid: str, status: str | None = None, user: dict = Depends(current_user)):
    _check_access(user, pid)
    conn = get_conn()
    try:
        if status and status != "all":
            cur = conn.execute("SELECT * FROM findings WHERE project_id=? AND status=? "
                             "ORDER BY created_at DESC", (pid, status))
        else:
            cur = conn.execute("SELECT * FROM findings WHERE project_id=? ORDER BY created_at DESC",
                             (pid,))
        rows = cur.fetchall()
    finally:
        conn.close()
    return {"data": [{
        "id": r["id"], "sev": r["severity"], "rule": r["rule"], "source": r["source"],
        "file": r["file"], "line": r["line"], "title": r["title"], "evidence": r["evidence"],
        "suggestion": r["suggestion"], "module": r["module"] or "—", "blast": r["blast"],
        "llmReviewed": bool(r["llm_reviewed"]), "status": r["status"],
    } for r in rows]}


@router.post("/{pid}/scan")
def trigger_scan(pid: str, branch: str | None = None, user: dict = Depends(current_user)):
    _check_access(user, pid)
    branch = branch or _default_branch(pid)
    jid = queue.enqueue("security_scan", pid, branch=branch,
                        priority=queue.PRIORITY_MANUAL, detail=f"安全扫描 {branch}")
    return {"jobId": jid}


class StatusReq(BaseModel):
    status: str  # resolved | ignored | new


@router.patch("/{pid}/findings/{fid}")
def update_finding(pid: str, fid: str, req: StatusReq, user: dict = Depends(current_user)):
    _check_access(user, pid)
    conn = get_conn()
    try:
        conn.execute("UPDATE findings SET status=? WHERE id=? AND project_id=?",
                     (req.status, fid, pid))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
