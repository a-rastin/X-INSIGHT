# HTTP Physicians Tests

> 11 nodes · cohesion 0.36

## Key Concepts

- **test_physicians.py** (15 connections) — `backend/tests/http/test_physicians.py`
- **headers()** (6 connections) — `backend/tests/http/test_physicians.py`
- **login()** (6 connections) — `backend/tests/http/test_physicians.py`
- **test_account_commands_replay_without_duplicate_mutations_or_secret_audit()** (3 connections) — `backend/tests/http/test_physicians.py`
- **test_admin_manages_safe_physician_accounts_with_stable_identity()** (3 connections) — `backend/tests/http/test_physicians.py`
- **test_deactivation_requires_review_and_explicit_discard_confirmation()** (3 connections) — `backend/tests/http/test_physicians.py`
- **test_idempotency_detects_changed_username_spelling_before_normalization()** (3 connections) — `backend/tests/http/test_physicians.py`
- **test_password_reset_revokes_all_sessions_and_obeys_account_revision()** (3 connections) — `backend/tests/http/test_physicians.py`
- **clean_accounts()** (2 connections) — `backend/tests/http/test_physicians.py`
- **fixture** (1 connections)
- **S04 physician administration through T1 HTTP and disposable PostgreSQL.** (1 connections) — `backend/tests/http/test_physicians.py`

## Relationships

- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [HTTP DDI Tests](HTTP_DDI_Tests.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_physicians.py`

## Audit Trail

- EXTRACTED: 26 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*