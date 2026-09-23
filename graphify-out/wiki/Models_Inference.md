# Models Inference

> 33 nodes · cohesion 0.11

## Key Concepts

- **inference.py** (34 connections) — `backend/src/x_insight/models/inference.py`
- **Any** (16 connections)
- **infer()** (14 connections) — `backend/src/x_insight/models/inference.py`
- **_exact_posterior()** (8 connections) — `backend/src/x_insight/models/inference.py`
- **infer_in_subprocess()** (7 connections) — `backend/src/x_insight/models/inference.py`
- **_enforce_engine_limits()** (6 connections) — `backend/src/x_insight/models/inference.py`
- **_build_model()** (5 connections) — `backend/src/x_insight/models/inference.py`
- **replay()** (5 connections) — `backend/src/x_insight/models/inference.py`
- **test_resource_exhaustion_returns_explicit_error()** (5 connections) — `backend/tests/models/test_cpt_inference.py`
- **_check_percentages()** (4 connections) — `backend/src/x_insight/models/inference.py`
- **_count_cpt_cells()** (4 connections) — `backend/src/x_insight/models/inference.py`
- **_evidence_joint()** (4 connections) — `backend/src/x_insight/models/inference.py`
- **_subprocess_worker()** (4 connections) — `backend/src/x_insight/models/inference.py`
- **_resolve_timeout()** (3 connections) — `backend/src/x_insight/models/inference.py`
- **_safe_parser()** (3 connections) — `backend/src/x_insight/models/inference.py`
- **_validate_query()** (3 connections) — `backend/src/x_insight/models/inference.py`
- **_validated_parents()** (3 connections) — `backend/src/x_insight/models/inference.py`
- **S23 slice 1: CPT validation, effective artifact, exact inference (T5).…** (1 connections) — `backend/src/x_insight/models/inference.py`
- **Build a pgmpy network from effective artifact tables only.** (1 connections) — `backend/src/x_insight/models/inference.py`
- **Count effective CPT cells (engineering bound, not clinical).** (1 connections) — `backend/src/x_insight/models/inference.py`
- **Enforce engineering resource limits before expensive work.** (1 connections) — `backend/src/x_insight/models/inference.py`
- **Exact float64 joint P(evidence) from effective tables only.** (1 connections) — `backend/src/x_insight/models/inference.py`
- **Shared deterministic exact-inference core (effective tables only).** (1 connections) — `backend/src/x_insight/models/inference.py`
- **Return P(target=state | evidence) via deterministic exact inference. Reads ONLY…** (1 connections) — `backend/src/x_insight/models/inference.py`
- **Deterministic exact replay from the frozen stored artifact only. No provider…** (1 connections) — `backend/src/x_insight/models/inference.py`
- *... and 8 more nodes in this community*

## Relationships

- [Model CPT Inference Tests Validation](Model_CPT_Inference_Tests_Validation.md) (10 shared connections)
- [Model CPT Inference Tests 2](Model_CPT_Inference_Tests_2.md) (8 shared connections)
- [Models Validation Xml](Models_Validation_Xml.md) (3 shared connections)
- [Reasoning Coordinator Provider](Reasoning_Coordinator_Provider.md) (3 shared connections)
- [DDI Checker](DDI_Checker.md) (2 shared connections)
- [Model Admission Tests](Model_Admission_Tests.md) (1 shared connections)
- [Reasoning Queue Contracts](Reasoning_Queue_Contracts.md) (1 shared connections)
- [Reasoning Provider](Reasoning_Provider.md) (1 shared connections)
- [Provider Estimation Tests Init](Provider_Estimation_Tests_Init.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/models/inference.py`
- `backend/tests/models/test_cpt_inference.py`

## Audit Trail

- EXTRACTED: 84 (97%)
- INFERRED: 3 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*