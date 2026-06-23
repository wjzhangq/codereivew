"""api/analysis.py — 逐 commit 理解 + 周期/贡献报告"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user
from app.api.projects import _check_access, _default_branch
from app.db.session import get_conn_ro
from app.queue import queue

router = APIRouter(prefix="/api/projects", tags=["analysis"])


@router.get("/{pid}/commits")
def get_commits(pid: str, range: str = "30d", branch: str | None = None,
                user: dict = Depends(current_user)):
    _check_access(user, pid)
    conn = get_conn_ro()
    try:
        cur = conn.execute(
            "SELECT * FROM commit_analysis WHERE project_id=? ORDER BY committed_at DESC LIMIT 200",
            (pid,))
        rows = cur.fetchall()
    finally:
        conn.close()
    return {"data": [{
        "sha": r["commit_sha"][:7], "author": r["author"], "branch": r["branch"],
        "when": r["committed_at"], "add": r["loc_add"], "del": r["loc_del"],
        "modules": json.loads(r["modules"]) if r["modules"] else [],
        "drift": bool(r["msg_drift"]), "summary": r["summary"],
        "problem": r["problem"], "approach": r["approach"], "rawMsg": r["raw_msg"],
    } for r in rows]}


@router.post("/{pid}/analyze")
def trigger_analyze(pid: str, branch: str | None = None, user: dict = Depends(current_user)):
    _check_access(user, pid)
    branch = branch or _default_branch(pid)
    jid = queue.enqueue("commit_analyze", pid, branch=branch,
                        priority=queue.PRIORITY_MANUAL, detail=f"分析 {branch} commits")
    return {"jobId": jid}


@router.get("/{pid}/contributors")
def get_contributors(pid: str, mode: str = "log", user: dict = Depends(current_user)):
    _check_access(user, pid)
    conn = get_conn_ro()
    try:
        row = conn.execute(
            "SELECT payload FROM reports WHERE project_id=? AND type=? "
            "ORDER BY created_at DESC LIMIT 1", (pid, f"contributor_{mode}")).fetchone()
    finally:
        conn.close()
    if row:
        return json.loads(row["payload"])
    # 无缓存 → 触发任务
    queue.enqueue("contributor_report", pid, payload={"mode": mode},
                  priority=queue.PRIORITY_MANUAL, detail=f"贡献报告 {mode}")
    return {"mode": mode, "contributors": [], "pending": True}


@router.post("/{pid}/reports/period")
def trigger_period(pid: str, range: str = "30d", user: dict = Depends(current_user)):
    _check_access(user, pid)
    jid = queue.enqueue("period_report", pid, payload={"range": range},
                        priority=queue.PRIORITY_MANUAL, detail="周期报告")
    return {"jobId": jid}


@router.get("/{pid}/weekly")
def get_weekly(pid: str, week: str | None = None, since: str | None = None,
               until: str | None = None, llm: bool = True,
               user: dict = Depends(current_user)):
    """按周汇总各贡献者改动(功能范围/类别/质量)。

    周期解析:since+until 优先 → week(对齐到周一)→ 默认上一个完整自然周。
    llm=false 时跳过 LLM,仅用规则指标(更快/省 token)。
    """
    _check_access(user, pid)
    from app.reports import weekly

    if since and until:
        s, u = since, until
    elif week:
        s, u = weekly.week_of(week)
    else:
        s, u = weekly.last_full_week()

    try:
        md, stats = weekly.build_report(pid, s, u, use_llm=llm)
    except FileNotFoundError:
        raise HTTPException(404, "项目仓库不存在(尚未克隆/索引?)")

    return {
        "project": pid, "since": s, "until": u,
        "totalCommits": sum(st.commits for st in stats.values()),
        "authors": weekly.stats_to_json(stats),
        "markdown": md,
    }
