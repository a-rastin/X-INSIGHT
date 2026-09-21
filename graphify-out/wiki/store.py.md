# store.py

> 10 nodes

## Key Concepts

- **store.py** (18 connections) — `backend/src/x_insight/identity/store.py`
- **hash_password()** (13 connections) — `backend/src/x_insight/identity/hashing.py`
- **hashing.py** (12 connections) — `backend/src/x_insight/identity/hashing.py`
- **hashlib** (3 connections)
- **hmac** (2 connections)
- **secrets** (2 connections)
- **Standard password hashing (stdlib PBKDF2-HMAC-SHA256). No new dependency:…** (1 connections) — `backend/src/x_insight/identity/hashing.py`
- **Hash an exact (untrimmed) password; caller rejects empty input.** (1 connections) — `backend/src/x_insight/identity/hashing.py`
- **Identity persistence: users, sessions, singleton admin seed. Usernames are…** (1 connections) — `backend/src/x_insight/identity/store.py`
- **base64** (1 connections)

## Relationships

- [routes.py](routes.py.md) (14 shared connections)
- [accounts.py](accounts.py.md) (6 shared connections)
- [patients.py](patients.py.md) (6 shared connections)
- [test_identity.py](test_identity.py.md) (3 shared connections)
- [create_patient](create_patient.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/hashing.py`
- `backend/src/x_insight/identity/store.py`

## Audit Trail

- EXTRACTED: 42 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*