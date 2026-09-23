# HTTP Identity Tests

> 27 nodes · cohesion 0.16

## Key Concepts

- **test_identity.py** (30 connections) — `backend/tests/http/test_identity.py`
- **_client()** (17 connections) — `backend/tests/http/test_identity.py`
- **_login()** (16 connections) — `backend/tests/http/test_identity.py`
- **test_audit_records_success_and_failure_without_credentials()** (4 connections) — `backend/tests/http/test_identity.py`
- **test_admin_username_mutation_is_denied()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_empty_password_fails_without_trimming()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_fresh_database_permits_admin_admin()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_inactive_account_cannot_login()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_login_sets_opaque_cookie_and_me()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_login_throttling_returns_429()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_logout_revokes_current_session()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_mutation_requires_csrf_token()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_password_change_has_no_complexity_rule()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_password_change_revokes_prior_sessions()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_second_initialization_preserves_changed_password()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_session_has_no_idle_or_absolute_timeout()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_wrong_credentials_and_role_mismatch_share_generic_error()** (3 connections) — `backend/tests/http/test_identity.py`
- **sqlalchemy_exc** (3 connections)
- **_audit_rows()** (2 connections) — `backend/tests/http/test_identity.py`
- **_clean_identity()** (2 connections) — `backend/tests/http/test_identity.py`
- **test_self_registration_is_denied()** (2 connections) — `backend/tests/http/test_identity.py`
- **TestClient** (2 connections)
- **fixture** (1 connections)
- **S03 identity suite (T1, real PostgreSQL). Slices grow cumulatively.** (1 connections) — `backend/tests/http/test_identity.py`
- **test_admin_password_is_hashed()** (1 connections) — `backend/tests/http/test_identity.py`
- *... and 2 more nodes in this community*

## Relationships

- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [Cases Notes](Cases_Notes.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [MCP Server](MCP_Server.md) (1 shared connections)
- [Identity Accounts Contracts](Identity_Accounts_Contracts.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_identity.py`

## Audit Trail

- EXTRACTED: 65 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*