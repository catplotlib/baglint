# baglint

Validates the contents of MCAP recordings against a declarative specification.
Checks for missing topics, recording gaps and rate violations, and returns a
non-zero exit status when a recording does not satisfy the specification.

Validation of the MCAP container itself, such as chunk CRCs and index
integrity, is out of scope. Use `mcap doctor` for that.

## Requirements

* Python 3.10 or later

## Installation

```console
$ python3 -m venv .venv
$ .venv/bin/pip install -e .
```

When ROS 2 is sourced, `/opt/ros/$ROS_DISTRO/lib/python3.*/site-packages` is on
`PYTHONPATH` and is inherited by the virtual environment, which causes ROS
pytest plugins to load during test runs. Clear it when invoking the tool:

```console
$ env -u PYTHONPATH .venv/bin/baglint --help
```

## Usage

```console
$ baglint BAG [-s SPEC] [-f {text,json}] [--strict]
$ baglint BAG --init [--margin FRACTION]
```

| Option | Description |
| --- | --- |
| `-s`, `--spec` | Specification file to validate against |
| `-f`, `--format` | Output format, `text` (default) or `json` |
| `--strict` | Exit non-zero on `WARN` findings as well as `FAIL` |
| `--init` | Print a specification generated from the recording instead of validating it |
| `--margin` | With `--init`, the fraction below the observed rate at which to set `min_rate`. Default `0.1` |
| `--version` | Print version and exit |

Without `-s`, no checks run and nothing is validated.

## Generating a specification

`--init` writes a specification describing a recording, which is the practical
way to produce a first one:

```console
$ baglint good_run.mcap --init > spec.yaml
$ baglint experiment_042.mcap --spec spec.yaml
```

`min_rate` is set below each topic's observed mean rate by `--margin`, and
`max_gap_ms` to twice the worst interval observed. Topics with fewer than ten
messages are generated as presence-only, since a mean rate over so few samples
describes the recording length rather than the publisher.

The bounds describe the recording they came from, defects included. Generate
from a run that is known to be good, and treat the result as a starting point.

## Specification

Topic keys accept glob patterns. The first matching entry applies, so list
specific topics before wildcards.

```yaml
topics:
  /joint_states:
    min_rate: 490
    max_gap_ms: 10

  /camera/*:
    min_rate: 25

  /diagnostics:
    required: false
```

| Key | Type | Description |
| --- | --- | --- |
| `min_rate` | float | Minimum mean publication rate in Hz, measured over the topic's own span |
| `max_gap_ms` | float | Maximum permitted interval between consecutive messages |
| `required` | bool | Whether a topic named literally must be present. Default `true` |
| `check_stamps` | bool | Validate `header.stamp` ordering. Default `false`, as it deserializes payloads |

A `transforms.required` list of `[parent, child]` frame pairs is parsed and
validated, but no check consumes it yet.

## Output

```console
$ baglint experiment_042.mcap --spec examples/demo_spec.yaml
experiment_042.mcap
  3 topics · 680,884 messages · 18m32s

FAIL /camera/image
  rate 12.4 Hz below minimum 25 Hz  [log_time]

FAIL /joint_states
  3 missing interval(s) >10 ms (worst 122.0 ms at 904.00 s)  [log_time]

FAIL /tf
  required by spec but no messages in bag

3 findings: 3 FAIL
```

To regenerate the recording used above:

```console
$ python examples/make_demo_bag.py experiment_042.mcap
```

`--format json` emits the same findings for machine consumption. Each carries a
stable `code`, intended for filtering and baselining in CI:

| Code | Level | Meaning |
| --- | --- | --- |
| `gap` | FAIL | Consecutive messages exceeded `max_gap_ms` |
| `rate_below_min` | FAIL | Mean rate fell below `min_rate` |
| `rate_unmeasurable` | FAIL | Fewer than two messages, so no rate can be computed |
| `missing_topic` | FAIL | A required topic carried no messages |
| `stamp_backwards` | FAIL | A `header.stamp` preceded the stamp before it |
| `stamp_duplicate` | WARN | A message repeated the previous `header.stamp` |
| `stamp_unset` | WARN | A message carried a zero `header.stamp` |
| `stamp_unavailable` | WARN | `check_stamps` was set on a message type without a header |

## Message timestamps

Each message carries two timestamps, and findings state which one was used:

| Timestamp | Set by | A defect indicates |
| --- | --- | --- |
| `log_time` | the recorder, on write | the recorder stalled: disk I/O, CPU starvation, a terminated node |
| `header.stamp` | the publisher, at sample time | the sensor or its driver misbehaved |

Gap and rate checks read `log_time`. Stamp checks read `header.stamp` and are
enabled per topic with `check_stamps`, which is off by default because it
requires deserializing every message on that topic:

```yaml
topics:
  /imu:
    check_stamps: true
```

A stamp that moves backwards is reported as a failure. Downstream consumers
such as tf2, `message_filters` and the SLAM backends assume a non-decreasing
stamp sequence per topic, and do not report the violation themselves. Duplicate and zero stamps
are reported as warnings.

A zero stamp is treated as never populated rather than as a timestamp, so it
does not become the baseline for the messages that follow it.

## Exit codes

| Code | Condition |
| --- | --- |
| 0 | No `FAIL` findings. With `--strict`, no `WARN` findings either |
| 1 | At least one finding at or above the failing level |
| 2 | Invalid arguments, unreadable recording, or malformed specification |

## Development

```console
$ make install
$ make test
```

Tests construct MCAP recordings with injected defects at known offsets. See
`tests/fixtures.py`.
