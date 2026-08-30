"""Self-contained HTML report.

The text output gives counts, which answers what failed but not where. Whether
three dropouts are spread evenly or clustered in one second is a different bug,
and whether two topics stalled at the same instant separates a recorder-wide
stall from a single misbehaving driver. Both are obvious on a shared time axis
and invisible in a list.

The document embeds its own styles and references nothing external, so it can
be uploaded as a CI artifact or attached to a bug report and still render.
"""

from __future__ import annotations

from html import escape

from baglint.findings import Level
from baglint.report import Report, format_duration

_STYLE = """
:root {
  --bg: #ffffff; --fg: #202124; --muted: #5f6368; --rule: #e0e0e0;
  --track: #eceff1; --present: #90a4ae; --fail: #d93025; --warn: #f9ab00;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #17181a; --fg: #e8eaed; --muted: #9aa0a6; --rule: #303134;
    --track: #26282b; --present: #5f6f78; --fail: #f28b82; --warn: #fdd663;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1.5rem; background: var(--bg); color: var(--fg);
  font: 14px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
main { max-width: 60rem; margin: 0 auto; }
h1 { font-size: 1.35rem; margin: 0 0 .25rem; font-weight: 600; }
.meta { color: var(--muted); margin: 0 0 1.75rem; font-variant-numeric: tabular-nums; }
h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .06em;
     color: var(--muted); font-weight: 600; margin: 2rem 0 .75rem; }
.row { display: grid; grid-template-columns: minmax(6rem, 14rem) 1fr; gap: .75rem;
       align-items: center; margin-bottom: .3rem; }
.name { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .8rem;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.name.absent { color: var(--muted); text-decoration: line-through; }
.track { position: relative; height: 20px; background: var(--track); border-radius: 3px; }
.present { position: absolute; top: 0; bottom: 0; background: var(--present);
           border-radius: 3px; opacity: .55; }
.mark { position: absolute; top: 0; bottom: 0; min-width: 5px; border-radius: 2px; }
.span { position: absolute; top: 0; bottom: 0; border-radius: 3px; opacity: .3; }
.span.fail { background: var(--fail); }
.span.warn { background: var(--warn); }
.mark.fail { background: var(--fail); }
.mark.warn { background: var(--warn); }
.axis { display: flex; justify-content: space-between; color: var(--muted);
        font-size: .7rem; margin-top: .35rem; font-variant-numeric: tabular-nums; }
.legend { display: flex; gap: 1.25rem; color: var(--muted); font-size: .75rem; margin-top: 1rem; }
.legend span::before { content: ""; display: inline-block; width: .7rem; height: .7rem;
                       border-radius: 2px; margin-right: .35rem; vertical-align: -1px; }
.legend .p::before { background: var(--present); opacity: .55; }
.legend .f::before { background: var(--fail); }
.legend .w::before { background: var(--warn); }
.finding { border-left: 3px solid var(--rule); padding: .1rem 0 .1rem .8rem; margin-bottom: 1rem; }
.finding.FAIL { border-left-color: var(--fail); }
.finding.WARN { border-left-color: var(--warn); }
.finding .head { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .8rem; }
.finding .lvl { font-weight: 600; }
.finding.FAIL .lvl { color: var(--fail); }
.finding.WARN .lvl { color: var(--warn); }
.finding .msg { margin-top: .15rem; }
.finding .clock { color: var(--muted); font-size: .75rem; }
.pass { color: var(--muted); }
footer { color: var(--muted); font-size: .72rem; margin-top: 2.5rem;
         border-top: 1px solid var(--rule); padding-top: .75rem; }
"""


def _pct(value: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return max(0.0, min(100.0, value / total * 100.0))


def _marks_for(report: Report, summary) -> list[str]:
    """Positioned <div>s for every defect on a topic's track.

    A defect with a time gets a mark at that time. A defect without one, such
    as a rate measured across the whole recording, shades the topic's entire
    span instead. Leaving those undrawn made a failing topic look clean.
    """
    duration = report.duration_s
    spans, marks = [], []

    for finding in report.findings:
        if finding.topic != summary.topic or finding.code == "missing_topic":
            continue
        level = "fail" if finding.level is Level.FAIL else "warn"

        intervals = finding.details.get("intervals")
        if intervals:
            for iv in intervals:
                left = _pct(iv["start"], duration)
                width = _pct(iv["end"], duration) - left
                marks.append(f'<div class="mark {level}" style="left:{left:.3f}%;width:{width:.3f}%"></div>')
        elif finding.t_start is not None:
            left = _pct(finding.t_start, duration)
            marks.append(f'<div class="mark {level}" style="left:{left:.3f}%;width:0%"></div>')
        else:
            left = _pct(summary.start_s, duration)
            width = _pct(summary.end_s, duration) - left
            spans.append(f'<div class="span {level}" style="left:{left:.3f}%;width:{width:.3f}%"></div>')

    return spans + marks


def _timeline(report: Report) -> list[str]:
    present = {t.topic for t in report.topics}
    missing = sorted(
        {f.topic for f in report.findings if f.code == "missing_topic" and f.topic}
    )
    if not report.topics and not missing:
        return []

    out = ["<h2>Timeline</h2>"]

    for summary in report.topics:
        left = _pct(summary.start_s, report.duration_s)
        width = _pct(summary.end_s, report.duration_s) - left
        bars = [f'<div class="present" style="left:{left:.3f}%;width:{width:.3f}%"></div>']
        bars += _marks_for(report, summary)
        out.append(
            f'<div class="row"><div class="name">{escape(summary.topic)}</div>'
            f'<div class="track">{"".join(bars)}</div></div>'
        )

    for topic in missing:
        if topic not in present:
            out.append(
                f'<div class="row"><div class="name absent">{escape(topic)}</div>'
                f'<div class="track"></div></div>'
            )

    out.append(
        f'<div class="row"><div></div><div class="axis"><span>0s</span>'
        f"<span>{format_duration(report.duration_s)}</span></div></div>"
    )
    out.append(
        '<div class="legend"><span class="p">recorded</span>'
        '<span class="f">failure</span><span class="w">warning</span></div>'
    )
    return out


def _findings(report: Report) -> list[str]:
    out = ["<h2>Findings</h2>"]
    if not report.findings:
        message = (
            "No findings. The recording satisfies the spec."
            if report.spec_provided
            else "No spec given, so nothing was validated."
        )
        return out + [f'<p class="pass">{message}</p>']

    for finding in report.sorted_findings():
        topic = f" {escape(finding.topic)}" if finding.topic else ""
        clock = (
            f'<div class="clock">measured on {finding.clock.value}</div>'
            if finding.clock
            else ""
        )
        out.append(
            f'<div class="finding {finding.level.value}">'
            f'<div class="head"><span class="lvl">{finding.level.value}</span>{topic}'
            f" <span class=\"clock\">{escape(finding.code)}</span></div>"
            f'<div class="msg">{escape(finding.message)}</div>{clock}</div>'
        )
    return out


def render(report: Report) -> str:
    counts = report.counts()
    summary = ", ".join(
        f"{counts[level]} {level.value}"
        for level in (Level.FAIL, Level.WARN, Level.INFO)
        if counts[level]
    )
    body = "\n".join(_timeline(report) + _findings(report))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>baglint: {escape(report.path.name)}</title>
<style>{_STYLE}</style>
</head>
<body>
<main>
<h1>{escape(report.path.name)}</h1>
<p class="meta">{report.topic_count} topics &middot; {report.message_count:,} messages
&middot; {format_duration(report.duration_s)}{" &middot; " + summary if summary else ""}</p>
{body}
<footer>Generated by baglint. Bars show when each topic was recorded;
marks show where it failed.</footer>
</main>
</body>
</html>
"""
