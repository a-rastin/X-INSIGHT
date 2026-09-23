# Assessment Diagnosis Tests

> 20 nodes · cohesion 0.17

## Key Concepts

- **evaluate_diagnosis()** (12 connections) — `backend/src/x_insight/assessments/diagnosis.py`
- **diagnosis.py** (8 connections) — `backend/src/x_insight/assessments/diagnosis.py`
- **assessments/test_diagnosis.py** (8 connections) — `backend/tests/assessments/test_diagnosis.py`
- **_canonical_domain()** (4 connections) — `backend/src/x_insight/assessments/diagnosis.py`
- **_validate_present()** (4 connections) — `backend/src/x_insight/assessments/diagnosis.py`
- **_synthetic_qualifying_answers()** (4 connections) — `backend/tests/assessments/test_diagnosis.py`
- **test_missing_required_field_returns_partial_no_completed_result()** (4 connections) — `backend/tests/assessments/test_diagnosis.py`
- **Any** (3 connections)
- **_synthetic_symptom_count_only_answers()** (3 connections) — `backend/tests/assessments/test_diagnosis.py`
- **test_empty_answers_never_complete()** (3 connections) — `backend/tests/assessments/test_diagnosis.py`
- **test_qualifying_case_satisfies_all_criteria()** (3 connections) — `backend/tests/assessments/test_diagnosis.py`
- **test_symptom_count_alone_does_not_satisfy()** (3 connections) — `backend/tests/assessments/test_diagnosis.py`
- **_criterion_a()** (2 connections) — `backend/src/x_insight/assessments/diagnosis.py`
- **S09 slice 1 typed DSM-5-TR schizophrenia A-F evaluator. No I/O, no DB.** (1 connections) — `backend/src/x_insight/assessments/diagnosis.py`
- **Evaluate criteria A-F. Full inputs -> complete; missing -> partial.** (1 connections) — `backend/src/x_insight/assessments/diagnosis.py`
- **S09 slice 1: diagnosis threshold tracer at seam T2 (pure, no I/O, no DB).…** (1 connections) — `backend/tests/assessments/test_diagnosis.py`
- **S09 slice 2: empty input is partial (all items missing), not complete.** (1 connections) — `backend/tests/assessments/test_diagnosis.py`
- **SYNTHETIC: hand-worked qualifying case (A-F satisfied on paper).** (1 connections) — `backend/tests/assessments/test_diagnosis.py`
- **SYNTHETIC: same 2 domains but in different intervals (no shared phase).** (1 connections) — `backend/tests/assessments/test_diagnosis.py`
- **S09 slice 2 (FR-11/FR-16, T2): incomplete work is partial, never complete.** (1 connections) — `backend/tests/assessments/test_diagnosis.py`

## Relationships

- [HTTP Diagnosis Tests](HTTP_Diagnosis_Tests.md) (3 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/assessments/diagnosis.py`
- `backend/tests/assessments/test_diagnosis.py`

## Audit Trail

- EXTRACTED: 36 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*