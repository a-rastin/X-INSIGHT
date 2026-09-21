# Database Engine and Readiness

> 18 nodes · cohesion 0.14

## Key Concepts

- **db.py** (20 connections) — `backend/src/x_insight/db.py`
- **get_engine()** (7 connections) — `backend/src/x_insight/db.py`
- **check_readiness()** (6 connections) — `backend/src/x_insight/db.py`
- **ReadinessError** (5 connections) — `backend/src/x_insight/db.py`
- **os** (5 connections)
- **database_url_for()** (4 connections) — `backend/src/x_insight/db.py`
- **collections_abc** (4 connections)
- **dispose_engines()** (2 connections) — `backend/src/x_insight/db.py`
- **_sqlalchemy_url()** (2 connections) — `backend/src/x_insight/db.py`
- **Exception** (1 connections)
- **PostgreSQL connection lifecycle and readiness. Roles are logical connection…** (1 connections) — `backend/src/x_insight/db.py`
- **Database readiness failure with a public code.** (1 connections) — `backend/src/x_insight/db.py`
- **Return the configured URL for a logical role.** (1 connections) — `backend/src/x_insight/db.py`
- **Return a cached engine for the given URL (or the app role).** (1 connections) — `backend/src/x_insight/db.py`
- **Dispose cached engines (tests, process restart).** (1 connections) — `backend/src/x_insight/db.py`
- **Raise ReadinessError(UNAVAILABLE|INCOMPATIBLE_SCHEMA) when not ready.** (1 connections) — `backend/src/x_insight/db.py`
- **.__init__()** (1 connections) — `backend/src/x_insight/db.py`
- **Engine** (1 connections)

## Relationships

- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (4 shared connections)
- [Physician Accounts and Transactions](Physician_Accounts_and_Transactions.md) (4 shared connections)
- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (3 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (2 shared connections)
- [Encounter Draft Validation](Encounter_Draft_Validation.md) (2 shared connections)
- [MCP Connection Factory](MCP_Connection_Factory.md) (1 shared connections)
- [Patient Registration](Patient_Registration.md) (1 shared connections)
- [Shared HTTP Contracts](Shared_HTTP_Contracts.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [Identity HTTP Tests](Identity_HTTP_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/db.py`

## Audit Trail

- EXTRACTED: 42 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*