# Physician Accounts and Transactions

> 44 nodes · cohesion 0.14

## Key Concepts

- **accounts.py** (51 connections) — `backend/src/x_insight/identity/accounts.py`
- **transaction()** (25 connections) — `backend/src/x_insight/db.py`
- **start_command()** (18 connections) — `backend/src/x_insight/identity/accounts.py`
- **change_active()** (14 connections) — `backend/src/x_insight/identity/accounts.py`
- **edit_physician()** (13 connections) — `backend/src/x_insight/identity/accounts.py`
- **JSONResponse** (12 connections)
- **Request** (12 connections)
- **list_audit_events()** (11 connections) — `backend/src/x_insight/identity/accounts.py`
- **list_physicians()** (11 connections) — `backend/src/x_insight/identity/accounts.py`
- **UUID** (11 connections)
- **require_admin()** (11 connections) — `backend/src/x_insight/identity/accounts.py`
- **create_physician()** (10 connections) — `backend/src/x_insight/identity/accounts.py`
- **finish_command()** (10 connections) — `backend/src/x_insight/identity/accounts.py`
- **get_physician()** (9 connections) — `backend/src/x_insight/identity/accounts.py`
- **review_deactivation()** (9 connections) — `backend/src/x_insight/identity/accounts.py`
- **Any** (8 connections)
- **account_response()** (7 connections) — `backend/src/x_insight/identity/accounts.py`
- **deactivate()** (7 connections) — `backend/src/x_insight/identity/accounts.py`
- **reactivate()** (7 connections) — `backend/src/x_insight/identity/accounts.py`
- **parse_idempotency_key()** (6 connections) — `backend/src/x_insight/contracts.py`
- **check_revision()** (6 connections) — `backend/src/x_insight/identity/accounts.py`
- **DeactivateRequest** (5 connections) — `backend/src/x_insight/identity/accounts.py`
- **draft_review()** (5 connections) — `backend/src/x_insight/identity/accounts.py`
- **BaseModel** (5 connections)
- **safe_account()** (5 connections) — `backend/src/x_insight/identity/accounts.py`
- *... and 19 more nodes in this community*

## Relationships

- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (26 shared connections)
- [Patient Registration](Patient_Registration.md) (11 shared connections)
- [History HTTP Tests](History_HTTP_Tests.md) (8 shared connections)
- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (7 shared connections)
- [Encounter Draft Validation](Encounter_Draft_Validation.md) (7 shared connections)
- [Shared HTTP Contracts](Shared_HTTP_Contracts.md) (6 shared connections)
- [Database Engine and Readiness](Database_Engine_and_Readiness.md) (4 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/contracts.py`
- `backend/src/x_insight/db.py`
- `backend/src/x_insight/identity/accounts.py`

## Audit Trail

- EXTRACTED: 202 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*