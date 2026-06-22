"""api/qa.py — 代码问答"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import current_user
from app.api.projects import _check_access
from app.qa.retriever import answer, suggest_questions

router = APIRouter(prefix="/api/projects", tags=["qa"])


class QAReq(BaseModel):
    question: str
    branch: str | None = None


@router.post("/{pid}/qa")
def ask(pid: str, req: QAReq, user: dict = Depends(current_user)):
    _check_access(user, pid)
    return answer(pid, req.question, req.branch)


@router.get("/{pid}/qa/suggestions")
def suggestions(pid: str, branch: str | None = None, user: dict = Depends(current_user)):
    _check_access(user, pid)
    return suggest_questions(pid, branch)
