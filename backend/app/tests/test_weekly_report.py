"""周报核心逻辑单测 — 纯函数,不依赖网络/LLM/DB。"""
from app.reports import weekly
from app.reports.weekly import (
    AuthorWeekStats,
    aggregate_by_author,
    compute_quality,
    parse_category,
    parse_git_log,
)

_US = "\x1f"


def _commit_block(sha, author, date, subject, numstat_lines):
    head = f"{_US}{sha}{_US}{author}{_US}{date}{_US}{subject}"
    return "\n".join([head, *numstat_lines])


def test_parse_category():
    assert parse_category("feat(qa): 动态建议") == "feat"
    assert parse_category("fix: bug") == "fix"
    assert parse_category("refactor(graph): x") == "refactor"
    assert parse_category("FEAT: upper") == "feat"  # 大小写不敏感
    assert parse_category("feat!: breaking") == "feat"
    assert parse_category("随手改了点东西") == "other"
    assert parse_category("update readme") == "other"


def test_parse_git_log_basic():
    raw = "\n".join([
        _commit_block("aaa", "Alice", "2026-06-10", "feat(api): add endpoint",
                      ["10\t2\tbackend/app/api/qa.py", "5\t0\tbackend/app/qa/x.py"]),
        _commit_block("bbb", "Bob", "2026-06-11", "fix: crash",
                      ["1\t1\tfrontend/src/App.tsx"]),
        _commit_block("ccc", "Alice", "2026-06-11", "chore: bump",
                      ["-\t-\tassets/logo.png"]),  # 二进制 ins/del 为 -
    ])
    commits = parse_git_log(raw)
    assert len(commits) == 3
    a1 = commits[0]
    assert a1.author == "Alice" and a1.category == "feat"
    assert a1.files_changed == 2
    assert a1.insertions == 15 and a1.deletions == 2
    assert a1.dirs == {"backend"}
    # 二进制行不计入增删但计文件数
    assert commits[2].files_changed == 1
    assert commits[2].insertions == 0 and commits[2].deletions == 0


def test_top_dir_root_file():
    raw = _commit_block("d1", "Carol", "2026-06-10", "docs: readme",
                        ["3\t1\tREADME.md"])
    commits = parse_git_log(raw)
    assert commits[0].dirs == {"(root)"}


def test_subject_with_separator_safe():
    # commit subject 含竖线/特殊字符不应破坏解析(用 \x1f 分隔)
    raw = _commit_block("e1", "Dan", "2026-06-10", "fix: a | b || c : d",
                        ["1\t0\tsrc/x.py"])
    commits = parse_git_log(raw)
    assert len(commits) == 1
    assert commits[0].subject == "fix: a | b || c : d"
    assert commits[0].category == "fix"


def test_aggregate_by_author():
    raw = "\n".join([
        _commit_block("a", "Alice", "2026-06-10", "feat: x", ["10\t0\tbackend/a.py"]),
        _commit_block("b", "Alice", "2026-06-11", "fix: y", ["2\t1\tbackend/b.py"]),
        _commit_block("c", "Bob", "2026-06-11", "wip", ["1\t0\tfrontend/c.tsx"]),
    ])
    stats = aggregate_by_author(parse_git_log(raw))
    assert set(stats) == {"Alice", "Bob"}
    alice = stats["Alice"]
    assert alice.commits == 2
    assert alice.categories["feat"] == 1 and alice.categories["fix"] == 1
    assert alice.insertions == 12 and alice.deletions == 1
    assert alice.conventional_ratio == 1.0
    # Bob 的 "wip" 不规范
    assert stats["Bob"].conventional_ratio == 0.0


def test_compute_quality_bounds_and_ordering():
    # 全规范、聚焦、体量合理 → 高分
    good = AuthorWeekStats(author="g", commits=4)
    good.categories.update({"feat": 3, "refactor": 1})
    good.dir_counts.update({"backend": 3, "frontend": 1})
    good.insertions, good.deletions = 200, 80
    good.conventional_ratio = 1.0

    # 全是 wip(不规范)+ 巨型提交 → 低分
    bad = AuthorWeekStats(author="b", commits=4)
    bad.categories.update({"other": 4})
    bad.dir_counts.update({"a": 1, "b": 1, "c": 1, "d": 1, "e": 1, "f": 1,
                           "g": 1, "h": 1, "i": 1})
    bad.insertions, bad.deletions = 9000, 1000
    bad.conventional_ratio = 0.0

    gq = compute_quality(good)
    bq = compute_quality(bad)
    assert 0.0 <= bq <= 100.0
    assert 0.0 <= gq <= 100.0
    assert gq > bq
    assert gq >= 70.0  # 规范+聚焦+合理体量应当拿到高分


def test_compute_quality_empty():
    assert compute_quality(AuthorWeekStats(author="x", commits=0)) == 0.0


def test_week_helpers():
    since, until = weekly.week_of("2026-06-17")  # 周三
    assert since == "2026-06-15"  # 回退到周一
    assert until == "2026-06-22"  # 次周一(开区间)


def test_render_markdown_empty():
    md = weekly.render_markdown("proj", "2026-06-15", "2026-06-22", {})
    assert "无提交记录" in md
    assert "proj" in md
