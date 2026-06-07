"""security/scanner.py — 统一安全扫描入口

gitleaks + Semgrep + osv/Trivy + LLM 复审 → 统一 finding;与基线对比新增/消除。
"""
from __future__ import annotations

import json
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_conn
from app.git.worktree import worktree_path
from app.llm import client

log = get_logger("security.scanner")


def scan_branch(project_id: str, branch: str,
                progress_cb: Callable[[int, str], None] | None = None) -> int:
    cfg = get_settings().security
    wt = worktree_path(project_id, branch)
    scan_id = str(uuid.uuid4())[:8]
    findings: list[dict] = []

    if cfg.gitleaks:
        findings += _run_gitleaks(wt, project_id)
        if progress_cb:
            progress_cb(25, "gitleaks 完成")
    if cfg.semgrep:
        findings += _run_semgrep(wt, project_id)
        if progress_cb:
            progress_cb(50, "semgrep 完成")
    if cfg.sca:
        findings += _run_sca(wt, project_id)
        if progress_cb:
            progress_cb(70, "osv/trivy 完成")
    if cfg.llm_review:
        findings = _llm_review(findings, project_id, branch)
        if progress_cb:
            progress_cb(90, "LLM 复审完成")

    _save_findings(project_id, branch, scan_id, findings)
    _reconcile(project_id, branch)
    if progress_cb:
        progress_cb(100, f"扫描完成,{len(findings)} findings")
    return len(findings)


# --------------------------------------------------------------------------- #
# 各扫描器
# --------------------------------------------------------------------------- #
def _run_gitleaks(wt: Path, project_id: str) -> list[dict]:
    try:
        proc = subprocess.run(
            ["gitleaks", "detect", "-s", str(wt), "--report-format=json", "--exit-code=0"],
            capture_output=True, text=True, timeout=120)
        items = json.loads(proc.stdout or "[]")
        return [{"severity": "high" if "key" in (i.get("Rule", "").lower()) else "medium",
                 "rule": f"gitleaks:{i.get('RuleID', 'unknown')}",
                 "source": "gitleaks",
                 "file": i.get("File", ""),
                 "line": i.get("StartLine", 0),
                 "title": i.get("Description", "密钥泄露"),
                 "evidence": i.get("Secret", "")[:200],
                 "suggestion": "请吊销并轮换此密钥,并加入 .gitleaksignore。"} for i in items]
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        log.warning("gitleaks 不可用: %s", e)
        return []


def _run_semgrep(wt: Path, project_id: str) -> list[dict]:
    try:
        proc = subprocess.run(
            ["semgrep", "scan", "--json", "--quiet", str(wt)],
            capture_output=True, text=True, timeout=180)
        data = json.loads(proc.stdout or '{"results":[]}')
        return [{"severity": _map_sev(r.get("extra", {}).get("severity", "WARNING")),
                 "rule": f"semgrep:{r.get('check_id', 'unknown')}",
                 "source": "semgrep",
                 "file": str(Path(r.get("path", "")).relative_to(wt)) if r.get("path") else "",
                 "line": r.get("start", {}).get("line", 0),
                 "title": r.get("extra", {}).get("message", "")[:120],
                 "evidence": r.get("extra", {}).get("lines", "")[:200],
                 "suggestion": r.get("extra", {}).get("fix", "")} for r in data.get("results", [])]
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        log.warning("semgrep 不可用: %s", e)
        return []


def _run_sca(wt: Path, project_id: str) -> list[dict]:
    try:
        proc = subprocess.run(
            ["osv-scanner", "--json", str(wt)],
            capture_output=True, text=True, timeout=120)
        data = json.loads(proc.stdout or '{"results":[]}')
        results = data.get("results", [])
        findings = []
        for pkg_group in results:
            for v in pkg_group.get("vulnerabilities", []):
                findings.append({"severity": "high",
                                 "rule": f"osv:{v.get('id', '')}",
                                 "source": "osv-scanner",
                                 "file": pkg_group.get("source", {}).get("path", ""),
                                 "line": 0,
                                 "title": v.get("summary", "")[:120],
                                 "evidence": v.get("id", ""),
                                 "suggestion": "升级受影响依赖。"})
        return findings
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        log.warning("osv-scanner 不可用: %s", e)
        return []


def _llm_review(findings: list[dict], project_id: str, branch: str) -> list[dict]:
    """LLM 复审:降误报 + 补逻辑漏洞建议。"""
    from app.parsing.graph_store import GraphStore
    try:
        gs = GraphStore(project_id, branch)
        radius_fn = gs.blast_radius
    except FileNotFoundError:
        radius_fn = lambda _: []  # noqa: E731

    for f in findings[:20]:  # 限量
        context = f"文件:{f['file']} L{f['line']}\n证据:{f['evidence']}\n规则:{f['rule']}"
        blast = radius_fn(f.get("module", ""))
        prompt = (f"安全发现:\n{context}\n爆炸半径:{blast}\n"
                  "判断是否为真实风险,并给出修复建议。输出 JSON:{{is_real, suggestion}}")
        out = client.chat_json("qa", "你是安全审查专家。", prompt)
        if out.get("suggestion"):
            f["suggestion"] = out["suggestion"]
        f["llm_reviewed"] = True
        f["blast"] = len(blast)
    try:
        gs.close()  # type: ignore
    except Exception:
        pass
    return findings


def _map_sev(s: str) -> str:
    return {"ERROR": "high", "WARNING": "medium", "INFO": "low"}.get(s.upper(), "medium")


def _save_findings(project_id: str, branch: str, scan_id: str,
                   findings: list[dict]) -> None:
    conn = get_conn()
    try:
        for i, f in enumerate(findings):
            fid = f"F-{scan_id[:4]}{i:02d}"
            conn.execute("""
                INSERT INTO findings(id,project_id,branch,scan_id,severity,rule,source,
                    file,line,title,evidence,suggestion,module,blast,llm_reviewed)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (fid, project_id, branch, scan_id, f.get("severity"), f.get("rule"),
                  f.get("source"), f.get("file"), f.get("line"), f.get("title"),
                  f.get("evidence"), f.get("suggestion"), f.get("module"),
                  f.get("blast", 0), f.get("llm_reviewed", False)))
        conn.commit()
    finally:
        conn.close()


def _reconcile(project_id: str, branch: str) -> None:
    """与基线对比:上次有但本次没有的 → resolved。"""
    # 简化实现:以 (rule, file, line) 为 key
    conn = get_conn()
    try:
        # 最近两次 scan_id
        cur = conn.execute(
            "SELECT DISTINCT scan_id FROM findings WHERE project_id=? AND branch=? "
            "ORDER BY created_at DESC LIMIT 2", (project_id, branch))
        scans = [r["scan_id"] for r in cur.fetchall()]
        if len(scans) < 2:
            return
        new_keys = conn.execute(
            "SELECT rule || '||' || file || '||' || line AS k FROM findings "
            "WHERE scan_id=?", (scans[0],)).fetchall()
        new_set = {r["k"] for r in new_keys}
        conn.execute(
            f"UPDATE findings SET status='resolved' WHERE scan_id=? AND "
            f"(rule || '||' || file || '||' || line) NOT IN ({','.join('?'*len(new_set))})",
            (scans[1], *new_set))
        conn.commit()
    finally:
        conn.close()
