# Worker Single Question Tests

> 55 nodes · cohesion 0.08

## Key Concepts

- **test_single_question.py** (28 connections) — `backend/tests/worker/test_single_question.py`
- **test_api_settings.py** (24 connections) — `backend/tests/http/test_api_settings.py`
- **test_single_question_provenance_persisted_and_crash_resume()** (14 connections) — `backend/tests/worker/test_single_question.py`
- **test_single_question_structure_mutation_rejected_base_unchanged()** (14 connections) — `backend/tests/worker/test_single_question.py`
- **test_single_question_template_only_rendering_no_prose()** (14 connections) — `backend/tests/worker/test_single_question.py`
- **test_single_synthetic_question_end_to_end()** (14 connections) — `backend/tests/worker/test_single_question.py`
- **test_admin_saves_settings_masked_with_explicit_key_actions_and_revision()** (7 connections) — `backend/tests/http/test_api_settings.py`
- **_mutation_headers()** (7 connections) — `backend/tests/worker/test_single_question.py`
- **csrf_headers()** (6 connections) — `backend/tests/http/test_api_settings.py`
- **login()** (6 connections) — `backend/tests/http/test_api_settings.py`
- **_ProbeHandler** (6 connections) — `backend/tests/http/test_api_settings.py`
- **_create_sentinel_patient()** (6 connections) — `backend/tests/worker/test_single_question.py`
- **_insert_provider_config()** (6 connections) — `backend/tests/worker/test_single_question.py`
- **_make_physician()** (6 connections) — `backend/tests/worker/test_single_question.py`
- **threading** (6 connections)
- **test_config_versions_retained_with_explicit_removal_and_redacted_audit()** (5 connections) — `backend/tests/http/test_api_settings.py`
- **_clinical_draft()** (5 connections) — `backend/tests/worker/test_single_question.py`
- **_current_revision()** (5 connections) — `backend/tests/worker/test_single_question.py`
- **_insert_synthetic_bundle()** (5 connections) — `backend/tests/worker/test_single_question.py`
- **_login()** (5 connections) — `backend/tests/worker/test_single_question.py`
- **_synthetic_cpt_response()** (5 connections) — `backend/tests/worker/test_single_question.py`
- **http_server** (5 connections)
- **socketserver** (5 connections)
- **clean_settings()** (3 connections) — `backend/tests/http/test_api_settings.py`
- **create_physician()** (3 connections) — `backend/tests/http/test_api_settings.py`
- *... and 30 more nodes in this community*

## Relationships

- [Reasoning Retry](Reasoning_Retry.md) (4 shared connections)
- [DDI Checker](DDI_Checker.md) (3 shared connections)
- [Provider Estimation Tests Init](Provider_Estimation_Tests_Init.md) (3 shared connections)
- [Worker Recovery Tests](Worker_Recovery_Tests.md) (3 shared connections)
- [Worker Workflows Tests](Worker_Workflows_Tests.md) (3 shared connections)
- [Test Fixture Setup](Test_Fixture_Setup.md) (2 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (2 shared connections)
- [Database Migrations](Database_Migrations.md) (2 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (2 shared connections)
- [HTTP DDI Tests](HTTP_DDI_Tests.md) (2 shared connections)
- [MCP Server](MCP_Server.md) (2 shared connections)
- [Cases Notes](Cases_Notes.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_api_settings.py`
- `backend/tests/worker/test_single_question.py`

## Audit Trail

- EXTRACTED: 140 (97%)
- INFERRED: 5 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*