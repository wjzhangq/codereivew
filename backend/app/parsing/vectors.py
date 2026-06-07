"""parsing/vectors.py — sqlite-vec 向量库

库:storage/vectors/<project_id>.sqlite,按 (project,branch) 分区。
检索先用图谱 blast-radius / 模块元数据预过滤,再 KNN(控扫描量)。
embedding 维度由 config 锁定;换模型 = 全量重嵌。
SHA-256 复用:未变更 chunk 不重嵌。
"""
from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.parsing.chunker import Chunk

log = get_logger("parsing.vectors")

try:
    import sqlite_vec  # type: ignore
    _VEC_AVAILABLE = True
except Exception:  # noqa: BLE001
    _VEC_AVAILABLE = False


def _vec_path(project_id: str) -> Path:
    s = get_settings()
    p = Path(s.storage.vectors_dir) / f"{project_id}.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _serialize(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


class VectorStore:
    def __init__(self, project_id: str, dim: int | None = None):
        self.project_id = project_id
        self.dim = dim or get_settings().models.embedding["default"].dim or 1024
        self.db = sqlite3.connect(_vec_path(project_id), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        if _VEC_AVAILABLE:
            self.db.enable_load_extension(True)
            sqlite_vec.load(self.db)
            self.db.enable_load_extension(False)
        self._init_schema()

    def _init_schema(self) -> None:
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch TEXT, file TEXT, module TEXT, sha256 TEXT,
                content TEXT, start_line INTEGER,
                UNIQUE(branch, sha256)
            )""")
        if _VEC_AVAILABLE:
            self.db.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
                f"USING vec0(chunk_id INTEGER PRIMARY KEY, embedding float[{self.dim}])")
        else:
            # 回落:存原始浮点 blob,用 Python 暴力 KNN
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS vec_chunks (
                    chunk_id INTEGER PRIMARY KEY, embedding BLOB)""")
        self.db.commit()

    def existing_shas(self, branch: str) -> set[str]:
        cur = self.db.execute("SELECT sha256 FROM chunks WHERE branch=?", (branch,))
        return {r["sha256"] for r in cur.fetchall()}

    def upsert_chunks(self, branch: str, chunks: list[Chunk],
                      embeddings: list[list[float]]) -> int:
        """写入 chunk + embedding。调用方应先用 existing_shas 过滤已有 chunk。"""
        n = 0
        for ch, emb in zip(chunks, embeddings):
            cur = self.db.execute(
                "INSERT OR IGNORE INTO chunks(branch,file,module,sha256,content,start_line)"
                " VALUES (?,?,?,?,?,?)",
                (branch, ch.file, ch.module, ch.sha256, ch.content, ch.start_line))
            if cur.rowcount == 0:
                continue
            cid = cur.lastrowid
            if _VEC_AVAILABLE:
                self.db.execute("INSERT INTO vec_chunks(chunk_id, embedding) VALUES (?,?)",
                                (cid, _serialize(emb)))
            else:
                self.db.execute("INSERT INTO vec_chunks(chunk_id, embedding) VALUES (?,?)",
                                (cid, _serialize(emb)))
            n += 1
        self.db.commit()
        return n

    def knn(self, query_vec: list[float], branch: str | None = None,
            modules: list[str] | None = None, k: int = 10) -> list[dict]:
        """KNN。modules 预过滤控扫描量(plan §2)。"""
        if _VEC_AVAILABLE:
            return self._knn_vec(query_vec, branch, modules, k)
        return self._knn_bruteforce(query_vec, branch, modules, k)

    def _knn_vec(self, q, branch, modules, k):
        # sqlite-vec MATCH;预过滤通过 join chunks 实现
        rows = self.db.execute(
            f"""SELECT c.file, c.module, c.content, c.start_line, v.distance
                FROM vec_chunks v JOIN chunks c ON c.id = v.chunk_id
                WHERE v.embedding MATCH ? AND k = ?
                {"AND c.branch = ?" if branch else ""}
                {"AND c.module IN (%s)" % ",".join("?"*len(modules)) if modules else ""}
                ORDER BY v.distance""",
            tuple(x for x in [_serialize(q), k, *( [branch] if branch else [] ),
                              *(modules or [])])).fetchall()
        return [dict(r) for r in rows]

    def _knn_bruteforce(self, q, branch, modules, k):
        import math
        cond, params = [], []
        if branch:
            cond.append("c.branch=?"); params.append(branch)
        if modules:
            cond.append("c.module IN (%s)" % ",".join("?" * len(modules)))
            params += modules
        where = ("WHERE " + " AND ".join(cond)) if cond else ""
        rows = self.db.execute(
            f"""SELECT c.file, c.module, c.content, c.start_line, v.embedding
                FROM vec_chunks v JOIN chunks c ON c.id=v.chunk_id {where}""",
            params).fetchall()
        qn = math.sqrt(sum(x * x for x in q)) or 1.0
        scored = []
        for r in rows:
            emb = struct.unpack(f"{len(q)}f", r["embedding"][:len(q) * 4])
            dot = sum(a * b for a, b in zip(q, emb))
            en = math.sqrt(sum(x * x for x in emb)) or 1.0
            scored.append((1 - dot / (qn * en), r))
        scored.sort(key=lambda t: t[0])
        return [{"file": r["file"], "module": r["module"], "content": r["content"],
                 "start_line": r["start_line"], "distance": d} for d, r in scored[:k]]

    def close(self):
        self.db.close()
