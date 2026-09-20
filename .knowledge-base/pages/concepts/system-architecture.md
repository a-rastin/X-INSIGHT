# System Architecture

Four-subsystem decomposition and ownership rules for X-INSIGHT.

## Subsystems

Four subsystems as logical boundaries, not separate deployments: S1 Case/Encounter Management, S2 Research Knowledge Management, S3 Decision Support, S4 Administration and Governance (docs/dev/system-design/system-architecture.md, Section: 3. Subsystem decomposition). The LLM estimates all CPT percentages per question; the app validates, inserts into a run-local network, infers deterministically, and renders a predefined template (docs/dev/system-design/system-architecture.md, Section: 2. System boundary).

## Ownership and signing

S1 owns the physician final plan; S3 owns the generated proposal; S2 owns networks, prompts, mappings, and templates; S4 owns access and audit (docs/dev/system-design/system-architecture.md, Section: 5. Collaboration and ownership rules). A physician cannot sign a manual plan after a generation failure; the current successful proposal plus review are required (docs/dev/system-design/system-architecture.md, Section: 6. End-to-end responsibility).

## Constraints

Page notes never influence algorithms; missing, conflicting, and not-assessed must stay distinguishable from negatives (docs/dev/system-design/system-architecture.md, Section: 7. System-wide constraints). The modular monolith with database queue and separate worker fits a small pool; microservices are revisited only on measured scale need (docs/dev/system-design/system-architecture.md, Section: 10. Decision summary and growth boundaries).

Related: [system design](system-design.md), [MCP design](mcp-design.md), [requirements](requirements.md).

## Provenance

- docs/dev/system-design/system-architecture.md
