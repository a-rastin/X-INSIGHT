# Shared HTTP Contracts

> 5 nodes · cohesion 0.50

## Key Concepts

- **canonical_json()** (8 connections) — `backend/src/x_insight/contracts.py`
- **content_hash()** (8 connections) — `backend/src/x_insight/contracts.py`
- **Any** (3 connections)
- **Encode canonical UTF-8 JSON: sorted keys, compact, finite numbers. Object keys…** (1 connections) — `backend/src/x_insight/contracts.py`
- **SHA-256 hex of the canonical JSON encoding.** (1 connections) — `backend/src/x_insight/contracts.py`

## Relationships

- [Identity Accounts Contracts](Identity_Accounts_Contracts.md) (4 shared connections)
- [DDI Checker](DDI_Checker.md) (2 shared connections)
- [HTTP Diagnosis Tests](HTTP_Diagnosis_Tests.md) (2 shared connections)
- [Cases Patients](Cases_Patients.md) (1 shared connections)
- [MCP Server](MCP_Server.md) (1 shared connections)
- [Identity Hashing](Identity_Hashing.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/contracts.py`

## Audit Trail

- EXTRACTED: 16 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*