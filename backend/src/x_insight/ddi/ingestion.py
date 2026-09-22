from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

PARSER_VERSION = "ddi-ingest-1"

_CATEGORY_HEADING = re.compile(
    r"^(Contraindicated|Serious|Monitor Closely|Minor) \((\d+)\)$"
)
_CATEGORY_KEYS = {
    "Contraindicated": "contraindicated",
    "Serious": "serious",
    "Monitor Closely": "monitor_closely",
    "Minor": "minor",
}
_SECTION_END_HEADINGS = frozenset({"Adverse Effects", "Warnings"})
_PAGE_CHROME = (
    # repeated print header: timestamp + page title
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2}, \d{1,2}:\d{2} [AP]M "),
    # url footer with trailing page counter, e.g. "... 4/22"
    re.compile(r"^https?://\S+\s+\d+/\d+$"),
)


def _is_page_chrome(text: str) -> bool:
    return any(pattern.match(text) for pattern in _PAGE_CHROME)


def _starts_entry(text: str, prev_content: str, subject: str) -> bool:
    """Entry-header grammar (contract section 3) on ORIGINAL lines.

    A paragraph-start line begins a new entry when it contains no '.' and is not
    a category heading (headings match earlier), does not begin the document's
    subject-drug sentence pattern — concretely: it never names the subject drug,
    since interaction sentences name both drugs ("X will increase ... of
    sitagliptin by ...") — and does not continue the previous content line's
    unfinished sentence (that line ends with ',' or ';'). The last clause is the
    smallest honest added rule (recorded in the handoff): it keeps wrapped
    continuation fragments such as captopril line 215 and dulaglutide line 273
    description lines, reproducing exactly 166 headers on the fixture.
    """
    return (
        "." not in text
        and subject not in text
        and not prev_content.endswith((",", ";"))
    )


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _discover(source_dir: Path) -> list[str]:
    return sorted(
        path.relative_to(source_dir).as_posix()
        for path in source_dir.rglob("*.txt")
        if path.is_file()
    )


def _parse_document(
    relative_path: str, data: bytes
) -> tuple[dict[str, Any], dict[str, Any]]:
    lines = data.decode("utf-8-sig").splitlines()
    sha256 = _sha256_hex(data)
    subject = Path(relative_path).stem.lower()
    categories: list[dict[str, Any]] = []
    section_start = 0
    section_end = len(lines)
    current_category: dict[str, Any] | None = None
    current_entry: dict[str, Any] | None = None
    # current paragraph run of consecutive non-chrome, non-blank content lines
    run: list[tuple[int, str]] = []
    run_starts_entry = False
    prev_content = ""
    last_entry_end = 0

    def flush_run() -> None:
        nonlocal run, run_starts_entry, last_entry_end
        if run and current_entry is not None:
            body = run[1:] if run_starts_entry else run
            if body:
                current_entry["paragraphs"].append(
                    {
                        "text": " ".join(text for _, text in body),
                        "span": {"start_line": body[0][0], "end_line": body[-1][0]},
                    }
                )
                current_entry["span"]["end_line"] = body[-1][0]
                last_entry_end = body[-1][0]
        run = []
        run_starts_entry = False

    for number, line in enumerate(lines, start=1):
        text = line.strip()
        match = _CATEGORY_HEADING.match(text)
        if match:
            flush_run()
            current_entry = None
            if section_start == 0:
                section_start = number
            current_category = {
                "category": _CATEGORY_KEYS[match.group(1)],
                "heading_text": text,
                "heading_span": {"start_line": number, "end_line": number},
                "declared_count": int(match.group(2)),
                "entries": [],
            }
            categories.append(current_category)
            prev_content = text
            continue
        if section_start and text in _SECTION_END_HEADINGS:
            flush_run()
            section_end = number - 1
            break
        if not text or _is_page_chrome(text):
            flush_run()
            continue
        if (
            not run
            and current_category is not None
            and _starts_entry(text, prev_content, subject)
        ):
            current_entry = {
                "name_text": text,
                "raw_text": "",
                "span": {"start_line": number, "end_line": number},
                "paragraphs": [],
            }
            current_category["entries"].append(current_entry)
            last_entry_end = number
            run_starts_entry = True
        run.append((number, text))
        prev_content = text
    flush_run()

    for category in categories:
        for entry in category["entries"]:
            entry["raw_text"] = "\n".join(p["text"] for p in entry["paragraphs"])

    interaction_section = (
        {
            "start_line": section_start,
            "end_line": last_entry_end or section_end,
        }
        if section_start
        else None
    )

    count_checks: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    if interaction_section is None:
        anomalies.append(
            {
                "code": "missing_interaction_section",
                "span": None,
                "message": "no count-bearing category heading found",
            }
        )
    for category in categories:
        declared_count = category["declared_count"]
        parsed_count = len(category["entries"])
        count_checks.append(
            {
                "category": category["category"],
                "declared_count": declared_count,
                "parsed_count": parsed_count,
                "ok": declared_count == parsed_count,
            }
        )
        if declared_count != parsed_count:
            anomalies.append(
                {
                    "code": "count_mismatch",
                    "category": category["category"],
                    "declared_count": declared_count,
                    "parsed_count": parsed_count,
                    "span": category["heading_span"],
                    "message": (
                        f"{category['heading_text']}: declared {declared_count}, "
                        f"parsed {parsed_count}"
                    ),
                }
            )

    candidate = {
        "relative_path": relative_path,
        "sha256": sha256,
        "byte_count": len(data),
        "line_count": len(lines),
        "interaction_section": interaction_section,
        "categories": categories,
    }
    report = {
        "relative_path": relative_path,
        "sha256": sha256,
        "interaction_section_found": interaction_section is not None,
        "count_checks": count_checks,
        "anomalies": anomalies,
        "ok": interaction_section is not None
        and all(check["ok"] for check in count_checks),
    }
    return candidate, report


def _input_provenance(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    return {"path": str(path), "sha256": _sha256_hex(path.read_bytes())}


def build(
    source_dir: Path,
    terminology: Path | None = None,
    review_manifest: Path | None = None,
) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for relative_path in _discover(source_dir):
        candidate, report = _parse_document(
            relative_path, (source_dir / relative_path).read_bytes()
        )
        documents.append(candidate)
        reports.append(report)
    return {
        "candidates": {
            "schema_version": 1,
            "parser_version": PARSER_VERSION,
            "documents": documents,
        },
        "report": {
            "schema_version": 1,
            "parser_version": PARSER_VERSION,
            "inputs": {
                "sources_dir": str(source_dir),
                "terminology": _input_provenance(terminology),
                "review_manifest": _input_provenance(review_manifest),
            },
            "documents": reports,
            "ok": all(item["ok"] for item in reports),
        },
    }
