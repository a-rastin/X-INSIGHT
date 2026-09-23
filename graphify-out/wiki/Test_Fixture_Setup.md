# Test Fixture Setup

> 8 nodes · cohesion 0.32

## Key Concepts

- **pytest** (27 connections)
- **conftest.py** (9 connections) — `backend/tests/conftest.py`
- **_migrated_test_db()** (3 connections) — `backend/tests/conftest.py`
- **_isolate_audit_rows()** (2 connections) — `backend/tests/conftest.py`
- **fixture** (2 connections)
- **_upgrade_test_db()** (2 connections) — `backend/tests/conftest.py`
- **alembic_config** (1 connections)
- **Isolated test lifecycle: migrated disposable test database per session.** (1 connections) — `backend/tests/conftest.py`

## Relationships

- [Assessment PANSS Tests](Assessment_PANSS_Tests.md) (3 shared connections)
- [MCP Server](MCP_Server.md) (2 shared connections)
- [Database Migrations](Database_Migrations.md) (2 shared connections)
- [Worker Single Question Tests](Worker_Single_Question_Tests.md) (2 shared connections)
- [Assessment C-SSRS Tests](Assessment_C-SSRS_Tests.md) (1 shared connections)
- [DDI Publish Tests](DDI_Publish_Tests.md) (1 shared connections)
- [HTTP Content Tests](HTTP_Content_Tests.md) (1 shared connections)
- [HTTP C-SSRS Tests](HTTP_C-SSRS_Tests.md) (1 shared connections)
- [HTTP DDI Tests](HTTP_DDI_Tests.md) (1 shared connections)
- [HTTP Diagnosis Tests](HTTP_Diagnosis_Tests.md) (1 shared connections)
- [HTTP Drafts Tests](HTTP_Drafts_Tests.md) (1 shared connections)
- [HTTP Followup Tests](HTTP_Followup_Tests.md) (1 shared connections)

## Source Files

- `backend/tests/conftest.py`

## Audit Trail

- EXTRACTED: 38 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*