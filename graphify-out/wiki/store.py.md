# store.py

> 22 nodes

## Key Concepts

- **store.py** (18 connections) — `backend/src/x_insight/identity/store.py`
- **hash_password()** (13 connections) — `backend/src/x_insight/identity/hashing.py`
- **hashing.py** (12 connections) — `backend/src/x_insight/identity/hashing.py`
- **get_user_by_username()** (7 connections) — `backend/src/x_insight/identity/store.py`
- **get_valid_session()** (7 connections) — `backend/src/x_insight/identity/store.py`
- **create_session()** (6 connections) — `backend/src/x_insight/identity/store.py`
- **Connection** (5 connections)
- **get_user_by_id()** (4 connections) — `backend/src/x_insight/identity/store.py`
- **token_hash()** (4 connections) — `backend/src/x_insight/identity/store.py`
- **Any** (3 connections)
- **hashlib** (3 connections)
- **hmac** (2 connections)
- **secrets** (2 connections)
- **Standard password hashing (stdlib PBKDF2-HMAC-SHA256). No new dependency:…** (1 connections) — `backend/src/x_insight/identity/hashing.py`
- **Hash an exact (untrimmed) password; caller rejects empty input.** (1 connections) — `backend/src/x_insight/identity/hashing.py`
- **Identity persistence: users, sessions, singleton admin seed. Usernames are…** (1 connections) — `backend/src/x_insight/identity/store.py`
- **SHA-256 hex of the opaque session token (stored server-side).** (1 connections) — `backend/src/x_insight/identity/store.py`
- **Return the user row for a raw username (normalized), or None.** (1 connections) — `backend/src/x_insight/identity/store.py`
- **Return the user row by UUID text, or None.** (1 connections) — `backend/src/x_insight/identity/store.py`
- **Create a session; return (opaque_token, csrf_token).** (1 connections) — `backend/src/x_insight/identity/store.py`
- **Return session+user when active, unrevoked, revision-matching; else None. No…** (1 connections) — `backend/src/x_insight/identity/store.py`
- **base64** (1 connections)

## Relationships

- [routes.py](routes.py.md) (15 shared connections)
- [accounts.py](accounts.py.md) (8 shared connections)
- [encounters.py](encounters.py.md) (4 shared connections)
- [patients.py](patients.py.md) (3 shared connections)
- [test_identity.py](test_identity.py.md) (3 shared connections)

## Source Files

- `backend/src/x_insight/identity/hashing.py`
- `backend/src/x_insight/identity/store.py`

## Audit Trail

- EXTRACTED: 64 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*