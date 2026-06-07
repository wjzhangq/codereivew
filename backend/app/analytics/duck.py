"""analytics/duck.py — DuckDB OLAP 查询引擎

attach meta.sqlite 只读 + 读 Parquet。非持久库,是同一份数据上的查询引擎。
"""
from __future__ import annotations

from contextlib import contextmanager

import duckdb

from app.core.config import get_settings


@contextmanager
def duck():
    """打开 DuckDB,attach meta.sqlite 只读。"""
    s = get_settings()
    con = duckdb.connect(":memory:")
    try:
        con.execute("INSTALL sqlite; LOAD sqlite;")
        con.execute(f"ATTACH '{s.storage.meta_db}' AS meta (TYPE sqlite, READ_ONLY);")
        yield con
    finally:
        con.close()
