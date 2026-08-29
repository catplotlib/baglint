#!/usr/bin/env python3
"""Generate the demo bag used for the README's example output.

The synthetic-bag helper lives in tests/ rather than in the package: it is a
test utility, not shipped API, so this script puts it on the path explicitly.

    python examples/make_demo_bag.py /tmp/experiment_042.mcap
    baglint /tmp/experiment_042.mcap --spec examples/demo_spec.yaml
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from fixtures import SynthBag  # noqa: E402


def build(path: Path) -> Path:
    bag = SynthBag(path, duration=1112.0)

    # A 500 Hz control loop that stalls three times.
    bag.topic("/joint_states", rate=500).gap(at=180.0, ms=52).gap(at=312.4, ms=38).gap(at=904.0, ms=120)

    # A camera that never reaches its configured frame rate.
    bag.topic("/camera/image", rate=12.4)

    bag.topic("/imu", rate=100)

    # /tf is absent entirely, which the spec requires.
    return bag.write()


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "experiment_042.mcap")
    print(f"wrote {build(out)}")
