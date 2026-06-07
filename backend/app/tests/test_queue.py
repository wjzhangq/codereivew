from app.db.session import get_conn
from app.queue import queue

def _clear():
    conn=get_conn(); conn.execute("DELETE FROM jobs"); conn.commit(); conn.close()

def _proj(pid="qtest"):
    conn=get_conn()
    conn.execute("INSERT OR IGNORE INTO projects(id,name,git_url) VALUES (?,?,?)",(pid,pid,"/tmp/x"))
    conn.commit(); conn.close()
    return pid

def test_dedup():
    _clear(); pid=_proj()
    assert queue.enqueue("fetch",pid,priority=10) > 0
    assert queue.enqueue("fetch",pid,priority=10) == -1

def test_write_serial():
    _clear(); pid=_proj()
    queue.enqueue("fetch",pid,priority=10)
    queue.enqueue("index_build",pid,priority=5)
    c1=queue.claim("w1"); assert c1 and c1["type"]=="fetch"
    assert queue.claim("w2") is None
    queue.complete(c1["id"])
    c3=queue.claim("w2"); assert c3 and c3["type"]=="index_build"

def test_retry():
    _clear(); pid=_proj()
    queue.enqueue("fetch",pid,priority=10)
    job=queue.claim("w1")
    queue.fail(job["id"],"boom")
    conn=get_conn()
    r=conn.execute("SELECT status,attempts FROM jobs WHERE id=?",(job["id"],)).fetchone(); conn.close()
    assert r["status"]=="queued" and r["attempts"]==1
