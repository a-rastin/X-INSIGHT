# Identity HTTP Tests

> 30 nodes · cohesion 0.14

## Key Concepts

- **test_identity.py** (30 connections) — `backend/tests/http/test_identity.py`
- **_client()** (17 connections) — `backend/tests/http/test_identity.py`
- **_login()** (16 connections) — `backend/tests/http/test_identity.py`
- **pytest** (13 connections)
- **conftest.py** (9 connections) — `backend/tests/conftest.py`
- **test_second_initialization_preserves_changed_password()** (5 connections) — `backend/tests/http/test_identity.py`
- **test_audit_records_success_and_failure_without_credentials()** (4 connections) — `backend/tests/http/test_identity.py`
- **test_empty_password_fails_without_trimming()** (4 connections) — `backend/tests/http/test_identity.py`
- **test_inactive_account_cannot_login()** (4 connections) — `backend/tests/http/test_identity.py`
- **_migrated_test_db()** (3 connections) — `backend/tests/conftest.py`
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
- **_isolate_audit_rows()** (2 connections) — `backend/tests/conftest.py`
- **fixture** (2 connections)
- **_upgrade_test_db()** (2 connections) — `backend/tests/conftest.py`
- **_audit_rows()** (2 connections) — `backend/tests/http/test_identity.py`
- **TestClient** (2 connections)
- *... and 5 more nodes in this community*

## Relationships

- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (10 shared connections)
- [Released Content Tests](Released_Content_Tests.md) (2 shared connections)
- [PANSS Evaluation Tests](PANSS_Evaluation_Tests.md) (2 shared connections)
- [Database Engine and Readiness](Database_Engine_and_Readiness.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [Patient Registration](Patient_Registration.md) (1 shared connections)
- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (1 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (1 shared connections)
- [Test Fixture Resets](Test_Fixture_Resets.md) (1 shared connections)
- [C-SSRS Evaluation](C-SSRS_Evaluation.md) (1 shared connections)
- [Assessment Content Loading Tests](Assessment_Content_Loading_Tests.md) (1 shared connections)
- [C-SSRS HTTP Tests](C-SSRS_HTTP_Tests.md) (1 shared connections)

## Source Files

- `backend/tests/conftest.py`
- `backend/tests/http/test_identity.py`

## Audit Trail

- EXTRACTED: 90 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*