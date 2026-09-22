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
import re
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
        {
            "text": paragraph_1,
            "span": {"start_line": 206, "end_line": 207},
            "direction": {"subject": None, "object": None},
        },
        {
            "text": paragraph_2,
            "span": {"start_line": 215, "end_line": 215},
            "direction": {"subject": None, "object": None},
        },
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


_VARIANTS_PROVENANCE = (
    Path(__file__).resolve().parent / "fixtures" / "corpus-variants-provenance.json"
)


def _variants_provenance() -> dict[str, Any]:
    return json.loads(_VARIANTS_PROVENANCE.read_text(encoding="utf-8"))


def _make_variant_sources_dir(
    tmp_path: Path, provenance: dict[str, Any], stems: list[str]
) -> Path:
    """Copy variant originals byte-identically, preserving Group/Name.txt stems.

    Fixture-copy rule: each copy's sha256 must equal the recorded provenance
    hash. Subject detection uses the stem — files are NEVER renamed to x.txt.
    """
    by_name = {
        record["original"]["path"].split("/")[-1]: record
        for record in provenance["files"]
    }
    sources_dir = tmp_path / "sources"
    for stem in stems:
        record = by_name[stem]
        relative = Path(record["original"]["path"].split("DDI-text/")[-1])
        assert relative.parts[1] == stem, relative
        original = _REPO_ROOT / "docs" / "medical-docs" / "DDI-text" / relative
        copy_path = sources_dir / relative
        copy_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, copy_path)
        copy_sha256 = hashlib.sha256(copy_path.read_bytes()).hexdigest()
        assert copy_sha256 == record["original"]["sha256"], stem
    return sources_dir


def _variant_documents(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        document["relative_path"].split("/")[-1]: document
        for document in result["candidates"]["documents"]
    }


def test_build_drops_extended_page_chrome(tmp_path: Path) -> None:
    """S16 RED: Medscape page chrome is never parsed as entries."""
    provenance = _variants_provenance()
    sources_dir = _make_variant_sources_dir(
        tmp_path, provenance, ["Atropine.txt", "Tramadol.txt", "Ondansetron.txt"]
    )

    result = build(sources_dir)
    documents = _variant_documents(result)
    assert set(documents) == {"Atropine.txt", "Tramadol.txt", "Ondansetron.txt"}

    chrome_patterns = [
        ("bare pager", re.compile(r"^\d+/\d+$")),
        ("bare datetime", re.compile(r"^\d{1,2}/\d{1,2}/\d{2},")),
        (
            "dosing title",
            re.compile(r"dosing, indications, interactions, adverse effects, and more"),
        ),
        ("url", re.compile(r"^https?://")),
        ("sponsor", re.compile(r"^Sponsor$")),
    ]
    for stem, document in documents.items():
        for category in document["categories"]:
            for entry in category["entries"]:
                for kind, pattern in chrome_patterns:
                    assert not pattern.search(entry["name_text"]), (
                        kind,
                        stem,
                        category["category"],
                        entry["name_text"],
                        entry["span"],
                    )

    atropine = documents["Atropine.txt"]
    serious = next(c for c in atropine["categories"] if c["category"] == "serious")
    serious_names = [entry["name_text"] for entry in serious["entries"]]
    assert "2/21" not in serious_names
    assert not any(name.startswith("6/22/26") for name in serious_names)
    assert not any(
        "dosing, indications, interactions, adverse effects, and more" in name
        for name in serious_names
    )
    assert len(serious["entries"]) == 10


def test_build_ondansetron_contra_spans_sponsor_block(tmp_path: Path) -> None:
    """S16 RED: Ondansetron contraindicated spans + sponsor ad-block chrome."""
    provenance = _variants_provenance()
    sources_dir = _make_variant_sources_dir(tmp_path, provenance, ["Ondansetron.txt"])

    result = build(sources_dir)
    document = _variant_documents(result)["Ondansetron.txt"]
    contraindicated = next(
        c for c in document["categories"] if c["category"] == "contraindicated"
    )
    assert contraindicated["declared_count"] == 4

    entries = contraindicated["entries"]
    assert [entry["name_text"] for entry in entries] == [
        "apomorphine",
        "dronedarone",
        "lefamulin",
        "posaconazole",
    ]
    assert [entry["span"] for entry in entries] == [
        {"start_line": 143, "end_line": 147},
        {"start_line": 148, "end_line": 154},
        {"start_line": 155, "end_line": 158},
        {"start_line": 159, "end_line": 161},
    ]

    posaconazole = entries[3]
    assert "CYP3A4 metabolism. Contraindicated." in posaconazole["raw_text"]
    dronedarone = entries[1]
    assert len(dronedarone["paragraphs"]) == 2

    chrome_markers = (
        "Sponsor",
        "Luxena Pharmaceuticals",
        "medscape.com",
        "5:31 PM",
        "dosing, indications, interactions, adverse effects, and more",
        "5/41",
    )
    for entry in entries:
        for paragraph in entry["paragraphs"]:
            for marker in chrome_markers:
                assert marker not in paragraph["text"], (
                    entry["name_text"],
                    marker,
                )


def test_build_page_break_continuation_joins_entry(tmp_path: Path) -> None:
    """S16 RED: page-break continuations join ONE entry; next header separate."""
    provenance = _variants_provenance()
    sources_dir = _make_variant_sources_dir(
        tmp_path,
        provenance,
        [
            "Atropine.txt",
            "Tramadol.txt",
            "Celecoxib.txt",
            "Acetaminophen.txt",
        ],
    )

    result = build(sources_dir)
    documents = _variant_documents(result)

    def _entry(document: dict[str, Any], name: str) -> dict[str, Any]:
        matches = [
            entry
            for category in document["categories"]
            for entry in category["entries"]
            if entry["name_text"] == name
        ]
        assert len(matches) == 1, (name, len(matches))
        return matches[0]

    # Atropine glucagon-intranasal: ONE entry 69-83, chrome-free joined text.
    atropine = documents["Atropine.txt"]
    glucagon = _entry(atropine, "glucagon intranasal")
    assert glucagon["span"] == {"start_line": 69, "end_line": 83}
    # Source L71 ends with trailing "and" and L82 supplies "glucagon ...":
    # the sentence is split across the chrome gap. raw_text joins paragraphs
    # with "\n" (S15-pinned seam behavior), so assert each half separately
    # rather than a space-joined cross-paragraph string.
    assert "Coadministration of anticholinergic drugs and" in glucagon["raw_text"]
    assert (
        "glucagon increase the risk of gastrointestinal adverse reactions "
        "due to additive effects on inhibition of gastrointestinal motility. ."
    ) in glucagon["raw_text"]
    assert "medscape.com" not in glucagon["raw_text"]
    assert "6/22/26" not in glucagon["raw_text"]
    glycopyrronium = _entry(atropine, "glycopyrronium tosylate topical")
    assert glycopyrronium["span"]["start_line"] == 84
    assert glycopyrronium is not glucagon

    # Tramadol encorafenib: ONE entry 1521-1533 with its tail.
    tramadol = documents["Tramadol.txt"]
    encorafenib = _entry(tramadol, "encorafenib")
    assert encorafenib["span"] == {"start_line": 1521, "end_line": 1533}
    assert (
        "CYP3A4 substrates may result in increased toxicity or decreased "
        "efficacy of these agents."
    ) in encorafenib["raw_text"]
    enzalutamide = _entry(tramadol, "enzalutamide")
    assert enzalutamide["span"]["start_line"] == 1535

    # Celecoxib fosinopril (serious occurrence at 202; a second fosinopril
    # entry lives in monitor_closely, so scope the lookup to serious).
    celecoxib = documents["Celecoxib.txt"]
    serious = next(c for c in celecoxib["categories"] if c["category"] == "serious")
    fosinopril_matches = [
        entry for entry in serious["entries"] if entry["name_text"] == "fosinopril"
    ]
    assert len(fosinopril_matches) == 1
    fosinopril = fosinopril_matches[0]
    assert fosinopril in serious["entries"]
    assert fosinopril["span"] == {"start_line": 202, "end_line": 214}
    assert (
        "interactions is likely related to the ability of NSAIDs to reduce "
        "the synthesis of vasodilating renal prostaglandins."
    ) in fosinopril["raw_text"]
    ivosidenib = _entry(celecoxib, "ivosidenib")
    assert ivosidenib["span"]["start_line"] == 216

    # Acetaminophen flibanserin 334-345 and midazolam-intranasal 393-404.
    acetaminophen = documents["Acetaminophen.txt"]
    flibanserin = _entry(acetaminophen, "flibanserin")
    assert flibanserin["span"] == {"start_line": 334, "end_line": 345}
    assert (
        "flibanserin adverse effects may occur if coadministered with "
        "multiple weak CYP3A4 inhibitors."
    ) in flibanserin["raw_text"]
    imatinib = _entry(acetaminophen, "imatinib")
    assert imatinib["span"]["start_line"] == 347
    midazolam = _entry(acetaminophen, "midazolam intranasal")
    assert midazolam["span"] == {"start_line": 393, "end_line": 404}
    assert (
        "Coadministration of mild CYP3A4 inhibitors with midazolam "
        "intranasal may cause higher midazolam systemic exposure, which may "
        "prolong sedation."
    ) in midazolam["raw_text"]
    mipomersen = _entry(acetaminophen, "mipomersen")
    assert mipomersen["span"]["start_line"] == 406
    # Ondansetron across-chrome same-entry fragments (rule ordering: the
    # fragment after a chrome gap joins the pre-gap open entry, and the
    # P2-wraps-P1 rule takes precedence over the entry-header grammar).
    ondansetron_dir = _make_variant_sources_dir(
        tmp_path / "ondan", provenance, ["Ondansetron.txt"]
    )
    ondansetron = _variant_documents(build(ondansetron_dir))["Ondansetron.txt"]
    monitor = next(
        c for c in ondansetron["categories"] if c["category"] == "monitor_closely"
    )
    # albuterol inhaled: header 1003 through chrome-separated fragment 1011.
    albuterol_inhaled = [
        entry
        for entry in monitor["entries"]
        if entry["name_text"] == "albuterol inhaled"
    ]
    assert len(albuterol_inhaled) == 1
    assert albuterol_inhaled[0]["span"] == {
        "start_line": 1003,
        "end_line": 1011,
    }
    # Source L1005 ends "... monitor electrolytes and ECG" and L1011 supplies
    # "changes" across the chrome gap: separate paragraphs, so raw_text
    # (S15 "\n"-joined) holds each half, not a space-joined string.
    assert "monitor electrolytes and ECG" in albuterol_inhaled[0]["raw_text"]
    assert albuterol_inhaled[0]["paragraphs"][-1]["text"] == "changes"
    # elvitegravir combo: header 1140 through fragment 1149-1150.
    elvitegravir = [
        entry
        for entry in monitor["entries"]
        if entry["name_text"] == "elvitegravir/cobicistat/emtricitabine/tenofovir DF"
    ]
    assert len(elvitegravir) == 1
    assert elvitegravir[0]["span"] == {
        "start_line": 1140,
        "end_line": 1150,
    }
    assert "threatening events." in elvitegravir[0]["raw_text"]
    # panobinostat: header 1330 through fragment 1339-1340.
    panobinostat = [
        entry for entry in monitor["entries"] if entry["name_text"] == "panobinostat"
    ]
    assert len(panobinostat) == 1
    assert panobinostat[0]["span"] == {
        "start_line": 1330,
        "end_line": 1340,
    }
    assert "frequent ECG monitoring." in panobinostat[0]["raw_text"]
    # The fragments are never entries themselves.
    fragment_names = [entry["name_text"] for entry in monitor["entries"]]
    assert "changes" not in fragment_names
    assert (
        "for which elevated plasma concentrations are associated with "
        "serious and/or life-"
    ) not in fragment_names
    assert (
        "recommended; however, antiemetic drugs known to prolong QTc (eg, dolasetron,"
    ) not in fragment_names


def test_build_wrapped_entity_heading_preserved(tmp_path: Path) -> None:
    """S16 RED: wrapped heading/description fragments stay in ONE entry."""
    provenance = _variants_provenance()
    sources_dir = _make_variant_sources_dir(
        tmp_path, provenance, ["Bupropion.txt", "Nortriptyline.txt"]
    )

    result = build(sources_dir)
    documents = _variant_documents(result)

    # Bupropion modafinil: header 1279 through chrome-separated tail 1288.
    bupropion = documents["Bupropion.txt"]
    minor = next(c for c in bupropion["categories"] if c["category"] == "minor")
    modafinil = [
        entry for entry in minor["entries"] if entry["name_text"] == "modafinil"
    ]
    assert len(modafinil) == 1
    assert modafinil[0]["span"] == {"start_line": 1279, "end_line": 1288}
    assert (
        "levels of bupropion, but incr levels of active metabolites. ."
        in modafinil[0]["raw_text"]
    )
    orphans = [
        entry
        for category in bupropion["categories"]
        for entry in category["entries"]
        if "levels of bupropion" in entry["name_text"]
    ]
    assert orphans == []

    # Nortriptyline zuranolone (serious): header 1206 through tail 1217.
    nortriptyline = documents["Nortriptyline.txt"]
    serious = next(c for c in nortriptyline["categories"] if c["category"] == "serious")
    zuranolone = [
        entry for entry in serious["entries"] if entry["name_text"] == "zuranolone"
    ]
    assert len(zuranolone) == 1
    assert zuranolone[0]["span"] == {"start_line": 1206, "end_line": 1217}
    assert (
        "CNS depressants may increase impairment of psychomotor performance "
        "or CNS depressant effects. If unavoidable, consider dose reduction. ."
        in zuranolone[0]["raw_text"]
    )
    fragments = [
        entry
        for category in nortriptyline["categories"]
        for entry in category["entries"]
        if "CNS depressants may increase" in entry["name_text"]
    ]
    assert fragments == []


def test_build_simethicone_reports_missing_section(tmp_path: Path) -> None:
    """S16 RED: a monograph with no interaction section reports, never raises."""
    provenance = _variants_provenance()
    sources_dir = _make_variant_sources_dir(tmp_path, provenance, ["Simethicone.txt"])

    result = build(sources_dir)
    assert len(result["candidates"]["documents"]) == 1
    document = result["candidates"]["documents"][0]
    assert document["relative_path"] == "Gastrointestinal Medications/Simethicone.txt"
    assert document["sha256"] == next(
        record["original"]["sha256"]
        for record in provenance["files"]
        if record["original"]["path"].endswith("Simethicone.txt")
    )
    assert document["interaction_section"] is None
    assert document["categories"] == []

    assert len(result["report"]["documents"]) == 1
    report_document = result["report"]["documents"][0]
    assert report_document["interaction_section_found"] is False
    assert report_document["count_checks"] == []
    assert report_document["ok"] is False
    assert len(report_document["anomalies"]) == 1
    anomaly = report_document["anomalies"][0]
    assert anomaly["code"] == "missing_interaction_section"
    assert report_document["sha256"] == document["sha256"]
    assert report_document["relative_path"] == document["relative_path"]


_S16_SLICE2_ORIGINALS: dict[str, tuple[str, str]] = {
    "Bromocriptine.txt": (
        "Anticholinergics & Parkinsonism Agents/Bromocriptine.txt",
        "9f53a99b9b1510696d5b944b7dfaeb3ef6a8592b370578d819e1050b3b82070c",
    ),
    "Ondansetron.txt": (
        "Gastrointestinal Medications/Ondansetron.txt",
        "cf5fcef10659632064d8bc4b81657548565e8ef3414a402fbe055f090bcbf25e",
    ),
}


def _make_slice2_sources_dir(base_dir: Path, stems: list[str]) -> Path:
    """Copy slice-2 originals byte-identically, preserving Group/Name.txt stems.

    Fixture-copy rule: each copy's sha256 must equal the pinned provenance
    hash above (originals under docs/medical-docs/DDI-text are READ-ONLY;
    subject detection uses the stem -- files are NEVER renamed to x.txt).
    """
    sources_dir = base_dir / "sources"
    for stem in stems:
        relative, sha256 = _S16_SLICE2_ORIGINALS[stem]
        original = _REPO_ROOT / "docs" / "medical-docs" / "DDI-text" / relative
        copy_path = sources_dir / relative
        copy_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, copy_path)
        assert hashlib.sha256(copy_path.read_bytes()).hexdigest() == sha256, stem
    return sources_dir


def test_build_repeated_pair_entries_survive(tmp_path: Path) -> None:
    """S16 slice 2 RED: repeated-pair entries survive in every category."""
    provenance = _provenance()
    sources_dir = _make_sources_dir(tmp_path / "sita", provenance)
    result = build(sources_dir)
    document = result["candidates"]["documents"][0]
    assert document["sha256"] == provenance["original"]["sha256"]
    assert document["byte_count"] == 44041
    assert document["line_count"] == 1265

    # Declared counts pinned from the monograph headings (grep -n: L122/L658;
    # parser numbering identical here -- Sitagliptin.txt carries a BOM but no
    # 0x0C bytes, so splitlines numbering equals grep -n numbering).
    expected: dict[str, int] = {
        "contraindicated": 0,
        "serious": 4,
        "monitor_closely": 92,
        "minor": 70,
    }
    parsed_counts = {c["category"]: len(c["entries"]) for c in document["categories"]}
    assert parsed_counts == expected
    assert sum(parsed_counts.values()) == 166
    report_document = result["report"]["documents"][0]
    for check in report_document["count_checks"]:
        assert check["parsed_count"] == check["declared_count"]
        assert check["ok"] is True

    # Sitagliptin ofloxacin, re-verified with sed -n against the original:
    # monitor header L525, para L526-529; minor header L912, para L913-914.
    # Consistent with (not replacing) the pre-existing span test above.
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
    assert ofloxacin_monitor[0]["paragraphs"][0]["span"] == {
        "start_line": 526,
        "end_line": 529,
    }
    assert ofloxacin_minor[0]["paragraphs"][0]["span"] == {
        "start_line": 913,
        "end_line": 914,
    }
    assert ofloxacin_monitor[0]["paragraphs"][0]["text"] == (
        "ofloxacin increases effects of sitagliptin by pharmacodynamic "
        "synergism. Use Caution/Monitor. Quinolone antibiotic administration "
        "may result in hyper- or hypoglycemia. Gatifloxacin is most likely "
        "to produce dysglycemia; moxifloxacin is least likely."
    )
    assert ofloxacin_minor[0]["paragraphs"][0]["text"] == (
        "ofloxacin, sitagliptin. Mechanism: unspecified interaction "
        "mechanism. Minor/Significance Unknown. Potential dysglycemia."
    )
    # Two distinct entry objects with different raw_text -- neither category
    # swallowed the pair.
    assert ofloxacin_monitor[0] is not ofloxacin_minor[0]
    assert ofloxacin_monitor[0]["raw_text"] != ofloxacin_minor[0]["raw_text"]

    # Ondansetron buprenorphine block, re-verified with grep -n / sed -n
    # (no BOM, no 0x0C bytes: parser numbering equals grep -n numbering):
    # base header L257, desc L258, chrome gap L259-262, blank L263, tail
    # 'Drug.' L264; variant headers L265/L268/L271/L274.
    ondan_dir = _make_slice2_sources_dir(tmp_path / "ondan", ["Ondansetron.txt"])
    ondan_result = build(ondan_dir)
    ondan_document = _variant_documents(ondan_result)["Ondansetron.txt"]
    assert ondan_document["sha256"] == _S16_SLICE2_ORIGINALS["Ondansetron.txt"][1]
    serious = next(
        c for c in ondan_document["categories"] if c["category"] == "serious"
    )
    serious_check = next(
        c
        for c in ondan_result["report"]["documents"][0]["count_checks"]
        if c["category"] == "serious"
    )
    assert serious_check["declared_count"] == 164
    assert serious_check["parsed_count"] == 164
    assert serious_check["ok"] is True
    bup_entries = [
        e for e in serious["entries"] if e["name_text"].startswith("buprenorphine")
    ]
    assert [e["name_text"] for e in bup_entries] == [
        "buprenorphine",
        "buprenorphine buccal",
        "buprenorphine subdermal implant",
        "buprenorphine transdermal",
        "buprenorphine, long-acting injection",
    ]
    assert [e["span"] for e in bup_entries] == [
        {"start_line": 257, "end_line": 264},
        {"start_line": 265, "end_line": 267},
        {"start_line": 268, "end_line": 270},
        {"start_line": 271, "end_line": 273},
        {"start_line": 274, "end_line": 276},
    ]
    # Base entry keeps its chrome-split wrapped description in ONE entry:
    # para L258 plus tail 'Drug.' L264.
    base = bup_entries[0]
    assert [p["span"] for p in base["paragraphs"]] == [
        {"start_line": 258, "end_line": 258},
        {"start_line": 264, "end_line": 264},
    ]
    assert base["paragraphs"][0]["text"] == (
        "buprenorphine and ondansetron both increase QTc interval. "
        "Avoid or Use Alternate"
    )
    assert base["paragraphs"][1]["text"] == "Drug."
    assert bup_entries[1]["paragraphs"][0]["text"] == (
        "buprenorphine buccal and ondansetron both increase QTc interval. "
        "Avoid or Use Alternate Drug."
    )
    assert bup_entries[2]["paragraphs"][0]["text"] == (
        "buprenorphine subdermal implant and ondansetron both increase QTc "
        "interval. Avoid or Use Alternate Drug."
    )
    assert bup_entries[3]["paragraphs"][0]["text"] == (
        "buprenorphine transdermal and ondansetron both increase QTc "
        "interval. Avoid or Use Alternate Drug."
    )
    assert bup_entries[4]["paragraphs"][0]["text"] == (
        "buprenorphine, long-acting injection and ondansetron both increase "
        "QTc interval. Avoid or Use Alternate Drug."
    )
    # Five distinct entries, none swallowed/merged.
    assert len({id(e) for e in bup_entries}) == 5
    assert len({e["raw_text"] for e in bup_entries}) == 5


def test_build_contradictory_severity_survives(tmp_path: Path) -> None:
    """S16 slice 2 RED: contradictory severity assertions both survive."""
    # Bromocriptine.txt ground truth, verified with sha256sum / wc -c /
    # grep -n / sed -n before pinning: sha256
    # 9f53a99b9b1510696d5b944b7dfaeb3ef6a8592b370578d819e1050b3b82070c,
    # 61937 bytes, 1456 splitlines lines (no BOM; thirty 0x0C page-break
    # bytes fused onto datetime chrome lines shift parser numbering ahead
    # of grep -n numbering: headings grep L138/L207/L479/L880 = parser
    # L141/L211/L489/L898; amphetamine headers grep L220/L487 = parser
    # L225/L497; descriptions grep L221-222/L488-489 = parser L226-227 and
    # L498-499). Spans below use parser (splitlines 1-based) numbering.
    sources_dir = _make_slice2_sources_dir(tmp_path, ["Bromocriptine.txt"])
    result = build(sources_dir)
    document = result["candidates"]["documents"][0]
    assert document["sha256"] == _S16_SLICE2_ORIGINALS["Bromocriptine.txt"][1]
    assert document["byte_count"] == 61937
    assert document["line_count"] == 1456

    expected: dict[str, int] = {
        "contraindicated": 16,
        "serious": 58,
        "monitor_closely": 88,
        "minor": 7,
    }
    heading_spans = {c["category"]: c["heading_span"] for c in document["categories"]}
    assert heading_spans == {
        "contraindicated": {"start_line": 141, "end_line": 141},
        "serious": {"start_line": 211, "end_line": 211},
        "monitor_closely": {"start_line": 489, "end_line": 489},
        "minor": {"start_line": 898, "end_line": 898},
    }
    parsed_counts = {c["category"]: len(c["entries"]) for c in document["categories"]}
    assert parsed_counts == expected
    assert sum(parsed_counts.values()) == 169
    report_document = result["report"]["documents"][0]
    for check in report_document["count_checks"]:
        assert check["parsed_count"] == check["declared_count"]
        assert check["ok"] is True

    # amphetamine in BOTH serious and monitor_closely with source-pinned text.
    serious = next(c for c in document["categories"] if c["category"] == "serious")
    monitor_closely = next(
        c for c in document["categories"] if c["category"] == "monitor_closely"
    )
    serious_amp = [e for e in serious["entries"] if e["name_text"] == "amphetamine"]
    monitor_amp = [
        e for e in monitor_closely["entries"] if e["name_text"] == "amphetamine"
    ]
    assert len(serious_amp) == 1
    assert len(monitor_amp) == 1
    assert serious_amp[0]["span"] == {"start_line": 225, "end_line": 227}
    assert monitor_amp[0]["span"] == {"start_line": 497, "end_line": 499}
    assert serious_amp[0]["paragraphs"][0]["span"] == {
        "start_line": 226,
        "end_line": 227,
    }
    assert monitor_amp[0]["paragraphs"][0]["span"] == {
        "start_line": 498,
        "end_line": 499,
    }
    assert serious_amp[0]["raw_text"] == (
        "bromocriptine, amphetamine. Mechanism: pharmacodynamic synergism. "
        "Contraindicated. Additive vasospasm; risk of hypertension."
    )
    assert monitor_amp[0]["raw_text"] == (
        "bromocriptine, amphetamine. Either increases effects of the other by "
        "pharmacodynamic synergism. Use Caution/Monitor. Hypertension, V tach."
    )
    assert "Contraindicated. Additive vasospasm" in serious_amp[0]["raw_text"]
    assert "Use Caution/Monitor. Hypertension, V tach." in monitor_amp[0]["raw_text"]
    # The conflict is preserved, not resolved or hidden: two distinct entries
    # with differing raw_text, and category counts reported as-is.
    assert serious_amp[0] is not monitor_amp[0]
    assert serious_amp[0]["raw_text"] != monitor_amp[0]["raw_text"]


def _paragraph_direction(entry_name: str, paragraph: dict[str, Any]) -> Any:
    """Return a paragraph's explicit direction marking (RED if absent)."""
    assert "direction" in paragraph, (
        f"{entry_name}: paragraph {paragraph['span']} carries no direction "
        "marking distinguishing explicit subject->object assertions from "
        f"unknown/mutual ones: {paragraph['text'][:80]!r}"
    )
    return paragraph["direction"]


def test_build_direction_marked_unknown_unless_explicit(tmp_path: Path) -> None:
    """S16 slice 2 RED: direction marked only when the source is explicit."""
    # Wording verified with sed -n against the originals: Ondansetron
    # dronedarone contra entry L148-154 holds para1 L149-150 ('dronedarone
    # will increase the level or effect of ondansetron by affecting ...' --
    # directed dronedarone->ondansetron) and para2 L151-154 ('dronedarone
    # and ondansetron both increase QTc interval. ...' -- mutual, no
    # directed subject); Sitagliptin ofloxacin monitor para L526-529
    # ('ofloxacin increases effects of sitagliptin ...' -- directed
    # ofloxacin->sitagliptin) and minor para L913-914 ('ofloxacin,
    # sitagliptin. Mechanism: unspecified interaction mechanism.' -- no
    # direction verb, unknown).
    ondan_dir = _make_slice2_sources_dir(tmp_path / "ondan", ["Ondansetron.txt"])
    ondan_document = _variant_documents(build(ondan_dir))["Ondansetron.txt"]
    contraindicated = next(
        c for c in ondan_document["categories"] if c["category"] == "contraindicated"
    )
    dronedarone = next(
        e for e in contraindicated["entries"] if e["name_text"] == "dronedarone"
    )
    assert dronedarone["span"] == {"start_line": 148, "end_line": 154}
    assert len(dronedarone["paragraphs"]) == 2
    dron_directed, dron_mutual = dronedarone["paragraphs"]
    assert dron_directed["span"] == {"start_line": 149, "end_line": 150}
    assert dron_mutual["span"] == {"start_line": 151, "end_line": 154}
    assert dron_directed["text"].startswith(
        "dronedarone will increase the level or effect of ondansetron"
    )
    assert dron_mutual["text"].startswith(
        "dronedarone and ondansetron both increase QTc interval."
    )

    provenance = _provenance()
    sita_dir = _make_sources_dir(tmp_path / "sita", provenance)
    sita_document = build(sita_dir)["candidates"]["documents"][0]
    monitor_closely = next(
        c for c in sita_document["categories"] if c["category"] == "monitor_closely"
    )
    minor = next(c for c in sita_document["categories"] if c["category"] == "minor")
    oflox_monitor = next(
        e for e in monitor_closely["entries"] if e["name_text"] == "ofloxacin"
    )
    oflox_minor = next(e for e in minor["entries"] if e["name_text"] == "ofloxacin")
    monitor_para = oflox_monitor["paragraphs"][0]
    minor_para = oflox_minor["paragraphs"][0]
    assert monitor_para["text"].startswith(
        "ofloxacin increases effects of sitagliptin by pharmacodynamic synergism."
    )
    assert minor_para["text"].startswith(
        "ofloxacin, sitagliptin. Mechanism: unspecified interaction mechanism."
    )

    # Explicit subject->object assertions carry their direction ...
    assert _paragraph_direction("dronedarone", dron_directed) == {
        "subject": "dronedarone",
        "object": "ondansetron",
    }
    assert _paragraph_direction("ofloxacin/monitor", monitor_para) == {
        "subject": "ofloxacin",
        "object": "sitagliptin",
    }
    # ... while mutual ('both increase') and verb-free ('unspecified
    # interaction mechanism') wordings mark no directed subject.
    assert _paragraph_direction("dronedarone", dron_mutual) == {
        "subject": None,
        "object": None,
    }
    assert _paragraph_direction("ofloxacin/minor", minor_para) == {
        "subject": None,
        "object": None,
    }


def test_report_covers_entire_corpus_with_enumerated_anomalies(
    tmp_path: Path,
) -> None:
    """S16 slice 3: report-only full-corpus discovery enumerates anomalies."""
    sources = _REPO_ROOT / "docs" / "medical-docs" / "DDI-text"
    originals = sorted(
        path.relative_to(sources).as_posix()
        for path in sources.rglob("*.txt")
        if path.is_file()
    )
    # Complete 128-file discovery unless sources changed (AGENTS.md audit).
    assert len(originals) == 128

    result = build(sources)
    report = result["report"]
    assert report["parser_version"] == "ddi-ingest-1"
    documents = report["documents"]
    assert len(documents) == 128
    # Stable relative-path order; every discovered file has a verdict.
    assert [d["relative_path"] for d in documents] == originals
    for document in documents:
        assert (
            document["sha256"]
            == hashlib.sha256(
                (sources / document["relative_path"]).read_bytes()
            ).hexdigest()
        )
        assert isinstance(document["ok"], bool)
        assert isinstance(document["interaction_section_found"], bool)
        assert isinstance(document["count_checks"], list)
        assert isinstance(document["anomalies"], list)
        for check in document["count_checks"]:
            assert set(check) == {
                "category",
                "declared_count",
                "parsed_count",
                "ok",
            }
            assert check["ok"] == (check["parsed_count"] == check["declared_count"])
        for anomaly in document["anomalies"]:
            assert anomaly["code"] in {
                "missing_interaction_section",
                "count_mismatch",
            }
            assert "message" in anomaly
        # Failures stay in the denominator: a failed document is still
        # reported with its counts, checksum and diagnostic location.
        assert document["ok"] == (
            document["interaction_section_found"]
            and all(c["ok"] for c in document["count_checks"])
        )
        if not document["ok"]:
            assert document["anomalies"], document["relative_path"]
            for anomaly in document["anomalies"]:
                assert anomaly.get("span") is None or set(anomaly["span"]) == {
                    "start_line",
                    "end_line",
                }

    # Report-only CLI agrees with the library and exits 0 despite failures.
    out_dir = tmp_path / "out-report"
    env = dict(os.environ)
    src = str(_REPO_ROOT / "backend" / "src")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (src, env.get("PYTHONPATH")) if part
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "x_insight.ddi",
            "report",
            "--sources",
            str(sources),
            "--output",
            str(out_dir),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads((out_dir / "report.json").read_text(encoding="utf-8")) == report
    assert (
        json.loads((out_dir / "candidates.json").read_text(encoding="utf-8"))
        == result["candidates"]
    )
