#!/usr/bin/env python3
"""Generate the demo recording used for the README's example output.

The synthetic-bag helper lives in tests/ rather than in the package: it is a
test utility, not shipped API, so this script puts it on the path explicitly.

    python examples/make_demo_bag.py run_028.mcap
    baglint run_028.mcap --spec examples/demo_spec.yaml
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from fixtures import SynthBag  # noqa: E402


def build(path: Path) -> Path:
    bag = SynthBag(path, duration=120.0)

    # A 500 Hz control loop that stalls twice.
    bag.topic("/joint_states", rate=500).gap(at=31.2, ms=64).gap(at=88.5, ms=110)

    # A camera that degrades partway through the run.
    bag.topic("/camera/image", rate=30).rate_change(at=40.0, new_rate=21.0)

    # A flaky IMU driver: a clock reset, repeated stamps, some never populated.
    (
        bag.topic("/imu", rate=100)
        .rewind_stamps(count=1, at_index=5000, ms=200)
        .duplicate_stamps(count=18, at_index=400)
        .unset_stamps(count=6, at_index=9000)
    )

    # Published once, so no rate can be measured.
    bag.topic("/diagnostics", rate=0.008)

    # The transform chain drops out while the mount driver is down.
    bag.transform("base_link", "torso", static=True)
    bag.transform("torso", "camera_mount", rate=50)
    bag.transform("camera_mount", "camera_link", rate=50, end=60.0)
    bag.transform("camera_mount", "camera_link", rate=50, start=74.0)

    # /scan is never recorded, though the spec requires it.
    return bag.write()


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "run_028.mcap")
    print(f"wrote {build(out)}")
