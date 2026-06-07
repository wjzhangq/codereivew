"""auth/users.py — 本地账号 CRUD

admin 来自 config 引导创建;管理员添加/禁用普通用户、按项目授权。
"""
from __future__ import annotations

import json
import uuid

from app.core.config import get_settings
from app.core.logging import audit, get_logger
from app.core.security import hash_password, verify_password
from app.db.session import get_conn

log = get_logger("auth.users")


def bootstrap_admin() -> None:
    """首启从 config 引导创建 admin(幂等)。"""
    s = get_settings()
    admin = s.auth.admin
    conn = get_conn()
    try:
        existing = conn.execute("SELECT id FROM users WHERE username=?",
                               (admin.username,)).fetchone()
        if existing:
            return
        pwd_hash = admin.password_hash
        if not pwd_hash and admin.password:
            pwd_hash = hash_password(admin.password)
        if not pwd_hash:
            log.warning("admin 密码未配置(ADMIN_PASSWORD_HASH / password),跳过引导")
            return
        conn.execute(
            "INSERT INTO users(id,username,name,password_hash,role) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4())[:8], admin.username, "系统管理员", pwd_hash, "admin"))
        conn.commit()
        log.info("bootstrapped admin user: %s", admin.username)
    finally:
        conn.close()


def authenticate(username: str, password: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE username=? AND disabled=0",
                          (username,)).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        conn.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (row["id"],))
        conn.commit()
        return {"id": row["id"], "username": row["username"], "name": row["name"],
                "role": row["role"]}
    finally:
        conn.close()


def create_user(username: str, password: str, name: str, role: str,
                projects: list[str] | None = None) -> dict:
    uid = str(uuid.uuid4())[:8]
    conn = get_conn()
    try:
        conn.execute("INSERT INTO users(id,username,name,password_hash,role) VALUES (?,?,?,?,?)",
                     (uid, username, name, hash_password(password), role))
        for pid in (projects or []):
            conn.execute("INSERT OR IGNORE INTO project_access(user_id,project_id) VALUES (?,?)",
                         (uid, pid))
        conn.commit()
        audit("create_user", username=username, role=role)
        return {"id": uid, "username": username, "name": name, "role": role}
    finally:
        conn.close()


def set_disabled(user_id: str, disabled: bool) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET disabled=? WHERE id=?", (int(disabled), user_id))
        conn.commit()
        audit("set_user_disabled", user=user_id, disabled=disabled)
    finally:
        conn.close()


def set_access(user_id: str, project_ids: list[str]) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM project_access WHERE user_id=?", (user_id,))
        for pid in project_ids:
            conn.execute("INSERT OR IGNORE INTO project_access(user_id,project_id) VALUES (?,?)",
                         (user_id, pid))
        conn.commit()
        audit("set_access", user=user_id, projects=len(project_ids))
    finally:
        conn.close()


def list_users() -> list[dict]:
    conn = get_conn()
    try:
        users = [dict(r) for r in conn.execute("SELECT * FROM users").fetchall()]
        for u in users:
            if u["role"] == "admin":
                u["projects"] = "全部"
            else:
                rows = conn.execute("SELECT project_id FROM project_access WHERE user_id=?",
                                   (u["id"],)).fetchall()
                u["projects"] = [r["project_id"] for r in rows]
            u.pop("password_hash", None)
            u["disabled"] = bool(u["disabled"])
        return users
    finally:
        conn.close()


def user_can_access(user: dict, project_id: str) -> bool:
    if user.get("role") == "admin":
        return True
    conn = get_conn()
    try:
        row = conn.execute("SELECT 1 FROM project_access WHERE user_id=? AND project_id=?",
                          (user["id"], project_id)).fetchone()
        return row is not None
    finally:
        conn.close()
