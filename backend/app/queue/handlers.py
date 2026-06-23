"""queue/handlers.py — 任务处理器

把 git/parsing/analysis/security 各层串成可执行的任务。
"""
from __future__ import annotations

import json

from app.core.logging import audit, get_logger
from app.core.security import decrypt_secret
from app.db.session import get_conn
from app.queue import queue
from app.queue.result import JobResult

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
def handle_fetch(job: dict) -> JobResult:
    from app.git import repo
    p = _project(job["project_id"])
    key = _deploy_key(p)
    repo.clone_mirror(p["git_url"], p["id"], key)
    _sync_branches(p["id"])
    queue.update_progress(job["id"], 100, "fetch 完成")
    return JobResult(produced=1, note="fetch 完成")


def handle_index_build(job: dict) -> JobResult:
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
    if not branches:
        _set_status(pid, "active", 100)
        return JobResult(produced=0, skipped=["无白名单分支(默认分支同步失败?)"],
                         note="无分支可索引")
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
    _enqueue_post_index(pid, branches)
    return JobResult(produced=len(branches), note=f"索引 {len(branches)} 个分支")


def _enqueue_post_index(project_id: str, branches: list[str]) -> None:
    """索引完成后自动串起下游分析链:逐分支 commit 理解 + 安全扫描,项目级 Wiki。

    这是接入仓库后报告/面板有内容的关键 —— 不再等 webhook push 或人工点击。
    周期/贡献报告不在此处入队:它们聚合 commit_analysis,必须等 commit_analyze
    跑完才有数据,否则会因零产出判失败。改由 commit_analyze 完成后串联(见下)。
    """
    for br in branches:
        queue.enqueue("commit_analyze", project_id, branch=br,
                      priority=queue.PRIORITY_BACKFILL, detail=f"自动分析 {br} commits")
        queue.enqueue("security_scan", project_id, branch=br,
                      priority=queue.PRIORITY_BACKFILL, detail=f"自动安全扫描 {br}")
    queue.enqueue("wiki_gen", project_id, priority=queue.PRIORITY_BACKFILL,
                  detail="自动生成 Wiki")


def handle_index_incremental(job: dict) -> JobResult:
    """增量:只重解析/重嵌变更分支。"""
    from app.git import repo, worktree
    from app.parsing import engine
    pid = job["project_id"]
    br = job["branch"]
    p = _project(pid)
    key = _deploy_key(p)
    repo.fetch(pid, key)
    worktree.add_worktree(pid, br)
    engine.build_graph(pid, br)
    _index_vectors(pid, br)  # SHA-256 复用未变更 chunk
    _mark_branch_indexed(pid, br)

    change_note = _detect_branch_changes(pid, br)
    queue.update_progress(job["id"], 100, f"增量索引 {br} 完成")
    return JobResult(produced=1, note=f"增量索引 {br} 完成{change_note}")


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


def _detect_branch_changes(project_id: str, branch: str) -> str:
    """用图谱 detect_changes 分析最新 commit 的影响范围,返回摘要字符串。

    取最近 1 条 commit 的变更文件,查询受影响模块与爆炸半径,写日志。
    无图谱或无 commit 时静默返回空串。
    """
    from app.git.history import list_commits, get_commit_diff
    from app.parsing.graph_store import GraphStore
    try:
        shas = list_commits(project_id, branch, last_count=1)
        if not shas:
            return ""
        diff = get_commit_diff(project_id, shas[0])
        changed_files = [f.file for f in diff.files]
        if not changed_files:
            return ""
        gs = GraphStore(project_id, branch)
        result = gs.detect_changes(changed_files)
        gs.close()
        n_mod = len(result["affected_modules"])
        n_rad = len(result["blast_radius"])
        log.info("detect_changes %s@%s: %d affected modules, blast_radius=%d",
                 project_id, branch, n_mod, n_rad)
        if n_mod:
            return f";影响模块 {n_mod} 个,爆炸半径 {n_rad} 个"
        return ""
    except Exception as e:  # noqa: BLE001
        log.debug("detect_changes 跳过: %s", e)
        return ""



# commit 分析 / 安全扫描 / 报告 / wiki
# --------------------------------------------------------------------------- #
def handle_commit_analyze(job: dict) -> JobResult:
    from app.analysis.commit_analyzer import analyze_branch
    res = analyze_branch(job["project_id"], job["branch"],
                         progress_cb=lambda pct, d: queue.update_progress(job["id"], pct, d))
    # 有 commit 产出后,串联聚合类报告(此时 commit_analysis 已有数据)。
    if res.produced > 0:
        pid = job["project_id"]
        queue.enqueue("period_report", pid, payload={"range": "30d"},
                      priority=queue.PRIORITY_BACKFILL, detail="自动周期报告")
        queue.enqueue("contributor_report", pid, payload={"mode": "log"},
                      priority=queue.PRIORITY_BACKFILL, detail="自动贡献报告(by_log)")
    return res


def handle_security_scan(job: dict) -> JobResult:
    from app.security.scanner import scan_branch
    res = scan_branch(job["project_id"], job["branch"],
                      progress_cb=lambda pct, d: queue.update_progress(job["id"], pct, d))
    audit("security_scan", project=job["project_id"], branch=job["branch"])
    return res


def handle_period_report(job: dict) -> JobResult:
    from app.analytics.period_report import build_period_report
    payload = json.loads(job["payload"]) if job["payload"] else {}
    return build_period_report(job["project_id"], job["branch"], payload.get("range", "30d"))


def handle_contributor_report(job: dict) -> JobResult:
    from app.analytics.contributor import build_contributor_report
    payload = json.loads(job["payload"]) if job["payload"] else {}
    return build_contributor_report(job["project_id"], job["branch"], payload.get("mode", "log"))


def handle_wiki_gen(job: dict) -> JobResult:
    from app.wiki.generator import generate_wiki
    return generate_wiki(job["project_id"], job["branch"])


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
