"""queue/result.py — 任务执行结果契约

handler 跑完返回 JobResult,让 worker 据此判定「成功 / 零产出失败」,
并把执行详情(产出条数 + 跳过原因)写回 jobs 表供前端定位。

约定(用户要求):零产出一律判失败 —— 即使是「组件缺失 / 无图谱 / 无 commit」
这类降级路径,也要标 failed 并写明原因,而不是静默 complete。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JobResult:
    """一次任务执行的结构化结果。

    produced  本次实际产出的条目数(findings / commits / pages / contributors…)。
              produced == 0 → worker 判 failed。
    skipped   被跳过的原因列表(如「gitleaks 未安装」「无图谱」),用于定位空结果。
    note      人类可读的执行摘要,落到 jobs.detail。
    """

    produced: int = 0
    skipped: list[str] = field(default_factory=list)
    note: str = ""

    def reason(self) -> str:
        """零产出时拼出可定位的失败原因。"""
        base = self.note or "执行完成但无任何产出"
        if self.skipped:
            return f"{base};跳过:{' / '.join(self.skipped)}"
        return base

    def detail(self) -> str:
        """成功时写入 jobs.detail 的执行摘要。"""
        parts = [self.note] if self.note else []
        if self.skipped:
            parts.append(f"跳过:{' / '.join(self.skipped)}")
        return ";".join(parts) or f"产出 {self.produced} 条"
