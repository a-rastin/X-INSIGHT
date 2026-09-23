# HTTP History Tests

> 16 nodes · cohesion 0.23

## Key Concepts

- **_login()** (9 connections) — `backend/tests/http/test_history.py`
- **_mutation_headers()** (9 connections) — `backend/tests/http/test_history.py`
- **_encounter()** (7 connections) — `backend/tests/http/test_history.py`
- **test_excluded_medication_regimen_fields_rejected()** (6 connections) — `backend/tests/http/test_history.py`
- **test_history_reconciliation_shape_rejected_when_not_explicit()** (6 connections) — `backend/tests/http/test_history.py`
- **test_undeclared_history_field_rejected_revision_unchanged()** (6 connections) — `backend/tests/http/test_history.py`
- **test_declared_history_values_round_trip_with_server_provenance()** (5 connections) — `backend/tests/http/test_history.py`
- **test_effect_status_and_severity_validation_round_trips_with_provenance()** (5 connections) — `backend/tests/http/test_history.py`
- **test_effect_status_change_requires_explicit_severity_clear()** (5 connections) — `backend/tests/http/test_history.py`
- **test_history_content_route_exposes_released_only()** (5 connections) — `backend/tests/http/test_history.py`
- **test_physician_phone_update_via_patient_patch()** (5 connections) — `backend/tests/http/test_history.py`
- **S12 slice A: undeclared history field -> 422, revision/draft unchanged.** (1 connections) — `backend/tests/http/test_history.py`
- **S12 slice A (RED): FR-14-excluded regimen fields -> 422, never stored. FR-14…** (1 connections) — `backend/tests/http/test_history.py`
- **S12 slice B (RED): optional phone text update belongs to S12 step 4. Expected…** (1 connections) — `backend/tests/http/test_history.py`
- **S12 slice B (RED): reconciliation state must be validated, not verbatim. S12…** (1 connections) — `backend/tests/http/test_history.py`
- **S12 slice B (RED): GET /content/history serves released versions only. Mirrors…** (1 connections) — `backend/tests/http/test_history.py`

## Relationships

- [MCP Server](MCP_Server.md) (11 shared connections)
- [HTTP C-SSRS Tests](HTTP_C-SSRS_Tests.md) (8 shared connections)

## Source Files

- `backend/tests/http/test_history.py`

## Audit Trail

- EXTRACTED: 38 (83%)
- INFERRED: 8 (17%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*