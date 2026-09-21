# record_audit

> 5 nodes

## Key Concepts

- **record_audit()** (16 connections) — `backend/src/x_insight/operations/audit.py`
- **Any** (1 connections)
- **Connection** (1 connections)
- **Session** (1 connections)
- **Insert one audit event in the ambient transaction; return its ID.** (1 connections) — `backend/src/x_insight/operations/audit.py`

## Relationships

- [routes.py](routes.py.md) (4 shared connections)
- [transaction](transaction.md) (2 shared connections)
- [patients.py](patients.py.md) (2 shared connections)
- [accounts.py](accounts.py.md) (2 shared connections)
- [encounters.py](encounters.py.md) (2 shared connections)

## Source Files

- `backend/src/x_insight/operations/audit.py`

## Audit Trail

- EXTRACTED: 16 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*