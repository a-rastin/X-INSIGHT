# transaction

> 25 nodes

## Key Concepts

- **transaction()** (22 connections) — `backend/src/x_insight/db.py`
- **record_audit()** (16 connections) — `backend/src/x_insight/operations/audit.py`
- **discard_encounter()** (14 connections) — `backend/src/x_insight/cases/encounters.py`
- **patch_encounter()** (13 connections) — `backend/src/x_insight/cases/encounters.py`
- **_get_encounter()** (11 connections) — `backend/src/x_insight/cases/encounters.py`
- **list_encounters()** (8 connections) — `backend/src/x_insight/cases/encounters.py`
- **_payload()** (7 connections) — `backend/src/x_insight/cases/encounters.py`
- **UUID** (5 connections)
- **DiscardRequest** (4 connections) — `backend/src/x_insight/cases/encounters.py`
- **JSONResponse** (4 connections)
- **Request** (4 connections)
- **DraftPatch** (3 connections) — `backend/src/x_insight/cases/encounters.py`
- **Any** (2 connections)
- **BaseModel** (2 connections)
- **get** (2 connections)
- **.check_confirmed()** (1 connections) — `backend/src/x_insight/cases/encounters.py`
- **patch** (1 connections)
- **post** (1 connections)
- **Connection** (1 connections)
- **Any** (1 connections)
- **Connection** (1 connections)
- **Session** (1 connections)
- **Explicit author-confirmed discard (S07 slice 4). Requires If-Match current…** (1 connections) — `backend/src/x_insight/cases/encounters.py`
- **Yield one transactional connection; callers commit/rollback together. Future…** (1 connections) — `backend/src/x_insight/db.py`
- **Insert one audit event in the ambient transaction; return its ID.** (1 connections) — `backend/src/x_insight/operations/audit.py`

## Relationships

- [routes.py](routes.py.md) (17 shared connections)
- [patients.py](patients.py.md) (13 shared connections)
- [accounts.py](accounts.py.md) (11 shared connections)
- [create_patient](create_patient.md) (3 shared connections)
- [get_engine](get_engine.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/cases/encounters.py`
- `backend/src/x_insight/db.py`
- `backend/src/x_insight/operations/audit.py`

## Audit Trail

- EXTRACTED: 86 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*