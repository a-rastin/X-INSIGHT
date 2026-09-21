# http/test_diagnosis.py

> 35 nodes

## Key Concepts

- **http/test_diagnosis.py** (22 connections) — `backend/tests/http/test_diagnosis.py`
- **evaluate_diagnosis()** (14 connections) — `backend/src/x_insight/assessments/diagnosis.py`
- **test_answers_change_invalidates_prior_ack()** (10 connections) — `backend/tests/http/test_diagnosis.py`
- **test_below_threshold_without_ack_stays_unacknowledged()** (9 connections) — `backend/tests/http/test_diagnosis.py`
- **test_forged_warning_ack_rejected()** (9 connections) — `backend/tests/http/test_diagnosis.py`
- **diagnosis.py** (9 connections) — `backend/src/x_insight/assessments/diagnosis.py`
- **assessments/test_diagnosis.py** (8 connections) — `backend/tests/assessments/test_diagnosis.py`
- **create_patient()** (7 connections) — `backend/tests/http/test_diagnosis.py`
- **create_physician()** (7 connections) — `backend/tests/http/test_diagnosis.py`
- **test_bypass_without_reason_succeeds_and_survives_resume()** (7 connections) — `backend/tests/http/test_diagnosis.py`
- **test_forged_bypass_rejected()** (7 connections) — `backend/tests/http/test_diagnosis.py`
- **draft_headers()** (6 connections) — `backend/tests/http/test_diagnosis.py`
- **encounter_body()** (6 connections) — `backend/tests/http/test_diagnosis.py`
- **login()** (6 connections) — `backend/tests/http/test_diagnosis.py`
- **synthetic_below_threshold_answers()** (5 connections) — `backend/tests/http/test_diagnosis.py`
- **_canonical_domain()** (4 connections) — `backend/src/x_insight/assessments/diagnosis.py`
- **_validate_present()** (4 connections) — `backend/src/x_insight/assessments/diagnosis.py`
- **_synthetic_qualifying_answers()** (4 connections) — `backend/tests/assessments/test_diagnosis.py`
- **test_missing_required_field_returns_partial_no_completed_result()** (4 connections) — `backend/tests/assessments/test_diagnosis.py`
- **_synthetic_symptom_count_only_answers()** (3 connections) — `backend/tests/assessments/test_diagnosis.py`
- **test_empty_answers_never_complete()** (3 connections) — `backend/tests/assessments/test_diagnosis.py`
- **test_qualifying_case_satisfies_all_criteria()** (3 connections) — `backend/tests/assessments/test_diagnosis.py`
- **test_symptom_count_alone_does_not_satisfy()** (3 connections) — `backend/tests/assessments/test_diagnosis.py`
- **patient_headers()** (3 connections) — `backend/tests/http/test_diagnosis.py`
- **Any** (3 connections)
- *... and 10 more nodes in this community*

## Relationships

- [physician](physician.md) (6 shared connections)
- [app.py](app.py.md) (5 shared connections)
- [encounters.py](encounters.py.md) (3 shared connections)
- [content_hash](content_hash.md) (2 shared connections)
- [test_content.py](test_content.py.md) (1 shared connections)
- [throttle.py](throttle.py.md) (1 shared connections)
- [test_identity.py](test_identity.py.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/assessments/diagnosis.py`
- `backend/tests/assessments/test_diagnosis.py`
- `backend/tests/http/test_diagnosis.py`

## Audit Trail

- EXTRACTED: 93 (95%)
- INFERRED: 5 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*