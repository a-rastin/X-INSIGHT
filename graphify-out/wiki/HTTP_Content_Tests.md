# HTTP Content Tests

> 9 nodes · cohesion 0.31

## Key Concepts

- **test_content.py** (14 connections) — `backend/tests/http/test_content.py`
- **login()** (4 connections) — `backend/tests/http/test_content.py`
- **clean_content()** (2 connections) — `backend/tests/http/test_content.py`
- **test_draft_definitions_not_exposed()** (2 connections) — `backend/tests/http/test_content.py`
- **test_released_definition_served_from_content_dir()** (2 connections) — `backend/tests/http/test_content.py`
- **test_unknown_assessment_type_not_found()** (2 connections) — `backend/tests/http/test_content.py`
- **fixture** (1 connections)
- **Slice 4 (RED): authenticated released-only content routes (T1, real PG). No…** (1 connections) — `backend/tests/http/test_content.py`
- **test_anonymous_content_denied()** (1 connections) — `backend/tests/http/test_content.py`

## Relationships

- [MCP Server](MCP_Server.md) (1 shared connections)
- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [HTTP DDI Tests](HTTP_DDI_Tests.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_content.py`

## Audit Trail

- EXTRACTED: 18 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*