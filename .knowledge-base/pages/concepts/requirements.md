# Requirements

Source-of-truth requirements for the X-INSIGHT research prototype, plus tracker status. Synthesis of user-requirements.md, root AGENTS.md rules, and progress-tracker.md.

## Users and flow

One admin plus under ten physicians share a patient pool; physician flow is register, assess, review AI proposal, finalize and sign (docs/dev/user-requirements.md, Section: X-INSIGHT). Registration enforces letters-only names, sex M/F, age 18–99, unique ten-digit ID with leading zeros, and DSM-5-TR/PANSS/C-SSRS rules (docs/dev/user-requirements.md, Section: New patient registration). Medications use a bundled demo catalog without dose/route/frequency; unknown drugs are marked coverage-unavailable (docs/dev/user-requirements.md, Section: New patient registration).

## Reasoning pipeline (FR-30–36)

Seven registration plus six follow-up Bayesian networks process sequentially with fixed structures and question-scoped patient variables (docs/dev/user-requirements.md, Section: Reasoning pipeline). The LLM estimates CPT percentages via the internal MCP; the app executes deterministically and renders predefined templates with full transparency (docs/dev/user-requirements.md, Section: Reasoning pipeline). Failures retry two to three times then stop the affected question; saved data is retained for later retry (docs/dev/user-requirements.md, Section: Reasoning pipeline). BN authoring profile: XMLBIF 0.3 exactly, identifiers without hyphens, one FOR plus one nonempty TABLE per DEFINITION, finite doubles only (AGENTS.md, Section: Implementation and Verification Rules). Only verified commands are `python3 BNs/test_schema.py` and `xmllint` with schema validation; no npm/pytest/deploy commands exist (AGENTS.md, Section: Implementation and Verification Rules). BN files are qualitative authoring drafts; registered tables are runtime-replaced placeholders, never clinical probabilities (AGENTS.md, Section: Pitfalls).

## Tracker

The progress tracker records current implementation status, unresolved risks, and next concrete work, with per-packet detail in Git history rather than the tracker file (docs/dev/progress-tracker.md, Section: INSIGHT Progress Tracker). MODULE-000 template fields remain empty placeholders; each implementation package gets its own markdown tracker (docs/dev/progress-tracker.md, Section: Tracker Maintenance Rule).

Related: [reasoning pipeline](../topics/reasoning-pipeline.md), [system design](system-design.md), [system architecture](system-architecture.md).

## Provenance

- docs/dev/user-requirements.md
- AGENTS.md
- docs/dev/progress-tracker.md
