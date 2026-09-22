"""CLI for the S15 DDI ingestion seam: `python -m x_insight.ddi build ...`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from x_insight.ddi import build


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m x_insight.ddi")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--sources", required=True, type=Path)
    build_parser.add_argument("--terminology", type=Path)
    build_parser.add_argument("--review-manifest", type=Path)
    build_parser.add_argument("--output", required=True, type=Path)
    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--sources", required=True, type=Path)
    report_parser.add_argument("--terminology", type=Path)
    report_parser.add_argument("--review-manifest", type=Path)
    report_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    result = build(
        args.sources,
        terminology=args.terminology,
        review_manifest=args.review_manifest,
    )
    report = result["report"]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "candidates.json").write_text(
        json.dumps(result["candidates"], indent=2), encoding="utf-8"
    )
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    if args.command == "report":
        # report-only mode: every discovered file gets passed/failed
        # status, category counts, checksum and diagnostic location;
        # failures stay in the denominator (S16 slice 3)
        return 0
    if not report["ok"]:
        print(
            "build failed: documents did not validate; see report.json",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
