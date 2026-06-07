"""parsing/engine.py — code-review-graph 引擎封装

⚠️ M0 spike(dev.md §M0.4):确认引擎安装方式、Python 入口、输出图谱 SQLite schema。
本模块用适配器模式:
  - 若 code-review-graph 已安装 → 调其 API 跑解析,写 graphs/<pid>/<branch>.sqlite。
  - 否则 → 回落到内置最小解析(tree-sitter 不可用时用 git ls-files + 目录启发式),
    保证 M0 流水线可端到端跑通,待引擎就位后只换本文件实现。

**禁用引擎自带 embedding**:embedding 由 parsing/vectors.py + llm/embedder.py 负责。
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.git.worktree import worktree_path

log = get_logger("parsing.engine")

try:  # 引擎就位后启用
    import code_review_graph as _crg  # type: ignore
    _ENGINE_AVAILABLE = True
except Exception:  # noqa: BLE001
    _crg = None
    _ENGINE_AVAILABLE = False


def graph_db_path(project_id: str, branch: str) -> Path:
    s = get_settings()
    safe = branch.replace("/", "__")
    p = Path(s.storage.graphs_dir) / project_id / f"{safe}.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def build_graph(project_id: str, branch: str) -> Path:
    """对一个 worktree 跑引擎解析 → 写图谱 SQLite。返回路径。"""
    wt = worktree_path(project_id, branch)
    out = graph_db_path(project_id, branch)
    if _ENGINE_AVAILABLE:
        # ⚠️ 真实调用签名以 spike 笔记为准,例如:
        #   _crg.analyze(repo_path=str(wt), out_db=str(out), embeddings=False)
        log.info("running code-review-graph on %s@%s", project_id, branch)
        _crg.analyze(repo_path=str(wt), out_db=str(out), embeddings=False)  # type: ignore
    else:
        log.warning("code-review-graph 未安装,使用内置最小解析(M0 回落)")
        _fallback_build(wt, out)
    return out


# --------------------------------------------------------------------------- #
# 回落:内置最小图谱(目录即模块的启发式)
# 引擎就位后此函数废弃。schema 故意与引擎产出对齐(见 graph_store 的注释)。
# --------------------------------------------------------------------------- #
_FALLBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS modules (
    id TEXT PRIMARY KEY, name TEXT, cat TEXT, files INTEGER, loc INTEGER,
    x REAL, y REAL, health INTEGER, churn TEXT, description TEXT
);
CREATE TABLE IF NOT EXISTS module_edges (src TEXT, dst TEXT);
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY, name TEXT, kind TEXT, file TEXT, module TEXT,
    start_line INTEGER, end_line INTEGER
);
CREATE TABLE IF NOT EXISTS edges (src TEXT, dst TEXT, type TEXT);
CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, module TEXT, loc INTEGER, sha256 TEXT);
"""

_CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
             ".rb", ".kt", ".swift", ".php", ".c", ".cpp", ".h", ".vue", ".svelte"}
_CAT_HINT = {"core": ["core", "src", "lib"], "api": ["api", "cli", "mcp", "routes"],
             "infra": ["infra", "db", "storage", "client", "embed"],
             "feature": ["feature", "filter", "gov"]}


def _fallback_build(wt: Path, out: Path) -> None:
    out.unlink(missing_ok=True)
    db = sqlite3.connect(out)
    db.executescript(_FALLBACK_SCHEMA)
    mod_loc: dict[str, int] = {}
    mod_files: dict[str, int] = {}
    for f in wt.rglob("*"):
        if not f.is_file() or f.suffix not in _CODE_EXT or ".git" in f.parts:
            continue
        rel = f.relative_to(wt)
        module = rel.parts[1] if len(rel.parts) > 1 and rel.parts[0] in ("src", "lib") \
            else rel.parts[0] if len(rel.parts) > 1 else "root"
        try:
            loc = sum(1 for _ in f.open("rb"))
        except OSError:
            loc = 0
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        db.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?)",
                   (str(rel), module, loc, sha))
        mod_loc[module] = mod_loc.get(module, 0) + loc
        mod_files[module] = mod_files.get(module, 0) + 1
    # 简易布局:圆周排列
    import math
    mods = list(mod_loc.keys())
    for i, m in enumerate(mods):
        ang = 2 * math.pi * i / max(len(mods), 1)
        x = 50 + 32 * math.cos(ang)
        y = 50 + 32 * math.sin(ang)
        cat = next((c for c, hints in _CAT_HINT.items()
                    if any(h in m.lower() for h in hints)), "core")
        db.execute("INSERT OR REPLACE INTO modules VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (m, m, cat, mod_files[m], mod_loc[m], x, y, 80, "med", ""))
    db.commit()
    db.close()
    log.info("fallback graph built: %d modules", len(mods))
