# Reasoning Retry

> 21 nodes · cohesion 0.13

## Key Concepts

- **run_once()** (27 connections) — `backend/src/x_insight/reasoning/worker.py`
- **retry.py** (8 connections) — `backend/src/x_insight/reasoning/retry.py`
- **retryable_error()** (7 connections) — `backend/src/x_insight/reasoning/retry.py`
- **_record_question_failure()** (6 connections) — `backend/src/x_insight/reasoning/worker.py`
- **backoff_delay_seconds()** (5 connections) — `backend/src/x_insight/reasoning/retry.py`
- **budget_exhausted()** (4 connections) — `backend/src/x_insight/reasoning/retry.py`
- **is_retryable()** (4 connections) — `backend/src/x_insight/reasoning/retry.py`
- **_provider_leaf()** (4 connections) — `backend/src/x_insight/reasoning/retry.py`
- **BaseException** (3 connections)
- **_claimed_result()** (3 connections) — `backend/src/x_insight/reasoning/worker.py`
- **Any** (3 connections)
- **Any** (1 connections)
- **Shared retry budget and backoff (S47 slice 1). One budget for the whole…** (1 connections) — `backend/src/x_insight/reasoning/retry.py`
- **Return the driving ProviderError, unwrapping transport wrappers. The real MCP…** (1 connections) — `backend/src/x_insight/reasoning/retry.py`
- **Return the retry-driving ProviderError, or None to fail fast.** (1 connections) — `backend/src/x_insight/reasoning/retry.py`
- **Return True only for retryable provider failures. Source of truth is…** (1 connections) — `backend/src/x_insight/reasoning/retry.py`
- **True when the shared budget is spent (attempt count reached max).** (1 connections) — `backend/src/x_insight/reasoning/retry.py`
- **Deterministic backoff delay in seconds, capped at 60s. Exponential ``base 2s *…** (1 connections) — `backend/src/x_insight/reasoning/retry.py`
- **BaseException** (1 connections)
- **Claim one job, run the provider outside the claim transaction. The lease stays…** (1 connections) — `backend/src/x_insight/reasoning/worker.py`
- **Best-effort terminal failure marker; never masks the original error. Sets the…** (1 connections) — `backend/src/x_insight/reasoning/worker.py`

## Relationships

- [DDI Checker](DDI_Checker.md) (8 shared connections)
- [Worker Queue Tests](Worker_Queue_Tests.md) (6 shared connections)
- [Reasoning Queue Contracts](Reasoning_Queue_Contracts.md) (4 shared connections)
- [Worker Single Question Tests](Worker_Single_Question_Tests.md) (4 shared connections)
- [Worker Recovery Tests](Worker_Recovery_Tests.md) (3 shared connections)
- [Reasoning Queue Proposal](Reasoning_Queue_Proposal.md) (1 shared connections)
- [Reasoning Coordinator Provider](Reasoning_Coordinator_Provider.md) (1 shared connections)
- [Worker Workflows Tests](Worker_Workflows_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/reasoning/retry.py`
- `backend/src/x_insight/reasoning/worker.py`

## Audit Trail

- EXTRACTED: 42 (75%)
- INFERRED: 14 (25%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*