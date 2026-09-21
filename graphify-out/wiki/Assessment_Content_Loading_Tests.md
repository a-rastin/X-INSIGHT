# Assessment Content Loading Tests

> 40 nodes · cohesion 0.08

## Key Concepts

- **test_definitions.py** (18 connections) — `backend/tests/assessments/test_definitions.py`
- **evaluate()** (16 connections) — `backend/src/x_insight/assessments/__init__.py`
- **load_definition()** (9 connections) — `backend/src/x_insight/assessments/__init__.py`
- **main()** (9 connections) — `BNs/test_schema.py`
- **_load_with_reason()** (6 connections) — `backend/src/x_insight/assessments/content.py`
- **test_schema.py** (6 connections) — `BNs/test_schema.py`
- **load_released()** (5 connections) — `backend/src/x_insight/assessments/content.py`
- **_synthetic_definition()** (5 connections) — `backend/tests/assessments/test_definitions.py`
- **Any** (3 connections)
- **_reject_forbidden_keys()** (3 connections) — `backend/src/x_insight/assessments/__init__.py`
- **test_empty_answers_is_unanswered()** (3 connections) — `backend/tests/assessments/test_definitions.py`
- **test_explicit_skip_is_not_assessed()** (3 connections) — `backend/tests/assessments/test_definitions.py`
- **test_full_answers_is_complete_with_hand_computed_total()** (3 connections) — `backend/tests/assessments/test_definitions.py`
- **test_load_definition_round_trip_preserves_scoring()** (3 connections) — `backend/tests/assessments/test_definitions.py`
- **test_single_answer_is_partial_with_scores_none()** (3 connections) — `backend/tests/assessments/test_definitions.py`
- **copy** (3 connections)
- **Any** (2 connections)
- **Path** (2 connections)
- **test_bool_answer_rejected()** (2 connections) — `backend/tests/assessments/test_definitions.py`
- **test_load_definition_rejects_executable_expressions()** (2 connections) — `backend/tests/assessments/test_definitions.py`
- **test_load_definition_rejects_unknown_operator()** (2 connections) — `backend/tests/assessments/test_definitions.py`
- **test_max_operator_scores_peak()** (2 connections) — `backend/tests/assessments/test_definitions.py`
- **test_mixed_skip_rejected()** (2 connections) — `backend/tests/assessments/test_definitions.py`
- **test_out_of_range_answer_rejected()** (2 connections) — `backend/tests/assessments/test_definitions.py`
- **test_undeclared_item_id_rejected()** (2 connections) — `backend/tests/assessments/test_definitions.py`
- *... and 15 more nodes in this community*

## Relationships

- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (11 shared connections)
- [PANSS Evaluation Tests](PANSS_Evaluation_Tests.md) (1 shared connections)
- [Identity HTTP Tests](Identity_HTTP_Tests.md) (1 shared connections)

## Source Files

- `BNs/test_schema.py`
- `backend/src/x_insight/assessments/__init__.py`
- `backend/src/x_insight/assessments/content.py`
- `backend/tests/assessments/test_definitions.py`

## Audit Trail

- EXTRACTED: 70 (93%)
- INFERRED: 5 (7%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*