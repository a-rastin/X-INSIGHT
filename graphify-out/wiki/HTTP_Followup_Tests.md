# HTTP Followup Tests

> 25 nodes · cohesion 0.26

## Key Concepts

- **test_followup.py** (24 connections) — `backend/tests/http/test_followup.py`
- **mutation_headers()** (12 connections) — `backend/tests/http/test_followup.py`
- **create_patient()** (11 connections) — `backend/tests/http/test_followup.py`
- **create_physician()** (11 connections) — `backend/tests/http/test_followup.py`
- **sign_baseline()** (11 connections) — `backend/tests/http/test_followup.py`
- **login()** (10 connections) — `backend/tests/http/test_followup.py`
- **encounter_body()** (9 connections) — `backend/tests/http/test_followup.py`
- **test_followup_copies_history_and_medications_with_pending_reconciliation()** (8 connections) — `backend/tests/http/test_followup.py`
- **test_followup_reconciliation_rejects_bare_marker_and_requires_object()** (8 connections) — `backend/tests/http/test_followup.py`
- **test_followup_reports_changed_baseline_after_newer_signed_record()** (8 connections) — `backend/tests/http/test_followup.py`
- **test_followup_starts_with_unanswered_panss_cssrs_but_baseline_scores_preserved()** (8 connections) — `backend/tests/http/test_followup.py`
- **test_two_physicians_create_separate_followup_drafts()** (8 connections) — `backend/tests/http/test_followup.py`
- **test_other_open_drafts_visible_read_only_in_list()** (7 connections) — `backend/tests/http/test_followup.py`
- **test_physician_creates_followup_from_signed_baseline()** (7 connections) — `backend/tests/http/test_followup.py`
- **test_shared_read_but_author_only_edit_on_followup()** (7 connections) — `backend/tests/http/test_followup.py`
- **test_followup_guards_baseline_state_auth_and_idempotency()** (6 connections) — `backend/tests/http/test_followup.py`
- **clean_followup()** (2 connections) — `backend/tests/http/test_followup.py`
- **fixture** (1 connections)
- **S14 slice 1 (RED): follow-up creation + shared read + author-only edit (T1).…** (1 connections) — `backend/tests/http/test_followup.py`
- **Slice-2 copy contract (RED): baseline history/meds copy, recon pending.** (1 connections) — `backend/tests/http/test_followup.py`
- **Slice-2 freshness pin: PANSS/C-SSRS never copy; baseline keeps scores.** (1 connections) — `backend/tests/http/test_followup.py`
- **Slice-2 guard pin on follow_up kind: bare recon 422, FR-14 dose 422.** (1 connections) — `backend/tests/http/test_followup.py`
- **Slice-3a: two physicians hold separate drafts on one signed baseline.** (1 connections) — `backend/tests/http/test_followup.py`
- **Slice-3b (RED): follow-up flags a newer signed record (read-side only).** (1 connections) — `backend/tests/http/test_followup.py`
- **Fixture setup only: mark the registration draft as signed via SQL.** (1 connections) — `backend/tests/http/test_followup.py`

## Relationships

- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [MCP Server](MCP_Server.md) (1 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [HTTP DDI Tests](HTTP_DDI_Tests.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_followup.py`

## Audit Trail

- EXTRACTED: 86 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*