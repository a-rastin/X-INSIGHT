# DDI Ingestion

> 25 nodes · cohesion 0.14

## Key Concepts

- **build()** (34 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **ingestion.py** (23 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **_parse_document()** (11 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **_load_resolvable_terminology()** (6 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **_input_provenance()** (4 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **_opens_new_entry()** (4 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **Path** (4 connections)
- **test_report_covers_entire_corpus_with_enumerated_anomalies()** (4 connections) — `backend/tests/ddi/test_ingestion.py`
- **_discover()** (3 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **_is_page_chrome()** (3 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **_paragraph_direction()** (3 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **_restarts_assertion()** (3 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **_sha256_hex()** (3 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **_starts_entry()** (3 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **_unfinished()** (3 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **flush_run()** (2 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **Any** (2 connections)
- **start_entry()** (1 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **Description line restating the entry name starts a new entry. A bare repeated…** (1 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **Previous content line ends mid-sentence (page break cut the entry).** (1 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **Direction of one description paragraph (S16 slice 2). Explicit assertions name…** (1 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **Return a terminology for entry resolution, or None for provenance-only. S15…** (1 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **Entry-header grammar (contract section 3) on ORIGINAL lines. A paragraph-start…** (1 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **Header-shaped line that opens a new entry despite no blank separator. Some…** (1 connections) — `backend/src/x_insight/ddi/ingestion.py`
- **S16 slice 3: report-only full-corpus discovery enumerates anomalies.** (1 connections) — `backend/tests/ddi/test_ingestion.py`

## Relationships

- [DDI Terminology Tests](DDI_Terminology_Tests.md) (11 shared connections)
- [DDI Ingestion Tests 2](DDI_Ingestion_Tests_2.md) (9 shared connections)
- [MCP Server](MCP_Server.md) (7 shared connections)
- [DDI Publish Tests](DDI_Publish_Tests.md) (6 shared connections)
- [DDI Ingestion Tests 3](DDI_Ingestion_Tests_3.md) (5 shared connections)
- [DDI Checker](DDI_Checker.md) (2 shared connections)
- [DDI Checker Tests](DDI_Checker_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/ddi/ingestion.py`
- `backend/tests/ddi/test_ingestion.py`

## Audit Trail

- EXTRACTED: 60 (73%)
- INFERRED: 22 (27%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*