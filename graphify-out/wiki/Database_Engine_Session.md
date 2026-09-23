# Database Engine Session

> 16 nodes · cohesion 0.17

## Key Concepts

- **db.py** (33 connections) — `backend/src/x_insight/db.py`
- **get_engine()** (7 connections) — `backend/src/x_insight/db.py`
- **check_readiness()** (6 connections) — `backend/src/x_insight/db.py`
- **database_url_for()** (6 connections) — `backend/src/x_insight/db.py`
- **ReadinessError** (5 connections) — `backend/src/x_insight/db.py`
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

- [MCP Server](MCP_Server.md) (8 shared connections)
- [DDI Checker](DDI_Checker.md) (5 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (2 shared connections)
- [Reasoning Queue Proposal](Reasoning_Queue_Proposal.md) (2 shared connections)
- [MCP Builder Connections 4](MCP_Builder_Connections_4.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [Cases Encounters](Cases_Encounters.md) (1 shared connections)
- [Cases Notes](Cases_Notes.md) (1 shared connections)
- [DDI Publish Tests](DDI_Publish_Tests.md) (1 shared connections)
- [Identity Accounts Contracts](Identity_Accounts_Contracts.md) (1 shared connections)
- [Identity Hashing](Identity_Hashing.md) (1 shared connections)
- [Models Routes 2](Models_Routes_2.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/db.py`

## Audit Trail

- EXTRACTED: 50 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*