"""S19 slice 1 RED ONLY: order-independent pair generation, no self-pairs.

Scope (slice 1 ONLY): through the NEW public checker seam (T4 library form)
against real PostgreSQL with a tiny synthetic release inserted directly:

  A/B vs B/A yields the same pair_key/pair list/evidence.
  Three unique drugs yield exactly three pairs with pinned unordered keys.
  Duplicate alias entries for one concept yield zero pairs (no self-pair)
  and a single resolved medication.

This file is RED: ``x_insight.ddi.checker`` does not exist yet, so every
test fails with ``ModuleNotFoundError`` at the ``_seam()`` import. Do NOT
implement the seam to make it pass here.

Proposed minimal public seam for the backend agent (small and deep):

  x_insight.ddi.checker.check(medications, dataset_version) -> dict
      ``medications`` is a list of dicts with exactly one discriminator
      per entry; slice 1 uses ``{"catalog_drug_id": str}`` only
      (``unknown_label`` entries are a later slice). ``dataset_version``
      names a row in ``ddi_dataset_releases``. Returns a DDIReport dict
      with at least:
        "dataset_version": str (echo of the requested release),
        "pairs": list of {"pair_key": str, "drug_a": str, "drug_b": str,
                          "evidence": [evidence rows from the release]},
        "resolved_medications": list of {"concept_id": str, ...}
          (one entry per unique recognized concept, duplicates folded).
      Pair identity is the unordered normalized join "min:max" over the
      normalized concept ids (same form as terminology.canonical_pair_key).
      Each unique unordered pair is generated once; a concept paired with
      itself is never generated. Normalization is exact only (strip,
      collapse whitespace, casefold); no fuzzy matching.

Backend implementation requirements NOT asserted here (no side-channel
assertions in tests): the per-pair evidence fetch must be one batched
indexed lookup over the release evidence (no per-pair round trips).

Deferred (NOT slice 1): unknown_label/ambiguous handling, severity
ordering, conflicts, coverage_basis, limitations, fingerprint,
zero/one-med warnings, HTTP (T1) surface.

Synthetic fixture (conspicuously synthetic, tests-only; never clinical):
concept ids "synthetic-drug-a/b/c" with one evidence row per pair.
Expected pair keys are pinned literals below, never computed via the
code under test. They hold because normalize() casefolds and the ids are
already lowercase single-spaced, sorted a < b < c.
"""

from __future__ import annotations

import hashlib
import json
import socket
import uuid
from typing import Any

from sqlalchemy import text

from x_insight import db
from x_insight.contracts import canonical_json

# Pinned synthetic concept literals (never computed by code under test).
DRUG_A = "synthetic-drug-a"
DRUG_B = "synthetic-drug-b"
DRUG_C = "synthetic-drug-c"
# Case + whitespace variant of DRUG_A: normalize() folds it to the same id.
ALIAS_A = "  SYNTHETIC-DRUG-A  "

# Pinned unordered pair keys (normalized sorted-join "min:max" form).
PAIR_AB = "synthetic-drug-a:synthetic-drug-b"
PAIR_AC = "synthetic-drug-a:synthetic-drug-c"
PAIR_BC = "synthetic-drug-b:synthetic-drug-c"

# Pinned per-pair evidence markers (one row per pair in the fixture).
EVIDENCE_AB = "SYNTHETIC evidence for synthetic-drug-a + synthetic-drug-b - test only"
EVIDENCE_AC = "SYNTHETIC evidence for synthetic-drug-a + synthetic-drug-c - test only"
EVIDENCE_BC = "SYNTHETIC evidence for synthetic-drug-b + synthetic-drug-c - test only"


def _seam() -> Any:
    """Import the NEW S19 slice-1 checker seam.

    RED: raises ModuleNotFoundError until the backend agent implements
    ``x_insight.ddi.checker.check``.
    """
    from x_insight.ddi.checker import check

    return check


def _evidence_row(pair_key: str, raw_text: str, start_line: int) -> dict[str, Any]:
    return {
        "pair_key": pair_key,
        "source_severity": "monitor_closely",
        "management": None,
        "direction": {"subject": None, "object": None},
        "source_path": "SYNTHETIC-slice1.txt",
        "span": {"start_line": start_line, "end_line": start_line + 1},
        "raw_text": raw_text,
    }


def _insert_synthetic_release(version: str) -> None:
    """Fixture SETUP only (not under test): insert a tiny synthetic release.

    Uses disposable test storage directly via db.transaction; all expected
    values asserted below are pinned literals, never read back from here.
    Unique version per test, so no TRUNCATE of other tests' releases.
    """
    evidence = [
        _evidence_row(PAIR_AB, EVIDENCE_AB, 1),
        _evidence_row(PAIR_AC, EVIDENCE_AC, 10),
        _evidence_row(PAIR_BC, EVIDENCE_BC, 20),
    ]
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO ddi_dataset_releases "
                "(version, dataset_hash, source_inventory, "
                "terminology_provenance, review_record, corrections, "
                "coverage, evidence) "
                "VALUES (:version, :dataset_hash, "
                "CAST(:source_inventory AS JSONB), "
                "CAST(:terminology_provenance AS JSONB), "
                "CAST(:review_record AS JSONB), "
                "CAST(:corrections AS JSONB), "
                "CAST(:coverage AS JSONB), "
                "CAST(:evidence AS JSONB))"
            ),
            {
                "version": version,
                "dataset_hash": f"synthetic-hash-{version}",
                "source_inventory": json.dumps([]),
                "terminology_provenance": json.dumps(None),
                "review_record": json.dumps(
                    {"synthetic_fixture": True, "reviewer": "dr-synthetic"}
                ),
                "corrections": json.dumps([]),
                "coverage": json.dumps({"scope": "limited", "exclusions": []}),
                "evidence": json.dumps(evidence),
            },
        )


def _new_version() -> str:
    return f"s19-slice1-{uuid.uuid4().hex[:8]}"


def test_reversed_input_yields_same_pair_and_evidence() -> None:
    """A/B and B/A yield the same pair_key, pair list, and evidence."""
    check = _seam()
    version = _new_version()
    _insert_synthetic_release(version)

    forward = check([{"catalog_drug_id": DRUG_A}, {"catalog_drug_id": DRUG_B}], version)
    reversed_ = check(
        [{"catalog_drug_id": DRUG_B}, {"catalog_drug_id": DRUG_A}], version
    )

    assert forward["dataset_version"] == version
    assert [pair["pair_key"] for pair in forward["pairs"]] == [PAIR_AB]
    assert [pair["pair_key"] for pair in reversed_["pairs"]] == [PAIR_AB]
    assert forward["pairs"] == reversed_["pairs"]
    assert EVIDENCE_AB in forward["pairs"][0]["evidence"][0]["raw_text"]
    assert forward["pairs"][0]["evidence"] == reversed_["pairs"][0]["evidence"]


def test_three_unique_drugs_yield_three_pairs() -> None:
    """Three unique drugs yield exactly three pairs with unordered keys."""
    check = _seam()
    version = _new_version()
    _insert_synthetic_release(version)

    report = check(
        [
            {"catalog_drug_id": DRUG_A},
            {"catalog_drug_id": DRUG_B},
            {"catalog_drug_id": DRUG_C},
        ],
        version,
    )

    pairs = report["pairs"]
    assert len(pairs) == 3
    assert {pair["pair_key"] for pair in pairs} == {PAIR_AB, PAIR_AC, PAIR_BC}
    by_key = {pair["pair_key"]: pair for pair in pairs}
    assert EVIDENCE_AB in by_key[PAIR_AB]["evidence"][0]["raw_text"]
    assert EVIDENCE_AC in by_key[PAIR_AC]["evidence"][0]["raw_text"]
    assert EVIDENCE_BC in by_key[PAIR_BC]["evidence"][0]["raw_text"]


def test_duplicate_aliases_yield_no_self_pair() -> None:
    """Canonical + alias variant of one concept: zero pairs, one resolved."""
    check = _seam()
    version = _new_version()
    _insert_synthetic_release(version)

    report = check([{"catalog_drug_id": DRUG_A}, {"catalog_drug_id": ALIAS_A}], version)

    assert report["pairs"] == []
    resolved = report["resolved_medications"]
    assert len(resolved) == 1
    assert resolved[0]["concept_id"] == DRUG_A


# ---------------------------------------------------------------------------
# S19 slice 2 (RED): known evidence -> interaction_found with every assertion,
# highest known severity, conflict/unknown indicators, directional retention.
#
# Scope (slice 2 ONLY, T4 seam, real PostgreSQL, synthetic data labeled):
# a single pair with three assertion rows (serious + monitor_closely from
# different source_paths + one unknown-severity row, with subject/object vs
# None directions) must yield status interaction_found, every assertion row,
# highest_known_severity == serious (unknown ignored for highest but flagged),
# non-empty conflicts listing severities/sources, and verbatim direction /
# raw_text / management / source_path / span per row.
#
# Deferred (NOT slice 2): coverage states (slice 3), fingerprint/pinning
# (slice 4), HTTP (T1) surface.
# ---------------------------------------------------------------------------

# Pinned synthetic slice-2 literals (never computed by code under test).
SLICE2_PATH_SERIOUS = "SYNTHETIC-slice2-serious.txt"
SLICE2_PATH_MONITOR = "SYNTHETIC-slice2-monitor.txt"
SLICE2_PATH_UNKNOWN = "SYNTHETIC-slice2-unknown.txt"
SLICE2_RAW_SERIOUS = (
    "SYNTHETIC serious assertion for synthetic-drug-a + synthetic-drug-b - test only"
)
SLICE2_RAW_MONITOR = (
    "SYNTHETIC monitor_closely assertion for synthetic-drug-a +"
    " synthetic-drug-b - test only"
)
SLICE2_RAW_UNKNOWN = (
    "SYNTHETIC unknown-severity assertion for synthetic-drug-a +"
    " synthetic-drug-b - test only"
)
SLICE2_MGMT_SERIOUS = "SYNTHETIC serious management - test only"
SLICE2_MGMT_UNKNOWN = "SYNTHETIC unknown management - test only"
SLICE2_DIR_SERIOUS = {"subject": "synthetic-drug-a", "object": "synthetic-drug-b"}
SLICE2_DIR_MONITOR = {"subject": "synthetic-drug-b", "object": "synthetic-drug-a"}
SLICE2_SPAN_SERIOUS = {"start_line": 3, "end_line": 5}
SLICE2_SPAN_MONITOR = {"start_line": 11, "end_line": 12}
SLICE2_SPAN_UNKNOWN = {"start_line": 21, "end_line": 22}


def _insert_slice2_release(version: str) -> None:
    """Fixture SETUP only (not under test): one pair, three assertion rows.

    All rows share PAIR_AB with distinct severities/sources/directions.
    Unique version per test; expected values below are pinned literals.
    """
    evidence = [
        {
            "pair_key": PAIR_AB,
            "source_severity": "serious",
            "management": SLICE2_MGMT_SERIOUS,
            "direction": dict(SLICE2_DIR_SERIOUS),
            "source_path": SLICE2_PATH_SERIOUS,
            "span": dict(SLICE2_SPAN_SERIOUS),
            "raw_text": SLICE2_RAW_SERIOUS,
        },
        {
            "pair_key": PAIR_AB,
            "source_severity": "monitor_closely",
            "management": None,
            "direction": dict(SLICE2_DIR_MONITOR),
            "source_path": SLICE2_PATH_MONITOR,
            "span": dict(SLICE2_SPAN_MONITOR),
            "raw_text": SLICE2_RAW_MONITOR,
        },
        {
            "pair_key": PAIR_AB,
            "source_severity": "unknown",
            "management": SLICE2_MGMT_UNKNOWN,
            "direction": None,
            "source_path": SLICE2_PATH_UNKNOWN,
            "span": dict(SLICE2_SPAN_UNKNOWN),
            "raw_text": SLICE2_RAW_UNKNOWN,
        },
    ]
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO ddi_dataset_releases "
                "(version, dataset_hash, source_inventory, "
                "terminology_provenance, review_record, corrections, "
                "coverage, evidence) "
                "VALUES (:version, :dataset_hash, "
                "CAST(:source_inventory AS JSONB), "
                "CAST(:terminology_provenance AS JSONB), "
                "CAST(:review_record AS JSONB), "
                "CAST(:corrections AS JSONB), "
                "CAST(:coverage AS JSONB), "
                "CAST(:evidence AS JSONB))"
            ),
            {
                "version": version,
                "dataset_hash": f"synthetic-hash-{version}",
                "source_inventory": json.dumps([]),
                "terminology_provenance": json.dumps(None),
                "review_record": json.dumps(
                    {"synthetic_fixture": True, "reviewer": "dr-synthetic"}
                ),
                "corrections": json.dumps([]),
                "coverage": json.dumps({"scope": "limited", "exclusions": []}),
                "evidence": json.dumps(evidence),
            },
        )


def _new_slice2_version() -> str:
    return f"s19-slice2-{uuid.uuid4().hex[:8]}"


def _slice2_pair() -> dict[str, Any]:
    check = _seam()
    version = _new_slice2_version()
    _insert_slice2_release(version)
    report = check([{"catalog_drug_id": DRUG_A}, {"catalog_drug_id": DRUG_B}], version)
    assert report["dataset_version"] == version
    assert len(report["pairs"]) == 1
    pair = report["pairs"][0]
    assert pair["pair_key"] == PAIR_AB
    return pair


def test_known_evidence_yields_interaction_found_with_every_assertion() -> None:
    """Known evidence gives interaction_found with all three assertion rows."""
    pair = _slice2_pair()

    assert pair["status"] == "interaction_found"
    assert len(pair["evidence"]) == 3
    assert {row["raw_text"] for row in pair["evidence"]} == {
        SLICE2_RAW_SERIOUS,
        SLICE2_RAW_MONITOR,
        SLICE2_RAW_UNKNOWN,
    }


def test_highest_known_severity_ignores_unknown_but_flags_it() -> None:
    """Highest known severity is serious; unknown is flagged, not highest."""
    pair = _slice2_pair()

    assert pair["highest_known_severity"] == "serious"
    assert pair["has_unknown_severity"] is True


def test_conflicts_and_directional_evidence_retained() -> None:
    """Conflicts list known severities/sources; rows keep direction verbatim."""
    pair = _slice2_pair()

    conflicts = pair["conflicts"]
    assert {row["source_severity"] for row in conflicts} == {
        "serious",
        "monitor_closely",
    }
    assert {row["source_path"] for row in conflicts} == {
        SLICE2_PATH_SERIOUS,
        SLICE2_PATH_MONITOR,
    }
    assert all(row["source_severity"] != "unknown" for row in conflicts)

    by_raw = {row["raw_text"]: row for row in pair["evidence"]}
    serious = by_raw[SLICE2_RAW_SERIOUS]
    assert serious["direction"] == SLICE2_DIR_SERIOUS
    assert serious["management"] == SLICE2_MGMT_SERIOUS
    assert serious["source_path"] == SLICE2_PATH_SERIOUS
    assert serious["span"] == SLICE2_SPAN_SERIOUS

    monitor = by_raw[SLICE2_RAW_MONITOR]
    assert monitor["direction"] == SLICE2_DIR_MONITOR
    assert monitor["management"] is None
    assert monitor["source_path"] == SLICE2_PATH_MONITOR
    assert monitor["span"] == SLICE2_SPAN_MONITOR

    unknown = by_raw[SLICE2_RAW_UNKNOWN]
    assert unknown["direction"] is None
    assert unknown["management"] == SLICE2_MGMT_UNKNOWN
    assert unknown["source_path"] == SLICE2_PATH_UNKNOWN
    assert unknown["span"] == SLICE2_SPAN_UNKNOWN


# ---------------------------------------------------------------------------
# S19 slice 3 (RED): empty-evidence coverage + unknown_label handling.
#
# Scope (slice 3 ONLY, T4 seam, real PostgreSQL, synthetic data labeled):
# (a) no evidence with explicit complete coverage ->
#     covered_no_listed_interaction with coverage_basis citing complete;
# (b) no evidence with limited/missing coverage -> coverage_unavailable
#     with coverage_basis citing limited/unavailable;
# (c) unknown_label entry -> unresolved_medications contains it, every pair
#     involving it is coverage_unavailable even under complete scope,
#     resolved-resolved coverage is unaffected;
# (d) zero meds and one med -> valid report, pairs == [], unresolved
#     warnings still visible when an unknown is present, no crash.
# Medications use exactly one discriminator per entry:
# {"catalog_drug_id": str} | {"unknown_label": str}.
#
# Deferred (NOT slice 3): fingerprint/pinning (slice 4), HTTP (T1) surface.
#
# Synthetic fixture (conspicuously synthetic, tests-only; never clinical):
# concept ids reuse DRUG_A/B, unknown labels "synthetic-unknown-x".
# Expected pair keys are pinned literals below, never computed via the
# code under test. Empty evidence isolates the coverage decision.
# ---------------------------------------------------------------------------

# Pinned synthetic slice-3 unknown literals (never computed by code under test).
SLICE3_UNKNOWN_X = "synthetic-unknown-x"
# Pinned unordered pair keys involving the unknown (drug < unknown: "d" < "u").
SLICE3_PAIR_AX = "synthetic-drug-a:synthetic-unknown-x"
SLICE3_PAIR_BX = "synthetic-drug-b:synthetic-unknown-x"


def _insert_slice3_release(
    version: str, coverage: Any, evidence: list[dict[str, Any]] | None = None
) -> None:
    """Fixture SETUP only (not under test): empty evidence + chosen coverage.

    ``coverage`` is a dict like {"scope": "complete", "exclusions": []} or
    None for SQL NULL (missing coverage). ``evidence`` defaults to [].
    Unique version per test; expected values below are pinned literals.
    """
    rows = evidence if evidence is not None else []
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO ddi_dataset_releases "
                "(version, dataset_hash, source_inventory, "
                "terminology_provenance, review_record, corrections, "
                "coverage, evidence) "
                "VALUES (:version, :dataset_hash, "
                "CAST(:source_inventory AS JSONB), "
                "CAST(:terminology_provenance AS JSONB), "
                "CAST(:review_record AS JSONB), "
                "CAST(:corrections AS JSONB), "
                "CAST(:coverage AS JSONB), "
                "CAST(:evidence AS JSONB))"
            ),
            {
                "version": version,
                "dataset_hash": f"synthetic-hash-{version}",
                "source_inventory": json.dumps([]),
                "terminology_provenance": json.dumps(None),
                "review_record": json.dumps(
                    {"synthetic_fixture": True, "reviewer": "dr-synthetic"}
                ),
                "corrections": json.dumps([]),
                "coverage": json.dumps(coverage) if coverage is not None else None,
                "evidence": json.dumps(rows),
            },
        )


def _new_slice3_version() -> str:
    return f"s19-slice3-{uuid.uuid4().hex[:8]}"


def test_no_evidence_with_complete_coverage_is_covered_no_listed() -> None:
    """Complete scope + no evidence => covered_no_listed_interaction."""
    check = _seam()
    version = _new_slice3_version()
    _insert_slice3_release(version, {"scope": "complete", "exclusions": []}, [])

    report = check([{"catalog_drug_id": DRUG_A}, {"catalog_drug_id": DRUG_B}], version)

    assert report["dataset_version"] == version
    assert len(report["pairs"]) == 1
    pair = report["pairs"][0]
    assert pair["pair_key"] == PAIR_AB
    assert pair["drug_a"] == DRUG_A
    assert pair["drug_b"] == DRUG_B
    assert pair["evidence"] == []
    assert pair["status"] == "covered_no_listed_interaction"
    assert isinstance(pair["coverage_basis"], str) and pair["coverage_basis"]
    assert "complete" in pair["coverage_basis"].lower()
    assert pair["highest_known_severity"] is None
    assert pair["has_unknown_severity"] is False
    assert pair["conflicts"] == []
    assert len(report["resolved_medications"]) == 2
    assert report["unresolved_medications"] == []
    assert report["limitations"] == []


def test_no_evidence_with_limited_or_missing_coverage_is_unavailable() -> None:
    """Limited or missing (NULL) coverage + no evidence => coverage_unavailable."""
    check = _seam()

    limited_version = _new_slice3_version()
    _insert_slice3_release(limited_version, {"scope": "limited", "exclusions": []}, [])
    limited = check(
        [{"catalog_drug_id": DRUG_A}, {"catalog_drug_id": DRUG_B}], limited_version
    )
    assert len(limited["pairs"]) == 1
    limited_pair = limited["pairs"][0]
    assert limited_pair["pair_key"] == PAIR_AB
    assert limited_pair["evidence"] == []
    assert limited_pair["status"] == "coverage_unavailable"
    assert isinstance(limited_pair["coverage_basis"], str)
    assert "limited" in limited_pair["coverage_basis"].lower()
    assert limited_pair["highest_known_severity"] is None
    assert limited_pair["has_unknown_severity"] is False
    assert limited_pair["conflicts"] == []
    assert limited["unresolved_medications"] == []

    missing_version = _new_slice3_version()
    _insert_slice3_release(missing_version, None, [])
    missing = check(
        [{"catalog_drug_id": DRUG_A}, {"catalog_drug_id": DRUG_B}], missing_version
    )
    assert len(missing["pairs"]) == 1
    missing_pair = missing["pairs"][0]
    assert missing_pair["pair_key"] == PAIR_AB
    assert missing_pair["evidence"] == []
    assert missing_pair["status"] == "coverage_unavailable"
    assert isinstance(missing_pair["coverage_basis"], str)
    assert "unavailable" in missing_pair["coverage_basis"].lower()
    assert missing["unresolved_medications"] == []


def test_unknown_label_pair_always_coverage_unavailable_under_complete() -> None:
    """One resolved + one unknown under complete scope: single uncovered pair."""
    check = _seam()
    version = _new_slice3_version()
    _insert_slice3_release(version, {"scope": "complete", "exclusions": []}, [])

    report = check(
        [{"catalog_drug_id": DRUG_A}, {"unknown_label": SLICE3_UNKNOWN_X}], version
    )

    assert report["dataset_version"] == version
    assert [entry["concept_id"] for entry in report["resolved_medications"]] == [DRUG_A]
    assert [entry["unknown_label"] for entry in report["unresolved_medications"]] == [
        SLICE3_UNKNOWN_X
    ]
    assert len(report["pairs"]) == 1
    pair = report["pairs"][0]
    assert pair["pair_key"] == SLICE3_PAIR_AX
    assert pair["evidence"] == []
    assert pair["status"] == "coverage_unavailable"
    assert "unknown" in pair["coverage_basis"].lower()
    assert isinstance(report["limitations"], list) and report["limitations"]
    assert any(
        "unresolv" in entry.lower() or "unknown" in entry.lower()
        for entry in report["limitations"]
    )


def test_unknown_does_not_pollute_resolved_pair_coverage() -> None:
    """Two resolved + one unknown, complete, no evidence: AB covered, AX/BX off."""
    check = _seam()
    version = _new_slice3_version()
    _insert_slice3_release(version, {"scope": "complete", "exclusions": []}, [])

    report = check(
        [
            {"catalog_drug_id": DRUG_A},
            {"catalog_drug_id": DRUG_B},
            {"unknown_label": SLICE3_UNKNOWN_X},
        ],
        version,
    )

    assert len(report["pairs"]) == 3
    by_key = {pair["pair_key"]: pair for pair in report["pairs"]}
    assert set(by_key) == {PAIR_AB, SLICE3_PAIR_AX, SLICE3_PAIR_BX}
    assert by_key[PAIR_AB]["status"] == "covered_no_listed_interaction"
    assert "complete" in by_key[PAIR_AB]["coverage_basis"].lower()
    for key in (SLICE3_PAIR_AX, SLICE3_PAIR_BX):
        assert by_key[key]["status"] == "coverage_unavailable"
        assert "unknown" in by_key[key]["coverage_basis"].lower()
        assert by_key[key]["evidence"] == []
    assert [entry["unknown_label"] for entry in report["unresolved_medications"]] == [
        SLICE3_UNKNOWN_X
    ]
    assert any(
        "unresolv" in entry.lower() or "unknown" in entry.lower()
        for entry in report["limitations"]
    )


def test_zero_and_one_med_reports_valid_with_unresolved_warnings() -> None:
    """Zero/one unique input has no pairs; unknown warnings stay visible."""
    check = _seam()
    version = _new_slice3_version()
    _insert_slice3_release(version, {"scope": "complete", "exclusions": []}, [])

    empty = check([], version)
    assert empty["dataset_version"] == version
    assert empty["pairs"] == []
    assert empty["resolved_medications"] == []
    assert empty["unresolved_medications"] == []
    assert empty["limitations"] == []

    one_resolved = check([{"catalog_drug_id": DRUG_A}], version)
    assert one_resolved["pairs"] == []
    assert [entry["concept_id"] for entry in one_resolved["resolved_medications"]] == [
        DRUG_A
    ]
    assert one_resolved["unresolved_medications"] == []
    assert one_resolved["limitations"] == []

    one_unknown = check([{"unknown_label": SLICE3_UNKNOWN_X}], version)
    assert one_unknown["pairs"] == []
    assert one_unknown["resolved_medications"] == []
    unresolved_labels = [
        entry["unknown_label"] for entry in one_unknown["unresolved_medications"]
    ]
    assert unresolved_labels == [SLICE3_UNKNOWN_X]
    assert one_unknown["limitations"]
    assert any(
        "unresolv" in entry.lower() or "unknown" in entry.lower()
        for entry in one_unknown["limitations"]
    )


def test_medication_entries_require_exactly_one_discriminator() -> None:
    """Both/neither discriminator and non-str unknown_label raise ValueError."""
    check = _seam()
    version = _new_slice3_version()
    _insert_slice3_release(version, {"scope": "complete", "exclusions": []}, [])

    try:
        check([{"catalog_drug_id": DRUG_A, "unknown_label": SLICE3_UNKNOWN_X}], version)
    except ValueError:
        pass
    else:
        raise AssertionError("both discriminators must raise ValueError")

    try:
        check([{}], version)
    except ValueError:
        pass
    else:
        raise AssertionError("neither discriminator must raise ValueError")

    try:
        check([{"unknown_label": 123}], version)  # type: ignore[dict-item]
    except ValueError:
        pass
    else:
        raise AssertionError("non-str unknown_label must raise ValueError")


# ---------------------------------------------------------------------------
# S19 slice 4 (RED): pinned dataset/catalog/fingerprint, invalid refusal,
# excluded regimen fields, offline execution.
#
# Scope (slice 4 ONLY, T4 seam, real PostgreSQL, synthetic data labeled):
# (a) report pins dataset_version echo + catalog_version (pinned string from
#     release terminology_provenance.terminology_version) + dataset_hash echo
#     + medication_fingerprint (deterministic over canonical sorted lists)
#     + generated_at UTC Z string;
# (b) order/alias-case invariance (same meds different order => same
#     fingerprint) and distinctness (different meds => different fingerprint);
#     one fixed input pins a literal fingerprint computed independently via
#     hashlib.sha256(canonical_json) (never via the code under test);
# (c) unknown dataset_version raises (LookupError or ValueError);
# (d) any FR-14 excluded regimen field (dose/unit/route/frequency/active/
#     stopped) on an entry raises ValueError;
# (e) checker executes with external network access disabled (sockets blocked).
#
# Deferred (NOT slice 4): HTTP (T1) surface (separate file).
#
# Synthetic fixture (conspicuously synthetic, tests-only; never clinical).
# ---------------------------------------------------------------------------

# Pinned synthetic slice-4 catalog literal (stored in terminology_provenance).
SLICE4_CATALOG_VERSION = "synthetic-catalog-s19-s4-v1"
# Pinned literal fingerprint for [DRUG_A, DRUG_B] (resolved sorted, no
# unresolved): hashlib.sha256(canonical_json(
#   {"resolved": ["synthetic-drug-a", "synthetic-drug-b"],
#    "unresolved": []})).hexdigest() computed independently in a shell.
SLICE4_PINNED_FINGERPRINT_AB = (
    "f7a3f2908c0a5db1f6f548cdcb48085a8588422ddbf920f3e51fba640a71eb8c"
)
# Pinned excluded regimen literals (FR-14, never stored).
SLICE4_EXCLUDED_FIELDS = ("dose", "unit", "route", "frequency", "active", "stopped")


def _insert_slice4_release(version: str) -> None:
    """Fixture SETUP only (not under test): empty evidence + pinned provenance."""
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO ddi_dataset_releases "
                "(version, dataset_hash, source_inventory, "
                "terminology_provenance, review_record, corrections, "
                "coverage, evidence) "
                "VALUES (:version, :dataset_hash, "
                "CAST(:source_inventory AS JSONB), "
                "CAST(:terminology_provenance AS JSONB), "
                "CAST(:review_record AS JSONB), "
                "CAST(:corrections AS JSONB), "
                "CAST(:coverage AS JSONB), "
                "CAST(:evidence AS JSONB))"
            ),
            {
                "version": version,
                "dataset_hash": f"synthetic-hash-{version}",
                "source_inventory": json.dumps([]),
                "terminology_provenance": json.dumps(
                    {
                        "terminology_version": SLICE4_CATALOG_VERSION,
                        "synthetic_fixture": True,
                    }
                ),
                "review_record": json.dumps(
                    {"synthetic_fixture": True, "reviewer": "dr-synthetic"}
                ),
                "corrections": json.dumps([]),
                "coverage": json.dumps({"scope": "limited", "exclusions": []}),
                "evidence": json.dumps([]),
            },
        )


def _new_slice4_version() -> str:
    return f"s19-slice4-{uuid.uuid4().hex[:8]}"


def _independent_fingerprint(resolved: list[str], unresolved: list[str]) -> str:
    """Independent expectation: hashlib over canonical JSON (not via checker)."""
    return hashlib.sha256(
        canonical_json({"resolved": resolved, "unresolved": unresolved})
    ).hexdigest()


def test_report_pins_dataset_catalog_fingerprint_hash_and_generated_at() -> None:
    """Report echoes dataset/catalog/hash with deterministic fingerprint + time."""
    check = _seam()
    version = _new_slice4_version()
    _insert_slice4_release(version)

    report = check([{"catalog_drug_id": DRUG_A}, {"catalog_drug_id": DRUG_B}], version)

    assert report["dataset_version"] == version
    assert report["catalog_version"] == SLICE4_CATALOG_VERSION
    assert report["dataset_hash"] == f"synthetic-hash-{version}"
    assert report["medication_fingerprint"] == SLICE4_PINNED_FINGERPRINT_AB
    assert (
        _independent_fingerprint(["synthetic-drug-a", "synthetic-drug-b"], [])
        == SLICE4_PINNED_FINGERPRINT_AB
    )
    generated_at = report["generated_at"]
    assert isinstance(generated_at, str) and generated_at.endswith("Z")
    assert "T" in generated_at


def test_fingerprint_order_alias_invariant_and_distinct() -> None:
    """Reordered/alias-case inputs share a fingerprint; different meds differ."""
    check = _seam()
    version = _new_slice4_version()
    _insert_slice4_release(version)

    forward = check([{"catalog_drug_id": DRUG_A}, {"catalog_drug_id": DRUG_B}], version)
    reordered = check(
        [{"catalog_drug_id": DRUG_B}, {"catalog_drug_id": DRUG_A}], version
    )
    aliased = check(
        [{"catalog_drug_id": ALIAS_A}, {"catalog_drug_id": DRUG_B}], version
    )
    different = check(
        [{"catalog_drug_id": DRUG_A}, {"catalog_drug_id": DRUG_C}], version
    )

    assert forward["medication_fingerprint"] == reordered["medication_fingerprint"]
    assert forward["medication_fingerprint"] == aliased["medication_fingerprint"]
    assert forward["medication_fingerprint"] != different["medication_fingerprint"]


def test_unknown_dataset_version_raises() -> None:
    """Unknown dataset version raises (LookupError or ValueError)."""
    check = _seam()
    try:
        check(
            [{"catalog_drug_id": DRUG_A}],
            f"s19-slice4-missing-{uuid.uuid4().hex[:8]}",
        )
    except (LookupError, ValueError):
        pass
    else:
        raise AssertionError("unknown dataset version must raise")


def test_excluded_regimen_fields_raise() -> None:
    """Any FR-14 excluded regimen field on an entry raises ValueError."""
    check = _seam()
    version = _new_slice4_version()
    _insert_slice4_release(version)

    for field in SLICE4_EXCLUDED_FIELDS:
        try:
            check([{"catalog_drug_id": DRUG_A, field: "synthetic-dose"}], version)
        except ValueError:
            pass
        else:
            raise AssertionError(f"excluded field {field} must raise ValueError")


def test_checker_executes_with_sockets_disabled(monkeypatch: Any) -> None:
    """Checker needs no network: blocked sockets still yield a pinned report."""
    check = _seam()
    version = _new_slice4_version()
    _insert_slice4_release(version)

    def _blocked(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("network access is disabled for DDI check")

    monkeypatch.setattr(socket, "socket", _blocked)

    report = check([{"catalog_drug_id": DRUG_A}, {"catalog_drug_id": DRUG_B}], version)
    assert report["dataset_version"] == version
    assert report["catalog_version"] == SLICE4_CATALOG_VERSION
    assert report["medication_fingerprint"] == SLICE4_PINNED_FINGERPRINT_AB


# ---------------------------------------------------------------------------
# S19 verify/exit (T4, real PostgreSQL): source-backed checker fixture.
#
# Scope: ONE test only. Real monograph
# docs/medical-docs/DDI-text/Antidiabetic Agents/Sitagliptin.txt is read-only:
# copied byte-identically to a temp dir (provenance sha pinned), built via
# x_insight.ddi.ingestion.build, ofloxacin candidate entries converted to
# release evidence rows in the publish._build_evidence shape, wrapped in a
# conspicuously synthetic release (real-derived evidence, limited scope).
# Then checker.check([sitagliptin, ofloxacin]) must yield interaction_found
# with real source_path/span/raw_text and slice-2 conflict handling when
# both severities are present. All three statuses are covered elsewhere in
# this file (slice 2 interaction_found, slice 3 covered_no_listed_interaction
# + coverage_unavailable + zero/one); this test adds the source-backed leg.
# ---------------------------------------------------------------------------


def test_source_backed_sitagliptin_ofloxacin_interaction_found(tmp_path: Any) -> None:
    """Real Sitagliptin/ofloxacin rows check as interaction_found."""
    import shutil
    from pathlib import Path

    from x_insight.ddi.ingestion import build
    from x_insight.ddi.terminology import canonical_pair_key

    # Pinned literals from the source (never parser output for counts).
    sitagliptin_id = "sitagliptin"
    ofloxacin_id = "ofloxacin"
    pinned_pair_key = "ofloxacin:sitagliptin"
    pinned_subject_stem = "Sitagliptin"
    pinned_relative_path = "Antidiabetic Agents/Sitagliptin.txt"
    pinned_monitor_span = {"start_line": 525, "end_line": 529}
    pinned_minor_span = {"start_line": 912, "end_line": 914}
    pinned_monitor_text = "ofloxacin increases effects of sitagliptin"
    pinned_minor_text = "Mechanism: unspecified"
    pinned_sha = "e7c9bc45ed5b3f829dfe8e29b015ee727645db2f3ed6cad8de99fea2dcd4022f"

    repo_root = Path(__file__).resolve().parents[3]
    original = (
        repo_root
        / "docs"
        / "medical-docs"
        / "DDI-text"
        / "Antidiabetic Agents"
        / "Sitagliptin.txt"
    )
    provenance_path = (
        Path(__file__).resolve().parent / "fixtures" / "sitagliptin-provenance.json"
    )
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert provenance["original"]["sha256"] == pinned_sha

    sources_dir = tmp_path / "sources"
    copy_path = sources_dir / "Antidiabetic Agents" / "Sitagliptin.txt"
    copy_path.parent.mkdir(parents=True)
    shutil.copyfile(original, copy_path)
    assert hashlib.sha256(copy_path.read_bytes()).hexdigest() == pinned_sha

    built = build(sources_dir)
    documents = built["candidates"]["documents"]
    assert len(documents) == 1
    document = documents[0]
    assert document["relative_path"] == pinned_relative_path
    assert Path(document["relative_path"]).stem == pinned_subject_stem

    found: list[tuple[str, dict[str, Any]]] = [
        (category["category"], entry)
        for category in document["categories"]
        for entry in category["entries"]
        if entry["name_text"] == ofloxacin_id
    ]
    assert len(found) >= 1

    # Same row shape publish._build_evidence uses (pair_key via
    # terminology.canonical_pair_key, management None, direction from the
    # first paragraph or None, real source_path/span/raw_text).
    rows: list[dict[str, Any]] = []
    for category_key, entry in found:
        subject = Path(document["relative_path"]).stem
        pair_key = canonical_pair_key(subject, entry["name_text"])
        assert pair_key == pinned_pair_key
        direction: dict[str, Any] | None = None
        paragraphs = entry.get("paragraphs", [])
        if paragraphs and isinstance(paragraphs[0], dict):
            first_direction = paragraphs[0].get("direction")
            if isinstance(first_direction, dict):
                direction = dict(first_direction)
        rows.append(
            {
                "pair_key": pair_key,
                "source_severity": category_key,
                "management": None,
                "direction": direction,
                "source_path": document["relative_path"],
                "span": dict(entry["span"]),
                "raw_text": entry["raw_text"],
            }
        )
    assert any(row["source_path"].endswith("Sitagliptin.txt") for row in rows)
    found_spans = [row["span"] for row in rows]
    assert pinned_monitor_span in found_spans or pinned_minor_span in found_spans

    version = f"synthetic-source-backed-s19-{uuid.uuid4().hex[:8]}"
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO ddi_dataset_releases "
                "(version, dataset_hash, source_inventory, "
                "terminology_provenance, review_record, corrections, "
                "coverage, evidence) "
                "VALUES (:version, :dataset_hash, "
                "CAST(:source_inventory AS JSONB), "
                "CAST(:terminology_provenance AS JSONB), "
                "CAST(:review_record AS JSONB), "
                "CAST(:corrections AS JSONB), "
                "CAST(:coverage AS JSONB), "
                "CAST(:evidence AS JSONB))"
            ),
            {
                "version": version,
                "dataset_hash": f"synthetic-hash-{version}",
                "source_inventory": json.dumps([]),
                "terminology_provenance": json.dumps(None),
                "review_record": json.dumps(
                    {
                        "synthetic_fixture": True,
                        "evidence": "real-derived",
                        "reviewer": "dr-synthetic",
                        "note": (
                            "synthetic wrapper around real Sitagliptin "
                            "ofloxacin rows - test only, never clinical"
                        ),
                    }
                ),
                "corrections": json.dumps([]),
                "coverage": json.dumps({"scope": "limited", "exclusions": []}),
                "evidence": json.dumps(rows),
            },
        )

    check = _seam()
    report = check(
        [{"catalog_drug_id": sitagliptin_id}, {"catalog_drug_id": ofloxacin_id}],
        version,
    )

    assert report["dataset_version"] == version
    assert len(report["pairs"]) == 1
    pair = report["pairs"][0]
    assert pair["pair_key"] == pinned_pair_key
    assert pair["status"] == "interaction_found"
    assert len(pair["evidence"]) == len(rows) and pair["evidence"]
    for row in pair["evidence"]:
        assert row["source_path"] == pinned_relative_path
        assert row["source_path"].endswith("Sitagliptin.txt")
        assert row["span"] in (pinned_monitor_span, pinned_minor_span)
        assert (
            pinned_monitor_text in row["raw_text"]
            or pinned_minor_text in row["raw_text"]
        )
    severities = {row["source_severity"] for row in pair["evidence"]}
    assert severities <= {"monitor_closely", "minor"} and severities
    assert pair["highest_known_severity"] in {"monitor_closely", "minor"}
    if severities == {"monitor_closely", "minor"}:
        assert pair["highest_known_severity"] == "monitor_closely"
        assert pair["has_unknown_severity"] is False
        assert {row["source_severity"] for row in pair["conflicts"]} == severities
        assert {row["source_path"] for row in pair["conflicts"]} == {
            pinned_relative_path
        }
    else:
        assert pair["highest_known_severity"] == next(iter(severities))
