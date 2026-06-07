"""git/history.py — log / blame / diff

逐 commit 分析与贡献汇总的底层数据源。
排除 vendor/生成/lockfile(config.git.exclude_globs)。
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import get_settings
from app.git.repo import bare_path, run_git
from app.git.worktree import worktree_path


@dataclass
class FileChange:
    file: str
    add: int
    del_: int


@dataclass
class CommitDiff:
    sha: str
    author: str
    email: str
    committed_at: str
    raw_msg: str
    files: list[FileChange] = field(default_factory=list)
    patch: str = ""

    @property
    def loc_add(self) -> int:
        return sum(f.add for f in self.files)

    @property
    def loc_del(self) -> int:
        return sum(f.del_ for f in self.files)


def _excluded(path: str) -> bool:
    globs = get_settings().git.exclude_globs
    return any(fnmatch.fnmatch(path, g) for g in globs)


def list_commits(project_id: str, branch: str, last_days: int | None = None,
                 last_count: int | None = None) -> list[str]:
    """回溯范围 = max(最近 N 天, 最近 M 条):取覆盖更多者。"""
    bare = bare_path(project_id)
    by_days: list[str] = []
    if last_days:
        out = run_git(["log", branch, f"--since={last_days} days ago",
                       "--pretty=%H"], cwd=bare, check=False)
        by_days = out.split()
    by_count: list[str] = []
    if last_count:
        out = run_git(["log", branch, f"-n{last_count}", "--pretty=%H"],
                      cwd=bare, check=False)
        by_count = out.split()
    # 取覆盖更多者(更长的列表)
    return by_days if len(by_days) >= len(by_count) else by_count


def get_commit_diff(project_id: str, sha: str) -> CommitDiff:
    bare = bare_path(project_id)
    meta = run_git(["show", "-s", "--pretty=%an%x09%ae%x09%cI%x09%B", sha],
                   cwd=bare).split("\t", 3)
    author, email, when, msg = (meta + ["", "", "", ""])[:4]
    numstat = run_git(["show", "--numstat", "--pretty=format:", sha], cwd=bare)
    files: list[FileChange] = []
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, d, fpath = parts
        if _excluded(fpath):
            continue
        files.append(FileChange(file=fpath, add=int(a) if a.isdigit() else 0,
                                del_=int(d) if d.isdigit() else 0))
    patch = run_git(["show", "--unified=3", "--pretty=format:", sha], cwd=bare,
                    check=False)
    return CommitDiff(sha=sha, author=author, email=email, committed_at=when,
                      raw_msg=msg.strip(), files=files, patch=patch[:200_000])


def blame_context(project_id: str, branch: str, file: str,
                  lines: tuple[int, int] | None = None) -> str:
    """改动行 git blame 取上下文(供 LLM 理解)。"""
    wt = worktree_path(project_id, branch)
    args = ["blame", "-w"]
    if lines:
        args += ["-L", f"{lines[0]},{lines[1]}"]
    args += [file]
    return run_git(args, cwd=wt, check=False)


def log_numstat(project_id: str, branch: str, since: str, until: str) -> list[dict]:
    """by_log:周期内谁改了什么(author + numstat)。"""
    bare = bare_path(project_id)
    out = run_git(["log", branch, f"--since={since}", f"--until={until}",
                   "--numstat", "--pretty=format:@@@%H%x09%an%x09%ae%x09%cI"],
                  cwd=bare, check=False)
    commits: list[dict] = []
    cur: dict | None = None
    for line in out.splitlines():
        if line.startswith("@@@"):
            sha, an, ae, when = line[3:].split("\t")
            cur = {"sha": sha, "author": an, "email": ae, "when": when, "files": []}
            commits.append(cur)
        elif cur and "\t" in line:
            parts = line.split("\t")
            if len(parts) == 3 and not _excluded(parts[2]):
                a, d, f = parts
                cur["files"].append({"file": f, "add": int(a) if a.isdigit() else 0,
                                     "del": int(d) if d.isdigit() else 0})
    return commits


def blame_ownership(project_id: str, branch: str, files: list[str]) -> dict[str, int]:
    """by_blame:当前快照谁拥有代码(按行归属)。返回 email -> 行数。"""
    wt = worktree_path(project_id, branch)
    owners: dict[str, int] = {}
    for f in files:
        if _excluded(f) or not (Path(wt) / f).exists():
            continue
        out = run_git(["blame", "-w", "--line-porcelain", f], cwd=wt, check=False)
        for line in out.splitlines():
            if line.startswith("author-mail "):
                email = line[len("author-mail "):].strip("<>")
                owners[email] = owners.get(email, 0) + 1
    return owners
