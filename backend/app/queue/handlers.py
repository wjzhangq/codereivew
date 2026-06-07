"""queue/handlers.py — 任务处理器

把 git/parsing/analysis/security 各层串成可执行的任务。
"""
from __future__ import annotations

import json

from app.core.logging import audit, get_logger
from app.core.security import decrypt_secret
from app.db.session import get_conn
from app.queue import queue

log = get_logger("queue.handlers")


def _project(project_id: str) -> dict:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def _deploy_key(project: dict) -> str | None:
    enc = project.get("deploy_key_enc")
    return decrypt_secret(enc) if enc else None


# --------------------------------------------------------------------------- #
# fetch / index
# --------------------------------------------------------------------------- #
def handle_fetch(job: dict) -> None:
    from app.git import repo
    p = _project(job["project_id"])
    key = _deploy_key(p)
    repo.clone_mirror(p["git_url"], p["id"], key)
    _sync_branches(p["id"])
    queue.update_progress(job["id"], 100, "fetch 完成")


def handle_index_build(job: dict) -> None:
    """全量索引:对所有白名单分支建 worktree → 图谱 → 向量。"""
    from app.git import repo, worktree
    from app.parsing import engine
    pid = job["project_id"]
    p = _project(pid)
    key = _deploy_key(p)
    repo.clone_mirror(p["git_url"], pid, key)
    _set_status(pid, "indexing", 5)
    _sync_branches(pid)

    branches = _whitelisted_branches(pid)
    total = max(len(branches), 1)
    for i, br in enumerate(branches):
        worktree.add_worktree(pid, br)
        engine.build_graph(pid, br)
        _index_vectors(pid, br)
        _mark_branch_indexed(pid, br)
        queue.update_progress(job["id"], int(5 + 90 * (i + 1) / total),
                              f"已索引分支 {br}")
    _update_project_stats(pid)
    _set_status(pid, "active", 100)
    audit("index_build", project=pid, branches=len(branches))


def handle_index_incremental(job: dict) -> None:
    """增量:只重解析/重嵌变更分支。"""
    from app.git import worktree
    from app.parsing import engine
    pid = job["project_id"]
    br = job["branch"]
    p = _project(pid)
    key = _deploy_key(p)
    from app.git import repo
    repo.fetch(pid, key)
    worktree.add_worktree(pid, br)
    engine.build_graph(pid, br)
    _index_vectors(pid, br)  # SHA-256 复用未变更 chunk
    _mark_branch_indexed(pid, br)
    queue.update_progress(job["id"], 100, f"增量索引 {br} 完成")


def _index_vectors(project_id: str, branch: str) -> None:
    from app.llm.embedder import embed_texts
    from app.parsing.chunker import chunk_repo
    from app.parsing.vectors import VectorStore
    chunks = chunk_repo(project_id, branch)
    vs = VectorStore(project_id)
    existing = vs.existing_shas(branch)
    fresh = [c for c in chunks if c.sha256 not in existing]  # SHA-256 复用
    if fresh:
        embeddings = embed_texts([c.content for c in fresh])
        n = vs.upsert_chunks(branch, fresh, embeddings)
        log.info("indexed %d new chunks (skipped %d reused) for %s@%s",
                 n, len(chunks) - len(fresh), project_id, branch)
    vs.close()


# --------------------------------------------------------------------------- #
# commit 分析 / 安全扫描 / 报告 / wiki
# --------------------------------------------------------------------------- #
def handle_commit_analyze(job: dict) -> None:
    from app.analysis.commit_analyzer import analyze_branch
    analyze_branch(job["project_id"], job["branch"],
                   progress_cb=lambda pct, d: queue.update_progress(job["id"], pct, d))


def handle_security_scan(job: dict) -> None:
    from app.security.scanner import scan_branch
    scan_branch(job["project_id"], job["branch"],
                progress_cb=lambda pct, d: queue.update_progress(job["id"], pct, d))
    audit("security_scan", project=job["project_id"], branch=job["branch"])


def handle_period_report(job: dict) -> None:
    from app.analytics.period_report import build_period_report
    payload = json.loads(job["payload"]) if job["payload"] else {}
    build_period_report(job["project_id"], job["branch"], payload.get("range", "30d"))


def handle_contributor_report(job: dict) -> None:
    from app.analytics.contributor import build_contributor_report
    payload = json.loads(job["payload"]) if job["payload"] else {}
    build_contributor_report(job["project_id"], job["branch"], payload.get("mode", "log"))


def handle_wiki_gen(job: dict) -> None:
    from app.wiki.generator import generate_wiki
    generate_wiki(job["project_id"], job["branch"])


# --------------------------------------------------------------------------- #
# 分支同步 / 项目统计辅助
# --------------------------------------------------------------------------- #
def _sync_branches(project_id: str) -> None:
    from app.git import repo
    p = _project(project_id)
    default = p.get("default_branch") or repo.default_branch(project_id)
    remote = repo.list_remote_branches(project_id)
    conn = get_conn()
    try:
        for b in remote:
            is_def = 1 if b.name == default else 0
            existing = conn.execute(
                "SELECT id, whitelisted FROM branches WHERE project_id=? AND name=?",
                (project_id, b.name)).fetchone()
            wl = 1 if is_def else (existing["whitelisted"] if existing else 0)
            conn.execute("""
                INSERT INTO branches(project_id,name,whitelisted,is_default,last_commit,
                                     last_commit_msg,author,committed_at,indexed)
                VALUES (?,?,?,?,?,?,?,?,COALESCE((SELECT indexed FROM branches
                        WHERE project_id=? AND name=?),0))
                ON CONFLICT(project_id,name) DO UPDATE SET
                    last_commit=excluded.last_commit, last_commit_msg=excluded.last_commit_msg,
                    author=excluded.author, committed_at=excluded.committed_at,
                    is_default=excluded.is_default,
                    whitelisted=MAX(branches.whitelisted, excluded.is_default)
            """, (project_id, b.name, wl, is_def, b.sha, b.subject, b.author,
                  b.committed_at, project_id, b.name))
        if default:
            conn.execute("UPDATE projects SET default_branch=? WHERE id=?",
                         (default, project_id))
        conn.commit()
    finally:
        conn.close()


def _whitelisted_branches(project_id: str) -> list[str]:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT name FROM branches WHERE project_id=? AND whitelisted=1",
                           (project_id,))
        return [r["name"] for r in cur.fetchall()]
    finally:
        conn.close()


def _mark_branch_indexed(project_id: str, branch: str) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE branches SET indexed=1, graph_version=graph_version+1, "
                     "last_indexed_at=datetime('now') WHERE project_id=? AND name=?",
                     (project_id, branch))
        conn.commit()
    finally:
        conn.close()


def _set_status(project_id: str, status: str, progress: int) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE projects SET status=?, index_progress=? WHERE id=?",
                     (status, progress, project_id))
        conn.commit()
    finally:
        conn.close()


def _update_project_stats(project_id: str) -> None:
    """汇总图谱模块/文件/LOC 到 projects 表。"""
    from app.parsing.graph_store import GraphStore
    p = _project(project_id)
    default = p.get("default_branch")
    if not default:
        return
    try:
        gs = GraphStore(project_id, default)
        files = gs.all_files()
        loc = sum(f["loc"] for f in files)
        mods = len(gs.modules())
        gs.close()
        conn = get_conn()
        conn.execute("UPDATE projects SET files=?, loc=?, last_indexed_at=datetime('now') "
                     "WHERE id=?", (len(files), loc, project_id))
        conn.commit()
        conn.close()
        log.info("project %s stats: %d files, %d loc, %d modules", project_id,
                 len(files), loc, mods)
    except FileNotFoundError:
        pass


JOB_HANDLERS = {
    "fetch": handle_fetch,
    "index_build": handle_index_build,
    "index_incremental": handle_index_incremental,
    "commit_analyze": handle_commit_analyze,
    "security_scan": handle_security_scan,
    "period_report": handle_period_report,
    "contributor_report": handle_contributor_report,
    "wiki_gen": handle_wiki_gen,
}
