# HTTP Networks Tests

> 35 nodes · cohesion 0.18

## Key Concepts

- **test_networks.py** (39 connections) — `backend/tests/http/test_networks.py`
- **login()** (19 connections) — `backend/tests/http/test_networks.py`
- **csrf_headers()** (18 connections) — `backend/tests/http/test_networks.py`
- **_build_pins()** (9 connections) — `backend/tests/http/test_networks.py`
- **_import_synthetic_versions()** (9 connections) — `backend/tests/http/test_networks.py`
- **_import_v1()** (7 connections) — `backend/tests/http/test_networks.py`
- **TestClient** (7 connections)
- **test_activate_complete_registration_bundle_increments_revision()** (6 connections) — `backend/tests/http/test_networks.py`
- **test_activate_incomplete_bundle_rejected_pointer_unchanged()** (6 connections) — `backend/tests/http/test_networks.py`
- **test_activate_unreviewed_bundle_rejected_pointer_unchanged()** (6 connections) — `backend/tests/http/test_networks.py`
- **test_admin_graph_returns_ordered_nodes_edges_states_and_validation()** (6 connections) — `backend/tests/http/test_networks.py`
- **test_repin_one_question_to_v2_preserves_v1_immutability()** (6 connections) — `backend/tests/http/test_networks.py`
- **create_physician()** (5 connections) — `backend/tests/http/test_networks.py`
- **_import_seven_with_ids()** (5 connections) — `backend/tests/http/test_networks.py`
- **_pointer_revision_or_zero()** (5 connections) — `backend/tests/http/test_networks.py`
- **_sha()** (5 connections) — `backend/tests/http/test_networks.py`
- **test_admin_imports_synthetic_network_as_immutable_version_1()** (5 connections) — `backend/tests/http/test_networks.py`
- **test_bundle_activate_rollback_denied_for_physician_and_anonymous()** (5 connections) — `backend/tests/http/test_networks.py`
- **test_get_current_bundle_pointer_returns_revision_hash_and_pins()** (5 connections) — `backend/tests/http/test_networks.py`
- **test_rollback_to_prior_revision_creates_new_activation_and_preserves_audit()** (5 connections) — `backend/tests/http/test_networks.py`
- **test_stale_activate_after_repin_rejected_pointer_unchanged()** (5 connections) — `backend/tests/http/test_networks.py`
- **test_validate_returns_separate_reports_without_mutation()** (5 connections) — `backend/tests/http/test_networks.py`
- **test_admin_version_2_preserves_v1_bytes_and_stored_reports_differ()** (4 connections) — `backend/tests/http/test_networks.py`
- **test_graph_denied_for_physician_and_anonymous()** (4 connections) — `backend/tests/http/test_networks.py`
- **test_graph_has_no_edit_operation()** (4 connections) — `backend/tests/http/test_networks.py`
- *... and 10 more nodes in this community*

## Relationships

- [DDI Checker](DDI_Checker.md) (2 shared connections)
- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [HTTP DDI Tests](HTTP_DDI_Tests.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_networks.py`

## Audit Trail

- EXTRACTED: 115 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*