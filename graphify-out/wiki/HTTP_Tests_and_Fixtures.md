# HTTP Tests and Fixtures

> 49 nodes · cohesion 0.08

## Key Concepts

- **test_notes.py** (21 connections) — `backend/tests/http/test_notes.py`
- **test_physicians.py** (15 connections) — `backend/tests/http/test_physicians.py`
- **test_content.py** (14 connections) — `backend/tests/http/test_content.py`
- **pytest** (14 connections)
- **fastapi_testclient** (12 connections)
- **conftest.py** (9 connections) — `backend/tests/conftest.py`
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
- **headers()** (6 connections) — `backend/tests/http/test_physicians.py`
- **login()** (6 connections) — `backend/tests/http/test_physicians.py`
- **x_insight** (5 connections)
- **login()** (4 connections) — `backend/tests/http/test_content.py`
- **_migrated_test_db()** (3 connections) — `backend/tests/conftest.py`
- **test_health.py** (3 connections) — `backend/tests/http/test_health.py`
- **test_account_commands_replay_without_duplicate_mutations_or_secret_audit()** (3 connections) — `backend/tests/http/test_physicians.py`
- **test_admin_manages_safe_physician_accounts_with_stable_identity()** (3 connections) — `backend/tests/http/test_physicians.py`
- **test_deactivation_requires_review_and_explicit_discard_confirmation()** (3 connections) — `backend/tests/http/test_physicians.py`
- *... and 24 more nodes in this community*

## Relationships

- [App Wiring and Persistence](App_Wiring_and_Persistence.md) (12 shared connections)
- [Assessment Engine and PANSS Tests](Assessment_Engine_and_PANSS_Tests.md) (4 shared connections)
- [Identity HTTP Tests](Identity_HTTP_Tests.md) (3 shared connections)
- [C-SSRS HTTP Tests](C-SSRS_HTTP_Tests.md) (2 shared connections)
- [Diagnosis Evaluation Tests](Diagnosis_Evaluation_Tests.md) (2 shared connections)
- [Draft Lifecycle Tests](Draft_Lifecycle_Tests.md) (2 shared connections)
- [History HTTP Tests](History_HTTP_Tests.md) (2 shared connections)
- [Patient Registration Tests](Patient_Registration_Tests.md) (2 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [HTTP Contract Tests](HTTP_Contract_Tests.md) (1 shared connections)
- [C-SSRS Evaluation](C-SSRS_Evaluation.md) (1 shared connections)

## Source Files

- `backend/tests/conftest.py`
- `backend/tests/http/test_content.py`
- `backend/tests/http/test_health.py`
- `backend/tests/http/test_notes.py`
- `backend/tests/http/test_physicians.py`

## Audit Trail

- EXTRACTED: 130 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*