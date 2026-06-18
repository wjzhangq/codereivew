"""api/jobs.py — 任务队列监控"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user
from app.queue import queue

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_TYPE_LABEL = {
    "fetch": "拉取", "index_build": "全量索引", "index_incremental": "增量索引",
    "commit_analyze": "Commit 理解", "security_scan": "安全扫描",
    "period_report": "周期报告", "contributor_report": "贡献报告", "wiki_gen": "Wiki 生成",
}
_PRIORITY_LABEL = {10: "高", 5: "中", 1: "低", 0: "低"}

# worker.py claim() 的真实原子领取 SQL(供前端展示,避免编造)。
CLAIM_SQL = """BEGIN IMMEDIATE;

UPDATE jobs SET status='running', locked_by=:worker_id,
                locked_at=:now, attempts=attempts+1
WHERE id = (
    SELECT id FROM jobs WHERE status='queued'
      AND run_after <= :now
      -- 写类任务(fetch/index_build/index_incremental)按 project 串行:
      AND NOT (type IN ('fetch','index_build','index_incremental')
        AND EXISTS (
            SELECT 1 FROM jobs j2 WHERE j2.project_id = jobs.project_id
              AND j2.status='running'
              AND j2.type IN ('fetch','index_build','index_incremental')
        ))
    ORDER BY priority DESC, created_at ASC LIMIT 1)
RETURNING *;

COMMIT;"""


def _serialize(j: dict) -> dict:
    return {
        "id": f"J-{j['id']}", "type": j["type"],
        "typeLabel": _TYPE_LABEL.get(j["type"], j["type"]),
        "project": j["project_id"], "branch": j["branch"] or "—",
        "status": j["status"], "priority": _PRIORITY_LABEL.get(j["priority"], "低"),
        "progress": j["progress"], "worker": j["locked_by"], "attempts": j["attempts"],
        "detail": j["detail"], "error": j["error"], "resultRef": j["result_ref"],
        "lockedAt": j["locked_at"], "runAfter": j["run_after"],
        "createdAt": j["created_at"], "updatedAt": j["updated_at"],
        "when": j["updated_at"],
    }


@router.get("")
def get_jobs(status: str | None = None, user: dict = Depends(current_user)):
    jobs = queue.list_jobs(status)
    return {"data": [_serialize(j) for j in jobs], "claimSql": CLAIM_SQL}


@router.get("/{job_id}")
def get_job_detail(job_id: int, user: dict = Depends(current_user)):
    """单任务执行详情:含 error 全文、进度、领取时间,供前端定位。"""
    j = queue.get_job(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    data = _serialize(j)
    data["payload"] = j["payload"]
    return data


@router.post("/{job_id}/retry")
def retry(job_id: int, user: dict = Depends(current_user)):
    ok = queue.retry_job(job_id)
    return {"ok": ok}
