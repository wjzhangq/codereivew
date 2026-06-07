"""tests/test_pipeline.py — M0 解析流水线 + M2 commit 分析 E2E"""
import shutil

from app.db.session import get_conn
from app.git.repo import bare_path


def _register(pid, repo_path):
    conn = get_conn()
    conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    conn.execute("INSERT INTO projects(id,name,git_url,default_branch,status) VALUES (?,?,?,?,?)",
                 (pid, pid, repo_path, "main", "pending"))
    conn.commit()
    conn.close()


def test_index_build_pipeline(test_repo):
    pid = "pipe-test"
    b = bare_path(pid)
    if b.parent.exists():
        shutil.rmtree(b.parent)
    _register(pid, test_repo)

    from app.queue.handlers import handle_index_build
    handle_index_build({"id": 1, "project_id": pid, "branch": None})

    conn = get_conn()
    brs = conn.execute("SELECT name,whitelisted,is_default FROM branches WHERE project_id=?",
                       (pid,)).fetchall()
    proj = conn.execute("SELECT files,status FROM projects WHERE id=?", (pid,)).fetchone()
    conn.close()

    assert any(b["is_default"] and b["whitelisted"] for b in brs)  # 默认分支强制纳入
    assert proj["files"] >= 1
    assert proj["status"] == "active"

    from app.parsing.graph_store import GraphStore
    gs = GraphStore(pid, "main")
    assert len(gs.modules()) >= 1
    gs.close()


def test_commit_analysis_drift(test_repo):
    pid = "ca-test"
    b = bare_path(pid)
    if b.parent.exists():
        shutil.rmtree(b.parent)
    _register(pid, test_repo)

    from app.queue.handlers import handle_index_build
    handle_index_build({"id": 1, "project_id": pid, "branch": None})

    from app.queue.handlers import handle_commit_analyze
    handle_commit_analyze({"id": 2, "project_id": pid, "branch": "main"})

    conn = get_conn()
    rows = conn.execute("SELECT commit_sha,raw_msg,msg_drift FROM commit_analysis WHERE project_id=?",
                        (pid,)).fetchall()
    conn.close()
    assert len(rows) == 2  # 2 个 commit
    # 'wip' 这种文不对题应被标记 drift
    wip = [r for r in rows if r["raw_msg"] == "wip"]
    assert wip and wip[0]["msg_drift"] == 1
