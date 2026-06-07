"""parsing/chunker.py — 代码切块

按 signature_plus_body 粒度切块,带 module/file 元数据。
引擎就位后复用其 tree-sitter 节点;此处先用轻量行级/函数级启发式切块,
保证 M0 向量流水线可跑通。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from app.git.worktree import worktree_path
from app.parsing.graph_store import GraphStore

# 函数/类定义起始的多语言启发式
_DEF_RE = re.compile(
    r"^\s*(def |class |func |function |fn |public |private |export |async )",
)


@dataclass
class Chunk:
    file: str
    module: str
    sha256: str
    content: str
    start_line: int


def _module_map(project_id: str, branch: str) -> dict[str, str]:
    try:
        gs = GraphStore(project_id, branch)
        m = {f["path"]: f["module"] for f in gs.all_files()}
        gs.close()
        return m
    except FileNotFoundError:
        return {}


def chunk_file(path: Path, rel: str, module: str, max_lines: int = 80) -> list[Chunk]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    lines = text.splitlines()
    chunks: list[Chunk] = []
    buf: list[str] = []
    start = 1
    for i, line in enumerate(lines, 1):
        if _DEF_RE.match(line) and buf and len(buf) >= 3:
            _flush(chunks, buf, rel, module, start)
            buf, start = [], i
        buf.append(line)
        if len(buf) >= max_lines:
            _flush(chunks, buf, rel, module, start)
            buf, start = [], i + 1
    if buf:
        _flush(chunks, buf, rel, module, start)
    return chunks


def _flush(chunks: list[Chunk], buf: list[str], rel: str, module: str, start: int):
    content = "\n".join(buf).strip()
    if not content:
        return
    sha = hashlib.sha256(content.encode()).hexdigest()
    chunks.append(Chunk(file=rel, module=module, sha256=sha,
                        content=content, start_line=start))


def chunk_repo(project_id: str, branch: str) -> list[Chunk]:
    wt = worktree_path(project_id, branch)
    mmap = _module_map(project_id, branch)
    code_ext = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
                ".rb", ".kt", ".swift", ".php", ".c", ".cpp", ".h", ".vue"}
    out: list[Chunk] = []
    for f in wt.rglob("*"):
        if not f.is_file() or f.suffix not in code_ext or ".git" in f.parts:
            continue
        rel = str(f.relative_to(wt))
        out.extend(chunk_file(f, rel, mmap.get(rel, "root")))
    return out
