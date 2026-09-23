# Knowledge Base App

> 23 nodes · cohesion 0.10

## Key Concepts

- **app.py** (50 connections) — `backend/src/x_insight/app.py`
- **FastAPI** (13 connections)
- **ready()** (8 connections) — `backend/src/x_insight/app.py`
- **register_exception_handlers()** (4 connections) — `backend/src/x_insight/app.py`
- **RequestContextMiddleware** (4 connections) — `backend/src/x_insight/app.py`
- **health()** (3 connections) — `backend/src/x_insight/app.py`
- **Any** (3 connections)
- **.__call__()** (3 connections) — `backend/src/x_insight/app.py`
- **x_insight_identity_accounts** (3 connections)
- **index.md** (2 connections) — `.agents/skills/knowledge-base/SKILL.md`
- **get** (2 connections)
- **.__init__()** (2 connections) — `backend/src/x_insight/app.py`
- **Attach the standard contract handlers to another app (tests reuse).** (1 connections) — `backend/src/x_insight/app.py`
- **Liveness only; never touches the database.** (1 connections) — `backend/src/x_insight/app.py`
- **Readiness: database reachable and schema at the expected revision.** (1 connections) — `backend/src/x_insight/app.py`
- **Propagate/generate request IDs, enforce body size, echo ID on errors.** (1 connections) — `backend/src/x_insight/app.py`
- **send_with_id()** (1 connections) — `backend/src/x_insight/app.py`
- **fastapi_exceptions** (1 connections)
- **starlette_exceptions** (1 connections)
- **x_insight_assessments_content** (1 connections)
- **x_insight_cases_history_content** (1 connections)
- **x_insight_cases_notes** (1 connections)
- **x_insight_cases_patients** (1 connections)

## Relationships

- [MCP Server](MCP_Server.md) (6 shared connections)
- [App Middleware Errors](App_Middleware_Errors.md) (6 shared connections)
- [DDI Checker](DDI_Checker.md) (5 shared connections)
- [Models Routes 2](Models_Routes_2.md) (3 shared connections)
- [Reasoning Routes](Reasoning_Routes.md) (3 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (3 shared connections)
- [Cases Encounters](Cases_Encounters.md) (2 shared connections)
- [Cases Notes](Cases_Notes.md) (2 shared connections)
- [Reasoning Snapshots](Reasoning_Snapshots.md) (2 shared connections)
- [Worker Single Question Tests](Worker_Single_Question_Tests.md) (2 shared connections)
- [Database Engine Session](Database_Engine_Session.md) (2 shared connections)
- [Knowledge Base Skill](Knowledge_Base_Skill.md) (1 shared connections)

## Source Files

- `.agents/skills/knowledge-base/SKILL.md`
- `backend/src/x_insight/app.py`

## Audit Trail

- EXTRACTED: 80 (98%)
- INFERRED: 2 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*