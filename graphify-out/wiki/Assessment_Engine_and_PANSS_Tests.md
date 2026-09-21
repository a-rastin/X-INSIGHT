# Assessment Engine and PANSS Tests

> 53 nodes · cohesion 0.08

## Key Concepts

- **http/test_panss.py** (21 connections) — `backend/tests/http/test_panss.py`
- **test_definitions.py** (18 connections) — `backend/tests/assessments/test_definitions.py`
- **evaluate()** (16 connections) — `backend/src/x_insight/assessments/__init__.py`
- **evaluate_panss()** (16 connections) — `backend/src/x_insight/assessments/panss.py`
- **assessments/test_panss.py** (11 connections) — `backend/tests/assessments/test_panss.py`
- **load_definition()** (9 connections) — `backend/src/x_insight/assessments/__init__.py`
- **assessments/__init__.py** (8 connections) — `backend/src/x_insight/assessments/__init__.py`
- **panss.py** (8 connections) — `backend/src/x_insight/assessments/panss.py`
- **_setup_encounter()** (7 connections) — `backend/tests/http/test_panss.py`
- **test_full_all_1_persists_and_resumes_complete()** (7 connections) — `backend/tests/http/test_panss.py`
- **test_partial_persists_and_resume_preserves_completeness()** (7 connections) — `backend/tests/http/test_panss.py`
- **test_invalid_panss_rejected_server_side()** (6 connections) — `backend/tests/http/test_panss.py`
- **_synthetic_definition()** (5 connections) — `backend/tests/assessments/test_definitions.py`
- **_all_1_answers()** (4 connections) — `backend/tests/http/test_panss.py`
- **draft_headers()** (4 connections) — `backend/tests/http/test_panss.py`
- **encounter_body()** (4 connections) — `backend/tests/http/test_panss.py`
- **Any** (3 connections)
- **_reject_forbidden_keys()** (3 connections) — `backend/src/x_insight/assessments/__init__.py`
- **test_empty_answers_is_unanswered()** (3 connections) — `backend/tests/assessments/test_definitions.py`
- **test_explicit_skip_is_not_assessed()** (3 connections) — `backend/tests/assessments/test_definitions.py`
- **test_full_answers_is_complete_with_hand_computed_total()** (3 connections) — `backend/tests/assessments/test_definitions.py`
- **test_load_definition_round_trip_preserves_scoring()** (3 connections) — `backend/tests/assessments/test_definitions.py`
- **test_single_answer_is_partial_with_scores_none()** (3 connections) — `backend/tests/assessments/test_definitions.py`
- **create_patient()** (3 connections) — `backend/tests/http/test_panss.py`
- **create_physician()** (3 connections) — `backend/tests/http/test_panss.py`
- *... and 28 more nodes in this community*

## Relationships

- [App Wiring and Persistence](App_Wiring_and_Persistence.md) (7 shared connections)
- [HTTP Tests and Fixtures](HTTP_Tests_and_Fixtures.md) (4 shared connections)
- [Encounter Draft Validation](Encounter_Draft_Validation.md) (3 shared connections)
- [History HTTP Tests](History_HTTP_Tests.md) (3 shared connections)
- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (1 shared connections)
- [Login Throttle and Clock](Login_Throttle_and_Clock.md) (1 shared connections)
- [Test Fixture Resets](Test_Fixture_Resets.md) (1 shared connections)
- [BN Schema Validator](BN_Schema_Validator.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/assessments/__init__.py`
- `backend/src/x_insight/assessments/panss.py`
- `backend/tests/assessments/test_definitions.py`
- `backend/tests/assessments/test_panss.py`
- `backend/tests/http/test_panss.py`

## Audit Trail

- EXTRACTED: 122 (98%)
- INFERRED: 3 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*