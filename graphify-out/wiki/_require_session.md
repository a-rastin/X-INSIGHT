# _require_session

> 31 nodes

## Key Concepts

- **_require_session()** (25 connections) — `backend/src/x_insight/identity/routes.py`
- **login()** (20 connections) — `backend/src/x_insight/identity/routes.py`
- **_check_csrf()** (16 connections) — `backend/src/x_insight/identity/routes.py`
- **error_body()** (15 connections) — `backend/src/x_insight/contracts.py`
- **change_password()** (15 connections) — `backend/src/x_insight/identity/routes.py`
- **ensure_admin_seeded()** (15 connections) — `backend/src/x_insight/identity/store.py`
- **_request_id()** (14 connections) — `backend/src/x_insight/identity/routes.py`
- **Request** (11 connections)
- **verify_password()** (10 connections) — `backend/src/x_insight/identity/hashing.py`
- **logout()** (10 connections) — `backend/src/x_insight/identity/routes.py`
- **update_preferences()** (9 connections) — `backend/src/x_insight/identity/routes.py`
- **JSONResponse** (8 connections)
- **me()** (7 connections) — `backend/src/x_insight/identity/routes.py`
- **_client_key()** (4 connections) — `backend/src/x_insight/identity/routes.py`
- **_generic_login_denied()** (4 connections) — `backend/src/x_insight/identity/routes.py`
- **LoginRequest** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **PasswordChangeRequest** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **PreferencesRequest** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **_secure_cookie()** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **_session_token()** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **test_admin_password_is_hashed()** (3 connections) — `backend/tests/http/test_identity.py`
- **BaseModel** (3 connections)
- **post** (3 connections)
- **Any** (2 connections)
- **Connection** (1 connections)
- *... and 6 more nodes in this community*

## Relationships

- [routes.py](routes.py.md) (28 shared connections)
- [accounts.py](accounts.py.md) (16 shared connections)
- [record_audit](record_audit.md) (11 shared connections)
- [store.py](store.py.md) (8 shared connections)
- [ready](ready.md) (5 shared connections)
- [create_patient](create_patient.md) (5 shared connections)
- [test_identity.py](test_identity.py.md) (5 shared connections)
- [throttle.py](throttle.py.md) (3 shared connections)
- [test_definitions.py](test_definitions.py.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/contracts.py`
- `backend/src/x_insight/identity/hashing.py`
- `backend/src/x_insight/identity/routes.py`
- `backend/src/x_insight/identity/store.py`
- `backend/tests/http/test_identity.py`

## Audit Trail

- EXTRACTED: 149 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*