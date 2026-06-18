"""analysis/commit_analyzer.py — 逐 commit 理解(忽略 message,LLM 读真实 diff)

结果永久缓存(commit 不可变,UNIQUE project+sha)。
回溯范围 = max(最近 N 天, 最近 M 条)。可选 detect_message_drift。
"""
from __future__ import annotations

import json
from collections.abc import Callable

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_conn
from app.git import history
from app.llm import client
from app.queue.result import JobResult

log = get_logger("analysis.commit")

_SYSTEM = (
    "你是资深代码审查员。只依据真实的 diff 与 blame 上下文理解这次提交,"
    "完全忽略 commit message(它可能不可信)。"
    "输出 JSON:{summary, problem, approach},中文,精炼准确。"
)


def _prompt(diff: history.CommitDiff, modules: list[str]) -> str:
    files = "\n".join(f"  {f.file} (+{f.add}/-{f.del_})" for f in diff.files[:30])
    return (
        f"涉及模块: {', '.join(modules) or '未知'}\n"
        f"变更文件:\n{files}\n\n"
        f"diff(截断):\n{diff.patch[:12000]}\n\n"
        "请输出 JSON:summary(本次改动概述)、problem(解决的问题)、approach(采用的思路)。"
    )


def _module_lookup(project_id: str, branch: str):
    from app.parsing.graph_store import GraphStore
    try:
        return GraphStore(project_id, branch)
    except FileNotFoundError:
        return None


def detect_message_drift(summary: str, raw_msg: str) -> bool:
    """对比 LLM 理解与原 msg,标记偏差较大者(简易:关键词重叠率)。"""
    if not raw_msg.strip():
        return True
    sw = set(summary.lower().split())
    mw = set(raw_msg.lower().split())
    if not mw:
        return True
    overlap = len(sw & mw) / len(mw)
    return overlap < 0.15


def analyze_commit(project_id: str, branch: str, sha: str, gs=None) -> dict:
    cfg = get_settings()
    conn = get_conn()
    try:
        cached = conn.execute(
            "SELECT * FROM commit_analysis WHERE project_id=? AND commit_sha=?",
            (project_id, sha)).fetchone()
        if cached:
            return dict(cached)  # 永久缓存命中
    finally:
        conn.close()

    diff = history.get_commit_diff(project_id, sha)
    modules = gs.modules_for_files([f.file for f in diff.files]) if gs else []
    out = client.chat_json("commit_analyze", _SYSTEM, _prompt(diff, modules))
    summary = out.get("summary", "")
    if not out or "（占位)" in summary:
        log.error(
            "commit %s 落入占位结果(LLM 未生成真实内容,见上方 'LLM 调用失败' 日志): out=%s",
            sha[:10], out,
        )
    drift = detect_message_drift(summary, diff.raw_msg) if cfg.analysis.detect_message_drift else False

    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO commit_analysis
            (project_id,branch,commit_sha,author,committed_at,summary,problem,approach,
             modules,loc_add,loc_del,raw_msg,msg_drift,model)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (project_id, branch, sha, diff.author, diff.committed_at, summary,
              out.get("problem", ""), out.get("approach", ""), json.dumps(modules),
              diff.loc_add, diff.loc_del, diff.raw_msg, int(drift), "cheap"))
        conn.commit()
    finally:
        conn.close()
    return {"sha": sha, "summary": summary, "drift": drift}


def analyze_branch(project_id: str, branch: str,
                   progress_cb: Callable[[int, str], None] | None = None) -> JobResult:
    cfg = get_settings().analysis.backfill
    shas = history.list_commits(project_id, branch, cfg.last_days, cfg.last_count)
    gs = _module_lookup(project_id, branch)
    total = max(len(shas), 1)
    n = 0
    for i, sha in enumerate(shas):
        analyze_commit(project_id, branch, sha, gs)
        n += 1
        if progress_cb:
            progress_cb(int(100 * (i + 1) / total), f"分析 {i+1}/{total} commit")
    if gs:
        gs.close()
    log.info("analyzed %d commits for %s@%s", n, project_id, branch)
    skipped = [] if shas else [f"分支 {branch} 在回溯窗口内无 commit"]
    if gs is None and shas:
        skipped.append("无图谱,模块归属缺失")
    return JobResult(produced=n, skipped=skipped, note=f"分析 {n} 个 commit")
