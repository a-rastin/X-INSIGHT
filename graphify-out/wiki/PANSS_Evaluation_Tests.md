# PANSS Evaluation Tests

> 29 nodes · cohesion 0.13

## Key Concepts

- **http/test_panss.py** (21 connections) — `backend/tests/http/test_panss.py`
- **evaluate_panss()** (16 connections) — `backend/src/x_insight/assessments/panss.py`
- **assessments/test_panss.py** (11 connections) — `backend/tests/assessments/test_panss.py`
- **_setup_encounter()** (7 connections) — `backend/tests/http/test_panss.py`
- **test_full_all_1_persists_and_resumes_complete()** (7 connections) — `backend/tests/http/test_panss.py`
- **test_partial_persists_and_resume_preserves_completeness()** (7 connections) — `backend/tests/http/test_panss.py`
- **test_invalid_panss_rejected_server_side()** (6 connections) — `backend/tests/http/test_panss.py`
- **_all_1_answers()** (4 connections) — `backend/tests/http/test_panss.py`
- **draft_headers()** (4 connections) — `backend/tests/http/test_panss.py`
- **encounter_body()** (4 connections) — `backend/tests/http/test_panss.py`
- **create_patient()** (3 connections) — `backend/tests/http/test_panss.py`
- **create_physician()** (3 connections) — `backend/tests/http/test_panss.py`
- **_partial_29_answers()** (3 connections) — `backend/tests/http/test_panss.py`
- **patient_headers()** (3 connections) — `backend/tests/http/test_panss.py`
- **test_all_1_yields_7_7_16_30()** (2 connections) — `backend/tests/assessments/test_panss.py`
- **test_all_7_yields_49_49_112_210()** (2 connections) — `backend/tests/assessments/test_panss.py`
- **test_empty_answers_is_unanswered_with_null_scores()** (2 connections) — `backend/tests/assessments/test_panss.py`
- **test_explicit_skip_is_not_assessed_with_null_scores()** (2 connections) — `backend/tests/assessments/test_panss.py`
- **test_mixed_skip_with_answer_rejected()** (2 connections) — `backend/tests/assessments/test_panss.py`
- **test_noninteger_rejected_and_none_is_missing()** (2 connections) — `backend/tests/assessments/test_panss.py`
- **test_one_missing_suppresses_total()** (2 connections) — `backend/tests/assessments/test_panss.py`
- **test_out_of_range_rejected()** (2 connections) — `backend/tests/assessments/test_panss.py`
- **login()** (2 connections) — `backend/tests/http/test_panss.py`
- **Any** (1 connections)
- **Evaluate PANSS answers. Delegates to generic evaluator.** (1 connections) — `backend/src/x_insight/assessments/panss.py`
- *... and 4 more nodes in this community*

## Relationships

- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (4 shared connections)
- [History HTTP Tests](History_HTTP_Tests.md) (3 shared connections)
- [Encounter Draft Validation](Encounter_Draft_Validation.md) (2 shared connections)
- [Identity HTTP Tests](Identity_HTTP_Tests.md) (2 shared connections)
- [Assessment Content Loading Tests](Assessment_Content_Loading_Tests.md) (1 shared connections)
- [Released Content Tests](Released_Content_Tests.md) (1 shared connections)
- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (1 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (1 shared connections)
- [Login Throttle and Clock](Login_Throttle_and_Clock.md) (1 shared connections)
- [Test Fixture Resets](Test_Fixture_Resets.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/assessments/panss.py`
- `backend/tests/assessments/test_panss.py`
- `backend/tests/http/test_panss.py`

## Audit Trail

- EXTRACTED: 67 (96%)
- INFERRED: 3 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*