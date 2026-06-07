"""api/qa.py — 代码问答"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import current_user
from app.api.projects import _check_access
from app.qa.retriever import answer

router = APIRouter(prefix="/api/projects", tags=["qa"])


class QAReq(BaseModel):
    question: str
    branch: str | None = None


@router.post("/{pid}/qa")
def ask(pid: str, req: QAReq, user: dict = Depends(current_user)):
    _check_access(user, pid)
    return answer(pid, req.question, req.branch)
