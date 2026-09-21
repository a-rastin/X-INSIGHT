# test_drafts.py

> 70 nodes

## Key Concepts

- **test_drafts.py** (28 connections) — `backend/tests/http/test_drafts.py`
- **physician()** (23 connections) — `backend/src/x_insight/identity/accounts.py`
- **test_physicians.py** (15 connections) — `backend/tests/http/test_physicians.py`
- **test_patients.py** (14 connections) — `backend/tests/http/test_patients.py`
- **create_patient()** (13 connections) — `backend/tests/http/test_drafts.py`
- **create_physician()** (13 connections) — `backend/tests/http/test_drafts.py`
- **login()** (12 connections) — `backend/tests/http/test_drafts.py`
- **throttle.py** (12 connections) — `backend/src/x_insight/identity/throttle.py`
- **encounter_body()** (9 connections) — `backend/tests/http/test_drafts.py`
- **test_author_discards_draft_with_confirmation()** (9 connections) — `backend/tests/http/test_drafts.py`
- **test_malformed_patch_rejected_without_revision_bump()** (8 connections) — `backend/tests/http/test_drafts.py`
- **discard_headers()** (7 connections) — `backend/tests/http/test_drafts.py`
- **draft_headers()** (7 connections) — `backend/tests/http/test_drafts.py`
- **test_author_saves_and_retrieves_draft_across_restart()** (7 connections) — `backend/tests/http/test_drafts.py`
- **test_discard_requires_explicit_confirmation()** (7 connections) — `backend/tests/http/test_drafts.py`
- **test_double_discard_conflicts()** (7 connections) — `backend/tests/http/test_drafts.py`
- **test_discard_forbidden_for_non_author_and_anonymous()** (6 connections) — `backend/tests/http/test_drafts.py`
- **test_discard_rejects_stale_revision()** (6 connections) — `backend/tests/http/test_drafts.py`
- **test_revision_precondition_required()** (6 connections) — `backend/tests/http/test_drafts.py`
- **test_shared_read_but_author_only_write()** (6 connections) — `backend/tests/http/test_drafts.py`
- **test_terminal_invalid_and_archived_draft_rejected()** (6 connections) — `backend/tests/http/test_drafts.py`
- **test_concurrent_duplicate_archived_and_idempotent_create()** (6 connections) — `backend/tests/http/test_patients.py`
- **headers()** (6 connections) — `backend/tests/http/test_physicians.py`
- **login()** (6 connections) — `backend/tests/http/test_physicians.py`
- **clock.py** (6 connections) — `backend/src/x_insight/identity/clock.py`
- *... and 45 more nodes in this community*

## Relationships

- [patients.py](patients.py.md) (10 shared connections)
- [accounts.py](accounts.py.md) (8 shared connections)
- [routes.py](routes.py.md) (5 shared connections)
- [test_identity.py](test_identity.py.md) (5 shared connections)
- [conftest.py](conftest.py.md) (3 shared connections)
- [test_contracts.py](test_contracts.py.md) (1 shared connections)
- [evaluation.py](evaluation.py.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/__init__.py`
- `backend/src/x_insight/identity/accounts.py`
- `backend/src/x_insight/identity/clock.py`
- `backend/src/x_insight/identity/throttle.py`
- `backend/tests/http/test_drafts.py`
- `backend/tests/http/test_health.py`
- `backend/tests/http/test_patients.py`
- `backend/tests/http/test_physicians.py`

## Audit Trail

- EXTRACTED: 178 (92%)
- INFERRED: 16 (8%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*