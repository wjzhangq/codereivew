"""queue/queue.py — SQLite 自建 claim 队列(无 Redis)

原子领取(BEGIN IMMEDIATE + RETURNING):写类任务按 project 串行;读类并发。
优先级:webhook 增量 > 手动报告 > 全量回填。push 去抖合并。
"""
from __future__ import annotations

import datetime as dt
import json
import time

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_conn

log = get_logger("queue")

WRITE_TYPES = frozenset({"fetch", "index_build", "index_incremental"})

PRIORITY_WEBHOOK = 10
PRIORITY_MANUAL = 5
PRIORITY_BACKFILL = 1


def enqueue(type: str, project_id: str, branch: str | None = None,
            payload: dict | None = None, priority: int = 0,
            detail: str = "") -> int:
    """入队任务。push 去抖:同 project+type+branch 已有 queued 则跳过。"""
    conn = get_conn()
    try:
        # 去抖合并
        cur = conn.execute(
            "SELECT id FROM jobs WHERE project_id=? AND type=? AND branch IS ? "
            "AND status='queued'", (project_id, type, branch))
        if cur.fetchone():
            conn.close()
            return -1  # 已排队
        cur = conn.execute(
            "INSERT INTO jobs(project_id,branch,type,payload,priority,detail) "
            "VALUES (?,?,?,?,?,?)",
            (project_id, branch, type, json.dumps(payload) if payload else None,
             priority, detail))
        conn.commit()
        jid = cur.lastrowid
        log.info("enqueued J-%d %s %s@%s", jid, type, project_id, branch)
        return jid  # type: ignore
    finally:
        conn.close()


def claim(worker_id: str) -> dict | None:
    """原子领取一个任务(plan §7)。写类任务按 project 串行。"""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        # 串行约束:同 project 已有写类 running 则跳过
        cur = conn.execute(f"""
            UPDATE jobs SET status='running', locked_by=?, locked_at=?, attempts=attempts+1
            WHERE id = (
                SELECT id FROM jobs WHERE status='queued'
                  AND run_after <= ?
                  AND NOT (type IN ({','.join('?'*len(WRITE_TYPES))})
                    AND EXISTS (
                        SELECT 1 FROM jobs j2 WHERE j2.project_id=jobs.project_id
                        AND j2.status='running'
                        AND j2.type IN ({','.join('?'*len(WRITE_TYPES))})
                    ))
                ORDER BY priority DESC, created_at ASC LIMIT 1)
            RETURNING *
        """, (worker_id, now, now, *WRITE_TYPES, *WRITE_TYPES))
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def complete(job_id: int, result_ref: str | None = None,
             detail: str | None = None) -> None:
    conn = get_conn()
    try:
        if detail is not None:
            conn.execute("UPDATE jobs SET status='done', progress=100, result_ref=?, "
                         "detail=?, error=NULL, updated_at=datetime('now') WHERE id=?",
                         (result_ref, detail, job_id))
        else:
            conn.execute("UPDATE jobs SET status='done', progress=100, result_ref=?, "
                         "error=NULL, updated_at=datetime('now') WHERE id=?",
                         (result_ref, job_id))
        conn.commit()
    finally:
        conn.close()


def fail(job_id: int, error: str, permanent: bool = False) -> None:
    """退避重试:attempts++ 后按 attempts^2 * backoff_base 延后 run_after。

    permanent=True 时跳过退避,直接标 failed —— 用于确定性的零产出
    (缺扫描器 / 无图谱 / 无 commit),重试也不会有结果。
    """
    s = get_settings()
    conn = get_conn()
    try:
        cur = conn.execute("SELECT attempts FROM jobs WHERE id=?", (job_id,))
        row = cur.fetchone()
        attempts = row["attempts"] if row else 1
        if permanent or attempts >= s.queue.max_attempts:
            conn.execute("UPDATE jobs SET status='failed', error=?, updated_at=datetime('now') "
                         "WHERE id=?", (error, job_id))
        else:
            delay = s.queue.backoff_base_s * (attempts ** 2)
            run_after = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=delay)).isoformat()
            conn.execute("UPDATE jobs SET status='queued', locked_by=NULL, error=?, "
                         "run_after=?, updated_at=datetime('now') WHERE id=?",
                         (error, run_after, job_id))
        conn.commit()
    finally:
        conn.close()


def update_progress(job_id: int, progress: int, detail: str | None = None) -> None:
    conn = get_conn()
    try:
        if detail:
            conn.execute("UPDATE jobs SET progress=?, detail=?, updated_at=datetime('now') "
                         "WHERE id=?", (progress, detail, job_id))
        else:
            conn.execute("UPDATE jobs SET progress=?, updated_at=datetime('now') WHERE id=?",
                         (progress, job_id))
        conn.commit()
    finally:
        conn.close()


def retry_job(job_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute("UPDATE jobs SET status='queued', attempts=0, locked_by=NULL, "
                           "error=NULL, run_after=datetime('now'), updated_at=datetime('now') "
                           "WHERE id=? AND status='failed' RETURNING id", (job_id,))
        conn.commit()
        return cur.fetchone() is not None
    finally:
        conn.close()


def list_jobs(status: str | None = None, limit: int = 50) -> list[dict]:
    conn = get_conn()
    try:
        if status:
            cur = conn.execute("SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                               (status, limit))
        else:
            cur = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_job(job_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
