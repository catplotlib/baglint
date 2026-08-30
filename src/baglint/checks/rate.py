from __future__ import annotations

from baglint.checks.base import RunContext
from baglint.findings import Clock, Finding, Level
from baglint.reader import Message
from baglint.spec import Spec


class RateCheck:
    """Compares each topic's mean publication rate against the spec's min_rate.

    Pure finalize: the runner already accumulates the timing this needs.
    """

    def decode_topics(self, topics):
        return set()


    def __init__(self, spec: Spec):
        self._spec = spec

    def on_message(self, msg: Message) -> None:
        return

    def finalize(self, ctx: RunContext) -> list[Finding]:
        findings = []
        for topic, stat in sorted(ctx.stats.items()):
            ts = self._spec.for_topic(topic)
            if ts is None or ts.min_rate is None:
                continue

            rate = stat.rate_hz
            if rate is None:
                findings.append(
                    Finding(
                        level=Level.FAIL,
                        code="rate_unmeasurable",
                        topic=topic,
                        clock=Clock.LOG,
                        message=(
                            f"only {stat.count} message(s); too few to measure a rate "
                            f"against the {ts.min_rate:g} Hz minimum"
                        ),
                        details={"count": stat.count, "min_rate": ts.min_rate},
                    )
                )
            elif rate < ts.min_rate:
                findings.append(
                    Finding(
                        level=Level.FAIL,
                        code="rate_below_min",
                        topic=topic,
                        clock=Clock.LOG,
                        message=f"rate {rate:.1f} Hz below minimum {ts.min_rate:g} Hz",
                        details={
                            "rate_hz": round(rate, 3),
                            "min_rate": ts.min_rate,
                            "count": stat.count,
                            "span_s": round(stat.span_s, 3),
                        },
                    )
                )
        return findings
