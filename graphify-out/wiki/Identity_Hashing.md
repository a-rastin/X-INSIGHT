# Identity Hashing

> 32 nodes · cohesion 0.17

## Key Concepts

- **identity/routes.py** (45 connections) — `backend/src/x_insight/identity/routes.py`
- **_require_session()** (23 connections) — `backend/src/x_insight/identity/routes.py`
- **login()** (20 connections) — `backend/src/x_insight/identity/routes.py`
- **change_password()** (15 connections) — `backend/src/x_insight/identity/routes.py`
- **_check_csrf()** (14 connections) — `backend/src/x_insight/identity/routes.py`
- **_request_id()** (12 connections) — `backend/src/x_insight/identity/routes.py`
- **Request** (11 connections)
- **logout()** (10 connections) — `backend/src/x_insight/identity/routes.py`
- **ensure_admin_seeded()** (10 connections) — `backend/src/x_insight/identity/store.py`
- **error_body()** (9 connections) — `backend/src/x_insight/contracts.py`
- **verify_password()** (9 connections) — `backend/src/x_insight/identity/hashing.py`
- **update_preferences()** (9 connections) — `backend/src/x_insight/identity/routes.py`
- **JSONResponse** (8 connections)
- **me()** (7 connections) — `backend/src/x_insight/identity/routes.py`
- **_client_key()** (4 connections) — `backend/src/x_insight/identity/routes.py`
- **_generic_login_denied()** (4 connections) — `backend/src/x_insight/identity/routes.py`
- **LoginRequest** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **PasswordChangeRequest** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **PreferencesRequest** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **BaseModel** (3 connections)
- **post** (3 connections)
- **_secure_cookie()** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **_session_token()** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **Any** (2 connections)
- **Build the standard error envelope (plan section 4.3).** (1 connections) — `backend/src/x_insight/contracts.py`
- *... and 7 more nodes in this community*

## Relationships

- [Identity Store](Identity_Store.md) (18 shared connections)
- [MCP Server](MCP_Server.md) (15 shared connections)
- [Cases Patients](Cases_Patients.md) (12 shared connections)
- [Identity Accounts Contracts](Identity_Accounts_Contracts.md) (9 shared connections)
- [Identity Throttle Clock](Identity_Throttle_Clock.md) (5 shared connections)
- [Reasoning Queue Proposal](Reasoning_Queue_Proposal.md) (5 shared connections)
- [DDI Checker](DDI_Checker.md) (4 shared connections)
- [Shared HTTP Contracts](Shared_HTTP_Contracts.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [Database Engine Session](Database_Engine_Session.md) (1 shared connections)
- [Assessment PANSS Tests](Assessment_PANSS_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/contracts.py`
- `backend/src/x_insight/identity/hashing.py`
- `backend/src/x_insight/identity/routes.py`
- `backend/src/x_insight/identity/store.py`

## Audit Trail

- EXTRACTED: 157 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*