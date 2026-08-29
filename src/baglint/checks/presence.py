from __future__ import annotations

from baglint.checks.base import RunContext
from baglint.findings import Finding, Level
from baglint.reader import Message
from baglint.spec import Spec


class PresenceCheck:
    """Flags spec'd topics that carry no messages at all.

    Only literal topic names are required; a glob pattern matching nothing is
    not an error, since patterns are meant to describe whatever happens to be
    present.
    """

    wants_decoded = frozenset()

    def __init__(self, spec: Spec):
        self._spec = spec

    def on_message(self, msg: Message) -> None:
        return

    def finalize(self, ctx: RunContext) -> list[Finding]:
        findings = []
        for ts in self._spec.literal_topics():
            if not ts.required:
                continue
            stat = ctx.stats.get(ts.pattern)
            if stat is None or stat.count == 0:
                findings.append(
                    Finding(
                        level=Level.FAIL,
                        code="missing_topic",
                        topic=ts.pattern,
                        message="required by spec but no messages in bag",
                    )
                )
        return findings
