# Compose Service Topology

> 3 nodes · cohesion 0.67

## Key Concepts

- **API service depending on db** (2 connections) — `compose.yaml`
- **Postgres db service with pgdata volume** (1 connections) — `compose.yaml`
- **Web service depending on api** (1 connections) — `compose.yaml`

## Relationships

- No strong cross-community connections detected

## Source Files

- `compose.yaml`

## Audit Trail

- EXTRACTED: 2 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*