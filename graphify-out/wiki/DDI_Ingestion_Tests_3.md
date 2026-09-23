# DDI Ingestion Tests 3

> 15 nodes · cohesion 0.20

## Key Concepts

- **_make_variant_sources_dir()** (9 connections) — `backend/tests/ddi/test_ingestion.py`
- **test_build_page_break_continuation_joins_entry()** (8 connections) — `backend/tests/ddi/test_ingestion.py`
- **_variant_documents()** (8 connections) — `backend/tests/ddi/test_ingestion.py`
- **test_build_drops_extended_page_chrome()** (7 connections) — `backend/tests/ddi/test_ingestion.py`
- **test_build_ondansetron_contra_spans_sponsor_block()** (7 connections) — `backend/tests/ddi/test_ingestion.py`
- **test_build_wrapped_entity_heading_preserved()** (7 connections) — `backend/tests/ddi/test_ingestion.py`
- **_variants_provenance()** (7 connections) — `backend/tests/ddi/test_ingestion.py`
- **test_build_simethicone_reports_missing_section()** (6 connections) — `backend/tests/ddi/test_ingestion.py`
- **Copy variant originals byte-identically, preserving Group/Name.txt stems.…** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **S16 RED: Medscape page chrome is never parsed as entries.** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **S16 RED: Ondansetron contraindicated spans + sponsor ad-block chrome.** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **S16 RED: page-break continuations join ONE entry; next header separate.** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **S16 RED: wrapped heading/description fragments stay in ONE entry.** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **S16 RED: a monograph with no interaction section reports, never raises.** (1 connections) — `backend/tests/ddi/test_ingestion.py`
- **_entry()** (1 connections) — `backend/tests/ddi/test_ingestion.py`

## Relationships

- [DDI Ingestion Tests 2](DDI_Ingestion_Tests_2.md) (11 shared connections)
- [MCP Server](MCP_Server.md) (8 shared connections)
- [DDI Ingestion](DDI_Ingestion.md) (5 shared connections)

## Source Files

- `backend/tests/ddi/test_ingestion.py`

## Audit Trail

- EXTRACTED: 40 (89%)
- INFERRED: 5 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*