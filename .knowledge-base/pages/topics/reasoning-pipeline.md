# Reasoning Pipeline

Synthesis — how X-INSIGHT turns a patient record into reviewed treatment proposals. Draws across requirements, architecture, design, MCP, and repo rules.

## Flow

Seven registration plus six follow-up Bayesian networks process sequentially with fixed structures and question-scoped patient variables (docs/dev/user-requirements.md, Section: Reasoning pipeline). The LLM estimates every CPT percentage from the question prompt, network structure, and scoped patient variables only; the app validates, inserts into a run-local copy, executes deterministically, and renders a predefined template (AGENTS.md, Section: Implementation and Verification Rules). The model never alters structure, executes the network, or writes records (AGENTS.md, Section: Implementation and Verification Rules).

## Contracts

The single MCP tool `get_question_patient_inputs` returns only represented variables (docs/dev/system-design/MCP-design.md, Section: 4. Patient-record tool contract). Questions run strictly sequentially with three total attempts; failure stops later questions and retains completed results (docs/dev/system-design/MCP-design.md, Section: 5. Sequential run protocol). CPT validation requires complete coverage, exact ordering, finite 0–100 percentages, and row sums of 100 within 0.000001 tolerance with no silent repair (docs/dev/system-design/MCP-design.md, Section: 6. CPT response and validation). Page notes are excluded from snapshots, MCP, and prompts via an allowlisted serializer (docs/dev/system-design/system-design.md, Section: 4. Patient and encounter workflows).

## Ownership and replay

S1 owns the physician final plan; S3 owns the generated proposal; S2 owns networks, prompts, mappings, templates; S4 owns access and audit (docs/dev/system-design/system-architecture.md, Section: 5. Collaboration and ownership rules). Signing requires a successful current proposal and review; manual-plan signing after failure is rejected (docs/dev/system-design/system-design.md, Section: 7. Bayesian model registry and execution). Deterministic replay uses the stored snapshot, effective CPT artifact, evidence, and pinned engine without new LLM calls (docs/dev/system-design/MCP-design.md, Section: 8. Persistence and deterministic replay).

Related: [requirements](../concepts/requirements.md), [MCP design](../concepts/mcp-design.md), [system design](../concepts/system-design.md), [system architecture](../concepts/system-architecture.md).

## Provenance

- AGENTS.md
- docs/dev/user-requirements.md
- docs/dev/system-design/MCP-design.md
- docs/dev/system-design/system-design.md
- docs/dev/system-design/system-architecture.md
