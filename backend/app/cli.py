"""cli.py — 运维命令行入口

提供环境/依赖/LLM/图谱引擎的健康检查,以及项目查询与强制重建索引。

安装后(pip install -e .)可用 `cr <command>`,或直接 `python -m app.cli <command>`。

子命令:
  doctor                综合验证:配置 / 存储 / DB / 图谱引擎 / LLM chat / embedding
  check-llm             真实发一次 chat + embedding 请求,验证 provider 连通(非 stub/hash 回落)
  check-graph           验证 code-review-graph 引擎可用且能构建图谱
  projects              列出所有项目及状态
  status <project_id>   显示单个项目详情 + 分支 + 最近 jobs
  reindex <project_id>  前台同步执行全量索引(直接调 handle_index_build)
  report <project_id>   按周汇总各贡献者改动(功能范围/类别/质量),输出 Markdown
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import traceback
from pathlib import Path

# --------------------------------------------------------------------------- #
# 输出辅助
# --------------------------------------------------------------------------- #
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"{_GREEN}✓{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}✗{_RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"{_YELLOW}!{_RESET} {msg}")


def _step(idx: int, total: int, label: str) -> None:
    print(f"[{idx}/{total}] {label:<16} ", end="", flush=True)


# --------------------------------------------------------------------------- #
# 各项检查(返回 True=通过)
# --------------------------------------------------------------------------- #
def _check_config() -> bool:
    try:
        from app.core.config import get_settings
        s = get_settings()
        _ok(f"配置已加载 (storage.root={s.storage.root})")
        return True
    except Exception as e:  # noqa: BLE001
        _fail(f"配置加载失败: {e}")
        return False


def _check_storage() -> bool:
    try:
        from app.core.config import get_settings
        s = get_settings()
        s.ensure_dirs()
        missing = [p for p in (
            s.storage.root, s.storage.vectors_dir, s.storage.graphs_dir,
            s.storage.analytics_dir, s.storage.repos_dir, s.storage.reports_dir,
        ) if not Path(p).is_dir()]
        if missing:
            _fail(f"存储目录缺失: {missing}")
            return False
        # 可写探针
        probe = Path(s.storage.root) / ".cr_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        _ok("storage/ 全部就绪且可写")
        return True
    except Exception as e:  # noqa: BLE001
        _fail(f"存储目录检查失败: {e}")
        return False


def _check_db() -> bool:
    try:
        from app.db.session import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            conn.execute("SELECT 1").fetchone()
            n = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"]
        finally:
            conn.close()
        _ok(f"meta.sqlite 读写正常 (projects={n})")
        return True
    except Exception as e:  # noqa: BLE001
        _fail(f"数据库连接失败: {e}")
        return False


def _check_engine() -> bool:
    try:
        from app.parsing import engine
        if engine._ENGINE_AVAILABLE:
            _ok("code-review-graph 已安装")
            return True
        _warn("code-review-graph 未安装 — 将使用内置最小解析回落(功能受限)")
        return False
    except Exception as e:  # noqa: BLE001
        _fail(f"图谱引擎检测失败: {e}")
        return False


def _check_llm_chat() -> bool:
    try:
        from app.llm.client import chat
        from app.llm.registry import resolve_llm, tier_for_task
        rm = resolve_llm(tier_for_task("qa"))
        out = chat("test", "You are a connectivity test. Reply only with: OK", "ping")
        if not out or "占位" in out or "未配置" in out:
            _fail(f"LLM Chat 不可达(回落 stub) [provider={rm.provider_name} "
                  f"model={rm.model} base_url={rm.base_url}]")
            return False
        _ok(f"LLM Chat 可用 [provider={rm.provider_name} model={rm.model}] "
            f"{_DIM}回复: {out.strip()[:40]}{_RESET}")
        return True
    except Exception as e:  # noqa: BLE001
        _fail(f"LLM Chat 验证失败: {e}")
        return False


def _check_llm_embedding() -> bool:
    try:
        from app.llm.embedder import embed_one
        from app.llm.registry import resolve_embedding
        rm = resolve_embedding()
        vec = embed_one("hello world")
        if not vec:
            _fail("Embedding 返回空向量")
            return False
        dim_ok = rm.dim is None or len(vec) == rm.dim
        # hash 伪向量回落特征:embedder._hash_vec 产出值均落在 [-1, 1) 且步长 0.001
        looks_hashed = all(abs(round(v * 1000) - v * 1000) < 1e-6 for v in vec[:16])
        if looks_hashed:
            _fail(f"Embedding 不可达(回落 hash 伪向量) [provider={rm.provider_name} "
                  f"model={rm.model} dim={len(vec)}]")
            return False
        if not dim_ok:
            _warn(f"Embedding 维度不符:期望 {rm.dim} 实际 {len(vec)} "
                  f"[provider={rm.provider_name} model={rm.model}]")
            return False
        _ok(f"LLM Embedding 可用 [provider={rm.provider_name} model={rm.model} "
            f"dim={len(vec)}]")
        return True
    except Exception as e:  # noqa: BLE001
        _fail(f"Embedding 验证失败: {e}")
        return False


# --------------------------------------------------------------------------- #
# 子命令实现
# --------------------------------------------------------------------------- #
def cmd_doctor(_args: argparse.Namespace) -> int:
    checks = [
        ("配置加载", _check_config),
        ("存储目录", _check_storage),
        ("数据库连接", _check_db),
        ("图谱引擎", _check_engine),
        ("LLM Chat", _check_llm_chat),
        ("LLM Embedding", _check_llm_embedding),
    ]
    total = len(checks)
    results: list[bool] = []
    for i, (label, fn) in enumerate(checks, 1):
        _step(i, total, label)
        results.append(fn())
    passed = sum(results)
    print()
    if passed == total:
        _ok(f"全部 {total} 项检查通过,环境就绪。")
        return 0
    _warn(f"{passed}/{total} 项通过,{total - passed} 项需要处理(见上)。")
    # 引擎/LLM 回落不算致命:仅当配置/存储/DB 失败才返回非零
    fatal = not (results[0] and results[1] and results[2])
    return 1 if fatal else 0


def cmd_check_llm(_args: argparse.Namespace) -> int:
    chat_ok = _check_llm_chat()
    emb_ok = _check_llm_embedding()
    return 0 if (chat_ok and emb_ok) else 1


def cmd_check_graph(_args: argparse.Namespace) -> int:
    from app.parsing import engine
    try:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            (tdp / "main.py").write_text(
                "def hello():\n    return 'hi'\n\n\nclass Foo:\n    def bar(self):\n        return hello()\n",
                encoding="utf-8")
            out = tdp / "out.sqlite"
            if engine._ENGINE_AVAILABLE:
                # 引擎要求 repo_root 是项目根(含 .git/.svn/.code-review-graph),
                # 故在临时目录初始化一个空 git 仓库再跑。
                import subprocess
                subprocess.run(["git", "init", "-q", str(tdp)], check=True)
                engine._crg_build(repo_root=str(tdp), full_rebuild=True,  # type: ignore
                                  postprocess="minimal")
                crg_db = tdp / ".code-review-graph" / "graph.db"
                if not crg_db.exists():
                    _fail("引擎未产出 graph.db")
                    return 1
                import sqlite3
                db = sqlite3.connect(f"file:{crg_db}?mode=ro", uri=True)
                tables = {r[0] for r in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                db.close()
                _ok(f"code-review-graph 构建成功 (tables={len(tables)})")
                return 0
            # 引擎不可用 → 验证回落能否产出可查询图谱
            _warn("引擎未安装,验证内置最小解析回落")
            engine._fallback_build(tdp, out)
            import sqlite3
            db = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
            mods = db.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
            db.close()
            _ok(f"回落解析构建成功 (modules={mods})")
            return 0
    except Exception as e:  # noqa: BLE001
        _fail(f"图谱构建失败: {e}")
        traceback.print_exc()
        return 1


def cmd_projects(_args: argparse.Namespace) -> int:
    from app.db.session import get_conn
    conn = get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, name, status, files, loc, last_indexed_at "
            "FROM projects ORDER BY created_at DESC")]
    finally:
        conn.close()
    if not rows:
        print("(无项目)")
        return 0
    hdr = f"{'ID':<24} {'NAME':<24} {'STATUS':<10} {'FILES':>7} {'LOC':>9}  LAST_INDEXED"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{(r['id'] or ''):<24} {(r['name'] or ''):<24} "
              f"{(r['status'] or ''):<10} {(r['files'] or 0):>7} {(r['loc'] or 0):>9}  "
              f"{r['last_indexed_at'] or '-'}")
    print(f"\n共 {len(rows)} 个项目。")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from app.db.session import get_conn
    pid = args.project_id
    conn = get_conn()
    try:
        p = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not p:
            _fail(f"项目不存在: {pid}")
            return 1
        p = dict(p)
        branches = [dict(r) for r in conn.execute(
            "SELECT name, is_default, whitelisted, indexed, graph_version, last_indexed_at "
            "FROM branches WHERE project_id=? ORDER BY is_default DESC, name", (pid,))]
        jobs = [dict(r) for r in conn.execute(
            "SELECT id, type, branch, status, progress, detail, error, updated_at "
            "FROM jobs WHERE project_id=? ORDER BY id DESC LIMIT 10", (pid,))]
    finally:
        conn.close()

    print(f"项目: {p['name']} ({p['id']})")
    print(f"  状态        : {p['status']} (进度 {p['index_progress']}%)")
    print(f"  Git         : {p['git_url']}")
    print(f"  默认分支    : {p['default_branch'] or '-'}")
    print(f"  规模        : {p['files'] or 0} 文件 / {p['loc'] or 0} LOC")
    print(f"  最后索引    : {p['last_indexed_at'] or '-'}")

    print(f"\n分支 ({len(branches)}):")
    if branches:
        print(f"  {'NAME':<28} {'DEF':<4} {'WL':<4} {'IDX':<4} {'GV':<4} LAST_INDEXED")
        for b in branches:
            print(f"  {b['name']:<28} {('Y' if b['is_default'] else ''):<4} "
                  f"{('Y' if b['whitelisted'] else ''):<4} "
                  f"{('Y' if b['indexed'] else ''):<4} {b['graph_version']:<4} "
                  f"{b['last_indexed_at'] or '-'}")
    else:
        print("  (无分支,尚未 fetch)")

    print(f"\n最近 jobs ({len(jobs)}):")
    if jobs:
        for j in jobs:
            line = (f"  J-{j['id']:<5} {j['type']:<18} {(j['branch'] or '-'):<20} "
                    f"{j['status']:<8} {j['progress']:>3}%")
            print(line)
            if j['status'] == 'failed' and j['error']:
                print(f"        {_RED}error: {j['error'][:120]}{_RESET}")
    else:
        print("  (无 job 记录)")
    return 0


def cmd_reindex(args: argparse.Namespace) -> int:
    from app.db.session import get_conn
    from app.queue import queue
    from app.queue.handlers import handle_index_build
    pid = args.project_id

    conn = get_conn()
    try:
        p = conn.execute("SELECT id, name FROM projects WHERE id=?", (pid,)).fetchone()
    finally:
        conn.close()
    if not p:
        _fail(f"项目不存在: {pid}")
        return 1

    print(f"强制重建索引: {p['name']} ({pid}) — 前台同步执行,请稍候...\n")

    # 插入一条真实 job 记录,使 handler 内的 update_progress 落到 DB 且进度可见
    jid = queue.enqueue("index_build", pid, priority=queue.PRIORITY_MANUAL,
                        detail="CLI reindex (force)")
    if jid == -1:
        _warn("已有排队中的 index_build,使用临时 job 继续(进度仅打印)")
        jid = 0

    # 包一层 update_progress,把进度同时打印到 stdout
    _orig = queue.update_progress

    def _progress(job_id: int, progress: int, detail: str | None = None) -> None:
        _orig(job_id, progress, detail)
        print(f"  [{progress:>3}%] {detail or ''}")

    queue.update_progress = _progress  # type: ignore
    # handlers.py 已 `from app.queue import queue` 再 `queue.update_progress(...)`,
    # 故此处替换 queue 模块属性即可被 handler 看到。
    try:
        job = {"id": jid, "project_id": pid, "branch": None}
        result = handle_index_build(job)
        if jid:
            conn2 = get_conn()
            try:
                conn2.execute(
                    "UPDATE jobs SET status='done', progress=100, "
                    "detail=?, updated_at=datetime('now') WHERE id=?",
                    (result.detail(), jid))
                conn2.commit()
            finally:
                conn2.close()
        print()
        _ok(f"重建完成: produced={result.produced} {result.note}")
        if result.skipped:
            _warn(f"跳过: {result.skipped}")
        return 0
    except Exception as e:  # noqa: BLE001
        if jid:
            conn2 = get_conn()
            try:
                conn2.execute("UPDATE jobs SET status='failed', error=?, "
                              "updated_at=datetime('now') WHERE id=?", (str(e), jid))
                conn2.commit()
            finally:
                conn2.close()
        print()
        _fail(f"重建失败: {e}")
        traceback.print_exc()
        return 1
    finally:
        queue.update_progress = _orig  # type: ignore


def cmd_report(args: argparse.Namespace) -> int:
    from app.core.config import get_settings
    from app.db.session import get_conn
    from app.reports import weekly

    pid = args.project_id

    # 校验项目存在(沿用 cmd_status 模式)
    conn = get_conn()
    try:
        p = conn.execute("SELECT id, name FROM projects WHERE id=?", (pid,)).fetchone()
    finally:
        conn.close()
    if not p:
        _fail(f"项目不存在: {pid}")
        return 1

    # 周期解析:--since/--until 优先,其次 --week,默认上一个完整自然周
    if args.since and args.until:
        since, until = args.since, args.until
    elif args.week:
        since, until = weekly.week_of(args.week)
    else:
        since, until = weekly.last_full_week()

    try:
        md, stats = weekly.build_report(pid, since, until, use_llm=not args.no_llm)
    except FileNotFoundError as e:
        _fail(str(e))
        return 1
    except Exception as e:  # noqa: BLE001
        _fail(f"生成报告失败: {e}")
        traceback.print_exc()
        return 1

    if args.stdout:
        print(md)
        return 0

    s = get_settings()
    out_dir = Path(s.storage.reports_dir) / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"weekly-{since}.md"
    out_file.write_text(md, encoding="utf-8")
    _ok(f"报告已生成: {out_file}  ({len(stats)} 位贡献者, {since} ~ {until})")
    return 0


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cr", description="CodeReview 平台运维 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="综合验证运行环境")
    sub.add_parser("check-llm", help="真实验证 LLM chat + embedding 连通")
    sub.add_parser("check-graph", help="验证图谱引擎可构建图谱")
    sub.add_parser("projects", help="列出所有项目及状态")

    p_status = sub.add_parser("status", help="显示单个项目详情")
    p_status.add_argument("project_id", help="项目 id (slug)")

    p_reindex = sub.add_parser("reindex", help="前台同步强制重建索引")
    p_reindex.add_argument("project_id", help="项目 id (slug)")

    p_report = sub.add_parser("report", help="按周汇总各贡献者改动并输出 Markdown")
    p_report.add_argument("project_id", help="项目 id (slug)")
    p_report.add_argument("--week", help="指定周(该周任意一天 YYYY-MM-DD,对齐到周一)")
    p_report.add_argument("--since", help="自定义起始日 YYYY-MM-DD(与 --until 配对,覆盖 --week)")
    p_report.add_argument("--until", help="自定义截止日 YYYY-MM-DD(开区间,不含当天)")
    p_report.add_argument("--no-llm", action="store_true",
                          help="跳过 LLM,仅用规则指标(更快/离线/省 token)")
    p_report.add_argument("--stdout", action="store_true", help="打印到终端而非落盘")

    return parser


_DISPATCH = {
    "doctor": cmd_doctor,
    "check-llm": cmd_check_llm,
    "check-graph": cmd_check_graph,
    "projects": cmd_projects,
    "status": cmd_status,
    "reindex": cmd_reindex,
    "report": cmd_report,
}


def main(argv: list[str] | None = None) -> int:
    import logging

    from app.core.logging import setup_logging
    args = build_parser().parse_args(argv)
    # 检查/查询类命令压低日志噪声,让 ✓/✗ 输出对齐整洁;reindex 保留 INFO 进度日志。
    quiet = args.command in {"doctor", "check-llm", "check-graph", "projects",
                             "status", "report"}
    # report --stdout 要输出纯净 Markdown,连 WARNING 也压到 ERROR
    if args.command == "report" and getattr(args, "stdout", False):
        setup_logging(logging.ERROR)
    else:
        setup_logging(logging.WARNING if quiet else logging.INFO)
    return _DISPATCH[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
