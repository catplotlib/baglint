from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from baglint.findings import Finding, Level

_LEVEL_ORDER = {Level.FAIL: 0, Level.WARN: 1, Level.INFO: 2}


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{seconds:.2f}s"


@dataclass
class Report:
    path: Path
    findings: list[Finding]
    topic_count: int
    message_count: int
    duration_s: float

    def counts(self) -> dict[Level, int]:
        out = {Level.FAIL: 0, Level.WARN: 0, Level.INFO: 0}
        for f in self.findings:
            out[f.level] += 1
        return out

    def exit_code(self, strict: bool = False) -> int:
        counts = self.counts()
        if counts[Level.FAIL]:
            return 1
        if strict and counts[Level.WARN]:
            return 1
        return 0

    def sorted_findings(self) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda f: (_LEVEL_ORDER[f.level], f.topic or "", f.code),
        )

    def to_text(self) -> str:
        lines = [
            self.path.name,
            f"  {self.topic_count} topics · {self.message_count:,} messages · "
            f"{format_duration(self.duration_s)}",
        ]
        for f in self.sorted_findings():
            header = f"{f.level.value} {f.topic}" if f.topic else f"{f.level.value}"
            clock = f"  [{f.clock.value}]" if f.clock else ""
            lines += ["", header, f"  {f.message}{clock}"]

        counts = self.counts()
        summary = ", ".join(
            f"{counts[lvl]} {lvl.value}" for lvl in (Level.FAIL, Level.WARN, Level.INFO) if counts[lvl]
        )
        lines += ["", f"{len(self.findings)} findings" + (f": {summary}" if summary else "")]
        if not self.findings:
            lines[-1] = "no findings — bag satisfies the spec"
        return "\n".join(lines)

    def to_json(self) -> str:
        counts = self.counts()
        return json.dumps(
            {
                "file": str(self.path),
                "topics": self.topic_count,
                "messages": self.message_count,
                "duration_s": round(self.duration_s, 6),
                "summary": {lvl.value: counts[lvl] for lvl in Level},
                "findings": [f.to_dict() for f in self.sorted_findings()],
            },
            indent=2,
        )
