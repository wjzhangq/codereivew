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


def _connect(path: str, *, read_only: bool = False) -> sqlite3.Connection:
    """打开 meta.sqlite 连接。

    锁避免要点(见 db/README):
    - WAL:读写互不阻塞,单写者串行。
    - busy_timeout=30s:遇 SQLITE_BUSY 自动重试而非立即报错。
    - synchronous=NORMAL:WAL 下安全,缩短每次写的 fsync/持锁窗口。
    - read_only=True:以 mode=ro 打开 + query_only,只读路径永远拿不到写锁,
      不会与写者互锁,也不会触发 'read-only database' 类误用。
    """
    if read_only:
        # URI 模式只读打开:即便文件可写,本连接也不会获取写锁。
        uri = f"file:{Path(path).as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA query_only=ON")
        return conn

    conn = sqlite3.connect(path, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def get_conn() -> sqlite3.Connection:
    """获取 meta.sqlite 读写连接。调用方负责 commit/close 或用 with 块。

    注意:SQLite 是单写者。写完务必尽快 commit+close,不要在持有此连接期间
    跑 git / LLM / 网络等慢操作,否则会长期占用写锁导致其它写者超时。
    """
    s = get_settings()
    Path(s.storage.meta_db).parent.mkdir(parents=True, exist_ok=True)
    return _connect(s.storage.meta_db)


def get_conn_ro() -> sqlite3.Connection:
    """获取 meta.sqlite 只读连接,供 API / 查询路径使用。

    只读连接不参与写锁竞争 —— API 高并发读不会阻塞 worker 写,
    worker 写也不会让 API 读报 'database is locked'。
    """
    s = get_settings()
    return _connect(s.storage.meta_db, read_only=True)


def recover_locks() -> None:
    """启动时自愈:清理 git 残留锁 + WAL checkpoint。

    场景:worker 被 kill -9 / OOM 后留下 index.lock,下次 git worktree add 会
    报 "Another git process seems to be running"。SQLite WAL/SHM 不能手删(正
    常重连即自愈),但做一次 TRUNCATE checkpoint 能回收 WAL 空间并验证库完整。
    """
    import glob
    s = get_settings()

    # 1) 清 git index.lock(repos 下所有 bare/worktree)
    pattern = str(Path(s.storage.repos_dir) / "**" / "index.lock")
    for lock in glob.glob(pattern, recursive=True):
        try:
            Path(lock).unlink()
            log.warning("removed stale git lock: %s", lock)
        except OSError:
            pass

    # 2) WAL checkpoint — 回收 WAL 空间,验证数据库完整性
    try:
        conn = sqlite3.connect(s.storage.meta_db, timeout=5.0)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        log.info("WAL checkpoint completed for meta.sqlite")
    except Exception as e:  # noqa: BLE001
        log.warning("WAL checkpoint skipped: %s", e)


def init_db() -> None:
    """首启初始化 schema(幂等)+ 崩溃自愈。"""
    recover_locks()
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
    """写事务上下文:with tx() as conn: ...

    默认 immediate=True:进入即 BEGIN IMMEDIATE 抢写锁,避免两个连接
    "先读后升级写" 互相等待造成的真死锁(SQLITE_BUSY 升级死锁)。
    纯读场景请用 get_conn_ro(),不要用本类。
    """

    def __init__(self, immediate: bool = True):
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
