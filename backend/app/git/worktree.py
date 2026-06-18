"""git/worktree.py — 每分支一个 worktree(隔离、共享对象库、可并行解析)"""
from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.git.repo import bare_path, run_git

log = get_logger("git.worktree")


def worktree_path(project_id: str, branch: str) -> Path:
    s = get_settings()
    safe = branch.replace("/", "__")
    return Path(s.storage.repos_dir) / project_id / "worktrees" / safe


def _is_valid_worktree(wt: Path) -> bool:
    """worktree 目录含 .git 文件(指向 bare 的 worktree 元数据)才算有效。"""
    return (wt / ".git").exists()


def add_worktree(project_id: str, branch: str) -> Path:
    """git worktree add(共享 bare 对象库)。已存在且有效则更新到分支最新;
    残留的无效目录(上次失败遗留)先清理再重建。"""
    bare = bare_path(project_id)
    wt = worktree_path(project_id, branch).resolve()
    ref = f"refs/remotes/origin/{branch}"  # 远端分支命名空间(避开 refs/heads 与 fetch 冲突)
    if wt.exists() and _is_valid_worktree(wt):
        run_git(["reset", "--hard", ref], cwd=wt, check=False)
        return wt
    if wt.exists():
        # 残留无效目录:先从 git 注销再物理删除
        run_git(["worktree", "remove", "--force", str(wt)], cwd=bare, check=False)
        run_git(["worktree", "prune"], cwd=bare, check=False)
        import shutil
        shutil.rmtree(wt, ignore_errors=True)
    wt.parent.mkdir(parents=True, exist_ok=True)
    # --detach:基于远端 ref 检出但不占用任何 refs/heads/<branch>,worktree 间互不冲突
    run_git(["worktree", "add", "--force", "--detach", str(wt), ref], cwd=bare)
    log.info("worktree add %s@%s -> %s", project_id, branch, wt)
    return wt


def remove_worktree(project_id: str, branch: str) -> None:
    bare = bare_path(project_id)
    wt = worktree_path(project_id, branch)
    if wt.exists():
        run_git(["worktree", "remove", "--force", str(wt)], cwd=bare, check=False)
    log.info("worktree removed %s@%s", project_id, branch)


def prune_worktrees(project_id: str) -> None:
    """清理失活分支的 worktree。"""
    bare = bare_path(project_id)
    run_git(["worktree", "prune"], cwd=bare, check=False)
