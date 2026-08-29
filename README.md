# baglint

Semantic validation for robotics datasets. Point it at an MCAP file and a YAML
spec, and it tells you whether the recording is actually usable — with an exit
code, so it can gate CI.

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

That is captured output, not an illustration. Reproduce it with:

```console
$ python examples/make_demo_bag.py experiment_042.mcap
$ baglint experiment_042.mcap --spec examples/demo_spec.yaml
```

The scan above reads 680,884 messages in about six seconds, single-threaded,
because gap and rate analysis touch only `log_time` and never deserialize a
payload.

## What it is not

`mcap doctor` already validates MCAP *structure* — chunk CRCs, index integrity.
baglint assumes the file is well-formed and asks a different question: is the
data inside scientifically usable? Missing intervals, degraded rates, broken
transform chains, clock skew between sensors.

## No ROS required

MCAP embeds its own schemas, so baglint reads and decodes ROS 2 messages with
no ROS installation anywhere on the machine. It is a plain `pip install` and it
runs in any `python:3.12` CI container.

If you have ROS sourced in your shell, note that `/opt/ros/*/lib/python3.*/site-packages`
lands on `PYTHONPATH` and leaks into every virtualenv — which will pull ROS's
pytest plugins into this project's test run. The `Makefile` clears `PYTHONPATH`
for exactly that reason.

## The two clocks

Every bag carries two independent notions of time, and conflating them is the
usual bug in homegrown validation scripts:

| Clock | Meaning | A defect here means |
|---|---|---|
| `log_time` | when the recorder wrote the message | the recorder stalled — disk I/O, CPU starvation, a dead node |
| `header.stamp` | when the sensor sampled the data | the sensor or its driver misbehaved |

Every finding states which clock it was measured against.

## Spec

```yaml
topics:
  /joint_states:
    min_rate: 500
    max_gap_ms: 10

  /camera/*:          # glob patterns allowed; first match wins
    min_rate: 25

# Parsed and validated, but not yet enforced -- no check consumes this in v0.1.
transforms:
  required:
    - [camera_link, base_link]
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | no FAIL findings (add `--strict` to fail on WARN too) |
| 1 | at least one FAIL |
| 2 | bad invocation, unreadable bag, or malformed spec |

Use `--format json` for machine-readable output. Every finding carries a stable
`code` (`gap`, `rate_below_min`, `missing_topic`, ...) intended for filtering
and baselining in CI — those strings are treated as public API.

## Status

v0.1 implements presence, gap and rate checks. Planned, in order:
duplicate `header.stamp` detection, sustained rate-change detection, TF
connectivity over time, and a sensor clock-offset estimator.

## Development

```console
make install   # venv + editable install
make test
```
