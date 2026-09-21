# transaction()

> God node · 23 connections · `backend/src/x_insight/db.py`

**Community:** [accounts.py](accounts.py.md)

## Connections by Relation

### calls
- [login()](login.md) `EXTRACTED`
- create_patient() `EXTRACTED`
- change_password() `EXTRACTED`
- discard_encounter() `EXTRACTED`
- change_active() `EXTRACTED`
- patch_encounter() `EXTRACTED`
- edit_physician() `EXTRACTED`
- _get_encounter() `EXTRACTED`
- list_patients() `EXTRACTED`
- list_audit_events() `EXTRACTED`
- list_physicians() `EXTRACTED`
- create_physician() `EXTRACTED`
- logout() `EXTRACTED`
- get_physician() `EXTRACTED`
- review_deactivation() `EXTRACTED`
- update_preferences() `EXTRACTED`
- list_encounters() `EXTRACTED`
- get_assessment_content() `EXTRACTED`
- get_engine() `EXTRACTED`
- me() `EXTRACTED`

### contains
- db.py `EXTRACTED`

### rationale_for
- Yield one transactional connection; callers commit/rollback together. Future… `EXTRACTED`

### references
- Connection `EXTRACTED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*