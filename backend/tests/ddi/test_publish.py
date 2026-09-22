"""S18 slice 1 RED ONLY: publication rejects invalid releases; import is atomic.

Scope (slice 1 ONLY): rejection gates plus no-partial-import, all through the
NEW public publish seam (T3 library form; T1 PostgreSQL reads through the same
module's public read function). This file is RED: ``x_insight.ddi.publish``
does not exist yet, so every test fails with ``ModuleNotFoundError`` at the
``_seam()`` import. Do NOT implement the seam to make it pass here.

Proposed minimal public seam for the backend agent (small and deep):

  x_insight.ddi.publish.PublishRejectedError(ValueError)
      Raised when any publication gate fails. Nothing is imported.
  x_insight.ddi.publish.publish_release(manifest, *, database_url=None) -> dict
      ``manifest`` is a dict (a path to an equivalent JSON file is an accepted
      future spelling). Validates the gates below, then stages/imports the
      release as ONE atomic transaction. Returns the release record on success
      (success paths are slices 2-4, NOT asserted here).
  x_insight.ddi.publish.list_releases(*, database_url=None) -> list[dict]
      Public read seam. Slice 1 asserts rejected publications leave it
      unchanged (no raw-SQL/side-channel assertions in tests).
  Optional sibling (not asserted here):
      python -m x_insight.ddi publish --manifest <reviewed-manifest>
      Exit nonzero on rejection, zero on success.

Proposed manifest keys (all synthetic test data, ``synthetic_fixture: True``):

  sources_dir, terminology (path or None), source_inventory
  ([{relative_path, sha256, byte_count}] covering every discovered source),
  terminology_provenance ({path, sha256} whenever terminology is given),
  reviewer (non-null person id), decision ("approved" required),
  approvals ([{category, entry_name, reviewer, decision}] — one approved
  record per contraindicated/serious entry), coverage_exclusions
  ([{name, reason, reviewer, decision}] — the only way an unresolved entity
  leaves the release).

Proposed gates (ALL must pass; any failure raises PublishRejectedError):

  G1 counts: every document's declared/parsed category counts agree
      (tampered serious 4 declared / 3 parsed rejects).
  G2 resolution: every entry name needed by the release resolves against the
      controlled terminology or carries an approved coverage exclusion
      ("captopril" resolves nowhere in the slice-1 terminology fixture and
      has no exclusion, so it rejects).
  G3 provenance: source_inventory present and matching every discovered
      source; terminology_provenance present whenever terminology is given.
  G4 review: reviewer non-null, decision == "approved", and every
      contraindicated/serious entry has an approved approval record.
  G5 atomicity: a rejected publication imports nothing observable through
      list_releases().

Source grounding (read-only; pinned literals, never parser output):

  docs/medical-docs/DDI-text/Antidiabetic Agents/Sitagliptin.txt headings
  Contraindicated (0) L97 / Serious (4) L99 / Monitor Closely (92) L122 /
  Minor (70) L658 (plan.md 6.2; fixtures/sitagliptin-provenance.json).
  Serious entries [erdafitinib, ethanol, sotorasib, tepotinib] and the
  monitor_closely entry "captopril" are pinned from the source via the
  existing ingestion tests. "captopril" is absent from the synthetic
  slice-1 terminology fixture (concepts: sitagliptin, ofloxacin only).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ORIGINAL = (
    _REPO_ROOT
    / "docs"
    / "medical-docs"
    / "DDI-text"
    / "Antidiabetic Agents"
    / "Sitagliptin.txt"
)
_PROVENANCE_PATH = _FIXTURES / "sitagliptin-provenance.json"
_TERMINOLOGY = _FIXTURES / "synthetic-terminology-s17-slice1.json"

# Pinned source literals: monograph category headings (L97/99/122/658) and
# plan.md 6.2 — never parser output.
EXPECTED_COUNTS: dict[str, int] = {
    "contraindicated": 0,
    "serious": 4,
    "monitor_closely": 92,
    "minor": 70,
}
# Pinned serious entry headers in source order (existing ingestion tests).
SERIOUS_ENTRY_NAMES: list[str] = [
    "erdafitinib",
    "ethanol",
    "sotorasib",
    "tepotinib",
]
# Pinned monitor_closely entry; absent from the synthetic terminology below.
UNRESOLVED_PIN = "captopril"


def _seam() -> tuple[Any, Any, Any]:
    """Import the NEW S18 publish seam.

    RED: raises ModuleNotFoundError until the backend agent implements
    ``x_insight.ddi.publish``. Returns
    (PublishRejectedError, list_releases, publish_release).
    """
    from x_insight.ddi.publish import (
        PublishRejectedError,
        list_releases,
        publish_release,
    )

    return PublishRejectedError, list_releases, publish_release


def _provenance() -> dict[str, Any]:
    return json.loads(_PROVENANCE_PATH.read_text(encoding="utf-8"))


def _make_pristine_sources_dir(tmp_path: Path, provenance: dict[str, Any]) -> Path:
    """Copy the original monograph byte-identically under a temp sources dir."""
    sources_dir = tmp_path / "sources"
    copy_path = sources_dir / "Antidiabetic Agents" / "Sitagliptin.txt"
    copy_path.parent.mkdir(parents=True)
    shutil.copyfile(_ORIGINAL, copy_path)
    assert (
        hashlib.sha256(copy_path.read_bytes()).hexdigest()
        == provenance["original"]["sha256"]
    )
    return sources_dir


def _make_tampered_sources_dir(tmp_path: Path, provenance: dict[str, Any]) -> Path:
    """Delete the erdafitinib serious block (original lines 101-105 + blank 106).

    Same tampered-copy pattern as the ingestion count-mismatch test: declared
    serious stays 4 (pinned EXPECTED_COUNTS literal), parsed drops to 3.
    """
    original_bytes = _ORIGINAL.read_bytes()
    assert (
        hashlib.sha256(original_bytes).hexdigest() == provenance["original"]["sha256"]
    )
    lines = original_bytes.splitlines(keepends=True)
    assert lines[98] == b"Serious (4)\n"
    assert lines[99] == b"\n"
    assert lines[100] == b"erdafitinib\n"
    assert lines[101].startswith(b"erdafitinib will increase")
    assert lines[104] == b"substrates with narrow therapeutic index.\n"
    assert lines[105] == b"\n"
    assert lines[106] == b"ethanol\n"
    sources_dir = tmp_path / "sources"
    copy_path = sources_dir / "Antidiabetic Agents" / "Sitagliptin.txt"
    copy_path.parent.mkdir(parents=True)
    copy_path.write_bytes(b"".join(lines[:100] + lines[106:]))
    return sources_dir


def _base_manifest(sources_dir: Path) -> dict[str, Any]:
    """Otherwise-complete synthetic manifest; tests break exactly one gate."""
    inventory = []
    for path in sorted(sources_dir.rglob("*.txt")):
        data = path.read_bytes()
        inventory.append(
            {
                "relative_path": path.relative_to(sources_dir).as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "byte_count": len(data),
            }
        )
    terminology_bytes = _TERMINOLOGY.read_bytes()
    return {
        "synthetic_fixture": True,
        "sources_dir": str(sources_dir),
        "terminology": str(_TERMINOLOGY),
        "source_inventory": inventory,
        "terminology_provenance": {
            "path": str(_TERMINOLOGY),
            "sha256": hashlib.sha256(terminology_bytes).hexdigest(),
        },
        "reviewer": "dr-synthetic",
        "decision": "approved",
        "approvals": [
            {
                "category": "serious",
                "entry_name": name,
                "reviewer": "dr-synthetic",
                "decision": "approved",
            }
            for name in SERIOUS_ENTRY_NAMES
        ],
        "coverage_exclusions": [],
    }


def test_publish_rejects_count_mismatch(tmp_path: Path) -> None:
    """G1: declared 4 / parsed 3 serious entries reject publication."""
    PublishRejectedError, _, publish_release = _seam()
    provenance = _provenance()
    sources_dir = _make_tampered_sources_dir(tmp_path, provenance)
    assert EXPECTED_COUNTS["serious"] == 4

    manifest = _base_manifest(sources_dir)
    with pytest.raises(PublishRejectedError):
        publish_release(manifest)


def test_publish_rejects_unresolved_entity_needed_by_release(
    tmp_path: Path,
) -> None:
    """G2: UNRESOLVED_PIN has no concept and no exclusion, so it rejects."""
    PublishRejectedError, _, publish_release = _seam()
    provenance = _provenance()
    sources_dir = _make_pristine_sources_dir(tmp_path, provenance)

    terminology = json.loads(_TERMINOLOGY.read_text(encoding="utf-8"))
    assert terminology["_synthetic_fixture"] is True
    concept_ids = [concept["id"] for concept in terminology["concepts"]]
    assert UNRESOLVED_PIN not in concept_ids

    manifest = _base_manifest(sources_dir)
    assert manifest["coverage_exclusions"] == []
    with pytest.raises(PublishRejectedError):
        publish_release(manifest)


def test_publish_rejects_absent_provenance(tmp_path: Path) -> None:
    """G3: missing source inventory or terminology provenance rejects."""
    PublishRejectedError, _, publish_release = _seam()
    provenance = _provenance()
    sources_dir = _make_pristine_sources_dir(tmp_path, provenance)

    manifest = _base_manifest(sources_dir)
    del manifest["source_inventory"]
    with pytest.raises(PublishRejectedError):
        publish_release(manifest)

    manifest = _base_manifest(sources_dir)
    del manifest["terminology_provenance"]
    with pytest.raises(PublishRejectedError):
        publish_release(manifest)


def test_publish_rejects_required_unreviewed_evidence(tmp_path: Path) -> None:
    """G4: null reviewer, non-approved decision, or missing serious approvals."""
    PublishRejectedError, _, publish_release = _seam()
    provenance = _provenance()
    sources_dir = _make_pristine_sources_dir(tmp_path, provenance)
    assert len(SERIOUS_ENTRY_NAMES) == EXPECTED_COUNTS["serious"]

    manifest = _base_manifest(sources_dir)
    manifest["reviewer"] = None
    with pytest.raises(PublishRejectedError):
        publish_release(manifest)

    manifest = _base_manifest(sources_dir)
    manifest["decision"] = "draft"
    with pytest.raises(PublishRejectedError):
        publish_release(manifest)

    manifest = _base_manifest(sources_dir)
    manifest["approvals"] = []
    with pytest.raises(PublishRejectedError):
        publish_release(manifest)


def test_publish_rejection_imports_no_partial_release(tmp_path: Path) -> None:
    """G5: staging/import is one coherent operation — rejection imports nothing."""
    PublishRejectedError, list_releases, publish_release = _seam()
    provenance = _provenance()
    sources_dir = _make_tampered_sources_dir(tmp_path, provenance)

    before = list_releases()
    with pytest.raises(PublishRejectedError):
        publish_release(_base_manifest(sources_dir))
    assert list_releases() == before


# ---------------------------------------------------------------------------
# S18 slice 2 RED ONLY: corpus report + owner review records.
#
# Scope (slice 2 ONLY): a pure summary over the ALREADY-BUILT ingestion
# output (candidates + report dicts from ``x_insight.ddi.ingestion.build``).
# No DB, no publish, no terminology writes. Every test below imports the NEW
# seam and therefore FAILS with ImportError until the backend agent
# implements it. Do NOT implement it here.
#
# Proposed minimal public seam for the backend agent (ONE small deep seam;
# do NOT extend publish_release in this slice):
#
#   x_insight.ddi.publish.build_corpus_report(
#       candidates: dict, report: dict) -> dict
#
# ``candidates``/``report`` are the two dicts returned by
# ``x_insight.ddi.ingestion.build(sources_dir)`` (documents with
# count_checks/anomalies; candidates with categories/entries/paragraphs/
# direction/raw_text/spans, PARSER_VERSION). Returns a plain dict with:
#
#   discovered: int, processed: int, passed: int, failed: int,
#   severity_counts: {contraindicated, serious, monitor_closely, minor},
#   total_entries: int, unique_pairs: int, duplicate_evidence_count: int,
#   conflicts: [{pair_key, severities, sources}],
#   unknown_names: list[str],
#   document_hashes: [{relative_path, sha256}],
#   parser_version: str,
#   review_records: [{kind, source_path, span, raw_text, ...}]
#
# Pair identity is canonical_pair_key(subject, entry-name); the pinned
# duplicate below is therefore the literal "ofloxacin:sitagliptin" (never
# computed via the code under test). review_records must list every
# contraindicated/serious entry (kind "high_risk") + every conflict (kind
# "conflict") + every anomaly (kind "anomaly"), each carrying source_path /
# span / raw_text for owner review.
#
# Source grounding (read-only; pinned literals, never parser output):
# Sitagliptin headings 0/4/92/70 (L97/99/122/658), 166 total entries,
# ofloxacin monitor 525-529 + minor 912-914 (duplicate/conflict evidence),
# erdafitinib serious 101-105, serious heading span 99, parser "ddi-ingest-1",
# copy sha e7c9bc45ed5b3f829dfe8e29b015ee727645db2f3ed6cad8de99fea2dcd4022f.
# ---------------------------------------------------------------------------


def _corpus_seam() -> Any:
    """Import the NEW S18 slice-2 seam.

    RED: raises ImportError until the backend agent implements
    ``x_insight.ddi.publish.build_corpus_report``.
    """
    from x_insight.ddi.publish import build_corpus_report

    return build_corpus_report


def _ingestion_build() -> Any:
    """Existing ingestion build seam (already green; not under test)."""
    from x_insight.ddi.ingestion import build

    return build


def test_build_corpus_report_summarizes_pristine_sitagliptin_corpus(
    tmp_path: Path,
) -> None:
    """Slice 2: pristine single-document corpus summary pins."""
    build_corpus_report = _corpus_seam()
    build = _ingestion_build()
    provenance = _provenance()
    sources_dir = _make_pristine_sources_dir(tmp_path, provenance)

    built = build(sources_dir)
    corpus = build_corpus_report(built["candidates"], built["report"])

    # Discovered/processed/pass/fail: one pristine document, report ok.
    assert corpus["discovered"] == 1
    assert corpus["processed"] == 1
    assert corpus["passed"] == 1
    assert corpus["failed"] == 0

    # Severity counts pinned from monograph headings (L97/99/122/658).
    assert corpus["severity_counts"] == {
        "contraindicated": 0,
        "serious": 4,
        "monitor_closely": 92,
        "minor": 70,
    }
    assert corpus["total_entries"] == 166

    # Only ofloxacin repeats, so 165 unique pairs and 1 extra evidence.
    assert corpus["unique_pairs"] == 165
    assert corpus["duplicate_evidence_count"] == 1

    # No terminology passed to build(), so no resolution attempted.
    assert corpus["unknown_names"] == []

    # Document hashes pin the byte-identical copy identity.
    hashes = corpus["document_hashes"]
    assert len(hashes) == 1
    assert hashes[0]["relative_path"] == "Antidiabetic Agents/Sitagliptin.txt"
    assert (
        hashes[0]["sha256"]
        == "e7c9bc45ed5b3f829dfe8e29b015ee727645db2f3ed6cad8de99fea2dcd4022f"
    )

    # Parser version pinned literal (matches ingestion PARSER_VERSION).
    assert corpus["parser_version"] == "ddi-ingest-1"

    # The ofloxacin duplicate carries different severities -> one conflict.
    # pair_key is the pinned literal "ofloxacin:sitagliptin", never computed.
    conflicts = corpus["conflicts"]
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["pair_key"] == "ofloxacin:sitagliptin"
    assert set(conflict["severities"]) == {"monitor_closely", "minor"}
    spans = [
        source["span"]
        for source in conflict["sources"]
        if isinstance(source, dict) and "span" in source
    ]
    assert {"start_line": 525, "end_line": 529} in spans
    assert {"start_line": 912, "end_line": 914} in spans


def test_build_corpus_report_review_records_cover_high_risk_and_conflict(
    tmp_path: Path,
) -> None:
    """Slice 2: owner gets concrete high-risk + conflict review records."""
    build_corpus_report = _corpus_seam()
    build = _ingestion_build()
    provenance = _provenance()
    sources_dir = _make_pristine_sources_dir(tmp_path, provenance)

    built = build(sources_dir)
    corpus = build_corpus_report(built["candidates"], built["report"])
    review_records = corpus["review_records"]

    # High-risk: 0 contraindicated + 4 pinned serious entries.
    high_risk = [r for r in review_records if r["kind"] == "high_risk"]
    assert len(high_risk) == 4
    assert {r["entry_name"] for r in high_risk} == set(SERIOUS_ENTRY_NAMES)
    for record in high_risk:
        assert record["source_path"] == "Antidiabetic Agents/Sitagliptin.txt"
        assert record["severity"] == "serious"
        assert isinstance(record["span"], dict)
        assert record["raw_text"].strip() != ""

    # Erdafitinib serious entry span pinned from provenance (101-105).
    erdafitinib = next(r for r in high_risk if r["entry_name"] == "erdafitinib")
    assert erdafitinib["span"] == {"start_line": 101, "end_line": 105}
    assert "erdafitinib will increase" in erdafitinib["raw_text"]

    # Conflict: the ofloxacin duplicate-direction pair with both evidences.
    conflicts = [r for r in review_records if r["kind"] == "conflict"]
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["pair_key"] == "ofloxacin:sitagliptin"
    assert set(conflict["severities"]) == {"monitor_closely", "minor"}
    assert conflict["source_path"] == "Antidiabetic Agents/Sitagliptin.txt"
    assert conflict["raw_text"].strip() != ""

    # Pristine corpus carries no anomalies, so no anomaly review records.
    assert [r for r in review_records if r["kind"] == "anomaly"] == []


def test_build_corpus_report_flags_failed_document_and_anomaly_review(
    tmp_path: Path,
) -> None:
    """Slice 2: tampered corpus fails with an enumerated anomaly record."""
    build_corpus_report = _corpus_seam()
    build = _ingestion_build()
    provenance = _provenance()
    sources_dir = _make_tampered_sources_dir(tmp_path, provenance)

    built = build(sources_dir)
    corpus = build_corpus_report(built["candidates"], built["report"])

    # One document discovered/processed, zero pass, one fail.
    assert corpus["discovered"] == 1
    assert corpus["processed"] == 1
    assert corpus["passed"] == 0
    assert corpus["failed"] == 1

    # Serious drops 4 -> 3 (erdafitinib block removed); total 165.
    assert corpus["severity_counts"] == {
        "contraindicated": 0,
        "serious": 3,
        "monitor_closely": 92,
        "minor": 70,
    }
    assert corpus["total_entries"] == 165
    assert corpus["unique_pairs"] == 164
    assert corpus["duplicate_evidence_count"] == 1
    assert corpus["unknown_names"] == []
    assert corpus["parser_version"] == "ddi-ingest-1"

    hashes = corpus["document_hashes"]
    assert len(hashes) == 1
    assert hashes[0]["relative_path"] == "Antidiabetic Agents/Sitagliptin.txt"

    # The count-mismatch anomaly is enumerated with pinned literals.
    anomalies = [r for r in corpus["review_records"] if r["kind"] == "anomaly"]
    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly["code"] == "count_mismatch"
    assert anomaly["source_path"] == "Antidiabetic Agents/Sitagliptin.txt"
    assert anomaly["span"] == {"start_line": 99, "end_line": 99}
    assert anomaly["declared_count"] == 4
    assert anomaly["parsed_count"] == 3


# ---------------------------------------------------------------------------
# S18 slice 3 RED ONLY: approved corrections, duplicate evidence, coverage.
#
# Scope (slice 3 ONLY): corrections applied without touching originals,
# duplicate-direction evidence preserved with source severity separate from
# management, and explicit complete/limited coverage gating — all through
# the public publish seam plus a public read. Every test below FAILS until
# the backend agent implements the missing handling: correction/coverage
# keys are ignored (unexpected success or missing rejection) or the new
# read seam is absent (ImportError) or stored evidence fields are absent.
# Do NOT implement the seam here.
#
# Proposed minimal public seam for the backend agent (small and deep; do
# NOT extend build_corpus_report in this slice):
#
#   x_insight.ddi.publish.PublishRejectedError (exists)
#   x_insight.ddi.publish.publish_release(manifest, *, database_url=None)
#       (exists; extend to accept the two new manifest keys below, still
#       atomic G5: any rejection imports nothing observable).
#   x_insight.ddi.publish.get_release(version, *, database_url=None) -> dict
#       NEW public read. Returns the stored release record for ``version``
#       with keys: id, version, dataset_hash, source_inventory,
#       terminology_provenance, review_record, corrections, coverage,
#       evidence, created_at. ``evidence`` is a list of rows each with
#       {pair_key, source_severity, management, direction, source_path,
#       span, raw_text}. Raises PublishRejectedError (or KeyError/
#       ValueError) when the version is unknown — tests only call it for
#       versions just published.
#
# Proposed manifest keys (all synthetic test data, ``synthetic_fixture``):
#
#   corrections: [{relative_path, category, entry_name, span,
#       corrected_severity?, corrected_management?, reviewer, decision}]
#       Exactly one approved record per corrected entry; reviewer non-null
#       person id, decision == "approved" required. At least one of
#       corrected_severity / corrected_management present. Synthetic
#       strings are conspicuously "SYNTHETIC-..." (never clinical).
#   coverage: {scope: "complete" | "limited", exclusions: [...]}
#       ``exclusions`` items are {name, reason, reviewer, decision} with
#       decision == "approved". Legacy ``coverage_exclusions`` keeps its
#       slice-1 meaning during transition; when ``coverage`` is present its
#       ``exclusions`` govern. ``scope`` missing/unknown REJECTS; scope
#       "complete" with ANY unresolved name or failed document REJECTS
#       (approved exclusions do not make a partial corpus complete);
#       scope "limited" PUBLISHES only when every unresolved/failed item
#       carries an approved exclusion.
#
# Source grounding (read-only; pinned literals, never parser output):
# copy sha e7c9bc45ed5b3f829dfe8e29b015ee727645db2f3ed6cad8de99fea2dcd4022f,
# captopril monitor_closely entry span 205-215, ofloxacin monitor 525-529
# direction ofloxacin->sitagliptin vs minor 912-914 unknown direction,
# pair literals "captopril:sitagliptin" / "ofloxacin:sitagliptin" (same
# normalized sorted-join form as slice 2), captopril source severity
# "monitor_closely". Real sources are hashed before/after publish and
# never written. Never content/ddi/aliases.json as oracle.
# ---------------------------------------------------------------------------


def _release_seam() -> Any:
    """Import the NEW S18 slice-3 read seam.

    RED: raises ImportError until the backend agent implements
    ``x_insight.ddi.publish.get_release``.
    """
    from x_insight.ddi.publish import get_release

    return get_release


def _slice3_exclusions(sources_dir: Path) -> list[dict[str, Any]]:
    """Approved limited-coverage exclusions for every unresolved name.

    Fixture SETUP only (not under test): uses the already-green ingestion
    build seam to enumerate the unresolved set for the synthetic slice-1
    terminology (164 names; only sitagliptin/ofloxacin resolve), so the
    success-path manifests satisfy G2. Expected evidence values below are
    pinned literals, never derived from this helper.
    """
    from x_insight.ddi.ingestion import build

    built = build(sources_dir, _TERMINOLOGY)
    unresolved = built["report"]["terminology"]["unresolved_names"]
    assert UNRESOLVED_PIN in unresolved
    return [
        {
            "name": name,
            "reason": "SYNTHETIC-limited coverage exclusion for test only",
            "reviewer": "dr-synthetic",
            "decision": "approved",
        }
        for name in unresolved
    ]


def _slice3_manifest(
    sources_dir: Path, exclusions: list[dict[str, Any]], version: str
) -> dict[str, Any]:
    """Success-path manifest using BOTH legacy and new coverage keys."""
    import uuid as _uuid

    _ = _uuid
    manifest = _base_manifest(sources_dir)
    manifest["coverage_exclusions"] = list(exclusions)
    manifest["coverage"] = {"scope": "limited", "exclusions": list(exclusions)}
    manifest["corrections"] = []
    manifest["version"] = version
    return manifest


def test_publish_applies_approved_correction_without_modifying_source(
    tmp_path: Path,
) -> None:
    """Slice 3.1: approved correction publishes; original bytes untouched."""
    import uuid

    _, _, publish_release = _seam()
    get_release = _release_seam()
    provenance = _provenance()
    sources_dir = _make_pristine_sources_dir(tmp_path, provenance)
    copy_path = sources_dir / "Antidiabetic Agents" / "Sitagliptin.txt"
    before = copy_path.read_bytes()
    assert hashlib.sha256(before).hexdigest() == provenance["original"]["sha256"]

    exclusions = _slice3_exclusions(sources_dir)
    version = f"s18-slice3-corr-{uuid.uuid4().hex[:8]}"
    manifest = _slice3_manifest(sources_dir, exclusions, version)
    manifest["corrections"] = [
        {
            "relative_path": "Antidiabetic Agents/Sitagliptin.txt",
            "category": "monitor_closely",
            "entry_name": "captopril",
            "span": {"start_line": 205, "end_line": 215},
            "corrected_management": (
                "SYNTHETIC-approved management note for captopril "
                "monitor entry - test only, never clinical"
            ),
            "reviewer": "dr-synthetic",
            "decision": "approved",
        }
    ]

    record = publish_release(manifest)
    assert record["version"] == version

    # Originals are read-only: byte-identical after publish.
    after = copy_path.read_bytes()
    assert hashlib.sha256(after).hexdigest() == provenance["original"]["sha256"]
    assert after == before

    stored = get_release(version)
    assert stored["version"] == version
    corrections = stored["corrections"]
    match = [c for c in corrections if c.get("entry_name") == "captopril"]
    assert len(match) == 1
    correction = match[0]
    assert correction["reviewer"] == "dr-synthetic"
    assert correction["decision"] == "approved"
    assert "SYNTHETIC-" in correction["corrected_management"]

    # Source severity and corrected management stay two distinct fields.
    evidence = stored["evidence"]
    captopril_rows = [
        e for e in evidence if e.get("pair_key") == "captopril:sitagliptin"
    ]
    assert len(captopril_rows) >= 1
    row = next(
        r for r in captopril_rows if r.get("source_severity") == "monitor_closely"
    )
    assert row["source_severity"] == "monitor_closely"
    assert "SYNTHETIC-" in row["management"]
    assert row["source_severity"] != row["management"]
    assert row["source_path"] == "Antidiabetic Agents/Sitagliptin.txt"
    assert row["span"] == {"start_line": 205, "end_line": 215}
    assert row["raw_text"].strip() != ""


def test_publish_preserves_duplicate_direction_evidence(tmp_path: Path) -> None:
    """Slice 3.2: ofloxacin pair yields TWO rows; severities/directions kept."""
    import uuid

    _, _, publish_release = _seam()
    get_release = _release_seam()
    provenance = _provenance()
    sources_dir = _make_pristine_sources_dir(tmp_path, provenance)

    exclusions = _slice3_exclusions(sources_dir)
    version = f"s18-slice3-dupe-{uuid.uuid4().hex[:8]}"
    manifest = _slice3_manifest(sources_dir, exclusions, version)

    record = publish_release(manifest)
    assert record["version"] == version

    stored = get_release(version)
    rows = [
        e for e in stored["evidence"] if e.get("pair_key") == "ofloxacin:sitagliptin"
    ]
    # Not collapsed: both monitor 525-529 and minor 912-914 evidence kept.
    assert len(rows) == 2

    monitor = next(r for r in rows if r.get("source_severity") == "monitor_closely")
    assert monitor["span"] == {"start_line": 525, "end_line": 529}
    assert monitor["direction"] == {"subject": "ofloxacin", "object": "sitagliptin"}
    assert monitor["source_path"] == "Antidiabetic Agents/Sitagliptin.txt"
    assert "ofloxacin increases effects of sitagliptin" in monitor["raw_text"]

    minor = next(r for r in rows if r.get("source_severity") == "minor")
    assert minor["span"] == {"start_line": 912, "end_line": 914}
    assert minor["direction"] == {"subject": None, "object": None}
    assert minor["source_path"] == "Antidiabetic Agents/Sitagliptin.txt"
    assert "Mechanism: unspecified" in minor["raw_text"]

    assert {r["source_severity"] for r in rows} == {"monitor_closely", "minor"}


def test_publish_coverage_scope_gating(tmp_path: Path) -> None:
    """Slice 3.3: complete-with-gap and missing/unknown scope reject."""
    import uuid

    PublishRejectedError, list_releases, publish_release = _seam()
    provenance = _provenance()
    sources_dir = _make_pristine_sources_dir(tmp_path, provenance)
    exclusions = _slice3_exclusions(sources_dir)
    assert len(exclusions) > 0

    # Complete scope over a partial corpus REJECTS even with exclusions.
    complete_manifest = _slice3_manifest(
        sources_dir, exclusions, f"s18-slice3-cov-c-{uuid.uuid4().hex[:8]}"
    )
    complete_manifest["coverage"] = {
        "scope": "complete",
        "exclusions": list(exclusions),
    }
    before = list_releases()
    with pytest.raises(PublishRejectedError):
        publish_release(complete_manifest)
    assert list_releases() == before

    # Limited scope with an approved exclusion per gap PUBLISHES.
    limited_manifest = _slice3_manifest(
        sources_dir, exclusions, f"s18-slice3-cov-l-{uuid.uuid4().hex[:8]}"
    )
    limited_manifest["coverage"] = {
        "scope": "limited",
        "exclusions": list(exclusions),
    }
    limited_record = publish_release(limited_manifest)
    assert limited_record["version"] == limited_manifest["version"]

    # Missing scope REJECTS (never label partial complete by default).
    missing_manifest = _slice3_manifest(
        sources_dir, exclusions, f"s18-slice3-cov-m-{uuid.uuid4().hex[:8]}"
    )
    del missing_manifest["coverage"]
    with pytest.raises(PublishRejectedError):
        publish_release(missing_manifest)

    # Unknown scope REJECTS.
    unknown_manifest = _slice3_manifest(
        sources_dir, exclusions, f"s18-slice3-cov-u-{uuid.uuid4().hex[:8]}"
    )
    unknown_manifest["coverage"] = {
        "scope": "partial",
        "exclusions": list(exclusions),
    }
    with pytest.raises(PublishRejectedError):
        publish_release(unknown_manifest)


# ---------------------------------------------------------------------------
# S18 slice 4 RED ONLY: idempotent republish, new version on source change,
# failed publication preserves the released dataset (+ CLI sibling).
#
# Scope (slice 4 ONLY, final S18 slice): all through the public seams —
# ``publish_release`` / ``list_releases`` / ``get_release`` plus the CLI
# sibling ``python -m x_insight.ddi publish --manifest <path>``. Do NOT
# implement the seam here. RED status with current code:
#   4.1 republish returns the ORIGINAL record — current code attempts a
#       second INSERT and raises IntegrityError on the unique version column.
#   4.2 CLI ``publish`` exits 0 and stores the release — subcommand missing,
#       argparse exits 2 with "invalid choice".
#   4.3 CLI rejection names the gate and writes an anomaly report while
#       importing nothing — exits 2 usage error, prints no gate reason and
#       writes no anomaly file.
#
# Expected backend behavior (for the backend agent):
#   Idempotency: republishing byte-identical approved content returns the
#   original record (same id/version/dataset_hash); list_releases() gains no
#   row; get_release evidence is identical.
#   New version: changed sources (updated inventory hash) publish as a NEW
#   version (different version/hash); both releases stay listed and the old
#   one stays readable via get_release.
#   Preservation: a tampered/unapproved manifest raises PublishRejectedError
#   (library) / exits nonzero (CLI); list_releases() is unchanged and the
#   prior release reads back identically.
#   CLI: ``python -m x_insight.ddi publish --manifest <path>`` exits 0 on
#   success (release stored, readable via get_release); on rejection exits
#   nonzero, prints the gate reason to stderr, imports nothing, and still
#   writes an anomaly report file (any ``*anomal*`` file next to the
#   manifest / in cwd) per plan.md 6.2.
#
# Source grounding (read-only; pinned literals, never parser output):
# copy sha e7c9bc45ed5b3f829dfe8e29b015ee727645db2f3ed6cad8de99fea2dcd4022f,
# changed-copy sha differs by construction (appended SYNTHETIC trailing line
# at EOF, interaction section lines < 1005 untouched, counts stay 0/4/92/70),
# pair literals "captopril:sitagliptin" / "ofloxacin:sitagliptin". Originals
# are never written: every test re-asserts the original sha.
# ---------------------------------------------------------------------------

import os as _os
import subprocess as _subprocess
import sys as _sys


def _slice4_cli_publish(manifest: dict[str, Any], cwd: Path) -> Any:
    """Run the NEW S18 slice-4 CLI sibling; RED: exit 2, no subcommand."""
    cwd.mkdir(parents=True, exist_ok=True)
    manifest_path = cwd / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    env = {**_os.environ, "PYTHONPATH": str(_REPO_ROOT / "backend" / "src")}
    return _subprocess.run(
        [
            _sys.executable,
            "-m",
            "x_insight.ddi",
            "publish",
            "--manifest",
            str(manifest_path),
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _slice4_changed_sources_dir(
    tmp_path: Path, provenance: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    """Pristine copy plus ONE synthetic trailing line appended at EOF.

    derived_from provenance is recorded inline (never modify the original):
    the interaction section is untouched so parsed counts stay 0/4/92/70 and
    the corpus still publishes — only inventory bytes change.
    """
    sources_dir = tmp_path / "sources"
    copy_path = sources_dir / "Antidiabetic Agents" / "Sitagliptin.txt"
    copy_path.parent.mkdir(parents=True)
    shutil.copyfile(_ORIGINAL, copy_path)
    pristine_sha = hashlib.sha256(copy_path.read_bytes()).hexdigest()
    assert pristine_sha == provenance["original"]["sha256"]
    copy_path.write_bytes(
        copy_path.read_bytes() + b"\nSYNTHETIC-test trailing line - never clinical\n"
    )
    changed_sha = hashlib.sha256(copy_path.read_bytes()).hexdigest()
    assert changed_sha != provenance["original"]["sha256"]
    derived_from = {
        "derived_from_sha256": pristine_sha,
        "transformation": "SYNTHETIC: appended one trailing line at EOF",
    }
    assert (
        hashlib.sha256(_ORIGINAL.read_bytes()).hexdigest()
        == provenance["original"]["sha256"]
    )
    return sources_dir, derived_from


def test_repeated_publish_identical_content_is_idempotent(tmp_path: Path) -> None:
    """Slice 4.1: same approved limited manifest twice -> one row, same record."""
    import uuid

    _, list_releases, publish_release = _seam()
    get_release = _release_seam()
    provenance = _provenance()
    sources_dir = _make_pristine_sources_dir(tmp_path, provenance)
    exclusions = _slice3_exclusions(sources_dir)
    version = f"s18-slice4-idem-{uuid.uuid4().hex[:8]}"
    manifest = _slice3_manifest(sources_dir, exclusions, version)

    before = list_releases()
    first = publish_release(manifest)
    second = publish_release(manifest)

    # No duplicate: the second call returns the original record.
    assert second["version"] == first["version"] == version
    assert second["dataset_hash"] == first["dataset_hash"]
    assert second["id"] == first["id"]
    after = list_releases()
    assert len(after) == len(before) + 1
    assert [r["version"] for r in after].count(version) == 1

    stored = get_release(version)
    assert stored["dataset_hash"] == first["dataset_hash"]
    assert stored["evidence"] == first["evidence"]

    # Originals are read-only: never modified by either publication.
    assert (
        hashlib.sha256(_ORIGINAL.read_bytes()).hexdigest()
        == provenance["original"]["sha256"]
    )


def test_source_change_creates_new_candidate_version(tmp_path: Path) -> None:
    """Slice 4.2: changed sources publish as NEW version; old stays readable."""
    import uuid

    _, list_releases, publish_release = _seam()
    get_release = _release_seam()
    provenance = _provenance()

    pristine_dir = _make_pristine_sources_dir(tmp_path / "pristine", provenance)
    changed_dir, derived_from = _slice4_changed_sources_dir(
        tmp_path / "changed", provenance
    )
    assert derived_from["derived_from_sha256"] == provenance["original"]["sha256"]
    assert derived_from["transformation"].startswith("SYNTHETIC:")

    pristine_exclusions = _slice3_exclusions(pristine_dir)
    changed_exclusions = _slice3_exclusions(changed_dir)
    assert UNRESOLVED_PIN in [e["name"] for e in changed_exclusions]

    version_a = f"s18-slice4-srcA-{uuid.uuid4().hex[:8]}"
    version_b = f"s18-slice4-srcB-{uuid.uuid4().hex[:8]}"
    first = publish_release(_slice3_manifest(pristine_dir, pristine_exclusions, version_a))
    evidence_a = get_release(version_a)["evidence"]
    second = publish_release(_slice3_manifest(changed_dir, changed_exclusions, version_b))

    # New candidate version: different version AND different content hash.
    assert second["version"] == version_b != first["version"]
    assert second["dataset_hash"] != first["dataset_hash"]

    # Both releases listed; the old release still reads back identically.
    versions = [r["version"] for r in list_releases()]
    assert version_a in versions
    assert version_b in versions
    reread_a = get_release(version_a)
    assert reread_a["dataset_hash"] == first["dataset_hash"]
    assert reread_a["evidence"] == evidence_a

    # CLI sibling publishes a further manifest over the changed sources.
    version_c = f"s18-slice4-srcC-{uuid.uuid4().hex[:8]}"
    cli_manifest = _slice3_manifest(changed_dir, changed_exclusions, version_c)
    result = _slice4_cli_publish(cli_manifest, tmp_path / "cli-ok")
    assert result.returncode == 0
    stored_c = get_release(version_c)
    # Same bytes -> same content hash under the new version.
    assert stored_c["dataset_hash"] == second["dataset_hash"]


def test_failed_publication_preserves_released_dataset(tmp_path: Path) -> None:
    """Slice 4.3: tampered retry rejects; prior release intact; CLI rejects."""
    import uuid

    PublishRejectedError, list_releases, publish_release = _seam()
    get_release = _release_seam()
    provenance = _provenance()

    sources_dir = _make_pristine_sources_dir(tmp_path / "good", provenance)
    exclusions = _slice3_exclusions(sources_dir)
    version = f"s18-slice4-keep-{uuid.uuid4().hex[:8]}"
    record = publish_release(_slice3_manifest(sources_dir, exclusions, version))
    snapshot = get_release(version)
    releases_before = list_releases()

    # Tampered (count_mismatch: declared serious 4 / parsed 3) with its own
    # approved-shape manifest and a fresh version string.
    tampered_dir = _make_tampered_sources_dir(tmp_path / "tampered", provenance)
    assert EXPECTED_COUNTS["serious"] == 4
    tampered_exclusions = _slice3_exclusions(tampered_dir)
    bad_manifest = _slice3_manifest(
        tampered_dir, tampered_exclusions, f"s18-slice4-bad-{uuid.uuid4().hex[:8]}"
    )
    with pytest.raises(PublishRejectedError):
        publish_release(bad_manifest)

    # Library rejection imports nothing; the prior release reads identically.
    assert list_releases() == releases_before
    intact = get_release(version)
    assert intact["dataset_hash"] == snapshot["dataset_hash"] == record["dataset_hash"]
    assert intact["evidence"] == snapshot["evidence"]

    # CLI sibling rejects the same content: nonzero, names the gate, still
    # writes an anomaly report, and imports nothing.
    cli_manifest = _slice3_manifest(
        tampered_dir,
        tampered_exclusions,
        f"s18-slice4-cli-bad-{uuid.uuid4().hex[:8]}",
    )
    cli_dir = tmp_path / "cli-bad"
    result = _slice4_cli_publish(cli_manifest, cli_dir)
    assert result.returncode != 0
    output = (result.stdout + result.stderr).lower()
    assert "reject" in output or "mismatch" in output or "count" in output
    anomaly_files = [
        path
        for path in cli_dir.rglob("*")
        if path.is_file() and "anomal" in path.name.lower()
    ]
    assert anomaly_files != []
    assert list_releases() == releases_before

    # Originals are read-only throughout.
    assert (
        hashlib.sha256(_ORIGINAL.read_bytes()).hexdigest()
        == provenance["original"]["sha256"]
    )
