"""parsing/graph_store.py — **只读**图谱查询封装(应用外观层)

引擎可用时,底层直接打开 worktree 内 code-review-graph 的权威库
`<wt>/.code-review-graph/graph.db`,并委托引擎自带的 `code_review_graph.graph.GraphStore`
做查询(communities/edges/files/impact)—— 不再复制一份、不再手写引擎已有的 SQL。
引擎不可用(M0 回落)时,读 engine.py 回落产出的 `modules`/`module_edges`/`files` schema。

外观:`GraphStore(project_id, branch)` + `Module`/`GraphInfo` dataclass。消费者
(api/wiki/handlers/chunker/commit_analyzer/scanner)签名不变。
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.core.logging import get_logger
from app.git.worktree import worktree_path
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
    """只读图谱封装:一个实例对应一个 (project, branch)。

    引擎可用 → 委托 code_review_graph 的 GraphStore(读 worktree 内权威库)。
    回落 → 直接读回落 schema 的 SQLite。
    """

    def __init__(self, project_id: str, branch: str):
        path = graph_db_path(project_id, branch)
        if not path.exists():
            raise FileNotFoundError(f"图谱不存在: {path}")
        self._wt = worktree_path(project_id, branch).resolve()
        # 探测 schema:引擎产出有 communities 且无回落的 modules 表。
        probe = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        tables = {r[0] for r in probe.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        probe.close()
        self._engine_schema = "communities" in tables and "modules" not in tables

        if self._engine_schema:
            from code_review_graph.graph import GraphStore as EngineGraphStore
            # 引擎 GraphStore 自行以合适方式打开 db(只读查询路径)。
            self._engine = EngineGraphStore(str(path))
            self.db = self._engine._conn  # 复用其连接做少量补列查询(communities 富字段)
        else:
            self._engine = None
            self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            self.db.row_factory = sqlite3.Row

    def close(self) -> None:
        if self._engine is not None:
            self._engine.close()
        else:
            self.db.close()

    # ---------- 路径归一:引擎存绝对路径 → 相对 worktree ---------- #
    def _rel(self, p: str) -> str:
        try:
            return str(Path(p).resolve().relative_to(self._wt))
        except (ValueError, OSError):
            return p

    def _file_community_map(self) -> dict[str, int]:
        """引擎 schema 专用:文件(绝对路径) → community_id。

        File 节点本身无 community_id(只有符号有),故按文件下符号的多数社区归票。
        """
        cur = self.db.execute(
            "SELECT file_path, community_id, COUNT(*) AS c FROM nodes "
            "WHERE community_id IS NOT NULL AND kind != 'File' "
            "GROUP BY file_path, community_id")
        best: dict[str, tuple[int, int]] = {}  # path -> (community_id, votes)
        for r in cur.fetchall():
            fp, cid, c = r["file_path"], r["community_id"], r["c"]
            if fp not in best or c > best[fp][1]:
                best[fp] = (cid, c)
        return {fp: cid for fp, (cid, _) in best.items()}

    def _loc_per_community(self) -> dict[int, int]:
        """引擎 schema 专用:按 nodes 表的 line_end - line_start 累加各 community LOC。"""
        cur = self.db.execute(
            "SELECT community_id, SUM(line_end - line_start) AS loc "
            "FROM nodes WHERE community_id IS NOT NULL "
            "AND line_end IS NOT NULL AND line_start IS NOT NULL "
            "AND kind != 'File' GROUP BY community_id")
        return {r["community_id"]: r["loc"] or 0 for r in cur.fetchall()}

    # ---------- 模块 / 边 ---------- #
    def modules(self) -> list[Module]:
        if self._engine_schema:
            # 富字段(size/cohesion/description/dominant_language)在 communities 表 level=0。
            cur = self.db.execute(
                "SELECT id, name, cohesion, size, description, dominant_language "
                "FROM communities WHERE level=0")
            rows = cur.fetchall()
            # 每模块文件数:由文件→社区映射归票统计。
            files_per_cid: dict[int, int] = {}
            for cid in self._file_community_map().values():
                files_per_cid[cid] = files_per_cid.get(cid, 0) + 1
            loc_per_cid = self._loc_per_community()
            n = max(len(rows), 1)
            result = []
            for i, r in enumerate(rows):
                ang = 2 * math.pi * i / n
                result.append(Module(
                    id=str(r["id"]), name=r["name"] or f"cluster-{r['id']}",
                    cat="core", files=files_per_cid.get(r["id"], 0),
                    loc=loc_per_cid.get(r["id"], 0),
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
            # 委托引擎 API:把节点级 edges 按两端 community_id 上卷成社区(模块)间
            # 有向边。过滤同社区/未分配,去重。id 与 modules() 对齐(str(community_id))。
            cids = self._engine.get_all_community_ids()
            seen: set[tuple[str, str]] = set()
            for e in self._engine.get_all_edges():
                sc = cids.get(e.source_qualified)
                dc = cids.get(e.target_qualified)
                if sc is None or dc is None or sc == dc:
                    continue
                seen.add((str(sc), str(dc)))
            return list(seen)
        cur = self.db.execute("SELECT src, dst FROM module_edges")
        return [(r["src"], r["dst"]) for r in cur.fetchall()]

    def graph_info(self) -> GraphInfo:
        return GraphInfo(modules=self.modules(), edges=self.edges())

    # ---------- blast-radius ---------- #
    def blast_radius(self, symbol_or_module: str) -> list[str]:
        """返回直接被影响的符号 qualified_name 列表(双向 1-hop)。"""
        if self._engine_schema:
            # 委托引擎 API:出边目标 + 入边来源。
            ids = set(self._engine.get_outgoing_targets([symbol_or_module]))
            ids |= set(self._engine.get_incoming_sources([symbol_or_module]))
            return list(ids)
        # 回落 schema:按 module_edges 1-hop
        cur = self.db.execute(
            "SELECT dst FROM module_edges WHERE src=?", (symbol_or_module,))
        ids = [r["dst"] for r in cur.fetchall()]
        cur2 = self.db.execute(
            "SELECT src FROM module_edges WHERE dst=?", (symbol_or_module,))
        ids += [r["src"] for r in cur2.fetchall()]
        return list(set(ids))

    # ---------- 受影响模块(commit 分析用) ---------- #
    def modules_for_files(self, file_paths: list[str]) -> list[str]:
        """根据文件路径判断涉及哪些模块(community id)。"""
        if not file_paths:
            return []
        if self._engine_schema:
            # 入参多为相对 worktree;按文件→社区映射(归一两端路径)取命中文件的社区。
            fmap = self._file_community_map()  # 绝对路径 -> community_id
            wanted = set(file_paths) | {str((self._wt / p)) for p in file_paths}
            out: set[str] = set()
            for fp, cid in fmap.items():
                if fp in wanted or self._rel(fp) in file_paths:
                    out.add(str(cid))
            return list(out)
        ph = ",".join("?" * len(file_paths))
        cur = self.db.execute(
            f"SELECT DISTINCT module FROM files WHERE path IN ({ph})", file_paths)
        return [r["module"] for r in cur.fetchall() if r["module"]]

    # ---------- 文件列表 ---------- #
    def all_files(self) -> list[dict]:
        """返回 [{path(相对 worktree), module, loc, sha256}]。

        引擎 schema 无 loc(置 0);path 归一为相对 worktree,使 chunker 的
        path→module 映射可命中(旧实现返回绝对路径,映射恒 miss)。
        """
        if self._engine_schema:
            fmap = self._file_community_map()  # 绝对路径 -> community_id
            out: list[dict] = []
            for fp in self._engine.get_all_files():  # 绝对路径
                cid = fmap.get(fp)
                out.append({
                    "path": self._rel(fp),
                    "module": str(cid) if cid is not None else "",
                    "loc": 0,
                    "sha256": "",
                })
            return out
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
