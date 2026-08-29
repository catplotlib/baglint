from __future__ import annotations

import argparse
import sys
from pathlib import Path

from baglint import __version__
from baglint.runner import run
from baglint.spec import Spec, SpecError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="baglint",
        description="Semantic validation for robotics datasets (MCAP / rosbag2).",
    )
    p.add_argument("bag", type=Path, help="path to an .mcap file")
    p.add_argument("-s", "--spec", type=Path, help="YAML spec to validate against")
    p.add_argument("-f", "--format", choices=("text", "json"), default="text")
    p.add_argument("--strict", action="store_true", help="exit non-zero on WARN as well as FAIL")
    p.add_argument("--version", action="version", version=f"baglint {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.bag.exists():
        print(f"baglint: no such file: {args.bag}", file=sys.stderr)
        return 2

    try:
        spec = Spec.from_yaml(args.spec) if args.spec else Spec.empty()
    except (SpecError, OSError) as exc:
        print(f"baglint: bad spec: {exc}", file=sys.stderr)
        return 2

    try:
        report = run(args.bag, spec)
    except Exception as exc:  # unreadable or corrupt bag
        print(f"baglint: failed to read {args.bag}: {exc}", file=sys.stderr)
        return 2

    print(report.to_json() if args.format == "json" else report.to_text())
    return report.exit_code(strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
