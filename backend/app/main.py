"""main.py — FastAPI 应用入口

启动:uvicorn app.main:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analysis, auth, jobs, projects, qa, security, settings, users, webhook, wiki
from app.auth.users import bootstrap_admin
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    bootstrap_admin()
    yield


app = FastAPI(title="CodeReview 平台", version="0.1.0", lifespan=lifespan)

# CORS(前端开发)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# 注册 routers
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(analysis.router)
app.include_router(security.router)
app.include_router(qa.router)
app.include_router(wiki.router)
app.include_router(jobs.router)
app.include_router(users.router)
app.include_router(webhook.router)
app.include_router(settings.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
