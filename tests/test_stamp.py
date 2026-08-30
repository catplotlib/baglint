from baglint import Spec, run
from baglint.findings import Clock, Level
from fixtures import SynthBag

SPEC = Spec.from_dict({"topics": {"/imu": {"check_stamps": True}}})


def build(tmp_path, mutate=None):
    bag = SynthBag(tmp_path / "bag.mcap")
    topic = bag.topic("/imu", rate=100)
    if mutate:
        mutate(topic)
    return bag.write()


def test_monotonic_stamps_produce_no_findings(tmp_path):
    assert run(build(tmp_path), SPEC).findings == []


def test_backwards_stamp_fails(tmp_path):
    path = build(tmp_path, lambda t: t.rewind_stamps(count=1, ms=250))
    finding = next(f for f in run(path, SPEC).findings if f.code == "stamp_backwards")

    assert finding.level is Level.FAIL
    assert finding.clock is Clock.HEADER
    assert finding.details["count"] == 1
    # index 10 sits at 0.10 s; rewinding it 250 ms puts it 240 ms before its
    # predecessor at 0.09 s.
    assert 235 < finding.details["worst_ms"] < 245


def test_duplicate_stamps_warn_but_do_not_fail(tmp_path):
    path = build(tmp_path, lambda t: t.duplicate_stamps(count=3))
    report = run(path, SPEC)

    finding = next(f for f in report.findings if f.code == "stamp_duplicate")
    assert finding.level is Level.WARN
    assert finding.details["count"] == 3

    assert report.exit_code() == 0           # warnings alone do not fail
    assert report.exit_code(strict=True) == 1


def test_zero_stamps_are_reported_as_unset(tmp_path):
    path = build(tmp_path, lambda t: t.unset_stamps(count=4))
    finding = next(f for f in run(path, SPEC).findings if f.code == "stamp_unset")

    assert finding.level is Level.WARN
    assert finding.details["count"] == 4


def test_zero_stamp_does_not_masquerade_as_a_backwards_jump(tmp_path):
    """An unset stamp must not become the baseline, or every later message
    looks like it moved forwards from zero and the real ordering is lost."""
    path = build(tmp_path, lambda t: t.unset_stamps(count=1))
    codes = {f.code for f in run(path, SPEC).findings}

    assert "stamp_backwards" not in codes
    assert codes == {"stamp_unset"}


def test_stamps_are_not_checked_without_the_spec_key(tmp_path):
    path = build(tmp_path, lambda t: t.rewind_stamps(count=1, ms=250))
    spec = Spec.from_dict({"topics": {"/imu": {"min_rate": 50}}})

    assert run(path, spec).findings == []


def test_glob_pattern_enables_stamp_checking(tmp_path):
    """decode_topics resolves against the bag's channels, so a glob reaches
    topics whose names are not known until the file is opened."""
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/sensors/imu", rate=100).rewind_stamps(count=1, ms=250)
    spec = Spec.from_dict({"topics": {"/sensors/*": {"check_stamps": True}}})

    finding = next(f for f in run(bag.write(), spec).findings if f.code == "stamp_backwards")
    assert finding.topic == "/sensors/imu"
