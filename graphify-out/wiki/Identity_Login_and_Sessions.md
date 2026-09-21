# Identity Login and Sessions

> 38 nodes · cohesion 0.10

## Key Concepts

- **routes.py** (47 connections) — `backend/src/x_insight/identity/routes.py`
- **login()** (20 connections) — `backend/src/x_insight/identity/routes.py`
- **store.py** (17 connections) — `backend/src/x_insight/identity/store.py`
- **hash_password()** (12 connections) — `backend/src/x_insight/identity/hashing.py`
- **hashing.py** (11 connections) — `backend/src/x_insight/identity/hashing.py`
- **ensure_admin_seeded()** (10 connections) — `backend/src/x_insight/identity/store.py`
- **normalize_username()** (10 connections) — `backend/src/x_insight/identity/store.py`
- **verify_password()** (9 connections) — `backend/src/x_insight/identity/hashing.py`
- **get_user_by_username()** (7 connections) — `backend/src/x_insight/identity/store.py`
- **get_valid_session()** (7 connections) — `backend/src/x_insight/identity/store.py`
- **create_session()** (6 connections) — `backend/src/x_insight/identity/store.py`
- **Connection** (5 connections)
- **_client_key()** (4 connections) — `backend/src/x_insight/identity/routes.py`
- **_generic_login_denied()** (4 connections) — `backend/src/x_insight/identity/routes.py`
- **get_user_by_id()** (4 connections) — `backend/src/x_insight/identity/store.py`
- **token_hash()** (4 connections) — `backend/src/x_insight/identity/store.py`
- **LoginRequest** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **PasswordChangeRequest** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **PreferencesRequest** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **BaseModel** (3 connections)
- **_secure_cookie()** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **Any** (3 connections)
- **hashlib** (3 connections)
- **hmac** (2 connections)
- **secrets** (2 connections)
- *... and 13 more nodes in this community*

## Relationships

- [Patient and Session Routes](Patient_and_Session_Routes.md) (29 shared connections)
- [App Wiring and Persistence](App_Wiring_and_Persistence.md) (20 shared connections)
- [Physician Accounts and Transactions](Physician_Accounts_and_Transactions.md) (13 shared connections)
- [Login Throttle and Clock](Login_Throttle_and_Clock.md) (5 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (3 shared connections)
- [Encounter Draft Validation](Encounter_Draft_Validation.md) (3 shared connections)

## Source Files

- `backend/src/x_insight/identity/hashing.py`
- `backend/src/x_insight/identity/routes.py`
- `backend/src/x_insight/identity/store.py`

## Audit Trail

- EXTRACTED: 144 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*