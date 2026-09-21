# App Wiring and Persistence

> 46 nodes · cohesion 0.08

## Key Concepts

- **app.py** (37 connections) — `backend/src/x_insight/app.py`
- **patients.py** (34 connections) — `backend/src/x_insight/cases/patients.py`
- **sqlalchemy** (26 connections)
- **db.py** (21 connections) — `backend/src/x_insight/db.py`
- **notes.py** (18 connections) — `backend/src/x_insight/cases/notes.py`
- **typing** (18 connections)
- **content.py** (16 connections) — `backend/src/x_insight/assessments/content.py`
- **history_content.py** (15 connections) — `backend/src/x_insight/cases/history_content.py`
- **x_insight/__init__.py** (13 connections) — `backend/src/x_insight/__init__.py`
- **audit.py** (11 connections) — `backend/src/x_insight/operations/audit.py`
- **json** (10 connections)
- **FastAPI** (9 connections)
- **fastapi_responses** (8 connections)
- **get_engine()** (7 connections) — `backend/src/x_insight/db.py`
- **check_readiness()** (6 connections) — `backend/src/x_insight/db.py`
- **pathlib** (6 connections)
- **ReadinessError** (5 connections) — `backend/src/x_insight/db.py`
- **os** (5 connections)
- **pydantic** (5 connections)
- **sqlalchemy_engine** (5 connections)
- **register_exception_handlers()** (4 connections) — `backend/src/x_insight/app.py`
- **database_url_for()** (4 connections) — `backend/src/x_insight/db.py`
- **collections_abc** (4 connections)
- **dispose_engines()** (2 connections) — `backend/src/x_insight/db.py`
- **_sqlalchemy_url()** (2 connections) — `backend/src/x_insight/db.py`
- *... and 21 more nodes in this community*

## Relationships

- [Encounter Draft Validation](Encounter_Draft_Validation.md) (22 shared connections)
- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (20 shared connections)
- [Patient and Session Routes](Patient_and_Session_Routes.md) (15 shared connections)
- [Physician Accounts and Transactions](Physician_Accounts_and_Transactions.md) (13 shared connections)
- [HTTP Tests and Fixtures](HTTP_Tests_and_Fixtures.md) (12 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (10 shared connections)
- [Database Migrations](Database_Migrations.md) (8 shared connections)
- [Assessment Engine and PANSS Tests](Assessment_Engine_and_PANSS_Tests.md) (7 shared connections)
- [Encounter Notes Endpoints](Encounter_Notes_Endpoints.md) (6 shared connections)
- [Diagnosis Evaluation Tests](Diagnosis_Evaluation_Tests.md) (4 shared connections)
- [History HTTP Tests](History_HTTP_Tests.md) (4 shared connections)
- [Identity HTTP Tests](Identity_HTTP_Tests.md) (4 shared connections)

## Source Files

- `backend/src/x_insight/__init__.py`
- `backend/src/x_insight/app.py`
- `backend/src/x_insight/assessments/content.py`
- `backend/src/x_insight/cases/history_content.py`
- `backend/src/x_insight/cases/notes.py`
- `backend/src/x_insight/cases/patients.py`
- `backend/src/x_insight/db.py`
- `backend/src/x_insight/operations/audit.py`

## Audit Trail

- EXTRACTED: 232 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*