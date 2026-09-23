# DDI Ingestion Tests 2

> 26 nodes · cohesion 0.15

## Key Concepts

- **Path** (19 connections)
- **_make_sources_dir()** (11 connections) — `backend/tests/ddi/test_ingestion.py`
- **_provenance()** (9 connections) — `backend/tests/ddi/test_ingestion.py`
- **test_build_direction_marked_unknown_unless_explicit()** (9 connections) — `backend/tests/ddi/test_ingestion.py`
- **Any** (8 connections)
- **test_build_repeated_pair_entries_survive()** (8 connections) — `backend/tests/ddi/test_ingestion.py`
- **test_cli_build_matches_library_build()** (8 connections) — `backend/tests/ddi/test_ingestion.py`
- **_make_entry_removed_sources_dir()** (6 connections) — `backend/tests/ddi/test_ingestion.py`
- **_make_slice2_sources_dir()** (6 connections) — `backend/tests/ddi/test_ingestion.py`
- **test_preprocessing_keeps_original_spans_and_drops_page_chrome()** (6 connections) — `backend/tests/ddi/test_ingestion.py`
- **test_removed_entry_fails_count_validation_and_still_reports()** (6 connections) — `backend/tests/ddi/test_ingestion.py`
- **_make_bom_stripped_sources_dir()** (5 connections) — `backend/tests/ddi/test_ingestion.py`
- **test_build_contradictory_severity_survives()** (5 connections) — `backend/tests/ddi/test_ingestion.py`
- **test_build_locates_interaction_section_ignoring_navigation_headings()** (5 connections) — `backend/tests/ddi/test_ingestion.py`
- **test_candidate_counts_match_declared_counts()** (5 connections) — `backend/tests/ddi/test_ingestion.py`
- **_paragraph_direction()** (4 connections) — `backend/tests/ddi/test_ingestion.py`
- **S16 slice 2 RED: contradictory severity assertions both survive.** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **Return a paragraph's explicit direction marking (RED if absent).** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **S16 slice 2 RED: direction marked only when the source is explicit.** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **S15-D (seam T3): the CLI `python -m x_insight.ddi build ...` is a public…** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **Copy the original monograph byte-identically under a temp sources dir. Fixture-…** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **Build a transformed copy of the original: same bytes minus the UTF-8 BOM.…** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **Build a transformed copy of the original: the erdafitinib serious entry block…** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **Copy slice-2 originals byte-identically, preserving Group/Name.txt stems.…** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **S16 slice 2 RED: repeated-pair entries survive in every category.** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- *... and 1 more nodes in this community*

## Relationships

- [MCP Server](MCP_Server.md) (14 shared connections)
- [DDI Ingestion Tests 3](DDI_Ingestion_Tests_3.md) (11 shared connections)
- [DDI Ingestion](DDI_Ingestion.md) (9 shared connections)

## Source Files

- `backend/tests/ddi/test_ingestion.py`

## Audit Trail

- EXTRACTED: 74 (90%)
- INFERRED: 8 (10%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*