"""qa/retriever.py — 代码问答

检索 = 图谱 blast-radius + sqlite-vec 语义 + commit_analysis 演进史 → LLM。
返回当前实现 + 历史多种思路 + 关联 commit。
"""
from __future__ import annotations

import json

from app.core.logging import get_logger
from app.db.session import get_conn
from app.llm import client
from app.llm.embedder import embed_one
from app.parsing.vectors import VectorStore

log = get_logger("qa")

_SYSTEM = (
    "你是项目代码专家。基于提供的代码片段(图谱+向量召回)与提交演进史回答问题。"
    "说明当前实现,并指出历史上出现过的不同思路。支持 **加粗**。"
)


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
    conn = get_conn()
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
    conn = get_conn()
    try:
        r = conn.execute("SELECT default_branch FROM projects WHERE id=?",
                        (project_id,)).fetchone()
        return (r["default_branch"] if r else None) or "main"
    finally:
        conn.close()
