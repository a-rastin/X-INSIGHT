# Encounter Notes Endpoints

> 12 nodes · cohesion 0.21

## Key Concepts

- **create_note()** (7 connections) — `backend/src/x_insight/cases/notes.py`
- **list_notes()** (6 connections) — `backend/src/x_insight/cases/notes.py`
- **_payload()** (4 connections) — `backend/src/x_insight/cases/notes.py`
- **UUID** (4 connections)
- **NoteCreate** (3 connections) — `backend/src/x_insight/cases/notes.py`
- **Any** (2 connections)
- **project_encounter_for_analysis()** (2 connections) — `backend/src/x_insight/cases/notes.py`
- **JSONResponse** (2 connections)
- **Request** (2 connections)
- **BaseModel** (1 connections)
- **get** (1 connections)
- **post** (1 connections)

## Relationships

- [App Wiring and Persistence](App_Wiring_and_Persistence.md) (6 shared connections)
- [Encounter Draft Validation](Encounter_Draft_Validation.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/cases/notes.py`

## Audit Trail

- EXTRACTED: 21 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*