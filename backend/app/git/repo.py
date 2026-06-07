"""git/repo.py — clone / fetch(deploy key 只读)

git clone --mirror 建 bare 库;增量 git fetch。
deploy key 经临时 600 文件 + GIT_SSH_COMMAND 注入,用完即删。
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("git.repo")


@dataclass
class BranchInfo:
    name: str
    sha: str
    subject: str
    author: str
    committed_at: str


@contextmanager
def _ssh_env(deploy_key: str | None):
    """写临时 key(600)并设置 GIT_SSH_COMMAND;退出即删。"""
    env = dict(os.environ)
    if not deploy_key:
        yield env
        return
    fd, path = tempfile.mkstemp(prefix="cr_key_")
    try:
        os.write(fd, deploy_key.encode())
        if not deploy_key.endswith("\n"):
            os.write(fd, b"\n")
        os.close(fd)
        os.chmod(path, 0o600)
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {path} -o IdentitiesOnly=yes "
            f"-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null"
        )
        yield env
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def run_git(args: list[str], cwd: Path | None = None, deploy_key: str | None = None,
            check: bool = True) -> str:
    with _ssh_env(deploy_key) as env:
        log.debug("git %s (cwd=%s)", " ".join(args), cwd)
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd) if cwd else None, env=env,
            capture_output=True, text=True,
        )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def bare_path(project_id: str) -> Path:
    s = get_settings()
    return Path(s.storage.repos_dir) / project_id / "bare"


def clone_mirror(git_url: str, project_id: str, deploy_key: str | None) -> Path:
    """git clone --mirror 建 bare 库(只读)。已存在则 fetch。"""
    dest = bare_path(project_id)
    if dest.exists():
        fetch(project_id, deploy_key)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_git(["clone", "--mirror", git_url, str(dest)], deploy_key=deploy_key)
    log.info("cloned mirror %s -> %s", git_url, dest)
    return dest


def fetch(project_id: str, deploy_key: str | None) -> None:
    dest = bare_path(project_id)
    run_git(["fetch", "--prune", "origin", "+refs/heads/*:refs/heads/*"],
            cwd=dest, deploy_key=deploy_key)
    log.info("fetched %s", project_id)


def default_branch(project_id: str) -> str | None:
    dest = bare_path(project_id)
    try:
        out = run_git(["symbolic-ref", "--short", "HEAD"], cwd=dest, check=False).strip()
        if out:
            return out
        # 回落:remote show 不可用于 bare,改取 refs
        out = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=dest, check=False).strip()
        return out or None
    except RuntimeError:
        return None


def list_remote_branches(project_id: str) -> list[BranchInfo]:
    """git for-each-ref 列出所有分支及末次 commit 信息。"""
    dest = bare_path(project_id)
    fmt = "%(refname:short)%09%(objectname:short)%09%(contents:subject)%09%(authorname)%09%(committerdate:iso8601)"
    out = run_git(["for-each-ref", f"--format={fmt}", "refs/heads/"], cwd=dest)
    branches: list[BranchInfo] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        branches.append(BranchInfo(
            name=parts[0], sha=parts[1], subject=parts[2],
            author=parts[3], committed_at=parts[4],
        ))
    return branches
