# test_identity.py

> 32 nodes

## Key Concepts

- **test_identity.py** (30 connections) — `backend/tests/http/test_identity.py`
- **_client()** (17 connections) — `backend/tests/http/test_identity.py`
- **_login()** (16 connections) — `backend/tests/http/test_identity.py`
- **reset_all()** (6 connections) — `backend/src/x_insight/identity/throttle.py`
- **test_second_initialization_preserves_changed_password()** (5 connections) — `backend/tests/http/test_identity.py`
- **test_audit_records_success_and_failure_without_credentials()** (4 connections) — `backend/tests/http/test_identity.py`
- **test_empty_password_fails_without_trimming()** (4 connections) — `backend/tests/http/test_identity.py`
- **test_inactive_account_cannot_login()** (4 connections) — `backend/tests/http/test_identity.py`
- **clean_drafts()** (3 connections) — `backend/tests/http/test_drafts.py`
- **_clean_identity()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_admin_username_mutation_is_denied()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_fresh_database_permits_admin_admin()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_login_sets_opaque_cookie_and_me()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_login_throttling_returns_429()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_logout_revokes_current_session()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_mutation_requires_csrf_token()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_password_change_has_no_complexity_rule()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_password_change_revokes_prior_sessions()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_session_has_no_idle_or_absolute_timeout()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_wrong_credentials_and_role_mismatch_share_generic_error()** (3 connections) — `backend/tests/http/test_identity.py`
- **clean_patients()** (3 connections) — `backend/tests/http/test_patients.py`
- **clean_accounts()** (3 connections) — `backend/tests/http/test_physicians.py`
- **_audit_rows()** (2 connections) — `backend/tests/http/test_identity.py`
- **test_no_second_admin_can_be_provisioned()** (2 connections) — `backend/tests/http/test_identity.py`
- **test_self_registration_is_denied()** (2 connections) — `backend/tests/http/test_identity.py`
- *... and 7 more nodes in this community*

## Relationships

- [test_drafts.py](test_drafts.py.md) (5 shared connections)
- [routes.py](routes.py.md) (5 shared connections)
- [patients.py](patients.py.md) (4 shared connections)
- [store.py](store.py.md) (3 shared connections)
- [conftest.py](conftest.py.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/throttle.py`
- `backend/tests/http/test_drafts.py`
- `backend/tests/http/test_identity.py`
- `backend/tests/http/test_patients.py`
- `backend/tests/http/test_physicians.py`

## Audit Trail

- EXTRACTED: 79 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*