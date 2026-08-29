from __future__ import annotations

from pathlib import Path

from baglint.checks import ALL_CHECKS, RunContext, TopicStat
from baglint.reader import McapBagReader
from baglint.report import Report
from baglint.spec import Spec


def run(path: str | Path, spec: Spec | None = None, check_classes=None) -> Report:
    """Single streaming pass over a bag, feeding every check."""
    spec = spec or Spec.empty()
    checks = [cls(spec) for cls in (check_classes or ALL_CHECKS)]

    wants_decoded = frozenset().union(*(c.wants_decoded for c in checks)) if checks else frozenset()
    ctx = RunContext(spec=spec)

    with McapBagReader(path) as reader:
        for msg in reader.iter_messages(decode=wants_decoded):
            stat = ctx.stats.get(msg.topic)
            if stat is None:
                stat = ctx.stats[msg.topic] = TopicStat(msg.topic)
            stat.observe(msg.log_time_ns)
            for check in checks:
                check.on_message(msg)

        # Unindexed bags carry no summary section, so fall back to what we just saw.
        firsts = [s.first_ns for s in ctx.stats.values() if s.first_ns is not None]
        lasts = [s.last_ns for s in ctx.stats.values() if s.last_ns is not None]
        ctx.start_ns = reader.start_ns or (min(firsts) if firsts else 0)
        ctx.end_ns = reader.end_ns or (max(lasts) if lasts else 0)
        topic_count = len(reader.channels())
        message_count = reader.message_count or sum(s.count for s in ctx.stats.values())

    findings = [f for check in checks for f in check.finalize(ctx)]

    return Report(
        path=Path(path),
        findings=findings,
        topic_count=topic_count,
        message_count=message_count,
        duration_s=ctx.duration_s,
    )
