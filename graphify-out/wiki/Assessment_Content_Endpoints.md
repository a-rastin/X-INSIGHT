# Assessment Content Endpoints

> 9 nodes · cohesion 0.28

## Key Concepts

- **get_assessment_content()** (7 connections) — `backend/src/x_insight/assessments/content.py`
- **_load_with_reason()** (6 connections) — `backend/src/x_insight/assessments/content.py`
- **load_released()** (5 connections) — `backend/src/x_insight/assessments/content.py`
- **Any** (2 connections)
- **Path** (2 connections)
- **get** (1 connections)
- **JSONResponse** (1 connections)
- **Request** (1 connections)
- **Return released content or None; no DB, reads at most one file.** (1 connections) — `backend/src/x_insight/assessments/content.py`

## Relationships

- [App Wiring and Persistence](App_Wiring_and_Persistence.md) (3 shared connections)
- [Patient and Session Routes](Patient_and_Session_Routes.md) (2 shared connections)
- [Assessment Engine and PANSS Tests](Assessment_Engine_and_PANSS_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/assessments/content.py`

## Audit Trail

- EXTRACTED: 16 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*