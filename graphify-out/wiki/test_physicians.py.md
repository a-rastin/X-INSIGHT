# test_physicians.py

> 49 nodes

## Key Concepts

- **test_physicians.py** (15 connections) — `backend/tests/http/test_physicians.py`
- **test_patients.py** (14 connections) — `backend/tests/http/test_patients.py`
- **throttle.py** (11 connections) — `backend/src/x_insight/identity/throttle.py`
- **test_concurrent_duplicate_archived_and_idempotent_create()** (6 connections) — `backend/tests/http/test_patients.py`
- **headers()** (6 connections) — `backend/tests/http/test_physicians.py`
- **login()** (6 connections) — `backend/tests/http/test_physicians.py`
- **clock.py** (6 connections) — `backend/src/x_insight/identity/clock.py`
- **record_failure()** (5 connections) — `backend/src/x_insight/identity/throttle.py`
- **reset_all()** (5 connections) — `backend/src/x_insight/identity/throttle.py`
- **throttled()** (5 connections) — `backend/src/x_insight/identity/throttle.py`
- **headers()** (5 connections) — `backend/tests/http/test_patients.py`
- **login()** (5 connections) — `backend/tests/http/test_patients.py`
- **test_patient_field_validation_rejects_bad_demographics()** (5 connections) — `backend/tests/http/test_patients.py`
- **test_physician_registers_patient_with_registration_draft()** (5 connections) — `backend/tests/http/test_patients.py`
- **now()** (4 connections) — `backend/src/x_insight/identity/clock.py`
- **test_directory_search_filter_pagination_shared()** (4 connections) — `backend/tests/http/test_patients.py`
- **test_account_commands_replay_without_duplicate_mutations_or_secret_audit()** (4 connections) — `backend/tests/http/test_physicians.py`
- **test_admin_manages_safe_physician_accounts_with_stable_identity()** (4 connections) — `backend/tests/http/test_physicians.py`
- **test_deactivation_requires_review_and_explicit_discard_confirmation()** (4 connections) — `backend/tests/http/test_physicians.py`
- **clear()** (3 connections) — `backend/src/x_insight/identity/throttle.py`
- **_prune()** (3 connections) — `backend/src/x_insight/identity/throttle.py`
- **_clean_identity()** (3 connections) — `backend/tests/http/test_identity.py`
- **clean_patients()** (3 connections) — `backend/tests/http/test_patients.py`
- **clean_accounts()** (3 connections) — `backend/tests/http/test_physicians.py`
- **test_idempotency_detects_changed_username_spelling_before_normalization()** (3 connections) — `backend/tests/http/test_physicians.py`
- *... and 24 more nodes in this community*

## Relationships

- [accounts.py](accounts.py.md) (6 shared connections)
- [routes.py](routes.py.md) (5 shared connections)
- [app.py](app.py.md) (4 shared connections)
- [conftest.py](conftest.py.md) (2 shared connections)
- [contracts.py](contracts.py.md) (2 shared connections)
- [patients.py](patients.py.md) (2 shared connections)
- [test_identity.py](test_identity.py.md) (1 shared connections)
- [evaluation.py](evaluation.py.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/__init__.py`
- `backend/src/x_insight/identity/clock.py`
- `backend/src/x_insight/identity/throttle.py`
- `backend/tests/http/test_identity.py`
- `backend/tests/http/test_patients.py`
- `backend/tests/http/test_physicians.py`

## Audit Trail

- EXTRACTED: 87 (92%)
- INFERRED: 8 (8%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*