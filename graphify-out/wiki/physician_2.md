# physician()

> God node · 31 connections · `backend/src/x_insight/identity/accounts.py`

**Community:** [physician](physician.md)

## Connections by Relation

### calls
- change_active() `EXTRACTED`
- edit_physician() `EXTRACTED`
- get_physician() `EXTRACTED`
- review_deactivation() `EXTRACTED`

### contains
- [accounts.py](accounts.py.md) `EXTRACTED`

### indirect_call
- test_answers_change_invalidates_prior_ack() `INFERRED`
- test_below_threshold_without_ack_stays_unacknowledged() `INFERRED`
- test_forged_warning_ack_rejected() `INFERRED`
- test_author_discards_draft_with_confirmation() `INFERRED`
- test_malformed_patch_rejected_without_revision_bump() `INFERRED`
- test_bypass_without_reason_succeeds_and_survives_resume() `INFERRED`
- test_forged_bypass_rejected() `INFERRED`
- test_author_saves_and_retrieves_draft_across_restart() `INFERRED`
- test_discard_requires_explicit_confirmation() `INFERRED`
- test_double_discard_conflicts() `INFERRED`
- test_full_all_1_persists_and_resumes_complete() `INFERRED`
- test_partial_persists_and_resume_preserves_completeness() `INFERRED`
- test_discard_rejects_stale_revision() `INFERRED`
- test_revision_precondition_required() `INFERRED`
- test_terminal_invalid_and_archived_draft_rejected() `INFERRED`
- test_invalid_panss_rejected_server_side() `INFERRED`
- test_concurrent_duplicate_archived_and_idempotent_create() `INFERRED`
- test_unauthenticated_draft_access_denied() `INFERRED`
- test_patient_field_validation_rejects_bad_demographics() `INFERRED`
- test_physician_registers_patient_with_registration_draft() `INFERRED`
- *…and 3 more `indirect_call` connection(s) not listed (lowest-degree first to go)*

### references
- UUID `EXTRACTED`
- [Any](Any.md) `EXTRACTED`
- Connection `EXTRACTED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*