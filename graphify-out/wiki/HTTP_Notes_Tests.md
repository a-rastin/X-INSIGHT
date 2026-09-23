# HTTP Notes Tests

> 16 nodes · cohesion 0.37

## Key Concepts

- **test_notes.py** (21 connections) — `backend/tests/http/test_notes.py`
- **note_headers()** (8 connections) — `backend/tests/http/test_notes.py`
- **create_patient()** (7 connections) — `backend/tests/http/test_notes.py`
- **create_physician()** (7 connections) — `backend/tests/http/test_notes.py`
- **test_author_adds_note_visible_after_resume_idempotent_retry()** (7 connections) — `backend/tests/http/test_notes.py`
- **test_only_author_may_write_notes()** (7 connections) — `backend/tests/http/test_notes.py`
- **login()** (6 connections) — `backend/tests/http/test_notes.py`
- **notes_url()** (6 connections) — `backend/tests/http/test_notes.py`
- **test_note_provenance_is_server_derived()** (6 connections) — `backend/tests/http/test_notes.py`
- **test_note_shape_requires_page_and_text()** (6 connections) — `backend/tests/http/test_notes.py`
- **test_notes_are_listed_separately_from_history()** (6 connections) — `backend/tests/http/test_notes.py`
- **clean_notes()** (2 connections) — `backend/tests/http/test_notes.py`
- **note_item_url()** (2 connections) — `backend/tests/http/test_notes.py`
- **resumed_client()** (2 connections) — `backend/tests/http/test_notes.py`
- **fixture** (1 connections)
- **S13 failing-first: attributed page notes, append-only, separate history. T1…** (1 connections) — `backend/tests/http/test_notes.py`

## Relationships

- [MCP Server](MCP_Server.md) (1 shared connections)
- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [HTTP DDI Tests](HTTP_DDI_Tests.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_notes.py`

## Audit Trail

- EXTRACTED: 51 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*