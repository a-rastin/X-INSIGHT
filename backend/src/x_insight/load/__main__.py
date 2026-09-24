"""CLI entry: ``python -m x_insight.load`` prints a JSON load summary."""

from __future__ import annotations

import argparse
import json
import os


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synthetic load harness (S58 item 1, no provider calls)."
    )
    parser.add_argument("--host", default=os.environ.get("X_INSIGHT_LOAD_HOST", "ci"))
    parser.add_argument(
        "--dataset",
        default=os.environ.get("X_INSIGHT_LOAD_DATASET", "synthetic-ci-default"),
    )
    parser.add_argument(
        "--patients",
        type=int,
        default=int(os.environ.get("X_INSIGHT_LOAD_PATIENTS", "50")),
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=int(os.environ.get("X_INSIGHT_LOAD_THREADS", "4")),
    )
    parser.add_argument("--duration-s", type=float, default=5.0, dest="duration_s")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from x_insight.load.runner import run  # noqa: PLC0415

    result = run(
        host=str(args.host),
        dataset=str(args.dataset),
        duration_s=float(args.duration_s),
        patient_count=int(args.patients),
        concurrency=int(args.threads),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
