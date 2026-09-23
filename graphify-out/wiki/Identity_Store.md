# Identity Store

> 22 nodes · cohesion 0.13

## Key Concepts

- **store.py** (17 connections) — `backend/src/x_insight/identity/store.py`
- **hash_password()** (12 connections) — `backend/src/x_insight/identity/hashing.py`
- **hashing.py** (11 connections) — `backend/src/x_insight/identity/hashing.py`
- **normalize_username()** (10 connections) — `backend/src/x_insight/identity/store.py`
- **get_user_by_username()** (7 connections) — `backend/src/x_insight/identity/store.py`
- **get_valid_session()** (7 connections) — `backend/src/x_insight/identity/store.py`
- **create_session()** (6 connections) — `backend/src/x_insight/identity/store.py`
- **Connection** (5 connections)
- **secrets** (5 connections)
- **get_user_by_id()** (4 connections) — `backend/src/x_insight/identity/store.py`
- **token_hash()** (4 connections) — `backend/src/x_insight/identity/store.py`
- **Any** (3 connections)
- **hmac** (2 connections)
- **Standard password hashing (stdlib PBKDF2-HMAC-SHA256). No new dependency:…** (1 connections) — `backend/src/x_insight/identity/hashing.py`
- **Hash an exact (untrimmed) password; caller rejects empty input.** (1 connections) — `backend/src/x_insight/identity/hashing.py`
- **Identity persistence: users, sessions, singleton admin seed. Usernames are…** (1 connections) — `backend/src/x_insight/identity/store.py`
- **Normalize for uniqueness/lookup (passwords never use this).** (1 connections) — `backend/src/x_insight/identity/store.py`
- **SHA-256 hex of the opaque session token (stored server-side).** (1 connections) — `backend/src/x_insight/identity/store.py`
- **Return the user row for a raw username (normalized), or None.** (1 connections) — `backend/src/x_insight/identity/store.py`
- **Return the user row by UUID text, or None.** (1 connections) — `backend/src/x_insight/identity/store.py`
- **Create a session; return (opaque_token, csrf_token).** (1 connections) — `backend/src/x_insight/identity/store.py`
- **Return session+user when active, unrevoked, revision-matching; else None. No…** (1 connections) — `backend/src/x_insight/identity/store.py`

## Relationships

- [Identity Hashing](Identity_Hashing.md) (18 shared connections)
- [Identity Accounts Contracts](Identity_Accounts_Contracts.md) (9 shared connections)
- [DDI Checker](DDI_Checker.md) (3 shared connections)
- [MCP Server](MCP_Server.md) (3 shared connections)
- [Provider Config](Provider_Config.md) (1 shared connections)
- [Cases Patients](Cases_Patients.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [Identity Accounts Routes](Identity_Accounts_Routes.md) (1 shared connections)
- [Reasoning Coordinator Provider](Reasoning_Coordinator_Provider.md) (1 shared connections)
- [MCP Scoped Transport Tests](MCP_Scoped_Transport_Tests.md) (1 shared connections)
- [Provider Estimation Tests Init](Provider_Estimation_Tests_Init.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/hashing.py`
- `backend/src/x_insight/identity/store.py`

## Audit Trail

- EXTRACTED: 71 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*