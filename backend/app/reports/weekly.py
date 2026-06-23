"""reports/weekly.py — 周期贡献报告(按周汇总每个贡献者的改动)

从平台索引的 bare 仓库直接读 git 历史,按作者聚合一周内的:
  - 改动功能范围(LLM 生成自然语言描述,失败回落模板)
  - 类别(conventional commit 解析:feat/fix/refactor/...)
  - 完成质量(规则硬指标 0–100 + LLM 一句话点评)

设计要点:
  - 纯函数 + 数据类,LLM 与 git I/O 隔离,核心解析/聚合/评分可离线单测。
  - 复用 app.git.repo.run_git / bare_path、app.llm.client.chat_json。
  - LLM 不可达时全程回落,保证离线也能出报告(沿用项目"LLM 可回落"哲学)。
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.core.logging import get_logger
from app.git.repo import bare_path, run_git

log = get_logger("reports.weekly")

# conventional commit 前缀;匹配不到归为 "other"
_CATEGORIES = ("feat", "fix", "refactor", "docs", "test", "chore",
               "perf", "style", "ci", "build", "revert")
_CC_RE = re.compile(
    r"^(?P<type>" + "|".join(_CATEGORIES) + r")(?:\([^)]*\))?!?:",
    re.IGNORECASE,
)

# git log 字段分隔:ASCII unit separator(0x1f),不会出现在 commit message 里
_US = "\x1f"
_PRETTY = f"--pretty=format:{_US}%H{_US}%an{_US}%ad{_US}%s"


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class CommitInfo:
    sha: str
    author: str
    date: str
    subject: str
    category: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    dirs: set[str] = field(default_factory=set)  # 改动文件的 top-level 目录


@dataclass
class AuthorWeekStats:
    author: str
    commits: int = 0
    categories: Counter = field(default_factory=Counter)
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    dir_counts: Counter = field(default_factory=Counter)
    subjects: list[str] = field(default_factory=list)
    conventional_ratio: float = 0.0
    quality_score: float = 0.0
    scope_desc: str = ""
    quality_note: str = ""

    @property
    def churn(self) -> int:
        return self.insertions + self.deletions

    @property
    def top_dirs(self) -> list[str]:
        return [d for d, _ in self.dir_counts.most_common(5)]


# --------------------------------------------------------------------------- #
# 周期计算
# --------------------------------------------------------------------------- #
def last_full_week(today: date | None = None) -> tuple[str, str]:
    """返回上一个完整自然周(周一~周日)的 since/until(ISO 日期,until 为开区间次日)。"""
    today = today or date.today()
    # 本周一
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    last_sunday_end = this_monday  # git --until 为开区间,用本周一 00:00 截止
    return last_monday.isoformat(), last_sunday_end.isoformat()


def week_of(monday: str) -> tuple[str, str]:
    """给定某周周一(YYYY-MM-DD),返回该周 since/until(until=次周一,开区间)。"""
    d = datetime.strptime(monday, "%Y-%m-%d").date()
    start = d - timedelta(days=d.weekday())  # 容错:对齐到周一
    return start.isoformat(), (start + timedelta(days=7)).isoformat()


# --------------------------------------------------------------------------- #
# 采集与解析
# --------------------------------------------------------------------------- #
def parse_category(subject: str) -> str:
    m = _CC_RE.match(subject.strip())
    return m.group("type").lower() if m else "other"


def _top_dir(path: str) -> str:
    path = path.strip().strip("/")
    if not path:
        return ""
    head = path.split("/", 1)[0]
    return head if "/" in path else "(root)"


def parse_git_log(raw: str) -> list[CommitInfo]:
    """解析 `git log <_PRETTY> --numstat` 输出。

    每个 commit 形如:
        \\x1f<sha>\\x1f<author>\\x1f<date>\\x1f<subject>\\n
        <ins>\\t<del>\\t<path>\\n   (0..N 行;二进制为 -\\t-\\t<path>)
    """
    commits: list[CommitInfo] = []
    cur: CommitInfo | None = None
    for line in raw.splitlines():
        if line.startswith(_US):
            parts = line.split(_US)
            # parts[0] 为空(行首分隔符前),其后为 sha/author/date/subject
            if len(parts) >= 5:
                cur = CommitInfo(
                    sha=parts[1], author=parts[2], date=parts[3],
                    subject=parts[4], category=parse_category(parts[4]),
                )
                commits.append(cur)
            continue
        if cur is None or not line.strip():
            continue
        # numstat 行:ins\tdel\tpath
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        ins_s, del_s, path = cols[0], cols[1], cols[2]
        cur.files_changed += 1
        if ins_s.isdigit():
            cur.insertions += int(ins_s)
        if del_s.isdigit():
            cur.deletions += int(del_s)
        d = _top_dir(path)
        if d:
            cur.dirs.add(d)
    return commits


def collect_commits(project_id: str, since: str, until: str) -> list[CommitInfo]:
    """对项目 bare 库跑 git log 并解析。--all 覆盖所有分支,--no-merges 排除合并提交。"""
    bare = bare_path(project_id)
    if not bare.exists():
        raise FileNotFoundError(f"项目仓库不存在: {bare}(尚未克隆/索引?)")
    raw = run_git(
        ["log", "--all", "--no-merges",
         f"--since={since}", f"--until={until}",
         _PRETTY, "--date=short", "--numstat"],
        cwd=bare,
    )
    return parse_git_log(raw)


# --------------------------------------------------------------------------- #
# 聚合与评分
# --------------------------------------------------------------------------- #
def aggregate_by_author(commits: list[CommitInfo]) -> dict[str, AuthorWeekStats]:
    by: dict[str, AuthorWeekStats] = {}
    for c in commits:
        st = by.get(c.author)
        if st is None:
            st = AuthorWeekStats(author=c.author)
            by[c.author] = st
        st.commits += 1
        st.categories[c.category] += 1
        st.files_changed += c.files_changed
        st.insertions += c.insertions
        st.deletions += c.deletions
        for d in c.dirs:
            st.dir_counts[d] += 1
        st.subjects.append(c.subject)
    for st in by.values():
        conv = sum(n for cat, n in st.categories.items() if cat != "other")
        st.conventional_ratio = (conv / st.commits) if st.commits else 0.0
        st.quality_score = compute_quality(st)
    return by


def compute_quality(st: AuthorWeekStats) -> float:
    """纯规则质量分 0–100 = 提交规范度(40) + 改动聚焦度(30) + 体量合理度(30)。"""
    if st.commits == 0:
        return 0.0

    # 1) 提交规范度:conventional commit 占比
    norm = st.conventional_ratio * 40.0

    # 2) 改动聚焦度:fix 返工占比越高扣分;改动跨目录数适中(1~4)最佳
    fix_ratio = st.categories.get("fix", 0) / st.commits
    focus = 30.0 * (1.0 - min(fix_ratio, 0.6) / 0.6 * 0.5)  # fix 全占最多扣 50%
    n_dirs = len(st.dir_counts)
    if n_dirs == 0 or n_dirs > 8:
        focus *= 0.7  # 一个都没动(空)或散弹式扫一片,聚焦度打折
    elif n_dirs > 4:
        focus *= 0.85

    # 3) 体量合理度:单提交平均改动行数落在 [10, 400] 给满分,过大递减
    avg_churn = st.churn / st.commits
    if avg_churn <= 400:
        size = 30.0
    elif avg_churn <= 1500:
        # 400→1500 线性衰减到 12 分(疑似巨型提交/生成文件)
        size = 30.0 - (avg_churn - 400) / (1500 - 400) * 18.0
    else:
        size = 12.0
    if avg_churn < 3:
        size *= 0.8  # 几乎空提交也不理想

    return round(max(0.0, min(100.0, norm + focus + size)), 1)


# --------------------------------------------------------------------------- #
# LLM 描述(可回落)
# --------------------------------------------------------------------------- #
_SYS = (
    "你是工程团队的技术主管,正在为周会汇总某位开发者本周的 git 贡献。"
    "只依据提供的 commit 信息客观总结,不要臆造未提及的内容。"
    "用简体中文。严格返回 JSON。"
)


def _fallback_desc(st: AuthorWeekStats) -> tuple[str, str]:
    """LLM 不可达时的模板描述。"""
    main_cat = st.categories.most_common(1)[0][0] if st.categories else "other"
    dirs = "、".join(st.top_dirs[:3]) or "多处"
    scope = f"本周主要在 {dirs} 一带提交了 {st.commits} 次改动,以 {main_cat} 类为主。"
    return scope, ""


def describe_with_llm(st: AuthorWeekStats) -> tuple[str, str]:
    """返回 (功能范围描述, 质量点评)。LLM 失败回落模板,绝不抛出。"""
    try:
        from app.llm.client import chat_json
    except Exception:  # noqa: BLE001
        return _fallback_desc(st)

    cats = ", ".join(f"{k}:{v}" for k, v in st.categories.most_common())
    subjects = "\n".join(f"- {s}" for s in st.subjects[:30])
    user = (
        f"开发者:{st.author}\n"
        f"本周提交数:{st.commits}\n"
        f"类别分布:{cats}\n"
        f"主要改动目录:{', '.join(st.top_dirs) or '(无)'}\n"
        f"改动行数:+{st.insertions} / -{st.deletions}\n"
        f"提交规范率:{st.conventional_ratio:.0%}\n"
        f"commit 列表:\n{subjects}\n\n"
        "请返回 JSON:{\"scope\": \"一句话概括其本周改动的功能范围\", "
        "\"quality_note\": \"一句话点评完成质量(规范性/聚焦度/有无返工迹象)\"}"
    )
    try:
        out = chat_json("qa", _SYS, user)
        scope = (out.get("scope") or "").strip()
        note = (out.get("quality_note") or "").strip()
        if not scope:  # stub / 空回落
            return _fallback_desc(st)
        return scope, note
    except Exception as e:  # noqa: BLE001
        log.warning("LLM 描述失败,回落模板: %s", e)
        return _fallback_desc(st)


def enrich_descriptions(stats: dict[str, AuthorWeekStats], use_llm: bool = True) -> None:
    """原地填充每位作者的 scope_desc / quality_note。"""
    for st in stats.values():
        if use_llm:
            st.scope_desc, st.quality_note = describe_with_llm(st)
        else:
            st.scope_desc, st.quality_note = _fallback_desc(st)


# --------------------------------------------------------------------------- #
# 渲染
# --------------------------------------------------------------------------- #
def _cat_summary(st: AuthorWeekStats) -> str:
    return " ".join(f"{k}×{v}" for k, v in st.categories.most_common())


def render_markdown(project_id: str, since: str, until: str,
                    stats: dict[str, AuthorWeekStats]) -> str:
    # until 是开区间(次日),展示时回退一天为人类可读的"截止日"
    try:
        until_show = (datetime.strptime(until, "%Y-%m-%d").date()
                      - timedelta(days=1)).isoformat()
    except ValueError:
        until_show = until

    ranked = sorted(stats.values(), key=lambda s: (s.commits, s.churn), reverse=True)
    lines: list[str] = []
    lines.append(f"# 周期贡献报告 — {project_id}")
    lines.append("")
    lines.append(f"**周期**:{since} ~ {until_show}　**贡献者**:{len(ranked)} 人　"
                 f"**总提交**:{sum(s.commits for s in ranked)}")
    lines.append("")

    if not ranked:
        lines.append("> 本周期无提交记录。")
        return "\n".join(lines) + "\n"

    # 汇总表
    lines.append("## 汇总")
    lines.append("")
    lines.append("| 贡献者 | 提交 | 类别 | +增 / -删 | 规范率 | 质量分 |")
    lines.append("|---|---:|---|---|---:|---:|")
    for st in ranked:
        lines.append(
            f"| {st.author} | {st.commits} | {_cat_summary(st)} | "
            f"+{st.insertions} / -{st.deletions} | {st.conventional_ratio:.0%} | "
            f"{st.quality_score:.1f} |"
        )
    lines.append("")

    # 每人小节
    lines.append("## 明细")
    lines.append("")
    for st in ranked:
        lines.append(f"### {st.author}")
        lines.append("")
        lines.append(f"- **功能范围**:{st.scope_desc or '—'}")
        if st.quality_note:
            lines.append(f"- **质量点评**:{st.quality_note}")
        lines.append(f"- **改动模块**:{', '.join(st.top_dirs) or '—'}")
        lines.append(f"- **指标**:{st.commits} 提交 · "
                     f"{st.files_changed} 文件 · +{st.insertions}/-{st.deletions} 行 · "
                     f"质量 {st.quality_score:.1f}/100")
        lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# 顶层编排
# --------------------------------------------------------------------------- #
def build_report(project_id: str, since: str, until: str,
                 use_llm: bool = True) -> tuple[str, dict[str, AuthorWeekStats]]:
    """采集 → 聚合 → 评分 → 描述 → 渲染。返回 (markdown, stats)。"""
    commits = collect_commits(project_id, since, until)
    stats = aggregate_by_author(commits)
    enrich_descriptions(stats, use_llm=use_llm)
    md = render_markdown(project_id, since, until, stats)
    return md, stats


def stats_to_json(stats: dict[str, AuthorWeekStats]) -> list[dict]:
    """把作者统计序列化为前端友好的列表(按提交数、改动量降序)。"""
    ranked = sorted(stats.values(), key=lambda s: (s.commits, s.churn), reverse=True)
    return [{
        "author": st.author,
        "commits": st.commits,
        "categories": dict(st.categories),
        "filesChanged": st.files_changed,
        "insertions": st.insertions,
        "deletions": st.deletions,
        "topDirs": st.top_dirs,
        "conventionalRatio": round(st.conventional_ratio, 3),
        "qualityScore": st.quality_score,
        "scope": st.scope_desc,
        "qualityNote": st.quality_note,
    } for st in ranked]
