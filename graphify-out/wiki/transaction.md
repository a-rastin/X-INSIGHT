# transaction

> 22 nodes

## Key Concepts

- **transaction()** (23 connections) — `backend/src/x_insight/db.py`
- **discard_encounter()** (14 connections) — `backend/src/x_insight/cases/encounters.py`
- **patch_encounter()** (14 connections) — `backend/src/x_insight/cases/encounters.py`
- **_get_encounter()** (11 connections) — `backend/src/x_insight/cases/encounters.py`
- **_apply_diagnosis_ack()** (8 connections) — `backend/src/x_insight/cases/encounters.py`
- **list_encounters()** (8 connections) — `backend/src/x_insight/cases/encounters.py`
- **_payload()** (7 connections) — `backend/src/x_insight/cases/encounters.py`
- **UUID** (5 connections)
- **DiscardRequest** (4 connections) — `backend/src/x_insight/cases/encounters.py`
- **JSONResponse** (4 connections)
- **Request** (4 connections)
- **DraftPatch** (3 connections) — `backend/src/x_insight/cases/encounters.py`
- **Any** (3 connections)
- **BaseModel** (2 connections)
- **get** (2 connections)
- **.check_confirmed()** (1 connections) — `backend/src/x_insight/cases/encounters.py`
- **patch** (1 connections)
- **post** (1 connections)
- **Connection** (1 connections)
- **Apply S09 slice 3-4 ack/bypass semantics to the autosave payload (PATCH only).…** (1 connections) — `backend/src/x_insight/cases/encounters.py`
- **Explicit author-confirmed discard (S07 slice 4). Requires If-Match current…** (1 connections) — `backend/src/x_insight/cases/encounters.py`
- **Yield one transactional connection; callers commit/rollback together. Future…** (1 connections) — `backend/src/x_insight/db.py`

## Relationships

- [routes.py](routes.py.md) (13 shared connections)
- [encounters.py](encounters.py.md) (12 shared connections)
- [accounts.py](accounts.py.md) (9 shared connections)
- [patients.py](patients.py.md) (4 shared connections)
- [record_audit](record_audit.md) (2 shared connections)
- [http/test_diagnosis.py](http-test_diagnosis.py.md) (1 shared connections)
- [test_definitions.py](test_definitions.py.md) (1 shared connections)
- [get_engine](get_engine.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/cases/encounters.py`
- `backend/src/x_insight/db.py`

## Audit Trail

- EXTRACTED: 81 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*