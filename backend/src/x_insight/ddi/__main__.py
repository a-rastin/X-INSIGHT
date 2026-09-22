"""CLI for the DDI seams: ``python -m x_insight.ddi build|report|publish ...``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from x_insight.ddi import build


def _write_publish_anomaly(manifest_path: Path, reason: str) -> None:
    """Write a ``*anomal*`` rejection report next to the manifest (S18 slice 4).

    Never raises: a failed anomaly write must not mask the rejection exit.
    No patient data enters this file; only the gate reason, manifest path,
    and dataset hash when computable (None when gates fail before hashing).
    """
    payload = {
        "ok": False,
        "reason": reason,
        "manifest": str(manifest_path),
        "dataset_hash": None,
    }
    try:
        manifest_path.with_name(f"{manifest_path.stem}.anomaly.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    except OSError:
        try:
            (Path.cwd() / "ddi-publish-anomaly.json").write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        except OSError:
            pass


def _run_publish(args: argparse.Namespace) -> int:
    from x_insight.ddi.publish import PublishRejectedError, publish_release

    manifest_path: Path = args.manifest
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        reason = f"publish rejected: unreadable manifest {manifest_path}: {exc}"
        print(reason, file=sys.stderr)
        _write_publish_anomaly(manifest_path, reason)
        return 1
    if not isinstance(manifest, dict):
        reason = f"publish rejected: manifest must be a JSON object: {manifest_path}"
        print(reason, file=sys.stderr)
        _write_publish_anomaly(manifest_path, reason)
        return 1
    try:
        record = publish_release(manifest, database_url=args.database_url)
    except PublishRejectedError as exc:
        reason = f"publish rejected: {exc}"
        print(reason, file=sys.stderr)
        _write_publish_anomaly(manifest_path, reason)
        return 1
    print(
        json.dumps(
            {
                "id": record["id"],
                "version": record["version"],
                "dataset_hash": record["dataset_hash"],
            }
        )
    )
    return 0


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
    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("--manifest", required=True, type=Path)
    publish_parser.add_argument("--database-url", default=None)
    args = parser.parse_args(argv)

    if args.command == "publish":
        return _run_publish(args)

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
