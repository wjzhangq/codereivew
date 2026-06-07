"""tests/test_queue.py — 队列原子领取 + 写类串行 + 去抖"""
from app.db.session import get_conn
from app.queue import queue


def _clear_jobs():
    conn = get_conn()
    conn.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


def _ensure_project(pid="qtest"):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO projects(id,name,git_url) VALUES (?,?,?)",
                 (pid, pid, "/tmp/x"))
    conn.commit()
    conn.close()
    return pid


def test_enqueue_dedup():
    _clear_jobs()
    pid = _ensure_project()
    j1 = queue.enqueue("fetch", pid, priority=10)
    j2 = queue.enqueue("fetch", pid, priority=10)
    assert j1 > 0
    assert j2 == -1  # 去抖合并


def test_write_type_serialized_per_project():
    _clear_jobs()
    pid = _ensure_project()
    queue.enqueue("fetch", pid, priority=10)
    queue.enqueue("index_build", pid, priority=5)
    c1 = queue.claim("w1")
    assert c1 and c1["type"] == "fetch"
    c2 = queue.claim("w2")
    assert c2 is None  # 同 project 写类串行
    queue.complete(c1["id"])
    c3 = queue.claim("w2")
    assert c3 and c3["type"] == "index_build"


def test_retry_backoff():
    _clear_jobs()
    pid = _ensure_project()
    queue.enqueue("fetch", pid, priority=10)
    job = queue.claim("w1")
    queue.fail(job["id"], "boom")
    # attempts < max → 回到 queued(带退避 run_after)
    conn = get_conn()
    row = conn.execute("SELECT status, attempts FROM jobs WHERE id=?", (job["id"],)).fetchone()
    conn.close()
    assert row["status"] == "queued"
    assert row["attempts"] == 1
