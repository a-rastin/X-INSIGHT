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
    # print url footer with trailing page counter, e.g. "... 4/22"
    re.compile(r"^https?://\S+\s+\d+/\d+$"),
    # bare print url footer without a counter (Atropine line 73)
    re.compile(r"^https?://\S+$"),
    # repeated print header: timestamp + page title
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2}, \d{1,2}:\d{2} [AP]M "),
    # bare timestamp line without a title (Ondansetron ad line 165)
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2}, \d{1,2}:\d{2} [AP]M$"),
    # bare pager counter, e.g. "2/21"
    re.compile(r"^\d+/\d+$"),
    # dosing-page title line (matches anywhere on the line)
    re.compile(r"dosing, indications, interactions, adverse effects, and more"),
    # sponsor ad block between entries (Ondansetron lines 162-164, 168)
    re.compile(r"^Sponsor$"),
    re.compile(r"^Luxena Pharmaceuticals, Inc; "),
    re.compile(r"^California 95050$"),
)


def _is_page_chrome(text: str) -> bool:
    return any(pattern.search(text) for pattern in _PAGE_CHROME)


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


def _opens_new_entry(
    text: str, prev_content: str, subject: str, next_content: str
) -> bool:
    """Header-shaped line that opens a new entry despite no blank separator.

    Some blocks (Ondansetron contraindicated lines 143-161, Atropine serious
    lines 59-112) separate entries with no blank line. A header-shaped line
    (same grammar as _starts_entry) directly after a sentence-terminal "."
    opens a new entry when the next content line carries the name forward
    (e.g. dronedarone L148 -> L149 "dronedarone will ...", glucagon L64 ->
    L65 "glucagon increases ..."). Wrapped description fragments never
    satisfy this (e.g. Sitagliptin vadadustat line 642 -> "accordance ...",
    Ondansetron "changes" L1002 -> "albuterol inhaled"). A blank/chrome/EOF
    next line also opens (e.g. Atropine aclidinium L119 -> blank L120);
    wrapped fragments are always continued on the next content line.
    """
    if not prev_content.endswith("."):
        # no-blank header carried forward by the next line (Ondansetron
        # L1003 "albuterol inhaled" -> L1004 contains it as assertion
        # subject): a new entry even though the immediate prev is a
        # wrapped fragment without terminal punctuation (L1002
        # "changes"). Wrapped fragments never satisfy this: no next
        # line carries them forward (tails are never restated).
        # Header-shaped only: a description sentence is never a header.
        if "." in text or subject in text:
            return False
        return text.casefold() in next_content.casefold()
    if not next_content or _is_page_chrome(next_content):
        # blank/chrome/EOF next: only a header-shaped line opens (a drug
        # name header); wrapped description sentences (periods, subject
        # mentions, long text) always continue on the following content.
        return "." not in text and subject not in text and len(text) < 60
    return text.casefold() in next_content.casefold()


def _restarts_assertion(text: str, entry_name: str, has_body: bool) -> bool:
    """Description line restating the entry name starts a new entry.

    A bare repeated header (Atropine line 69 "glucagon intranasal" after the
    line-68 sentence ending ".") reasserts the same name: it opens a NEW
    entry rather than joining the previous paragraph. Same for description
    restatements carrying text after the name (Ondansetron dronedarone
    lines 149-150 vs 151-154); the restatement then starts a new assertion
    paragraph inside that same new entry.
    """
    if not entry_name:
        return False
    if text.casefold() == entry_name.casefold():
        return True
    if not has_body or len(text) <= len(entry_name):
        return False
    if not text.casefold().startswith(entry_name.casefold()):
        return False
    boundary = text[len(entry_name) : len(entry_name) + 1]
    return boundary in (" ", ",", ".", ":", ";", "(", "/", "-")


def _unfinished(prev_content: str) -> bool:
    """Previous content line ends mid-sentence (page break cut the entry)."""
    return bool(prev_content) and not prev_content.endswith(".")


def _paragraph_direction(
    paragraph_text: str, entry_name: str, subject: str
) -> dict[str, str | None]:
    """Direction of one description paragraph (S16 slice 2).

    Explicit assertions name a subject acting on an object ("X will
    increase/decrease the level or effect of Y", "X increases/decreases
    effects/levels of Y") and mark {"subject": X, "object": Y}. Anything
    else -- mutual ("X and Y both ...", "Either ... of the other"),
    verb-free ("unspecified interaction mechanism"), or unparseable --
    marks {"subject": None, "object": None} (unknown, never inferred).
    Names compare case-insensitively against the entry header (the
    interacting drug) and the document stem (the subject drug).
    """
    match = re.match(
        r"(.+?) (will increase|will decrease|increases|decreases) "
        r"(the level or effect of|effects of|levels of|effect of|level of) "
        r"(.+?) by ",
        paragraph_text,
        re.IGNORECASE,
    )
    if match is None:
        return {"subject": None, "object": None}
    candidates = {
        "entry": entry_name.casefold(),
        "subject": subject.casefold(),
    }
    raw_subject, raw_object = match.group(1).strip(), match.group(4).strip()
    resolved_subject = next(
        (key for key, folded in candidates.items() if raw_subject.casefold() == folded),
        None,
    )
    resolved_object = next(
        (key for key, folded in candidates.items() if raw_object.casefold() == folded),
        None,
    )
    if resolved_subject is None or resolved_object is None:
        return {"subject": None, "object": None}
    if resolved_subject == "entry":
        direction_subject: str | None = entry_name
    elif resolved_subject == "subject":
        direction_subject = Path(subject).stem
    else:
        direction_subject = None
    if resolved_object == "entry":
        direction_object: str | None = entry_name
    elif resolved_object == "subject":
        direction_object = Path(subject).stem
    else:
        direction_object = None
    return {"subject": direction_subject, "object": direction_object}


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
    # open entry whose description was cut by a page-break chrome gap while
    # mid-sentence; the next content line after the gap resumes it (S16 slice 1)
    suspended_entry: dict[str, Any] | None = None
    last_entry_end = 0

    def flush_run() -> None:
        nonlocal run, run_starts_entry, last_entry_end
        if run and current_entry is not None:
            body = run[1:] if run_starts_entry else run
            if body:
                paragraph_text = " ".join(text for _, text in body)
                current_entry["paragraphs"].append(
                    {
                        "text": paragraph_text,
                        "span": {
                            "start_line": body[0][0],
                            "end_line": body[-1][0],
                        },
                        "direction": _paragraph_direction(
                            paragraph_text,
                            current_entry["name_text"],
                            subject,
                        ),
                    }
                )
                current_entry["span"]["end_line"] = body[-1][0]
                last_entry_end = body[-1][0]
        run = []
        run_starts_entry = False

    def start_entry(number: int, text: str) -> None:
        nonlocal current_entry, run_starts_entry, last_entry_end
        assert current_category is not None
        current_entry = {
            "name_text": text,
            "raw_text": "",
            "span": {"start_line": number, "end_line": number},
            "paragraphs": [],
        }
        current_category["entries"].append(current_entry)
        last_entry_end = number
        run_starts_entry = True

    for number, line in enumerate(lines, start=1):
        # some print headers carry a form-feed page-break prefix (Atropine 0x0C)
        text = line.strip().lstrip("\x0c")
        match = _CATEGORY_HEADING.match(text)
        if match:
            flush_run()
            current_entry = None
            suspended_entry = None
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
            suspended_entry = None
            section_end = number - 1
            break
        if not text or _is_page_chrome(text):
            if (
                _is_page_chrome(text)
                and current_entry is not None
                and current_category is not None
                and _unfinished(prev_content)
            ):
                # page-break chrome cut the entry mid-sentence (the blank
                # line before the chrome already flushed the run, so run
                # state alone cannot detect this): keep it open across
                # the gap. S15 paragraphs end terminal ".", so they never
                # suspend; only genuine mid-sentence cuts do.
                suspended_entry = current_entry
            flush_run()
            continue
        if suspended_entry is not None and current_category is not None:
            if _unfinished(prev_content):
                # mid-phrase cut (pre-gap line ends mid-sentence, e.g.
                # Atropine L71 "... drugs and"): the resumption continues
                # the cut paragraph even when header-shaped
                current_entry = suspended_entry
                suspended_entry = None
                run_starts_entry = False
                run.append((number, text))
                prev_content = text
                continue
            # terminal cut (pre-gap line ends "."): the entry is complete.
            # A carryforward header (the next line restates it as assertion
            # subject, e.g. Atropine vecuronium L626 -> L636) still opens a
            # new entry; anything else falls to the normal rules below.
            if _restarts_assertion(
                lines[number].strip().lstrip("\x0c") if number < len(lines) else "",
                text,
                True,
            ):
                current_entry = suspended_entry
                suspended_entry = None
                flush_run()
                start_entry(number, text)
                run.append((number, text))
                prev_content = text
                continue
            # the resumption is handled by the normal rules below
            suspended_entry = None
        if current_category is not None and current_entry is not None and run:
            if text.startswith("Minor/Significance Unknown"):
                # severity tag line ("Minor/Significance Unknown[.] ...")
                # closes the open entry's description; never a new entry
                run.append((number, text))
                prev_content = text
                continue
            if _opens_new_entry(
                text,
                prev_content,
                subject,
                (lines[number].strip().lstrip("\x0c") if number < len(lines) else ""),
            ):
                flush_run()
                start_entry(number, text)
                run.append((number, text))
                prev_content = text
                continue
            if _restarts_assertion(
                text,
                current_entry["name_text"],
                len(run) > (1 if run_starts_entry else 0),
            ):
                flush_run()
                run.append((number, text))
                prev_content = text
                continue
        if (
            not run
            and current_category is not None
            and _starts_entry(text, prev_content, subject)
        ):
            # terminal-cut tail after a chrome gap (e.g. Acetaminophen L403):
            # header-shaped but carries no entry name and names no drug the
            # next line continues (L404 "higher ..."), so it extends the
            # open entry instead of opening a bogus new one
            if (
                current_entry is not None
                and "." not in text
                and text[:1].isupper()
                and prev_content.endswith(".")
                and not _opens_new_entry(
                    text,
                    prev_content,
                    subject,
                    (
                        lines[number].strip().lstrip("\x0c")
                        if number < len(lines)
                        else ""
                    ),
                )
            ):
                run.append((number, text))
                prev_content = text
                continue
            start_entry(number, text)
        run.append((number, text))
        prev_content = text

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
