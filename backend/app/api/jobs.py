"""api/jobs.py — 任务队列监控"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import current_user
from app.queue import queue

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_TYPE_LABEL = {
    "fetch": "拉取", "index_build": "全量索引", "index_incremental": "增量索引",
    "commit_analyze": "Commit 理解", "security_scan": "安全扫描",
    "period_report": "周期报告", "contributor_report": "贡献报告", "wiki_gen": "Wiki 生成",
}
_PRIORITY_LABEL = {10: "高", 5: "中", 1: "低", 0: "低"}


@router.get("")
def get_jobs(status: str | None = None, user: dict = Depends(current_user)):
    jobs = queue.list_jobs(status)
    return {"data": [{
        "id": f"J-{j['id']}", "type": j["type"], "typeLabel": _TYPE_LABEL.get(j["type"], j["type"]),
        "project": j["project_id"], "branch": j["branch"] or "—",
        "status": j["status"], "priority": _PRIORITY_LABEL.get(j["priority"], "低"),
        "progress": j["progress"], "worker": j["locked_by"], "attempts": j["attempts"],
        "when": j["updated_at"], "detail": j["detail"],
    } for j in jobs]}


@router.post("/{job_id}/retry")
def retry(job_id: int, user: dict = Depends(current_user)):
    ok = queue.retry_job(job_id)
    return {"ok": ok}
