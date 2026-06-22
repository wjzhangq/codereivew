"""qa/retriever.py — 代码问答

检索 = 图谱 blast-radius + sqlite-vec 语义 + commit_analysis 演进史 → LLM。
返回当前实现 + 历史多种思路 + 关联 commit。
"""
from __future__ import annotations

import json
import time

from app.core.logging import get_logger
from app.db.session import get_conn_ro
from app.llm import client
from app.llm.embedder import embed_one
from app.parsing.vectors import VectorStore

log = get_logger("qa")

_SYSTEM = (
    "你是项目代码专家。基于提供的代码片段(图谱+向量召回)与提交演进史回答问题。"
    "说明当前实现,并指出历史上出现过的不同思路。支持 **加粗**。"
)

_SUGGEST_SYSTEM = (
    "你是项目代码专家。根据提供的提交演进史(每条含改动概述/解决的问题/采用的思路/涉及模块),"
    "生成 4-6 条用户最可能想问的、贴合本项目实际改动的问题。"
    "每条问题不超过 40 字,面向'为什么这样改 / 如何实现 / 演进过程',避免空泛套话。"
    '只返回 JSON:{"questions": ["...", "..."]}。'
)

# 通用兜底问题:无 commit 数据 / LLM 不可用时返回,保证前端永远有内容。
_FALLBACK_QUESTIONS = [
    "项目整体架构是怎样的?有哪些核心模块?",
    "最近的改动主要集中在哪些模块?",
    "项目里有哪些关键的设计决策和取舍?",
    "核心功能的实现思路是怎样的?",
]

# 模块级内存缓存:{(project_id, branch): (questions, ts)},TTL 600s。
_SUGGEST_CACHE: dict[tuple[str, str], tuple[list[str], float]] = {}
_SUGGEST_TTL = 600.0


def suggest_questions(project_id: str, branch: str | None = None) -> dict:
    """基于提交演进史用 LLM 生成项目相关的建议问答,带内存缓存与兜底。"""
    branch = branch or _default_branch(project_id)
    key = (project_id, branch)
    now = time.time()

    cached = _SUGGEST_CACHE.get(key)
    if cached and now - cached[1] < _SUGGEST_TTL:
        return {"questions": cached[0], "cached": True}

    commits = _recent_commits_for_suggest(project_id, branch)
    if not commits:
        return {"questions": _FALLBACK_QUESTIONS, "cached": False}

    # 聚合模块(去重,保留出现顺序)
    modules: list[str] = []
    for c in commits:
        for m in c.get("modules") or []:
            if m and m not in modules:
                modules.append(m)

    ctx = "\n".join(
        f"- [{c['sha']}] {c.get('summary') or ''}"
        + (f" | 问题: {c['problem']}" if c.get("problem") else "")
        + (f" | 思路: {c['approach']}" if c.get("approach") else "")
        for c in commits[:15])
    mod_line = ("、".join(modules[:10])) if modules else "(未知)"
    prompt = (f"涉及模块:{mod_line}\n\n提交演进史:\n{ctx}\n\n"
              f"请据此生成建议问题。")

    try:
        data = client.chat_json("qa_suggest", _SUGGEST_SYSTEM, prompt, max_tokens=600)
        questions = [q.strip() for q in (data.get("questions") or []) if isinstance(q, str) and q.strip()]
    except Exception as e:  # noqa: BLE001
        log.warning("生成建议问答失败,使用兜底: %s", e)
        questions = []

    if not questions:
        return {"questions": _FALLBACK_QUESTIONS, "cached": False}

    questions = questions[:6]
    _SUGGEST_CACHE[key] = (questions, now)
    return {"questions": questions, "cached": False}


def _recent_commits_for_suggest(project_id: str, branch: str) -> list[dict]:
    """取最近的 commit_analysis 记录用于生成建议问题。"""
    conn = get_conn_ro()
    try:
        cur = conn.execute(
            "SELECT commit_sha, summary, problem, approach, modules "
            "FROM commit_analysis WHERE project_id=? "
            "ORDER BY committed_at DESC LIMIT 20",
            (project_id,))
        out = []
        for r in cur.fetchall():
            try:
                mods = json.loads(r["modules"]) if r["modules"] else []
            except (json.JSONDecodeError, TypeError):
                mods = []
            out.append({"sha": r["commit_sha"][:7], "summary": r["summary"],
                        "problem": r["problem"], "approach": r["approach"],
                        "modules": mods if isinstance(mods, list) else []})
        return out
    finally:
        conn.close()


def answer(project_id: str, question: str, branch: str | None = None) -> dict:
    branch = branch or _default_branch(project_id)
    qvec = embed_one(question)

    # 1) 向量召回(blast-radius/模块预过滤可在此加 modules=...)
    vs = VectorStore(project_id)
    seeds = vs.knn(qvec, branch=branch, k=8)
    vs.close()

    # 2) commit 演进史(关键词召回)
    history = _related_commits(project_id, question)

    # 3) 组织上下文 → LLM
    code_ctx = "\n\n".join(
        f"// {s['file']}:{s['start_line']} [{s['module']}]\n{s['content'][:800]}"
        for s in seeds[:6])
    hist_ctx = "\n".join(
        f"- {c['sha']}: {c['summary']}" for c in history[:5])
    prompt = (f"问题:{question}\n\n相关代码:\n{code_ctx}\n\n"
              f"相关提交演进:\n{hist_ctx}\n\n请回答。")
    ans = client.chat("qa", _SYSTEM, prompt, max_tokens=1200)

    modules = list({s["module"] for s in seeds if s.get("module")})
    return {
        "answer": ans,
        "evidence": [
            {"type": "graph", "count": len(modules)},
            {"type": "vector", "count": len(seeds)},
            {"type": "history", "count": len(history)},
        ],
        "history": history[:5],
        "modules": modules,
    }


def _related_commits(project_id: str, question: str) -> list[dict]:
    """简易关键词召回演进史(可换成对 summary 的向量召回)。"""
    conn = get_conn_ro()
    try:
        terms = [t for t in question.split() if len(t) > 2][:5]
        like = " OR ".join("summary LIKE ?" for _ in terms) or "1=1"
        params = [f"%{t}%" for t in terms]
        cur = conn.execute(
            f"SELECT commit_sha, author, summary, problem, approach FROM commit_analysis "
            f"WHERE project_id=? AND ({like}) ORDER BY committed_at DESC LIMIT 8",
            (project_id, *params))
        return [{"sha": r["commit_sha"][:7], "author": r["author"],
                 "summary": r["summary"], "problem": r["problem"],
                 "approach": r["approach"]} for r in cur.fetchall()]
    finally:
        conn.close()


def _default_branch(project_id: str) -> str:
    conn = get_conn_ro()
    try:
        r = conn.execute("SELECT default_branch FROM projects WHERE id=?",
                        (project_id,)).fetchone()
        return (r["default_branch"] if r else None) or "main"
    finally:
        conn.close()
