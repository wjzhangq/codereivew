import shutil
from app.db.session import get_conn
from app.git.repo import bare_path

def _reg(pid, path):
    conn=get_conn()
    conn.execute("DELETE FROM projects WHERE id=?",(pid,))
    conn.execute("INSERT INTO projects(id,name,git_url,default_branch,status) VALUES(?,?,?,?,?)",
                 (pid,pid,path,"main","pending"))
    conn.commit(); conn.close()

def test_index(test_repo):
    pid="pt"
    b=bare_path(pid)
    if b.parent.exists(): shutil.rmtree(b.parent)
    _reg(pid,test_repo)
    from app.queue.handlers import handle_index_build
    handle_index_build({"id":1,"project_id":pid,"branch":None})
    conn=get_conn()
    brs=conn.execute("SELECT * FROM branches WHERE project_id=?",(pid,)).fetchall()
    assert any(r["is_default"] and r["whitelisted"] for r in brs)
    p=conn.execute("SELECT status FROM projects WHERE id=?",(pid,)).fetchone()
    assert p["status"]=="active"
    conn.close()

def test_commit_drift(test_repo):
    pid="cd"
    b=bare_path(pid)
    if b.parent.exists(): shutil.rmtree(b.parent)
    _reg(pid,test_repo)
    from app.queue.handlers import handle_index_build, handle_commit_analyze
    handle_index_build({"id":1,"project_id":pid,"branch":None})
    handle_commit_analyze({"id":2,"project_id":pid,"branch":"main"})
    conn=get_conn()
    rows=conn.execute("SELECT raw_msg,msg_drift FROM commit_analysis WHERE project_id=?",(pid,)).fetchall()
    conn.close()
    assert len(rows)==2
    wip=[r for r in rows if r["raw_msg"]=="wip"]
    assert wip and wip[0]["msg_drift"]==1
