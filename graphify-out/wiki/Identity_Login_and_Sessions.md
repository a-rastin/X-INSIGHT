# Identity Login and Sessions

> 57 nodes · cohesion 0.08

## Key Concepts

- **routes.py** (47 connections) — `backend/src/x_insight/identity/routes.py`
- **_require_session()** (28 connections) — `backend/src/x_insight/identity/routes.py`
- **sqlalchemy** (23 connections)
- **login()** (20 connections) — `backend/src/x_insight/identity/routes.py`
- **store.py** (18 connections) — `backend/src/x_insight/identity/store.py`
- **_check_csrf()** (17 connections) — `backend/src/x_insight/identity/routes.py`
- **change_password()** (15 connections) — `backend/src/x_insight/identity/routes.py`
- **_request_id()** (15 connections) — `backend/src/x_insight/identity/routes.py`
- **ensure_admin_seeded()** (15 connections) — `backend/src/x_insight/identity/store.py`
- **hash_password()** (13 connections) — `backend/src/x_insight/identity/hashing.py`
- **hashing.py** (12 connections) — `backend/src/x_insight/identity/hashing.py`
- **Request** (11 connections)
- **verify_password()** (10 connections) — `backend/src/x_insight/identity/hashing.py`
- **logout()** (10 connections) — `backend/src/x_insight/identity/routes.py`
- **normalize_username()** (10 connections) — `backend/src/x_insight/identity/store.py`
- **update_preferences()** (9 connections) — `backend/src/x_insight/identity/routes.py`
- **JSONResponse** (8 connections)
- **me()** (7 connections) — `backend/src/x_insight/identity/routes.py`
- **get_user_by_username()** (7 connections) — `backend/src/x_insight/identity/store.py`
- **get_valid_session()** (7 connections) — `backend/src/x_insight/identity/store.py`
- **create_session()** (6 connections) — `backend/src/x_insight/identity/store.py`
- **Connection** (5 connections)
- **sqlalchemy_engine** (5 connections)
- **_client_key()** (4 connections) — `backend/src/x_insight/identity/routes.py`
- **_generic_login_denied()** (4 connections) — `backend/src/x_insight/identity/routes.py`
- *... and 32 more nodes in this community*

## Relationships

- [Physician Accounts and Transactions](Physician_Accounts_and_Transactions.md) (26 shared connections)
- [Patient Registration](Patient_Registration.md) (22 shared connections)
- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (14 shared connections)
- [Encounter Draft Validation](Encounter_Draft_Validation.md) (13 shared connections)
- [Identity HTTP Tests](Identity_HTTP_Tests.md) (10 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (7 shared connections)
- [Database Migrations](Database_Migrations.md) (6 shared connections)
- [Login Throttle and Clock](Login_Throttle_and_Clock.md) (5 shared connections)
- [Database Engine and Readiness](Database_Engine_and_Readiness.md) (4 shared connections)
- [Shared HTTP Contracts](Shared_HTTP_Contracts.md) (2 shared connections)
- [Released Content Tests](Released_Content_Tests.md) (1 shared connections)
- [C-SSRS HTTP Tests](C-SSRS_HTTP_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/hashing.py`
- `backend/src/x_insight/identity/routes.py`
- `backend/src/x_insight/identity/store.py`
- `backend/tests/http/test_identity.py`

## Audit Trail

- EXTRACTED: 252 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*