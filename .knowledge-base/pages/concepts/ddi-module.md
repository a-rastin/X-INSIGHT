# Ddi Module

Deterministic drug–drug interaction strategy: offline ingestion, versioned relational store, simple runtime lookup. No LLM at runtime.

## Principle

Convert monographs once into a structured versioned DDI knowledge base; the runtime checker is a deterministic database lookup (docs/dev/system-design/DDI-Module.md, Section: Recommended strategy for the DDI module). The LLM must not determine DDIs at runtime due to hallucination, nondeterminism, latency, and audit risks (docs/dev/system-design/DDI-Module.md, Section: 3. Do not make an LLM the DDI engine). No-record-found must never automatically mean drugs do not interact; the database only knows imported sources (docs/dev/system-design/DDI-Module.md, Section: 1. Requirements).

## Model

The same pair can carry multiple source assertions with different severities, requiring an evidence-based model rather than one row per pair (docs/dev/system-design/DDI-Module.md, Section: 4. Your source requires more than a simple table). Core tables are `drug`, `drug_alias`, `source_document`, and `interaction_evidence` with directional subject/object plus a symmetric pair key and pair summary (docs/dev/system-design/DDI-Module.md, Section: 5. Recommended data model). Keep source severity separate from effect, mechanism, and management action (docs/dev/system-design/DDI-Module.md, Section: 6. Keep severity separate from recommended action).

## Ingestion integrity

The parser is a deterministic state machine; declared category counts must match parsed entries exactly or ingestion fails (docs/dev/system-design/DDI-Module.md, Section: 8. Use the source counts as automatic integrity checks). Never silently fuzzy-match medication names; return MEDICATION_NOT_RECOGNIZED on normalization failure (docs/dev/system-design/DDI-Module.md, Section: 9. Drug normalization is probably the hardest part). The ingestion tool is its own program producing an ingestion report artifact (docs/dev/system-design/DDI-Module.md, Section: 19. The ingestion tool should be its own program).

Related: [system design](system-design.md), [pharmacotherapy](../topics/antipsychotic-pharmacotherapy.md).

## Provenance

- docs/dev/system-design/DDI-Module.md
