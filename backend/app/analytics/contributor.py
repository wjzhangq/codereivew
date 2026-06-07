"""analytics/contributor.py — 用户汇总(by_log / by_blame 双口径)

by_log:周期内谁改了什么(活动量/LOC)。
by_blame:当前快照谁拥有代码(ownership)。
经 identities 把作者映射到平台账号。
"""
from __future__ import annotations

import datetime as dt
import json

from app.core.logging import get_logger
from app.db.session import get_conn
from app.git import history

log = get_logger("analytics.contributor")


def _resolve_identity(project_id: str, email: str, name: str) -> dict:
    """把 git 作者映射到平台账号;解析不到回落 email 并标 unverified。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT username, name, verified FROM identities "
            "WHERE project_id=? AND emails LIKE ?",
            (project_id, f'%{email}%')).fetchone()
        if row:
            return {"id": row["username"], "name": row["name"],
                    "verified": bool(row["verified"])}
    finally:
        conn.close()
    return {"id": email, "name": name or email, "verified": False}


def build_contributor_report(project_id: str, branch: str | None, mode: str) -> dict:
    conn = get_conn()
    try:
        p = conn.execute("SELECT default_branch FROM projects WHERE id=?",
                         (project_id,)).fetchone()
    finally:
        conn.close()
    branch = branch or (p["default_branch"] if p else "main")

    if mode == "blame":
        report = _by_blame(project_id, branch)
    else:
        report = _by_log(project_id, branch)
    _save(project_id, mode, report)
    return report


def _by_log(project_id: str, branch: str) -> dict:
    until = dt.datetime.now(dt.timezone.utc).date().isoformat()
    since = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=30)).isoformat()
    commits = history.log_numstat(project_id, branch, since, until)
    agg: dict[str, dict] = {}
    for c in commits:
        ident = _resolve_identity(project_id, c["email"], c["author"])
        a = agg.setdefault(ident["id"], {
            "id": ident["id"], "name": ident["name"], "verified": ident["verified"],
            "commits": 0, "add": 0, "del": 0, "modules": {}})
        a["commits"] += 1
        for f in c["files"]:
            a["add"] += f["add"]
            a["del"] += f["del"]
            mod = f["file"].split("/")[1] if f["file"].count("/") >= 1 else "root"
            a["modules"][mod] = a["modules"].get(mod, 0) + 1
    total_add = sum(a["add"] for a in agg.values()) or 1
    out = []
    for a in sorted(agg.values(), key=lambda x: -x["commits"]):
        top = sorted(a["modules"].items(), key=lambda kv: -kv[1])[:3]
        out.append({**a, "modules": [m for m, _ in top],
                    "ownPct": round(100 * a["add"] / total_add)})
    return {"mode": "log", "contributors": out}


def _by_blame(project_id: str, branch: str) -> dict:
    from app.parsing.graph_store import GraphStore
    try:
        gs = GraphStore(project_id, branch)
        files = [f["path"] for f in gs.all_files()]
        gs.close()
    except FileNotFoundError:
        files = []
    owners = history.blame_ownership(project_id, branch, files[:200])  # 限规模
    total = sum(owners.values()) or 1
    out = []
    for email, lines in sorted(owners.items(), key=lambda kv: -kv[1]):
        ident = _resolve_identity(project_id, email, email)
        out.append({"id": ident["id"], "name": ident["name"],
                    "verified": ident["verified"], "lines": lines,
                    "ownPct": round(100 * lines / total)})
    return {"mode": "blame", "contributors": out}


def _save(project_id: str, mode: str, payload: dict) -> None:
    conn = get_conn()
    try:
        conn.execute("INSERT INTO reports(project_id,type,range_spec,payload) VALUES (?,?,?,?)",
                     (project_id, f"contributor_{mode}", "30d",
                      json.dumps(payload, ensure_ascii=False)))
        conn.commit()
    finally:
        conn.close()
