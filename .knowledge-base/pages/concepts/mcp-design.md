# Mcp Design

Internal read-only MCP server: contracts, sequential protocol, validation, and replay.

## Boundaries

The MCP server exposes read-only question-scoped patient access; the app owns scheduling, validation, execution, and rendering (docs/dev/system-design/MCP-design.md, Section: 1. Scope and requirements). Every CPT including roots must be estimated per question; no registered table is a fallback; values go into a run-local copy (docs/dev/system-design/MCP-design.md, Section: 1. Scope and requirements). The single v1 tool `get_question_patient_inputs` returns only represented variables — no full-record, search, write, execution, or drafting tools (docs/dev/system-design/MCP-design.md, Section: 4. Patient-record tool contract).

## Protocol and validation

Questions run strictly sequentially with three total attempts; failure stops later questions and retains completed results (docs/dev/system-design/MCP-design.md, Section: 5. Sequential run protocol). CPT validation requires complete coverage, exact ordering, finite 0–100 percentages, row sums of 100 within 0.000001 tolerance, and no silent repair (docs/dev/system-design/MCP-design.md, Section: 6. CPT response and validation).

## Replay and transparency

Deterministic replay uses the stored snapshot, effective CPT artifact, evidence, and pinned engine without new LLM calls (docs/dev/system-design/MCP-design.md, Section: 8. Persistence and deterministic replay). The review UI shows the question, network version, supplied inputs, returned CPTs, network result, status, and retry action (docs/dev/system-design/MCP-design.md, Section: 9. Application API and physician transparency).

Related: [system design](system-design.md), [reasoning pipeline](../topics/reasoning-pipeline.md).

## Provenance

- docs/dev/system-design/MCP-design.md
