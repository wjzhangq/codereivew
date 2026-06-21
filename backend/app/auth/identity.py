"""auth/identity.py — 平台身份解析(不信 git config)

用 config 的平台 token 经 GitLab/GitHub commits API 把 commit 解析为平台账号。
解析不到回落 git email 并标 unverified;管理员可手动校正/合并。
"""
from __future__ import annotations

import json

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_conn_ro, tx

log = get_logger("auth.identity")


def resolve_project_identities(project_id: str) -> int:
    """对项目最近 commits 解析平台账号,建/更新 identities 映射。"""
    s = get_settings()
    conn = get_conn_ro()
    try:
        p = conn.execute("SELECT platform, org, name, git_url FROM projects WHERE id=?",
                        (project_id,)).fetchone()
    finally:
        conn.close()
    if not p:
        return 0
    platform = p["platform"]
    plat_cfg = getattr(s.platform, platform, None) if platform else None
    if not plat_cfg or not plat_cfg.enabled or not plat_cfg.token:
        log.info("项目 %s 平台未配置 token,跳过解析(将回落 unverified)", project_id)
        return 0

    repo_slug = _repo_slug(p["git_url"])
    if platform == "github":
        mappings = _github_commits(plat_cfg.token, repo_slug)
    elif platform == "gitlab":
        mappings = _gitlab_commits(plat_cfg, repo_slug)
    else:
        mappings = []

    n = 0
    with tx() as conn:
        for m in mappings:
            conn.execute("""
                INSERT INTO identities(project_id,platform,platform_user_id,username,name,
                    emails,verified)
                VALUES (?,?,?,?,?,?,1)
                ON CONFLICT(project_id,platform,platform_user_id) DO UPDATE SET
                    username=excluded.username, name=excluded.name,
                    emails=excluded.emails, verified=1
            """, (project_id, platform, m["platform_user_id"], m["username"],
                  m["name"], json.dumps(m["emails"])))
            n += 1
    log.info("resolved %d identities for %s", n, project_id)
    return n


def _repo_slug(git_url: str) -> str:
    # git@github.com:Org/repo.git -> Org/repo
    s = git_url.split(":")[-1] if ":" in git_url else git_url
    return s.replace(".git", "").strip("/")


def _github_commits(token: str, slug: str) -> list[dict]:
    try:
        with httpx.Client(timeout=30) as cli:
            r = cli.get(f"https://api.github.com/repos/{slug}/commits?per_page=100",
                        headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            seen: dict[str, dict] = {}
            for c in r.json():
                au = c.get("author") or {}
                commit_au = c.get("commit", {}).get("author", {})
                if not au.get("login"):
                    continue
                key = str(au["id"])
                ent = seen.setdefault(key, {
                    "platform_user_id": key, "username": au["login"],
                    "name": commit_au.get("name", au["login"]), "emails": set()})
                if commit_au.get("email"):
                    ent["emails"].add(commit_au["email"])
            return [{**v, "emails": list(v["emails"])} for v in seen.values()]
    except Exception as e:  # noqa: BLE001
        log.warning("GitHub API 失败: %s", e)
        return []


def _gitlab_commits(cfg, slug: str) -> list[dict]:
    try:
        proj = slug.replace("/", "%2F")
        with httpx.Client(timeout=30) as cli:
            r = cli.get(f"{cfg.base_url}/api/v4/projects/{proj}/repository/commits?per_page=100",
                        headers={"PRIVATE-TOKEN": cfg.token})
            r.raise_for_status()
            seen: dict[str, dict] = {}
            for c in r.json():
                email = c.get("author_email", "")
                name = c.get("author_name", email)
                key = email or name
                ent = seen.setdefault(key, {
                    "platform_user_id": key, "username": name,
                    "name": name, "emails": set()})
                if email:
                    ent["emails"].add(email)
            return [{**v, "emails": list(v["emails"])} for v in seen.values()]
    except Exception as e:  # noqa: BLE001
        log.warning("GitLab API 失败: %s", e)
        return []


def list_identities(project_id: str) -> list[dict]:
    conn = get_conn_ro()
    try:
        cur = conn.execute("SELECT * FROM identities WHERE project_id=? AND merged_into IS NULL",
                          (project_id,))
        out = []
        for r in cur.fetchall():
            d = dict(r)
            d["emails"] = json.loads(d["emails"]) if d["emails"] else []
            d["verified"] = bool(d["verified"])
            out.append(d)
        return out
    finally:
        conn.close()


def merge_identities(project_id: str, source_id: int, target_id: int) -> None:
    with tx() as conn:
        conn.execute("UPDATE identities SET merged_into=? WHERE id=? AND project_id=?",
                     (target_id, source_id, project_id))
