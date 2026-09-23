# HTTP DDI Tests

> 19 nodes · cohesion 0.20

## Key Concepts

- **test_ddi.py** (22 connections) — `backend/tests/http/test_ddi.py`
- **x_insight_identity_throttle** (13 connections)
- **_login()** (7 connections) — `backend/tests/http/test_ddi.py`
- **_insert_release()** (6 connections) — `backend/tests/http/test_ddi.py`
- **_new_version()** (5 connections) — `backend/tests/http/test_ddi.py`
- **test_physician_and_admin_can_check_pins()** (5 connections) — `backend/tests/http/test_ddi.py`
- **_make_physician()** (4 connections) — `backend/tests/http/test_ddi.py`
- **test_both_neither_discriminator_422()** (4 connections) — `backend/tests/http/test_ddi.py`
- **test_drugs_search_filters_case_insensitively_and_empty_bounded()** (4 connections) — `backend/tests/http/test_ddi.py`
- **test_excluded_fields_422()** (4 connections) — `backend/tests/http/test_ddi.py`
- **_mutation_headers()** (3 connections) — `backend/tests/http/test_ddi.py`
- **TestClient** (3 connections)
- **clean_ddi()** (2 connections) — `backend/tests/http/test_ddi.py`
- **test_unknown_dataset_version_404()** (2 connections) — `backend/tests/http/test_ddi.py`
- **fixture** (1 connections)
- **S19 slice 4 (RED): DDI HTTP surface T1, real PostgreSQL, synthetic only.…** (1 connections) — `backend/tests/http/test_ddi.py`
- **Fixture SETUP only (not under test): one synthetic release, one AB row.** (1 connections) — `backend/tests/http/test_ddi.py`
- **test_anon_check_requires_session()** (1 connections) — `backend/tests/http/test_ddi.py`
- **test_anon_drugs_requires_session()** (1 connections) — `backend/tests/http/test_ddi.py`

## Relationships

- [Worker Single Question Tests](Worker_Single_Question_Tests.md) (2 shared connections)
- [MCP Server](MCP_Server.md) (1 shared connections)
- [Cases Notes](Cases_Notes.md) (1 shared connections)
- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [HTTP Content Tests](HTTP_Content_Tests.md) (1 shared connections)
- [HTTP Followup Tests](HTTP_Followup_Tests.md) (1 shared connections)
- [HTTP Medications Tests](HTTP_Medications_Tests.md) (1 shared connections)
- [HTTP Networks Tests](HTTP_Networks_Tests.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_ddi.py`

## Audit Trail

- EXTRACTED: 54 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*