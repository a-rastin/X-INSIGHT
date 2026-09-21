# transaction()

> God node · 25 connections · `backend/src/x_insight/db.py`

**Community:** [Patient and Session Routes](Patient_and_Session_Routes.md)

## Connections by Relation

### calls
- [patch_encounter()](patch_encounter.md) `EXTRACTED`
- [login()](login.md) `EXTRACTED`
- create_patient() `EXTRACTED`
- change_password() `EXTRACTED`
- discard_encounter() `EXTRACTED`
- patch_patient_phone() `EXTRACTED`
- change_active() `EXTRACTED`
- edit_physician() `EXTRACTED`
- list_patients() `EXTRACTED`
- list_audit_events() `EXTRACTED`
- list_physicians() `EXTRACTED`
- create_physician() `EXTRACTED`
- logout() `EXTRACTED`
- _get_encounter() `EXTRACTED`
- get_physician() `EXTRACTED`
- review_deactivation() `EXTRACTED`
- update_preferences() `EXTRACTED`
- list_encounters() `EXTRACTED`
- get_assessment_content() `EXTRACTED`
- get_history_content() `EXTRACTED`
- *…and 2 more `calls` connection(s) not listed (lowest-degree first to go)*

### contains
- db.py `EXTRACTED`

### rationale_for
- Yield one transactional connection; callers commit/rollback together. Future… `EXTRACTED`

### references
- Connection `EXTRACTED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*