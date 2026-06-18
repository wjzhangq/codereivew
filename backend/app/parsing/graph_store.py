"""parsing/graph_store.py — **只读**图谱 SQLite 查询封装

所有图谱查询都走这里(模块/社区/边/blast-radius/detect_changes)。
Schema 字段以 engine.py fallback 为初始;引擎 spike 后按真实 schema 更新。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.core.logging import get_logger
from app.parsing.engine import graph_db_path

log = get_logger("parsing.graph_store")


@dataclass
class Module:
    id: str
    name: str
    cat: str
    files: int
    loc: int
    x: float
    y: float
    health: int
    churn: str = "low"
    description: str = ""
    findings: int = 0
    owner: str = ""


@dataclass
class GraphInfo:
    modules: list[Module] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)


class GraphStore:
    """只读图谱封装:一个实例对应一个 (project, branch)。"""

    def __init__(self, project_id: str, branch: str):
        path = graph_db_path(project_id, branch)
        if not path.exists():
            raise FileNotFoundError(f"图谱不存在: {path}")
        self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.db.row_factory = sqlite3.Row
        # Detect engine schema (communities/nodes) vs fallback schema (modules).
        tables = {r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self._engine_schema = "communities" in tables and "modules" not in tables

    def close(self) -> None:
        self.db.close()

    # ---------- 模块 / 边 ---------- #
    def modules(self) -> list[Module]:
        if self._engine_schema:
            cur = self.db.execute(
                "SELECT id, name, cohesion, size, description FROM communities WHERE level=0")
            rows = cur.fetchall()
            n = max(len(rows), 1)
            import math
            result = []
            for i, r in enumerate(rows):
                ang = 2 * math.pi * i / n
                result.append(Module(
                    id=str(r["id"]), name=r["name"] or f"cluster-{r['id']}",
                    cat="core", files=0, loc=r["size"] or 0,
                    x=50 + 32 * math.cos(ang), y=50 + 32 * math.sin(ang),
                    health=max(0, min(100, int((r["cohesion"] or 0) * 100))),
                    description=r["description"] or "",
                ))
            return result
        cur = self.db.execute("SELECT * FROM modules")
        return [Module(
            id=r["id"], name=r["name"], cat=r["cat"],
            files=r["files"], loc=r["loc"],
            x=r["x"], y=r["y"], health=r["health"],
            churn=r.get("churn") if hasattr(r, "get") else "med",
            description=r.get("description") if hasattr(r, "get") else "",
        ) for r in cur.fetchall()]

    def edges(self) -> list[tuple[str, str]]:
        if self._engine_schema:
            # communities don't have explicit cross-edges in this schema
            return []
        cur = self.db.execute("SELECT src, dst FROM module_edges")
        return [(r["src"], r["dst"]) for r in cur.fetchall()]

    def graph_info(self) -> GraphInfo:
        return GraphInfo(modules=self.modules(), edges=self.edges())

    # ---------- blast-radius ---------- #
    def blast_radius(self, symbol_or_module: str) -> list[str]:
        """返回直接被影响的符号/模块 id 列表。"""
        if self._engine_schema:
            # 引擎 schema:edges(source_qualified -> target_qualified),双向 1-hop
            cur = self.db.execute(
                "SELECT target_qualified AS x FROM edges WHERE source_qualified=?",
                (symbol_or_module,))
            ids = [r["x"] for r in cur.fetchall()]
            cur2 = self.db.execute(
                "SELECT source_qualified AS x FROM edges WHERE target_qualified=?",
                (symbol_or_module,))
            ids += [r["x"] for r in cur2.fetchall()]
            return list(set(ids))
        # fallback schema:按 module_edges 1-hop
        cur = self.db.execute(
            "SELECT dst FROM module_edges WHERE src=?", (symbol_or_module,))
        ids = [r["dst"] for r in cur.fetchall()]
        cur2 = self.db.execute(
            "SELECT src FROM module_edges WHERE dst=?", (symbol_or_module,))
        ids += [r["src"] for r in cur2.fetchall()]
        return list(set(ids))

    # ---------- 受影响模块(commit 分析用) ---------- #
    def modules_for_files(self, file_paths: list[str]) -> list[str]:
        """根据文件路径判断涉及哪些模块。"""
        if not file_paths:
            return []
        ph = ",".join("?" * len(file_paths))
        if self._engine_schema:
            cur = self.db.execute(
                f"SELECT DISTINCT community_id FROM nodes "
                f"WHERE file_path IN ({ph}) AND community_id IS NOT NULL",
                file_paths)
            return [str(r["community_id"]) for r in cur.fetchall()]
        cur = self.db.execute(
            f"SELECT DISTINCT module FROM files WHERE path IN ({ph})", file_paths)
        return [r["module"] for r in cur.fetchall() if r["module"]]

    # ---------- 文件列表 ---------- #
    def all_files(self) -> list[dict]:
        if self._engine_schema:
            # 引擎 schema 无 files 表;从 nodes 派生(path/module/sha,loc 不可得置 0)
            cur = self.db.execute(
                "SELECT file_path, "
                "MAX(community_id) AS community_id, MAX(file_hash) AS file_hash "
                "FROM nodes GROUP BY file_path")
            return [{"path": r["file_path"],
                     "module": str(r["community_id"]) if r["community_id"] is not None else "",
                     "loc": 0,
                     "sha256": r["file_hash"] or ""} for r in cur.fetchall()]
        cur = self.db.execute("SELECT path, module, loc, sha256 FROM files")
        return [dict(r) for r in cur.fetchall()]

    # ---------- detect_changes ---------- #
    def detect_changes(self, changed_files: list[str]) -> dict:
        """对比变更文件与图谱,返回受影响模块与爆炸半径。"""
        affected_modules = self.modules_for_files(changed_files)
        radius: set[str] = set()
        for m in affected_modules:
            radius.update(self.blast_radius(m))
        return {"affected_modules": affected_modules,
                "blast_radius": list(radius - set(affected_modules))}
