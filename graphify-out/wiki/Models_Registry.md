# Models Registry

> 20 nodes · cohesion 0.19

## Key Concepts

- **registry.py** (14 connections) — `backend/src/x_insight/models/registry.py`
- **load_version()** (10 connections) — `backend/src/x_insight/models/registry.py`
- **load_network()** (9 connections) — `backend/src/x_insight/models/registry.py`
- **_store_imported()** (9 connections) — `backend/src/x_insight/models/routes.py`
- **load_versions()** (7 connections) — `backend/src/x_insight/models/registry.py`
- **store_version()** (7 connections) — `backend/src/x_insight/models/registry.py`
- **network_key()** (6 connections) — `backend/src/x_insight/models/registry.py`
- **next_version()** (6 connections) — `backend/src/x_insight/models/registry.py`
- **Any** (6 connections)
- **Connection** (6 connections)
- **UUID** (6 connections)
- **store_network()** (6 connections) — `backend/src/x_insight/models/registry.py`
- **S24 slice 1: network registry storage helpers.** (1 connections) — `backend/src/x_insight/models/registry.py`
- **Return stored versions for a network, ordered by version.** (1 connections) — `backend/src/x_insight/models/registry.py`
- **Return one stored version row, or None when missing.** (1 connections) — `backend/src/x_insight/models/registry.py`
- **Derive a non-empty registry key from a validated document.** (1 connections) — `backend/src/x_insight/models/registry.py`
- **Return the next immutable version number for a network.** (1 connections) — `backend/src/x_insight/models/registry.py`
- **Insert one network row; return the stored row.** (1 connections) — `backend/src/x_insight/models/registry.py`
- **Insert one immutable network version; return the stored row.** (1 connections) — `backend/src/x_insight/models/registry.py`
- **Return one network row, or None when missing.** (1 connections) — `backend/src/x_insight/models/registry.py`

## Relationships

- [Models Routes 2](Models_Routes_2.md) (11 shared connections)
- [Models Routes 3](Models_Routes_3.md) (11 shared connections)
- [MCP Server](MCP_Server.md) (2 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/models/registry.py`
- `backend/src/x_insight/models/routes.py`

## Audit Trail

- EXTRACTED: 63 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*