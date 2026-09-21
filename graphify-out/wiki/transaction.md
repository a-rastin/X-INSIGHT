# transaction()

> God node · 18 connections · `backend/src/x_insight/db.py`

**Community:** [accounts.py](accounts.py.md)

## Connections by Relation

### calls
- [login()](login.md) `EXTRACTED`
- create_patient() `EXTRACTED`
- change_password() `EXTRACTED`
- change_active() `EXTRACTED`
- edit_physician() `EXTRACTED`
- list_patients() `EXTRACTED`
- list_audit_events() `EXTRACTED`
- list_physicians() `EXTRACTED`
- create_physician() `EXTRACTED`
- logout() `EXTRACTED`
- get_physician() `EXTRACTED`
- review_deactivation() `EXTRACTED`
- update_preferences() `EXTRACTED`
- get_engine() `EXTRACTED`
- me() `EXTRACTED`

### contains
- [db.py](db.py.md) `EXTRACTED`

### rationale_for
- Yield one transactional connection; callers commit/rollback together. Future… `EXTRACTED`

### references
- Connection `EXTRACTED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*