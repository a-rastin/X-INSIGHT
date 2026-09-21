# Physician Admin Tests

> 9 nodes · cohesion 0.50

## Key Concepts

- **test_physicians.py** (15 connections) — `backend/tests/http/test_physicians.py`
- **headers()** (6 connections) — `backend/tests/http/test_physicians.py`
- **login()** (6 connections) — `backend/tests/http/test_physicians.py`
- **test_account_commands_replay_without_duplicate_mutations_or_secret_audit()** (4 connections) — `backend/tests/http/test_physicians.py`
- **test_admin_manages_safe_physician_accounts_with_stable_identity()** (4 connections) — `backend/tests/http/test_physicians.py`
- **test_deactivation_requires_review_and_explicit_discard_confirmation()** (4 connections) — `backend/tests/http/test_physicians.py`
- **test_idempotency_detects_changed_username_spelling_before_normalization()** (3 connections) — `backend/tests/http/test_physicians.py`
- **test_password_reset_revokes_all_sessions_and_obeys_account_revision()** (3 connections) — `backend/tests/http/test_physicians.py`
- **S04 physician administration through T1 HTTP and disposable PostgreSQL.** (1 connections) — `backend/tests/http/test_physicians.py`

## Relationships

- [History HTTP Tests](History_HTTP_Tests.md) (3 shared connections)
- [Identity HTTP Tests](Identity_HTTP_Tests.md) (1 shared connections)
- [Released Content Tests](Released_Content_Tests.md) (1 shared connections)
- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (1 shared connections)
- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (1 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (1 shared connections)
- [Login Throttle and Clock](Login_Throttle_and_Clock.md) (1 shared connections)
- [Test Fixture Resets](Test_Fixture_Resets.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_physicians.py`

## Audit Trail

- EXTRACTED: 25 (89%)
- INFERRED: 3 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*