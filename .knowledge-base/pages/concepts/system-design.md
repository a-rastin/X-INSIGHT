# System Design

Detailed modular-monolith design: stack, workflows, BN registry, queue, APIs, and ADRs.

## Stack and deployment

TypeScript/React UI, Python/FastAPI API, separate worker, pgmpy inference, PostgreSQL, internal stdio MCP, and an OpenAI-compatible LLM (docs/dev/system-design/system-design.md, Section: 2. Proposed architecture and deployment). ADR-01 records the modular monolith with separate worker; ADR-02 PostgreSQL for records and the initial durable queue; ADR-03 fixed network structure with run-specific LLM-estimated CPTs; ADR-04 internal read-only MCP with application mediation; ADR-05 immutable signed snapshots with append-only corrections (docs/dev/system-design/system-design.md, Section: 13. Architecture decision records).

## Patient workflows

Registration requires names, M/F sex, age 18–99, unique ten-digit ID with leading zeros, DSM-5-TR, PANSS, C-SSRS, history, and meds, then an automatic run (docs/dev/system-design/system-design.md, Section: 4. Patient and encounter workflows). Page notes are excluded from snapshots, MCP, and prompts via an allowlisted serializer; history maps only through versioned variables (docs/dev/system-design/system-design.md, Section: 4. Patient and encounter workflows).

## BN registry and CPTs

The registry covers 7 registration plus 6 follow-up questions; each has one XMLBIF network, predefined prompt, manifest, and template (docs/dev/system-design/system-design.md, Section: 7. Bayesian model registry and execution). Every CPT is estimated per run with 0–100 percentages summing to 100 within 0.000001 tolerance; no default fallback or silent repair (docs/dev/system-design/system-design.md, Section: 7. Bayesian model registry and execution).

## Jobs and signing

The durable PostgreSQL queue uses leases, fencing, idempotency, two retries after the initial attempt, 60s provider timeout, and fairness across runs (docs/dev/system-design/system-design.md, Section: 9. Jobs, failures, caching, and capacity). Signing requires a successful current proposal and review; manual-plan signing after failure is rejected server-side and in the UI (docs/dev/system-design/system-design.md, Section: 7. Bayesian model registry and execution).

Related: [system architecture](system-architecture.md), [MCP design](mcp-design.md), [reasoning pipeline](../topics/reasoning-pipeline.md).

## Provenance

- docs/dev/system-design/system-design.md
