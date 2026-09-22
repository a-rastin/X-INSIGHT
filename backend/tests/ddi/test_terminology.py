"""S17 slice-1 terminology resolution through seam T3 (RED).

Scope (slice 1 ONLY): canonical/case/whitespace/approved-alias variants resolve
to one stable ID; an ambiguous alias yields unresolved, never the first row.
Unknown / look-alike / salt-strength / pair-identity tests are slice 2-3 and
are deliberately absent here. No fuzzy matching, no external terminology.

Source grounding (read-only, never parsed by the test for expectations):
docs/medical-docs/DDI-text/Antidiabetic Agents/Sitagliptin.txt line 5
"Brand and Other Names: Januvia, Zituvio, Brynovin". All expected IDs/names
below are pinned string literals, never computed by the code under test.

Proposed minimal public terminology interface under test (to be provided by
the backend agent; keep small and deep):

  x_insight.ddi.terminology.load_terminology(path: Path) -> Terminology
      Load the controlled concept/alias table from a JSON file path.
  x_insight.ddi.terminology.normalize(name: str) -> str
      Exact normalization only: strip leading/trailing whitespace, collapse
      internal whitespace runs to one space, casefold. No fuzzy matching,
      no salt/strength stripping, no combination splitting.
  x_insight.ddi.terminology.resolve(name: str, terminology: Terminology) -> dict
      Resolved:   {"status": "resolved", "concept_id": str,
                   "canonical_name": str}
      Unresolved: {"status": "unresolved", "reason": "ambiguous" | "collision",
                   "input": str} with NO "concept_id" key (or None). An alias
      claimed by two concepts never resolves to either row.
  x_insight.ddi.build(source_dir, terminology=Path) integration:
      Every candidate entry gains "name_resolution" in the resolve() dict
      shape above, keyed off the entry's "name_text". Slice 1 asserts this
      only for the pinned ofloxacin entries.

Deferred (NOT slice 1): canonical_pair_key / pair identity, unknown names,
look-alikes, salt/strength/combination rules.

Fixtures (conspicuously synthetic, tests-only; never content/ddi/aliases.json):
  fixtures/synthetic-terminology-s17-slice1.json (unambiguous sitagliptin +
    ofloxacin concepts)
  fixtures/synthetic-terminology-ambiguous-s17-slice1.json (normalized alias
    "ofloxacin" claimed by concepts "ofloxacin-a" and "ofloxacin-b")
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from x_insight.ddi import build
from x_insight.ddi.terminology import load_terminology, normalize, resolve

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_UNAMBIGUOUS = _FIXTURES / "synthetic-terminology-s17-slice1.json"
_AMBIGUOUS = _FIXTURES / "synthetic-terminology-ambiguous-s17-slice1.json"

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ORIGINAL = (
    _REPO_ROOT
    / "docs"
    / "medical-docs"
    / "DDI-text"
    / "Antidiabetic Agents"
    / "Sitagliptin.txt"
)
_PROVENANCE = _FIXTURES / "sitagliptin-provenance.json"


def _make_sources_dir(tmp_path: Path) -> Path:
    """Copy the original monograph byte-identically under a temp sources dir."""
    provenance = json.loads(_PROVENANCE.read_text(encoding="utf-8"))
    sources_dir = tmp_path / "sources"
    copy_path = sources_dir / "Antidiabetic Agents" / "Sitagliptin.txt"
    copy_path.parent.mkdir(parents=True)
    shutil.copyfile(_ORIGINAL, copy_path)
    assert (
        hashlib.sha256(copy_path.read_bytes()).hexdigest()
        == provenance["original"]["sha256"]
    )
    return sources_dir


def _ofloxacin_entries(document: dict) -> list[dict]:
    return [
        entry
        for category in document["categories"]
        for entry in category["entries"]
        if entry["name_text"] == "ofloxacin"
    ]


def test_canonical_case_whitespace_alias_variants_resolve_to_stable_id(
    tmp_path: Path,
) -> None:
    terminology = load_terminology(_UNAMBIGUOUS)

    # Exact normalization contract, pinned literals (not computed by code).
    assert normalize("  JANUVIA ") == "januvia"
    assert normalize("Sitagliptin") == "sitagliptin"
    assert normalize("  OFLOXACIN  ") == "ofloxacin"

    # Source-backed sitagliptin variants -> one stable ID (line 5 brand names).
    for variant in (
        "sitagliptin",
        "Sitagliptin",
        "SITAGLIPTIN",
        " sitagliptin ",
        "  sitagliptin  ",
        "Januvia",
        "JANUVIA",
        " januvia ",
        "Zituvio",
        "ZITUVIO",
        "  Zituvio  ",
        "Brynovin",
        "BRYNOVIN",
        " brynovin ",
    ):
        result = resolve(variant, terminology)
        assert result["status"] == "resolved", variant
        assert result["concept_id"] == "sitagliptin", variant
        assert result["canonical_name"] == "sitagliptin", variant

    # Ofloxacin case/whitespace variants -> one stable ID.
    for variant in (
        "ofloxacin",
        "Ofloxacin",
        "OFLOXACIN",
        " ofloxacin ",
        "  OFLOXACIN  ",
    ):
        result = resolve(variant, terminology)
        assert result["status"] == "resolved", variant
        assert result["concept_id"] == "ofloxacin", variant
        assert result["canonical_name"] == "ofloxacin", variant

    # T3 build integration: both pinned ofloxacin entries resolve in output.
    sources_dir = _make_sources_dir(tmp_path)
    document = build(sources_dir, terminology=_UNAMBIGUOUS)["candidates"]["documents"][
        0
    ]
    entries = _ofloxacin_entries(document)
    assert len(entries) == 2
    assert {tuple(sorted(e["span"].items())) for e in entries} == {
        tuple(sorted({"start_line": 525, "end_line": 529}.items())),
        tuple(sorted({"start_line": 912, "end_line": 914}.items())),
    }
    for entry in entries:
        resolution = entry["name_resolution"]
        assert resolution["status"] == "resolved"
        assert resolution["concept_id"] == "ofloxacin"
        assert resolution["canonical_name"] == "ofloxacin"


def test_ambiguous_alias_yields_unresolved_not_first_row(tmp_path: Path) -> None:
    terminology = load_terminology(_AMBIGUOUS)

    # The normalized alias "ofloxacin" is claimed by both "ofloxacin-a" and
    # "ofloxacin-b": every variant must stay unresolved, never either row.
    for variant in ("ofloxacin", "Ofloxacin", " OFLOXACIN "):
        result = resolve(variant, terminology)
        assert result["status"] == "unresolved", variant
        assert result["reason"] in ("ambiguous", "collision"), variant
        assert result.get("concept_id") is None, variant
        assert result.get("concept_id") != "ofloxacin-a", variant
        assert result.get("concept_id") != "ofloxacin-b", variant

    # T3 build integration: both pinned ofloxacin entries stay unresolved
    # with a collision reason, never the first colliding row.
    sources_dir = _make_sources_dir(tmp_path)
    document = build(sources_dir, terminology=_AMBIGUOUS)["candidates"]["documents"][0]
    entries = _ofloxacin_entries(document)
    assert len(entries) == 2
    for entry in entries:
        resolution = entry["name_resolution"]
        assert resolution["status"] == "unresolved"
        assert resolution["reason"] in ("ambiguous", "collision")
        assert resolution.get("concept_id") is None
        assert resolution.get("concept_id") != "ofloxacin-a"
        assert resolution.get("concept_id") != "ofloxacin-b"


# ---------------------------------------------------------------------------
# S17 slice 2 ONLY (appended; slice-1 above untouched).
#
# Scope: look-alike distinctness, unknown stays unknown, no salt/strength/
# combination rules without reviewed aliases, drug-only concept_type marking.
# Public seam only (load_terminology / resolve / build T3 integration).
# Synthetic fixture only: fixtures/synthetic-terminology-s17-slice2.json.
# No mocks, no fuzzy matching, independent pinned literals.
# ---------------------------------------------------------------------------

_SLICE2 = _FIXTURES / "synthetic-terminology-s17-slice2.json"


def test_look_alike_names_remain_distinct() -> None:
    """DDI design §9 example: clozapine/clonazepam/clomipramine never conflate."""
    terminology = load_terminology(_SLICE2)

    for variant, expected_id in (
        ("clozapine", "clozapine"),
        ("Clozapine", "clozapine"),
        (" clozapine ", "clozapine"),
        ("clonazepam", "clonazepam"),
        ("Clonazepam", "clonazepam"),
        (" clonazepam ", "clonazepam"),
        ("clomipramine", "clomipramine"),
        ("Clomipramine", "clomipramine"),
        (" clomipramine ", "clomipramine"),
    ):
        result = resolve(variant, terminology)
        assert result["status"] == "resolved", variant
        assert result["concept_id"] == expected_id, variant
        assert result["canonical_name"] == expected_id, variant

    # The three IDs are pairwise distinct; no variant ever lands on a sibling.
    assert (
        resolve("clozapine", terminology)["concept_id"]
        != resolve("clonazepam", terminology)["concept_id"]
    )
    assert (
        resolve("clozapine", terminology)["concept_id"]
        != resolve("clomipramine", terminology)["concept_id"]
    )
    assert (
        resolve("clonazepam", terminology)["concept_id"]
        != resolve("clomipramine", terminology)["concept_id"]
    )
    assert resolve("clozapine", terminology)["concept_id"] != "clonazepam"
    assert resolve("clozapine", terminology)["concept_id"] != "clomipramine"
    assert resolve("clonazepam", terminology)["concept_id"] != "clozapine"
    assert resolve("clonazepam", terminology)["concept_id"] != "clomipramine"
    assert resolve("clomipramine", terminology)["concept_id"] != "clozapine"
    assert resolve("clomipramine", terminology)["concept_id"] != "clonazepam"


def test_unknown_name_stays_unknown() -> None:
    """Unknown names stay unresolved unknown, never a concept."""
    terminology = load_terminology(_SLICE2)

    for variant in (
        "not_a_drug_xyz",
        "Not_A_Drug_XYZ",
        "  not_a_drug_xyz  ",
        "",
        "   ",
    ):
        result = resolve(variant, terminology)
        assert result["status"] == "unresolved", repr(variant)
        assert result["reason"] == "unknown", repr(variant)
        assert result.get("concept_id") is None, repr(variant)


def test_salt_strength_combination_not_applied_without_reviewed_rules() -> None:
    """No salt/strength/combination inference without explicit alias."""
    terminology = load_terminology(_SLICE2)

    # Salt variant: quetiapine exists but "quetiapine fumarate" is not aliased.
    for variant in (
        "quetiapine fumarate",
        "Quetiapine Fumarate",
        "  quetiapine fumarate  ",
    ):
        result = resolve(variant, terminology)
        assert result["status"] == "unresolved", variant
        assert result["reason"] == "unknown", variant
        assert result.get("concept_id") is None, variant
        assert result.get("concept_id") != "quetiapine", variant
    # Sanity: the bare ingredient still resolves.
    assert resolve("quetiapine", terminology)["concept_id"] == "quetiapine"

    # Strength variant: sitagliptin exists but "sitagliptin 100 mg" is not aliased.
    for variant in (
        "sitagliptin 100 mg",
        "Sitagliptin 100 MG",
        "  sitagliptin 100 mg  ",
    ):
        result = resolve(variant, terminology)
        assert result["status"] == "unresolved", variant
        assert result["reason"] == "unknown", variant
        assert result.get("concept_id") is None, variant
        assert result.get("concept_id") != "sitagliptin", variant
    assert resolve("sitagliptin", terminology)["concept_id"] == "sitagliptin"

    # Combination: the whole slash string is one explicit combination_drug
    # concept (real Ondansetron entry text, pinned literal only). It resolves
    # only as a whole; it is never split into parts.
    whole = "elvitegravir/cobicistat/emtricitabine/tenofovir DF"
    result = resolve(whole, terminology)
    assert result["status"] == "resolved"
    assert result["concept_id"] == "elvitegravir-cobicistat-emtricitabine-tenofovir-df"
    assert result["canonical_name"] == whole
    cased = resolve("ELVITEGRAVIR/COBICISTAT/EMTRICITABINE/TENOFOVIR DF", terminology)
    assert cased["status"] == "resolved"
    assert cased["concept_id"] == "elvitegravir-cobicistat-emtricitabine-tenofovir-df"
    for part in (
        "elvitegravir",
        "cobicistat",
        "emtricitabine",
        "tenofovir",
        "tenofovir DF",
    ):
        part_result = resolve(part, terminology)
        assert part_result["status"] == "unresolved", part
        assert part_result["reason"] == "unknown", part
        assert part_result.get("concept_id") is None, part
        assert (
            part_result.get("concept_id")
            != "elvitegravir-cobicistat-emtricitabine-tenofovir-df"
        ), part


def test_patient_inputs_remain_drug_only_concept_type(tmp_path: Path) -> None:
    """Non-drug concepts stay typed so callers can enforce drug-only.

    Minimal slice-2 gate: terminology marks ethanol as substance and cinnamon
    as herbal; resolve() must carry concept_type through so a patient-input
    validator can reject non-drug entries. Full S19/S20 patient-list
    enforcement (reject at the API boundary) is pending and NOT asserted here.
    """
    terminology = load_terminology(_SLICE2)

    # Concept table itself is typed (green part: load_terminology stores it).
    assert terminology.concepts["ethanol"]["concept_type"] == "substance"
    assert terminology.concepts["cinnamon"]["concept_type"] == "herbal"
    assert terminology.concepts["sitagliptin"]["concept_type"] == "ingredient"
    assert (
        terminology.concepts["elvitegravir-cobicistat-emtricitabine-tenofovir-df"][
            "concept_type"
        ]
        == "combination_drug"
    )

    # Resolve must carry concept_type so the caller can enforce drug-only
    # (RED until backend adds it; S19/S20 will enforce at the boundary).
    ethanol = resolve("ethanol", terminology)
    assert ethanol["status"] == "resolved"
    assert ethanol["concept_id"] == "ethanol"
    assert ethanol["concept_type"] == "substance"
    cinnamon = resolve("cinnamon", terminology)
    assert cinnamon["status"] == "resolved"
    assert cinnamon["concept_id"] == "cinnamon"
    assert cinnamon["concept_type"] == "herbal"

    # Drug-only distinguishability: non-drug types are never "ingredient".
    assert ethanol["concept_type"] != "ingredient"
    assert cinnamon["concept_type"] != "ingredient"
    assert resolve("sitagliptin", terminology)["concept_type"] == "ingredient"
    assert (
        resolve("elvitegravir/cobicistat/emtricitabine/tenofovir DF", terminology)[
            "concept_type"
        ]
        == "combination_drug"
    )


# ---------------------------------------------------------------------------
# S17 slice 3 ONLY (appended; slices 1-2 above untouched).
#
# Scope: canonical unordered pair identity, paragraph direction preservation
# across terminology resolution, report export of unresolved_names +
# collisions for review. Public seam only (proposed canonical_pair_key +
# build T3 integration). Synthetic fixtures only under fixtures/ (reuse of
# slice-1 unambiguous/ambiguous fixtures). No fuzzy matching, independent
# pinned literals.
# ---------------------------------------------------------------------------


def test_canonical_pair_key_unordered_stable_and_distinct() -> None:
    """Unordered pair identity stable under input reversal (RED: no helper yet).

    Proposed minimal public seam:
      x_insight.ddi.terminology.canonical_pair_key(a: str, b: str) -> str
    """
    from x_insight.ddi.terminology import (
        canonical_pair_key,  # type: ignore[attr-defined]
    )

    forward = canonical_pair_key("sitagliptin", "ofloxacin")
    reversed_ = canonical_pair_key("ofloxacin", "sitagliptin")
    assert isinstance(forward, str)
    assert forward == reversed_

    self_first = canonical_pair_key("sitagliptin", "sitagliptin")
    self_second = canonical_pair_key("sitagliptin", "sitagliptin")
    assert self_first == self_second

    other = canonical_pair_key("sitagliptin", "captopril")
    assert forward != other
    assert self_first != forward


def test_paragraph_direction_survives_terminology_resolution(tmp_path: Path) -> None:
    """Source assertion subject/object unchanged by terminology resolution."""
    sources_dir = _make_sources_dir(tmp_path)
    plain = build(sources_dir, terminology=None)["candidates"]["documents"][0]
    resolved = build(sources_dir, terminology=_UNAMBIGUOUS)["candidates"]["documents"][
        0
    ]

    plain_by_span = {
        tuple(sorted(e["span"].items())): e for e in _ofloxacin_entries(plain)
    }
    resolved_by_span = {
        tuple(sorted(e["span"].items())): e for e in _ofloxacin_entries(resolved)
    }
    monitor_key = tuple(sorted({"start_line": 525, "end_line": 529}.items()))
    minor_key = tuple(sorted({"start_line": 912, "end_line": 914}.items()))
    assert set(plain_by_span) == set(resolved_by_span) == {monitor_key, minor_key}

    # Pinned source assertions (independent literals, not computed by code).
    assert plain_by_span[monitor_key]["paragraphs"][0]["direction"] == {
        "subject": "ofloxacin",
        "object": "sitagliptin",
    }
    assert plain_by_span[minor_key]["paragraphs"][0]["direction"] == {
        "subject": None,
        "object": None,
    }

    # Identical with and without terminology.
    for key in (monitor_key, minor_key):
        assert plain_by_span[key]["paragraphs"] == resolved_by_span[key]["paragraphs"]
        for plain_para, resolved_para in zip(
            plain_by_span[key]["paragraphs"], resolved_by_span[key]["paragraphs"]
        ):
            assert plain_para["direction"] == resolved_para["direction"]


def test_report_exports_unresolved_names_and_collisions_for_review(
    tmp_path: Path,
) -> None:
    """Build report lists unresolved + collisions (public output only)."""
    sources_dir = _make_sources_dir(tmp_path)
    terminology_section = build(sources_dir, terminology=_AMBIGUOUS)["report"][
        "terminology"
    ]

    # Unknown: "captopril" is an entry in the Sitagliptin monograph but has no
    # concept in the ambiguous fixture, so it must be listed for review.
    assert "captopril" in terminology_section["unresolved_names"]
    # Ambiguous never resolves silently: "ofloxacin" stays unresolved too.
    assert "ofloxacin" in terminology_section["unresolved_names"]

    # Proposed contract: collisions expose the normalized alias with claimant IDs,
    # e.g. {"alias": "ofloxacin", "concept_ids": ["ofloxacin-a", "ofloxacin-b"]}.
    by_alias = {
        entry["alias"]: set(entry["concept_ids"])
        for entry in terminology_section["collisions"]
        if isinstance(entry, dict) and "alias" in entry and "concept_ids" in entry
    }
    assert "ofloxacin" in by_alias
    assert by_alias["ofloxacin"] == {"ofloxacin-a", "ofloxacin-b"}
