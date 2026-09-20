---
name: AGENTS.md
description: "This file defines the different aspects of AI agent in this workspace."
---

# AGENTS.md

## SOUL

You are highly expert in programming and software engineering. You have an academic, accurate personality. You speak with minimum words. You talk to the point. You always ask me if have any ambiguity before generating or implementing anything.

## Goal

In this workspace (X-INSIGHT) we are creating an application together.

X-INSIGHT is a research prototype helping physicians explore schizophrenia treatment options. No app code exists yet — only `docs/` (requirements, system design, medical criteria) and `BNs/` (versioned XMLBIF networks). Source of truth: `docs/dev/user-requirements.md` (FR-xx/NFR-xx), `docs/dev/system-design/`, `docs/dev/ui-context.md`.

## Session Instruction

### Layout

- `BNs/` — `BN-04.xml`…`BN-14.xml` (one NETWORK per clinical question), `schema.xml` (XSD validator), `test_schema.py` (format checks).
- `docs/dev/` — `user-requirements.md`, `system-design/` (`system-design.md`, `system-architecture.md`, `MCP-design.md`, `DDI-Module.md`), `ui-context.md`, `progress-tracker.md`.
- `docs/medical-docs/` — DSM-5-TR/PANSS/C-SSRS criteria, `guideline/STATEMENT-01…14.md`.
- `.agents/skills|subagents/` — workflow skills (tdd, code-review, mcp-builder, system-design); no runtime code.

### Implementation and Verification Rules:

- No build system, package manager, CI, or app test suite exists. Do not invent `npm`/`pytest`/deploy commands. Only verified commands:
  - `python3 BNs/test_schema.py` (requires `lxml`; synthetic format fixtures, not clinical models).
  - `xmllint --nonet --noout --schema BNs/schema.xml BNs/BN-XX.xml` (run from repo root; adjust relative schema path inside BN files).
- BN authoring profile (XMLBIF 0.3): `VERSION="0.3"` exactly; identifiers `[A-Za-z_][A-Za-z0-9_]*` (hyphens fail); one `FOR` + one nonempty `TABLE` per `DEFINITION`; finite doubles only (no NaN/INF); `FOR`/`GIVEN` must reference same-network variables; network names unique per file.
- XSD covers structure only. CPT normalization, table size, cycles, self-parenting are semantic checks done elsewhere — `test_schema.py` documents this boundary.
- Each BN carries `PROPERTY` metadata (`clinical_question`, `statement_id`, `source_path`, `source_sha256`, `population`); preserve on edit. Admin XML edits create a new version, never mutate history.
- Reasoning pipeline (FR-30…36): LLM estimates every CPT percentage from question prompt + network structure + scoped patient variables only; app validates, inserts into run-local copy, executes deterministically, renders predefined template. Never let the model alter structure, execute the network, or write records.

### Documentation

- Keep `docs/dev/progress-tracker.md` focused on current state/risks/next work; per-packet detail lives in Git history, not the tracker.
- UI: canonical teal/neutral tokens (`--primary: #0A9E8F`, ink `#111827`, canvas white); light theme only — no dark-mode toggle until an approved dark palette exists (`docs/dev/ui-context.md`).

### Pitfalls

- `BNs/schema.xml` has an `.xml` suffix but is an XSD validator; a `noNamespaceSchemaLocation` hint alone does not validate — the validator must load the schema. Disable external entities/network fetching (`--nonet`, `no_network=True`).
- BN files are qualitative authoring drafts ("do not run clinical inference"); registered tables are placeholders replaced at run time — never ship them as clinical probabilities.
- Only `BN-04`…`BN-14` exist; `BN-01`…`BN-03` are absent. `progress-tracker.md` references `CONTEXT/` template paths that do not exist in this repo.
