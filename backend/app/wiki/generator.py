"""wiki/generator.py — 项目 Wiki 生成

社区模块结构 + 各模块 commit 理解 → LLM 生成模块页 + 总览。
仅对有新 commit 的模块增量刷新(fresh 脉冲点)。
"""
from __future__ import annotations

import json

from app.core.logging import get_logger
from app.db.session import get_conn
from app.llm import client
from app.parsing.graph_store import GraphStore
from app.queue.result import JobResult

log = get_logger("wiki")

_SYSTEM = "你是技术文档作者。基于模块结构与提交理解,生成简洁准确的中文模块文档。"


def generate_wiki(project_id: str, branch: str | None = None) -> JobResult:
    branch = branch or _default_branch(project_id)
    try:
        gs = GraphStore(project_id, branch)
        modules = gs.modules()
        gs.close()
    except FileNotFoundError:
        log.warning("无图谱,跳过 wiki 生成")
        return JobResult(produced=0, skipped=[f"分支 {branch} 无图谱(请先索引)"],
                         note="无法生成 Wiki")

    if not modules:
        return JobResult(produced=0, skipped=["图谱中无模块"], note="无法生成 Wiki")

    n = 0
    # 总览页
    _gen_overview(project_id, modules)
    n += 1
    # 各模块页(仅 fresh 的)
    refreshed = 0
    for m in modules:
        if _has_new_commits(project_id, m.id):
            _gen_module_page(project_id, m)
            n += 1
            refreshed += 1
    log.info("wiki generated/refreshed %d pages for %s", n, project_id)
    note = f"Wiki 生成 {n} 页(总览 + {refreshed} 模块)"
    return JobResult(produced=n, skipped=[], note=note)


def _gen_overview(project_id: str, modules) -> None:
    mod_list = "\n".join(f"- {m.name} ({m.cat}, {m.files} 文件, {m.loc} 行)" for m in modules)
    content = client.chat("wiki", _SYSTEM,
                          f"项目模块列表:\n{mod_list}\n\n请生成项目总览。", max_tokens=1500)
    sections = [{"title": "项目总览", "body": content}]
    _upsert_page(project_id, "overview", "项目总览", "概览", sections, fresh=True)


def _gen_module_page(project_id: str, m) -> None:
    commits = _module_commits(project_id, m.id)
    hist = "\n".join(f"- {c['summary']}" for c in commits[:8])
    content = client.chat("wiki", _SYSTEM,
                          f"模块:{m.name}\n描述:{m.description}\n"
                          f"近期提交理解:\n{hist}\n\n请生成模块文档。", max_tokens=1200)
    group = {"core": "核心模块", "api": "接口", "infra": "基础设施",
             "feature": "功能"}.get(m.cat, "其他")
    sections = [{"title": m.name, "body": content}]
    _upsert_page(project_id, m.id, f"{m.name} 模块", group, sections, fresh=True)


def _has_new_commits(project_id: str, module_id: str) -> bool:
    conn = get_conn()
    try:
        page = conn.execute("SELECT updated_at FROM wiki_pages WHERE project_id=? AND page_key=?",
                           (project_id, module_id)).fetchone()
        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM commit_analysis WHERE project_id=? AND modules LIKE ?"
            + (" AND created_at > ?" if page else ""),
            (project_id, f'%"{module_id}"%', *([page["updated_at"]] if page else [])))
        return cur.fetchone()["n"] > 0 or page is None
    finally:
        conn.close()


def _module_commits(project_id: str, module_id: str) -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT summary, approach FROM commit_analysis WHERE project_id=? AND modules LIKE ? "
            "ORDER BY committed_at DESC LIMIT 10", (project_id, f'%"{module_id}"%'))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _upsert_page(project_id, page_key, title, group, sections, fresh) -> None:
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO wiki_pages(project_id,page_key,title,page_group,sections,fresh,updated_at)
            VALUES (?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(project_id,page_key) DO UPDATE SET
                title=excluded.title, page_group=excluded.page_group,
                sections=excluded.sections, fresh=excluded.fresh, updated_at=datetime('now')
        """, (project_id, page_key, title, group, json.dumps(sections, ensure_ascii=False),
              int(fresh)))
        conn.commit()
    finally:
        conn.close()


def _default_branch(project_id: str) -> str:
    conn = get_conn()
    try:
        r = conn.execute("SELECT default_branch FROM projects WHERE id=?",
                        (project_id,)).fetchone()
        return (r["default_branch"] if r else None) or "main"
    finally:
        conn.close()
