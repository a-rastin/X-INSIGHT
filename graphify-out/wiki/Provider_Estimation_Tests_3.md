# Provider Estimation Tests 3

> 6 nodes · cohesion 0.33

## Key Concepts

- **_EstimationHandler** (4 connections) — `backend/tests/provider/test_estimation.py`
- **_synthetic_candidate_response()** (4 connections) — `backend/tests/provider/test_estimation.py`
- **.do_POST()** (2 connections) — `backend/tests/provider/test_estimation.py`
- **.log_message()** (2 connections) — `backend/tests/provider/test_estimation.py`
- **Deterministic localhost endpoint: capture body, return strict CPT.** (1 connections) — `backend/tests/provider/test_estimation.py`
- **Strict candidate CPT for synthetic 2-node A->B (same math as S23 slice 1).** (1 connections) — `backend/tests/provider/test_estimation.py`

## Relationships

- [Provider Estimation Tests Init](Provider_Estimation_Tests_Init.md) (4 shared connections)

## Source Files

- `backend/tests/provider/test_estimation.py`

## Audit Trail

- EXTRACTED: 9 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*