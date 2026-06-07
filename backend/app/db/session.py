"""db/session.py — meta.sqlite 连接管理(WAL)+ schema 初始化

单写、可事务、低延迟。所有写都进 SQLite 家族。
sqlite-vec 向量库与图谱库各自单独成库,见 parsing/。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("db")

_SCHEMA = Path(__file__).parent / "schema.sql"


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def get_conn() -> sqlite3.Connection:
    """获取 meta.sqlite 连接。调用方负责 commit/close 或用 with 块。"""
    s = get_settings()
    Path(s.storage.meta_db).parent.mkdir(parents=True, exist_ok=True)
    return _connect(s.storage.meta_db)


def init_db() -> None:
    """首启初始化 schema(幂等)。"""
    conn = get_conn()
    try:
        conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
        cur = conn.execute("SELECT MAX(version) AS v FROM schema_version")
        if cur.fetchone()["v"] is None:
            conn.execute("INSERT INTO schema_version(version) VALUES (1)")
        conn.commit()
        log.info("meta.sqlite schema initialized")
    finally:
        conn.close()


class tx:
    """简单事务上下文:with tx() as conn: ..."""

    def __init__(self, immediate: bool = False):
        self.immediate = immediate

    def __enter__(self) -> sqlite3.Connection:
        self.conn = get_conn()
        if self.immediate:
            self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()
        return False
