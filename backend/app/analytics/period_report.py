"""analytics/period_report.py — 周期/功能报告(DuckDB 聚合已缓存 commit_analysis)

只有新 commit 花 LLM 成本;聚合零 LLM。
"""
from __future__ import annotations

import json

from app.analytics.duck import duck
from app.core.logging import get_logger
from app.db.session import get_conn
from app.queue.result import JobResult

log = get_logger("analytics.period")


def build_period_report(project_id: str, branch: str | None, range_spec: str) -> JobResult:
    """聚合 commit_analysis → 周期报告(commit 列表 + 模块统计 + drift 计数)。"""
    with duck() as con:
        rows = con.execute("""
            SELECT commit_sha, author, committed_at, summary, problem, approach,
                   modules, loc_add, loc_del, raw_msg, msg_drift
            FROM meta.commit_analysis
            WHERE project_id = ?
            ORDER BY committed_at DESC
        """, [project_id]).fetchall()
        cols = [d[0] for d in con.description]
    commits = []
    module_counter: dict[str, int] = {}
    drift_count = 0
    for r in rows:
        rec = dict(zip(cols, r))
        mods = json.loads(rec["modules"]) if rec["modules"] else []
        for m in mods:
            module_counter[m] = module_counter.get(m, 0) + 1
        if rec["msg_drift"]:
            drift_count += 1
        commits.append({
            "sha": rec["commit_sha"][:7], "author": rec["author"],
            "when": rec["committed_at"], "add": rec["loc_add"], "del": rec["loc_del"],
            "modules": mods, "drift": bool(rec["msg_drift"]),
            "summary": rec["summary"], "problem": rec["problem"],
            "approach": rec["approach"], "rawMsg": rec["raw_msg"],
        })
    report = {
        "range": range_spec, "commitCount": len(commits),
        "drift": drift_count, "topModules": sorted(
            module_counter.items(), key=lambda kv: -kv[1])[:8],
        "commits": commits,
    }
    _save(project_id, "period", range_spec, report)
    skipped = [] if commits else ["无已分析 commit(请先触发 Commit 理解)"]
    return JobResult(produced=len(commits), skipped=skipped,
                     note=f"周期报告:{len(commits)} commit,{drift_count} drift")


def _save(project_id: str, type: str, range_spec: str, payload: dict) -> None:
    conn = get_conn()
    try:
        conn.execute("INSERT INTO reports(project_id,type,range_spec,payload) VALUES (?,?,?,?)",
                     (project_id, type, range_spec, json.dumps(payload, ensure_ascii=False)))
        conn.commit()
    finally:
        conn.close()
