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

    def close(self) -> None:
        self.db.close()

    # ---------- 模块 / 边 ---------- #
    def modules(self) -> list[Module]:
        cur = self.db.execute("SELECT * FROM modules")
        return [Module(
            id=r["id"], name=r["name"], cat=r["cat"],
            files=r["files"], loc=r["loc"],
            x=r["x"], y=r["y"], health=r["health"],
            churn=r.get("churn") if hasattr(r, "get") else "med",
            description=r.get("description") if hasattr(r, "get") else "",
        ) for r in cur.fetchall()]

    def edges(self) -> list[tuple[str, str]]:
        cur = self.db.execute("SELECT src, dst FROM module_edges")
        return [(r["src"], r["dst"]) for r in cur.fetchall()]

    def graph_info(self) -> GraphInfo:
        return GraphInfo(modules=self.modules(), edges=self.edges())

    # ---------- blast-radius ---------- #
    def blast_radius(self, symbol_or_module: str) -> list[str]:
        """返回直接被影响的符号/模块 id 列表。"""
        # 引擎原生 blast-radius;fallback 按 module_edges 1-hop
        try:
            cur = self.db.execute(
                "SELECT dst FROM edges WHERE src=? AND type='depends'",
                (symbol_or_module,))
            return [r["dst"] for r in cur.fetchall()]
        except Exception:
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
        cur = self.db.execute(
            f"SELECT DISTINCT module FROM files WHERE path IN ({ph})", file_paths)
        return [r["module"] for r in cur.fetchall() if r["module"]]

    # ---------- 文件列表 ---------- #
    def all_files(self) -> list[dict]:
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
