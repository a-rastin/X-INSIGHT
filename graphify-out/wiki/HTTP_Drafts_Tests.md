# HTTP Drafts Tests

> 25 nodes · cohesion 0.26

## Key Concepts

- **test_drafts.py** (28 connections) — `backend/tests/http/test_drafts.py`
- **create_patient()** (13 connections) — `backend/tests/http/test_drafts.py`
- **create_physician()** (13 connections) — `backend/tests/http/test_drafts.py`
- **login()** (12 connections) — `backend/tests/http/test_drafts.py`
- **encounter_body()** (9 connections) — `backend/tests/http/test_drafts.py`
- **test_author_discards_draft_with_confirmation()** (9 connections) — `backend/tests/http/test_drafts.py`
- **test_malformed_patch_rejected_without_revision_bump()** (8 connections) — `backend/tests/http/test_drafts.py`
- **discard_headers()** (7 connections) — `backend/tests/http/test_drafts.py`
- **draft_headers()** (7 connections) — `backend/tests/http/test_drafts.py`
- **test_author_saves_and_retrieves_draft_across_restart()** (7 connections) — `backend/tests/http/test_drafts.py`
- **test_discard_requires_explicit_confirmation()** (7 connections) — `backend/tests/http/test_drafts.py`
- **test_double_discard_conflicts()** (7 connections) — `backend/tests/http/test_drafts.py`
- **test_discard_forbidden_for_non_author_and_anonymous()** (6 connections) — `backend/tests/http/test_drafts.py`
- **test_discard_rejects_stale_revision()** (6 connections) — `backend/tests/http/test_drafts.py`
- **test_revision_precondition_required()** (6 connections) — `backend/tests/http/test_drafts.py`
- **test_shared_read_but_author_only_write()** (6 connections) — `backend/tests/http/test_drafts.py`
- **test_terminal_invalid_and_archived_draft_rejected()** (6 connections) — `backend/tests/http/test_drafts.py`
- **test_unauthenticated_draft_access_denied()** (5 connections) — `backend/tests/http/test_drafts.py`
- **patient_headers()** (3 connections) — `backend/tests/http/test_drafts.py`
- **discard_audit_rows()** (2 connections) — `backend/tests/http/test_drafts.py`
- **S07 slice 1: author saves/retrieves draft; shared read, author-only write.…** (1 connections) — `backend/tests/http/test_drafts.py`
- **# NOTE: discard route lands in slice 4, so terminal states are set via** (1 connections) — `backend/tests/http/test_drafts.py`
- **S07 slice 3: failed (malformed) save returns 422, revision stays 1.** (1 connections) — `backend/tests/http/test_drafts.py`
- **CSRF + optional If-Match headers; never an Idempotency-Key (by design).** (1 connections) — `backend/tests/http/test_drafts.py`
- **Unwrap {"encounter": {...}} envelope if present, else flat payload.** (1 connections) — `backend/tests/http/test_drafts.py`

## Relationships

- [HTTP C-SSRS Tests](HTTP_C-SSRS_Tests.md) (9 shared connections)
- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [MCP Server](MCP_Server.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [Identity Throttle Clock](Identity_Throttle_Clock.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Identity Throttle C-SSRS](Identity_Throttle_C-SSRS.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_drafts.py`

## Audit Trail

- EXTRACTED: 85 (90%)
- INFERRED: 9 (10%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*