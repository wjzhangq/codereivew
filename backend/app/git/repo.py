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
    """git clone --bare 建只读裸库,远端分支收到 refs/remotes/origin/* 命名空间。

    不用 --mirror:mirror 会强制 fetch 进 refs/heads/*,与 linked worktree
    检出的 refs/heads/<branch> 冲突(git refusing to fetch into checked-out branch)。
    改用 refs/remotes/origin/* 后,worktree 与 fetch 各用各的命名空间,永不冲突。
    已存在则 fetch。
    """
    dest = bare_path(project_id)
    if dest.exists():
        fetch(project_id, deploy_key)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_git(["clone", "--bare", git_url, str(dest)], deploy_key=deploy_key)
    # --bare 默认的 fetch refspec 也写 refs/heads/*;改成 remotes 命名空间。
    run_git(["config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"], cwd=dest)
    fetch(project_id, deploy_key)
    log.info("cloned bare %s -> %s", git_url, dest)
    return dest


def fetch(project_id: str, deploy_key: str | None) -> None:
    dest = bare_path(project_id)
    # 远端分支落 refs/remotes/origin/*,避开被 worktree 检出的 refs/heads/<branch>。
    run_git(["fetch", "--prune", "origin", "+refs/heads/*:refs/remotes/origin/*"],
            cwd=dest, deploy_key=deploy_key)
    log.info("fetched %s", project_id)


def default_branch(project_id: str) -> str | None:
    dest = bare_path(project_id)
    try:
        # 远端 HEAD 指向的默认分支(origin/HEAD -> origin/<branch>)。
        out = run_git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                      cwd=dest, check=False).strip()
        if out:
            return out.removeprefix("origin/")
        # 回落:bare 自身 HEAD。
        out = run_git(["symbolic-ref", "--short", "HEAD"], cwd=dest, check=False).strip()
        return out or None
    except RuntimeError:
        return None


def list_remote_branches(project_id: str) -> list[BranchInfo]:
    """git for-each-ref 列出所有远端分支及末次 commit 信息。"""
    dest = bare_path(project_id)
    fmt = "%(refname:short)%09%(objectname:short)%09%(contents:subject)%09%(authorname)%09%(committerdate:iso8601)"
    out = run_git(["for-each-ref", f"--format={fmt}", "refs/remotes/origin/"], cwd=dest)
    branches: list[BranchInfo] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        name = parts[0].removeprefix("origin/")
        if name in ("HEAD", "origin", ""):  # origin/HEAD 符号引用,非真实分支
            continue
        branches.append(BranchInfo(
            name=name, sha=parts[1], subject=parts[2],
            author=parts[3], committed_at=parts[4],
        ))
    return branches
