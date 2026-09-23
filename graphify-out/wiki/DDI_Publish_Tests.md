# DDI Publish Tests

> 96 nodes · cohesion 0.06

## Key Concepts

- **test_publish.py** (36 connections) — `backend/tests/ddi/test_publish.py`
- **publish.py** (30 connections) — `backend/src/x_insight/ddi/publish.py`
- **PublishRejectedError** (26 connections) — `backend/src/x_insight/ddi/publish.py`
- **Path** (21 connections)
- **publish_release()** (17 connections) — `backend/src/x_insight/ddi/publish.py`
- **_seam()** (17 connections) — `backend/tests/ddi/test_publish.py`
- **Any** (16 connections)
- **_provenance()** (16 connections) — `backend/tests/ddi/test_publish.py`
- **_make_pristine_sources_dir()** (15 connections) — `backend/tests/ddi/test_publish.py`
- **canonical_pair_key()** (12 connections) — `backend/src/x_insight/ddi/terminology.py`
- **Any** (12 connections)
- **test_failed_publication_preserves_released_dataset()** (12 connections) — `backend/tests/ddi/test_publish.py`
- **_slice3_exclusions()** (11 connections) — `backend/tests/ddi/test_publish.py`
- **_slice3_manifest()** (11 connections) — `backend/tests/ddi/test_publish.py`
- **test_source_change_creates_new_candidate_version()** (11 connections) — `backend/tests/ddi/test_publish.py`
- **_base_manifest()** (10 connections) — `backend/tests/ddi/test_publish.py`
- **_check_coverage()** (9 connections) — `backend/src/x_insight/ddi/publish.py`
- **_release_seam()** (9 connections) — `backend/tests/ddi/test_publish.py`
- **test_publish_applies_approved_correction_without_modifying_source()** (9 connections) — `backend/tests/ddi/test_publish.py`
- **test_publish_coverage_scope_gating()** (9 connections) — `backend/tests/ddi/test_publish.py`
- **test_publish_preserves_duplicate_direction_evidence()** (9 connections) — `backend/tests/ddi/test_publish.py`
- **test_repeated_publish_identical_content_is_idempotent()** (9 connections) — `backend/tests/ddi/test_publish.py`
- **_make_tampered_sources_dir()** (8 connections) — `backend/tests/ddi/test_publish.py`
- **test_publish_rejection_imports_no_partial_release()** (8 connections) — `backend/tests/ddi/test_publish.py`
- **test_publish_rejects_absent_provenance()** (8 connections) — `backend/tests/ddi/test_publish.py`
- *... and 71 more nodes in this community*

## Relationships

- [MCP Server](MCP_Server.md) (12 shared connections)
- [DDI Checker](DDI_Checker.md) (7 shared connections)
- [DDI Ingestion](DDI_Ingestion.md) (6 shared connections)
- [DDI Terminology Tests](DDI_Terminology_Tests.md) (6 shared connections)
- [Reasoning Queue Proposal](Reasoning_Queue_Proposal.md) (3 shared connections)
- [Worker Workflows Tests](Worker_Workflows_Tests.md) (2 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [Database Engine Session](Database_Engine_Session.md) (1 shared connections)
- [DDI Checker Tests](DDI_Checker_Tests.md) (1 shared connections)
- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/ddi/__main__.py`
- `backend/src/x_insight/ddi/publish.py`
- `backend/src/x_insight/ddi/terminology.py`
- `backend/tests/ddi/test_publish.py`

## Audit Trail

- EXTRACTED: 283 (95%)
- INFERRED: 16 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*