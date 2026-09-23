# DDI Terminology Tests

> 37 nodes · cohesion 0.10

## Key Concepts

- **terminology.py** (18 connections) — `backend/src/x_insight/ddi/terminology.py`
- **test_terminology.py** (18 connections) — `backend/tests/ddi/test_terminology.py`
- **load_terminology()** (14 connections) — `backend/src/x_insight/ddi/terminology.py`
- **resolve()** (12 connections) — `backend/src/x_insight/ddi/terminology.py`
- **normalize()** (10 connections) — `backend/src/x_insight/ddi/terminology.py`
- **test_canonical_case_whitespace_alias_variants_resolve_to_stable_id()** (8 connections) — `backend/tests/ddi/test_terminology.py`
- **_make_sources_dir()** (7 connections) — `backend/tests/ddi/test_terminology.py`
- **test_ambiguous_alias_yields_unresolved_not_first_row()** (7 connections) — `backend/tests/ddi/test_terminology.py`
- **Terminology** (6 connections) — `backend/src/x_insight/ddi/terminology.py`
- **Path** (6 connections)
- **test_paragraph_direction_survives_terminology_resolution()** (6 connections) — `backend/tests/ddi/test_terminology.py`
- **test_patient_inputs_remain_drug_only_concept_type()** (5 connections) — `backend/tests/ddi/test_terminology.py`
- **test_report_exports_unresolved_names_and_collisions_for_review()** (5 connections) — `backend/tests/ddi/test_terminology.py`
- **_ofloxacin_entries()** (4 connections) — `backend/tests/ddi/test_terminology.py`
- **test_look_alike_names_remain_distinct()** (4 connections) — `backend/tests/ddi/test_terminology.py`
- **test_salt_strength_combination_not_applied_without_reviewed_rules()** (4 connections) — `backend/tests/ddi/test_terminology.py`
- **test_unknown_name_stays_unknown()** (4 connections) — `backend/tests/ddi/test_terminology.py`
- **_alias_text()** (3 connections) — `backend/src/x_insight/ddi/terminology.py`
- **test_canonical_pair_key_unordered_stable_and_distinct()** (3 connections) — `backend/tests/ddi/test_terminology.py`
- **shutil** (3 connections)
- **Copy the original monograph byte-identically under a temp sources dir.** (2 connections) — `backend/tests/ddi/test_publish.py`
- **Any** (1 connections)
- **Path** (1 connections)
- **S17 slice-1 controlled terminology: exact normalized resolution only. No fuzzy…** (1 connections) — `backend/src/x_insight/ddi/terminology.py`
- **Exact normalized match only; collisions never resolve silently.** (1 connections) — `backend/src/x_insight/ddi/terminology.py`
- *... and 12 more nodes in this community*

## Relationships

- [DDI Ingestion](DDI_Ingestion.md) (11 shared connections)
- [DDI Checker](DDI_Checker.md) (8 shared connections)
- [MCP Server](MCP_Server.md) (7 shared connections)
- [DDI Publish Tests](DDI_Publish_Tests.md) (6 shared connections)
- [Worker Workflows Tests](Worker_Workflows_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/ddi/terminology.py`
- `backend/tests/ddi/test_publish.py`
- `backend/tests/ddi/test_terminology.py`

## Audit Trail

- EXTRACTED: 94 (95%)
- INFERRED: 5 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*