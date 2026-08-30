from baglint import Spec, run
from baglint.html import render
from fixtures import SynthBag

SPEC = Spec.from_dict(
    {"topics": {"/joint_states": {"max_gap_ms": 10}, "/tf": {"min_rate": 10}}}
)


def test_report_is_a_self_contained_document(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=500)
    html = render(run(bag.write(), SPEC))

    assert html.startswith("<!doctype html>")
    assert "</html>" in html
    # nothing may be fetched at render time, or CI artifacts break
    assert "http://" not in html and "https://" not in html
    assert "<script" not in html


def test_gaps_are_positioned_on_the_topic_track(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap", duration=10.0)
    bag.topic("/joint_states", rate=500).gap(at=5.0, ms=100)
    html = render(run(bag.write(), SPEC))

    # a gap halfway through a 10 s recording sits near 50% of the track
    assert 'class="mark fail" style="left:49.' in html or 'class="mark fail" style="left:50.' in html


def test_missing_topic_is_drawn_as_an_empty_track(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=500)
    html = render(run(bag.write(), SPEC))

    assert 'class="name absent">/tf<' in html


def test_clean_recording_says_so(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=500)
    bag.topic("/tf", rate=50)
    html = render(run(bag.write(), SPEC))

    assert "satisfies the spec" in html
    assert 'class="mark' not in html


def test_topic_names_are_escaped(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/a<script>x</script>", rate=100)
    html = render(run(bag.write(), Spec.empty()))

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_warnings_and_failures_are_marked_differently(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/imu", rate=100).rewind_stamps(count=1, ms=200).duplicate_stamps(count=3, at_index=50)
    spec = Spec.from_dict({"topics": {"/imu": {"check_stamps": True}}})
    html = render(run(bag.write(), spec))

    assert 'class="finding FAIL"' in html
    assert 'class="finding WARN"' in html


def test_cli_emits_html(tmp_path, capsys):
    from baglint.cli import main

    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=500).gap(at=4.0, ms=50)
    spec_file = tmp_path / "s.yaml"
    spec_file.write_text("topics:\n  /joint_states:\n    max_gap_ms: 10\n")

    assert main([str(bag.write()), "--spec", str(spec_file), "--format", "html"]) == 1
    assert capsys.readouterr().out.startswith("<!doctype html>")


def test_rate_failure_shades_the_whole_span(tmp_path):
    """A rate is measured across the recording, so there is no instant to mark.
    The track must still show the topic failed."""
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/camera/image", rate=10)
    spec = Spec.from_dict({"topics": {"/camera/image": {"min_rate": 25}}})
    html = render(run(bag.write(), spec))

    assert 'class="span fail"' in html


def test_untimed_warning_shades_in_amber(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/imu", rate=100).duplicate_stamps(count=5)
    spec = Spec.from_dict({"topics": {"/imu": {"check_stamps": True}}})
    html = render(run(bag.write(), spec))

    assert 'class="span warn"' in html


def test_missing_topic_does_not_shade_a_track_it_has_none_of(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=500)
    html = render(run(bag.write(), SPEC))

    assert 'class="span' not in html
