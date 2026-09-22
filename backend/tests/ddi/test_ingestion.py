"""S15 ingestion through the build seam (T3): real monograph source files only.

Slice S15-A (red): build() discovers the fixture document, locates the
interaction section at the first count-bearing category heading (ignoring the
navigation/summary headings), and reports the four category headings.

Expected values are pinned from the source text itself (docs/medical-docs/,
read-only) and from fixtures/sitagliptin-provenance.json — never from parser
output.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from x_insight.ddi import build

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ORIGINAL = (
    _REPO_ROOT
    / "docs"
    / "medical-docs"
    / "DDI-text"
    / "Antidiabetic Agents"
    / "Sitagliptin.txt"
)
_PROVENANCE = (
    Path(__file__).resolve().parent / "fixtures" / "sitagliptin-provenance.json"
)


def _provenance() -> dict[str, Any]:
    return json.loads(_PROVENANCE.read_text(encoding="utf-8"))


def _make_sources_dir(tmp_path: Path, provenance: dict[str, Any]) -> Path:
    """Copy the original monograph byte-identically under a temp sources dir.

    Fixture-copy rule (contract section 1): the copy's sha256 must equal the
    recorded provenance hash.
    """
    sources_dir = tmp_path / "sources"
    copy_path = sources_dir / "Antidiabetic Agents" / "Sitagliptin.txt"
    copy_path.parent.mkdir(parents=True)
    shutil.copyfile(_ORIGINAL, copy_path)
    copy_sha256 = hashlib.sha256(copy_path.read_bytes()).hexdigest()
    assert copy_sha256 == provenance["original"]["sha256"]
    return sources_dir


_BOM = b"\xef\xbb\xbf"


def _make_bom_stripped_sources_dir(
    tmp_path: Path, provenance: dict[str, Any]
) -> tuple[Path, dict[str, str]]:
    """Build a transformed copy of the original: same bytes minus the UTF-8 BOM.

    Fixture-copy rule (contract section 1): a transformed copy records
    derived_from sha256 plus the transformation applied.
    """
    original_bytes = _ORIGINAL.read_bytes()
    assert original_bytes.startswith(_BOM)
    record = {
        "derived_from": hashlib.sha256(original_bytes).hexdigest(),
        "transformation": "strip UTF-8 BOM (EF BB BF) prefix",
    }
    assert record["derived_from"] == provenance["original"]["sha256"]
    sources_dir = tmp_path / "sources"
    copy_path = sources_dir / "Antidiabetic Agents" / "Sitagliptin.txt"
    copy_path.parent.mkdir(parents=True)
    copy_path.write_bytes(original_bytes[len(_BOM) :])
    return sources_dir, record


def _make_entry_removed_sources_dir(
    tmp_path: Path, provenance: dict[str, Any]
) -> tuple[Path, dict[str, str]]:
    """Build a transformed copy of the original: the erdafitinib serious entry
    block deleted (original lines 101-105 plus its trailing blank line 106).

    Fixture-copy rule (contract section 1): a transformed copy records
    derived_from sha256 plus the transformation applied.
    """
    original_bytes = _ORIGINAL.read_bytes()
    record = {
        "derived_from": hashlib.sha256(original_bytes).hexdigest(),
        "transformation": (
            "removed erdafitinib entry block, original lines 101-105, "
            "plus its trailing blank line 106"
        ),
    }
    assert record["derived_from"] == provenance["original"]["sha256"]
    lines = original_bytes.splitlines(keepends=True)
    # Block boundaries verified against the source with sed -n '99,107=' /
    # sed -n '99,107p':
    # line 99 heading 'Serious (4)', 100 blank, 101 entry header 'erdafitinib',
    # 102-105 description, 106 blank, 107 next entry header 'ethanol'.
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
    return sources_dir, record


def test_build_locates_interaction_section_ignoring_navigation_headings(
    tmp_path: Path,
) -> None:
    provenance = _provenance()
    sources_dir = _make_sources_dir(tmp_path, provenance)

    result = build(sources_dir)

    documents = result["candidates"]["documents"]
    assert len(documents) == 1
    document = documents[0]
    assert document["relative_path"] == "Antidiabetic Agents/Sitagliptin.txt"
    assert document["sha256"] == provenance["original"]["sha256"]

    section = document["interaction_section"]
    assert section is not None
    # First count-bearing category heading — not the navigation headings at
    # lines 74/76/81/83/85/87/89.
    assert section["start_line"] == 97
    # The section ends before the Adverse Effects marker at line 1005.
    assert section["end_line"] < 1005

    categories = document["categories"]
    assert [
        (c["category"], c["heading_text"], c["declared_count"]) for c in categories
    ] == [
        ("contraindicated", "Contraindicated (0)", 0),
        ("serious", "Serious (4)", 4),
        ("monitor_closely", "Monitor Closely (92)", 92),
        ("minor", "Minor (70)", 70),
    ]
    assert [c["heading_span"] for c in categories] == [
        {"start_line": 97, "end_line": 97},
        {"start_line": 99, "end_line": 99},
        {"start_line": 122, "end_line": 122},
        {"start_line": 658, "end_line": 658},
    ]


def test_preprocessing_keeps_original_spans_and_drops_page_chrome(
    tmp_path: Path,
) -> None:
    provenance = _provenance()
    sources_dir = _make_sources_dir(tmp_path / "with_bom", provenance)

    result = build(sources_dir)
    document = result["candidates"]["documents"][0]

    # 1. captopril (monitor_closely): ORIGINAL spans survive preprocessing even
    #    though page chrome (url footer at 209, timestamp+title at 213) and
    #    blank lines separate the two description paragraphs inside the
    #    contiguous entry span.
    monitor_closely = next(
        c for c in document["categories"] if c["category"] == "monitor_closely"
    )
    captopril = next(
        (e for e in monitor_closely["entries"] if e["name_text"] == "captopril"), None
    )
    assert captopril is not None, "entries are not yet parsed: no 'captopril' entry"
    paragraph_1 = (
        "sitagliptin, captopril. Either increases effects of the other by "
        "Mechanism: unspecified interaction mechanism. Use Caution/Monitor. "
        "Increased risk of adverse/toxic effects,"
    )
    # Line 215 has NO comma after 'specifically' (benazepril's fragment at
    # line 176 is a different entry and HAS the comma).
    paragraph_2 = "specifically increased risk of angioedema."
    assert captopril["span"] == {"start_line": 205, "end_line": 215}
    assert captopril["paragraphs"] == [
        {"text": paragraph_1, "span": {"start_line": 206, "end_line": 207}},
        {"text": paragraph_2, "span": {"start_line": 215, "end_line": 215}},
    ]
    assert captopril["raw_text"] == paragraph_1 + "\n" + paragraph_2

    # 2. Page chrome (medscape url footers, 6/22/26 timestamp+title lines) and
    #    the UTF-8 BOM never reach parsed text anywhere in the document.
    texts: list[str] = []
    for category in document["categories"]:
        for entry in category["entries"]:
            texts.append(entry["name_text"])
            texts.append(entry["raw_text"])
            texts.extend(p["text"] for p in entry["paragraphs"])
    for text in texts:
        assert "medscape.com" not in text
        assert "6/22/26" not in text
        assert "\ufeff" not in text

    # 3. Parsing stops at the Adverse Effects terminator (line 1005): the last
    #    minor entry is vanadium and interaction_section ends at its last
    #    content line — never including the terminator or anything after it.
    minor = next(c for c in document["categories"] if c["category"] == "minor")
    assert minor["entries"], "entries are not yet parsed: minor has no entries"
    vanadium = minor["entries"][-1]
    assert vanadium["name_text"] == "vanadium"
    assert vanadium["span"] == {"start_line": 1001, "end_line": 1003}
    assert document["interaction_section"] == {"start_line": 97, "end_line": 1003}
    # 'Nasopharyngitis' first appears at line 1021 (Adverse Effects onward).
    assert not any("Nasopharyngitis" in text for text in texts)

    # 4. BOM invariance: the provenance-recorded de-BOM'd copy parses to the
    #    same candidates except document sha256 and byte_count (BOM is 3 bytes).
    stripped_dir, record = _make_bom_stripped_sources_dir(
        tmp_path / "without_bom", provenance
    )
    assert record == {
        "derived_from": provenance["original"]["sha256"],
        "transformation": "strip UTF-8 BOM (EF BB BF) prefix",
    }
    stripped = build(stripped_dir)["candidates"]
    doc_with = dict(result["candidates"]["documents"][0])
    doc_without = dict(stripped["documents"][0])
    assert doc_with.pop("sha256") != doc_without.pop("sha256")
    assert doc_with.pop("byte_count") - doc_without.pop("byte_count") == len(_BOM)
    assert dict(result["candidates"], documents=[doc_with]) == dict(
        stripped, documents=[doc_without]
    )


def test_candidate_counts_match_declared_counts(tmp_path: Path) -> None:
    provenance = _provenance()
    sources_dir = _make_sources_dir(tmp_path, provenance)

    result = build(sources_dir)
    document = result["candidates"]["documents"][0]

    # Expected literals pinned from the monograph category headings in
    # docs/medical-docs/ (read-only source) and plan.md section 6.2 —
    # NEVER from parser output:
    #   'Contraindicated (0)'      line  97
    #   'Serious (4)'              line  99
    #   'Monitor Closely (92)'     line 122
    #   'Minor (70)'               line 658
    #   plan.md 6.2: 'declared counts are 0 contraindicated, 4 serious,
    #   92 monitor closely, 70 minor'
    expected: dict[str, int] = {
        "contraindicated": 0,
        "serious": 4,
        "monitor_closely": 92,
        "minor": 70,
    }

    # 1. Parsed entry counts per category equal the independently pinned
    #    literals; 166 total entries (contract section 1).
    parsed_counts = {c["category"]: len(c["entries"]) for c in document["categories"]}
    assert parsed_counts == expected
    assert sum(parsed_counts.values()) == 166

    # 2. Every count_check carries the independently pinned declared count and
    #    the parser's count agrees with it (ok is true).
    report_document = result["report"]["documents"][0]
    checks = {c["category"]: c for c in report_document["count_checks"]}
    assert set(checks) == set(expected)
    for category, declared in expected.items():
        check = checks[category]
        assert check["declared_count"] == declared
        assert check["parsed_count"] == check["declared_count"]
        assert check["ok"] is True

    # 3. Every entry has nonempty name/description text and a span inside the
    #    1265-line source (contract section 1 line_count), with entry headers
    #    appearing in source order.
    entries = [entry for c in document["categories"] for entry in c["entries"]]
    previous_start = 0
    for entry in entries:
        assert entry["name_text"].strip()
        assert entry["raw_text"].strip()
        span = entry["span"]
        assert 1 <= span["start_line"] <= span["end_line"] <= 1265
        assert span["start_line"] > previous_start
        previous_start = span["start_line"]

    # 4. ofloxacin appears in BOTH monitor_closely (span 525-529) and minor
    #    (span 912-914) as two separate entries (contract section 1).
    monitor_closely = next(
        c for c in document["categories"] if c["category"] == "monitor_closely"
    )
    minor = next(c for c in document["categories"] if c["category"] == "minor")
    ofloxacin_monitor = [
        e for e in monitor_closely["entries"] if e["name_text"] == "ofloxacin"
    ]
    ofloxacin_minor = [e for e in minor["entries"] if e["name_text"] == "ofloxacin"]
    assert len(ofloxacin_monitor) == 1
    assert len(ofloxacin_minor) == 1
    assert ofloxacin_monitor[0]["span"] == {"start_line": 525, "end_line": 529}
    assert ofloxacin_minor[0]["span"] == {"start_line": 912, "end_line": 914}
    # Two separate entries, not the same extraction counted twice.
    assert ofloxacin_monitor[0] is not ofloxacin_minor[0]
    assert ofloxacin_monitor[0]["raw_text"] != ofloxacin_minor[0]["raw_text"]


def test_removed_entry_fails_count_validation_and_still_reports(tmp_path: Path) -> None:
    provenance = _provenance()
    tampered_dir, record = _make_entry_removed_sources_dir(
        tmp_path / "tampered", provenance
    )
    assert record == {
        "derived_from": provenance["original"]["sha256"],
        "transformation": (
            "removed erdafitinib entry block, original lines 101-105, "
            "plus its trailing blank line 106"
        ),
    }

    # Contract section 2: structural/count failures never raise — build()
    # RETURNS the report.
    result = build(tampered_dir)

    report = result["report"]
    report_document = report["documents"][0]

    # 1. The serious count_check: declared_count 4 stays from the heading
    #    'Serious (4)' at line 99 (before the deletion, so its span is
    #    unshifted); parsed_count reflects exactly the one deleted entry.
    checks = {c["category"]: c for c in report_document["count_checks"]}
    assert checks["serious"] == {
        "category": "serious",
        "declared_count": 4,
        "parsed_count": 3,
        "ok": False,
    }

    # 2. Exactly one anomaly: count_mismatch (contract section 2 shape)
    #    carrying the unshifted serious heading span.
    anomalies = report_document["anomalies"]
    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly["code"] == "count_mismatch"
    assert anomaly["category"] == "serious"
    assert anomaly["declared_count"] == 4
    assert anomaly["parsed_count"] == 3
    assert anomaly["span"] == {"start_line": 99, "end_line": 99}

    # 3. The document and the whole report fail.
    assert report_document["ok"] is False
    assert report["ok"] is False

    # 4. The returned report is still complete: the three remaining serious
    #    entries (headers at original lines 107/112/117: ethanol, sotorasib,
    #    tepotinib) and the untouched contraindicated / monitor_closely /
    #    minor categories — nothing truncated or padded to hide the mismatch.
    document = result["candidates"]["documents"][0]
    serious = next(c for c in document["categories"] if c["category"] == "serious")
    assert [e["name_text"] for e in serious["entries"]] == [
        "ethanol",
        "sotorasib",
        "tepotinib",
    ]
    for category, count in (
        ("contraindicated", 0),
        ("monitor_closely", 92),
        ("minor", 70),
    ):
        assert checks[category] == {
            "category": category,
            "declared_count": count,
            "parsed_count": count,
            "ok": True,
        }
        section = next(c for c in document["categories"] if c["category"] == category)
        assert len(section["entries"]) == count

    # 5. Contrast in the same run: the pristine copy is unaffected.
    pristine_dir = _make_sources_dir(tmp_path / "pristine", provenance)
    pristine = build(pristine_dir)
    assert pristine["report"]["ok"] is True
    assert pristine["report"]["documents"][0]["anomalies"] == []
    pristine_checks = {
        c["category"]: c for c in pristine["report"]["documents"][0]["count_checks"]
    }
    assert pristine_checks["serious"] == {
        "category": "serious",
        "declared_count": 4,
        "parsed_count": 4,
        "ok": True,
    }


def test_cli_build_matches_library_build(tmp_path: Path) -> None:
    """S15-D (seam T3): the CLI `python -m x_insight.ddi build ...` is a public
    interface alongside `build(...)` and the two agree byte-for-byte on the
    JSON forms of the same result."""
    provenance = _provenance()
    # SYNTHETIC placeholder fixture (honest placeholder bytes, hashed only).
    terminology = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "synthetic-terminology-input.json"
    )

    def _run_cli(sources_dir: Path, out_dir: Path) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        src = str(_REPO_ROOT / "backend" / "src")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (src, env.get("PYTHONPATH")) if part
        )
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "x_insight.ddi",
                "build",
                "--sources",
                str(sources_dir),
                "--terminology",
                str(terminology),
                "--output",
                str(out_dir),
            ],
            env=env,
            capture_output=True,
            text=True,
        )

    # 1. Pristine byte-identical copy: exit 0; candidates.json / report.json
    #    parse-equal the in-test build() result for the same inputs.
    sources_dir = _make_sources_dir(tmp_path / "pristine", provenance)
    out_dir = tmp_path / "out-pristine"
    completed = _run_cli(sources_dir, out_dir)
    assert completed.returncode == 0, completed.stderr

    expected = build(sources_dir, terminology=terminology)
    candidates_file = out_dir / "candidates.json"
    report_file = out_dir / "report.json"
    assert candidates_file.is_file()
    assert report_file.is_file()
    assert (
        json.loads(candidates_file.read_text(encoding="utf-8"))
        == expected["candidates"]
    )
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report == expected["report"]
    assert report["inputs"]["terminology"] == {
        "path": str(terminology),
        "sha256": hashlib.sha256(terminology.read_bytes()).hexdigest(),
    }

    # 2. Provenance-recorded tampered copy (erdafitinib entry removed): exit 1
    #    and report.json is still written with the count_mismatch anomaly
    #    (declared 4 / parsed 3) and report.ok False.
    tampered_dir, _ = _make_entry_removed_sources_dir(tmp_path / "tampered", provenance)
    out_dir = tmp_path / "out-tampered"
    completed = _run_cli(tampered_dir, out_dir)
    assert completed.returncode == 1, completed.stderr

    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert report["ok"] is False
    report_document = report["documents"][0]
    checks = {c["category"]: c for c in report_document["count_checks"]}
    assert checks["serious"] == {
        "category": "serious",
        "declared_count": 4,
        "parsed_count": 3,
        "ok": False,
    }
    assert any(
        anomaly["code"] == "count_mismatch"
        and anomaly["category"] == "serious"
        and anomaly["declared_count"] == 4
        and anomaly["parsed_count"] == 3
        for anomaly in report_document["anomalies"]
    )
