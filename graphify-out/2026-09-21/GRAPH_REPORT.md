# Graph Report - X-INSIGHT  (2026-09-21)

## Corpus Check
- 121 files · ~1,191,864 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 26 file(s) not represented in the graph (top: .xml 13, (none) 8, .example 1)

## Summary
- 1709 nodes · 2316 edges · 146 communities (114 shown, 32 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 28 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7916eda4`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- STATEMENT 4: Antipsychotic Medications
- conftest.py
- MCP Server Evaluation Guide
- X-INSIGHT — MCP Server Design
- Node/TypeScript MCP Server Implementation Guide
- X-INSIGHT implementation plan
- App.tsx
- patients.py
- X-INSIGHT — System Design
- Python MCP Server Implementation Guide
- test_drafts.py
- routes.py
- accounts.py
- DDI-Module.md
- Dev Backend
- Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement
- What You Must Do When Invoked
- Codebase Design
- store.py
- 6. Model machinery and content packages
- Appendix C.
- Physical examination and item scoring
- UI Context
- create_patient
- main
- test_contracts.py
- Appendix D. Strength of Evidence
- AGENTS.md
- Barnes Akathisia Rating Scale (BARS)
- package.json
- MCPConnection
- Project Knowledge Base
- MCP Server Best Practices
- evaluation.py
- evaluate_single_task
- Test-Driven Development
- connections.py
- Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement
- STATEMENT 9: Clozapine in Aggressive Behavior
- STATEMENT 14: VMAT2 Medications for Tardive Dyskinesia
- STATEMENT 6: Continuing the Same Medications
- STATEMENT 8: Clozapine in Suicide Risk
- STATEMENT 10: Long-Acting Injectable Antipsychotic Medications
- STATEMENT 11: Anticholinergic Medications for Acute Dystonia
- STATEMENT 12: Treatments for Parkinsonism
- STATEMENT 13: Treatments for Akathisia
- 4. Records and assessments
- 7. Snapshots, MCP, provider, and reasoning
- Columbia-Suicide Severity Rating Scale (C-SSRS)
- Glossary-of-Terms.md
- Guideline Development Process
- STATEMENT 3: Evidence-Based Treatment Planning
- STATEMENT 5: Continuing Medications
- Required criteria
- accessibility.spec.ts
- compilerOptions
- Document Types
- graphify reference: extra exports and benchmark
- 🚀 High-Level Workflow
- Ponytail
- Framework
- test_identity.py
- Positive and Negative Syndrome Scale (PANSS)
- Process
- get_engine
- STATEMENT 4: Antipsychotic Medications
- identity.spec.ts
- Code Documentation Assistant
- Frontend Design
- 5. DDI ingestion, review, and checking
- Foundation and identity
- STATEMENT 7: Clozapine in Treatment-Resistant Schizophrenia
- ready
- /agent-browser
- /architecture
- graphify reference: query, path, explain
- mcp-builder/SKILL.md
- MCPConnectionStdio
- 📚 Documentation Library
- PatientCreate
- 8. Final plans, shared records, and reporting
- 9. Recovery and Linux operation
- STATEMENT 7: Clozapine in Treatment-Resistant Schizophrenia
- Commit
- .call_tool
- Phase 1: Deep Research and Planning
- transaction
- X-INSIGHT coding sessions
- Medication-Induced Acute Dystonia
- STATEMENT 14: VMAT2 Medications for Tardive Dyskinesia
- Guideline Statement Summary
- Tardive Dyskinesia
- Quality Checklist
- Dev Manager
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- Advanced FastMCP Features
- Workflows
- .valid_username
- STATEMENT 21: Self-Management Skills and Recovery-Focused
- Tools
- Dev Test
- Tools
- Tools
- Dev Testing
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- STATEMENT 8: Clozapine in Suicide Risk
- STATEMENT 9: Clozapine in Aggressive Behavior
- STATEMENT 16: Cognitive-Behavioral Therapy
- STATEMENT 22: Cognitive Remediation
- STATEMENT 15: Coordinated Specialty Care Programs
- STATEMENT 20: Family Interventions
- STATEMENT 17: Psychoeducation
- STATEMENT 23: Social Skills Training
- STATEMENT 18: Supported Employment Services
- STATEMENT 24: Supportive Psychotherapy
- STATEMENT 6: Continuing the Same Medications
- STATEMENT 5: Continuing Medications
- STATEMENT 10: Long-Acting Injectable Antipsychotic
- extraction-spec.md
- progress-tracker.md
- acronyms_abbreviations.md
- Implementation
- Table 3
- Table 4
- Table 5
- Table 6
- Table 7
- Table 8
- Table 9
- x-insight
- Quick Reference
- ReadinessError
- Code Best Practices
- Tool Implementation
- health
- Any

## God Nodes (most connected - your core abstractions)
1. `STATEMENT 4: Antipsychotic Medications` - 63 edges
2. `Appendix C.` - 27 edges
3. `physician()` - 23 edges
4. `_require_session()` - 23 edges
5. `transaction()` - 22 edges
6. `Node/TypeScript MCP Server Implementation Guide` - 21 edges
7. `6. Model machinery and content packages` - 21 edges
8. `login()` - 20 edges
9. `start_command()` - 18 edges
10. `Python MCP Server Implementation Guide` - 18 edges

## Surprising Connections (you probably didn't know these)
- `index.md` --references--> `ready()`  [INFERRED]
  .agents/skills/knowledge-base/SKILL.md → backend/src/x_insight/app.py
- `5. Persistence and invariants` --references--> `Patient`  [INFERRED]
  docs/dev/system-design/system-design.md → web/src/app/api.ts
- `5. Persistence and invariants` --references--> `Encounter`  [INFERRED]
  docs/dev/system-design/system-design.md → web/src/app/api.ts
- `test_no_second_admin_can_be_provisioned()` --calls--> `ensure_admin_seeded()`  [EXTRACTED]
  backend/tests/http/test_identity.py → backend/src/x_insight/identity/store.py
- `main()` --calls--> `create_connection()`  [EXTRACTED]
  .agents/skills/mcp-builder/scripts/evaluation.py → .agents/skills/mcp-builder/scripts/connections.py

## Import Cycles
- None detected.

## Communities (146 total, 32 thin omitted)

### Community 0 - "STATEMENT 4: Antipsychotic Medications"
Cohesion: 0.04
Nodes (55): Acute Dystonia, Akathisia, Allergic and Dermatological Side Effects, Anticholinergic Effects, APA Practice Guideline for the Treatment of Patients With Schizophrenia, Available Drug Formulations, Balancing of Benefits and Harms, Balancing of Benefits and Harms (+47 more)

### Community 1 - "conftest.py"
Cohesion: 0.07
Nodes (16): alembic, alembic_config, _database_url(), Run migrations in 'offline' mode. This configures the context with just a URL…, Run migrations in 'online' mode. In this scenario we need to create an Engine…, run_migrations_offline(), run_migrations_online(), _isolate_audit_rows() (+8 more)

### Community 2 - "MCP Server Evaluation Guide"
Cohesion: 0.04
Nodes (44): 1. Local STDIO Server, 2. Server-Sent Events (SSE), 3. HTTP (Streamable HTTP), Answer Guidelines, Command-Line Options, Complete Example Workflow, Complexity and Depth, Connection Errors (+36 more)

### Community 3 - "X-INSIGHT — MCP Server Design"
Cohesion: 0.05
Nodes (38): 10. Security and audit boundaries, 11. Capacity, trade-offs and growth, 12. Verification criteria, 1. Scope and requirements, 2. Component boundaries and deployment, 3. Snapshot and question scope, 4. Patient-record tool contract, 5. Sequential run protocol (+30 more)

### Community 4 - "Node/TypeScript MCP Server Implementation Guide"
Cohesion: 0.05
Nodes (41): Advanced Features (where applicable), Advanced MCP Features, Async/Await Best Practices, Building and Running, Character Limits and Truncation, Code Best Practices, Code Composability and Reusability, Code Quality (+33 more)

### Community 5 - "X-INSIGHT implementation plan"
Cohesion: 0.05
Nodes (40): 10.1 Exports and audit, 10.2 Backup creation, 10.3 Restore workflow, 10. Exports, audit, and recovery, 11. Security, operations, capacity, and trade-offs, 12.1 Approved test seams, 12.2 Command contract, 12.3 Mandatory release evidence (+32 more)

### Community 6 - "App.tsx"
Cohesion: 0.06
Nodes (53): 5. Persistence and invariants, react, react-dom, changeOwnPassword(), createPatient(), createPhysician(), csrfToken(), discardEncounter() (+45 more)

### Community 7 - "patients.py"
Cohesion: 0.08
Nodes (34): Attach the standard contract handlers to another app (tests reuse)., Propagate/generate request IDs, enforce body size, echo ID on errors., register_exception_handlers(), RequestContextMiddleware, Author-owned draft persistence (S07 slice 1: GET/PATCH with revisions)., Patient registration (S06 slice 1: create patient + registration draft)., new_request_id(), parse_idempotency_key() (+26 more)

### Community 8 - "X-INSIGHT — System Design"
Cohesion: 0.05
Nodes (39): 10. External API contracts, 11.1 Prototype security boundary, 11.2 Audit, 11.3 CSV and printable HTML, 11.4 Backup and restore, 11. Security, audit, exports, and recovery, 12. Deployment, operations, and growth, 13. Architecture decision records (+31 more)

### Community 9 - "Python MCP Server Implementation Guide"
Cohesion: 0.15
Nodes (13): Async/Await Best Practices, Complete Example, Error Handling, MCP Python SDK and FastMCP, Overview, Pagination Implementation, Pydantic v2 Key Features, Python MCP Server Implementation Guide (+5 more)

### Community 10 - "test_drafts.py"
Cohesion: 0.07
Nodes (61): physician(), now(), Injectable clock for identity (throttling windows; sessions have no timeout).…, Return current clock seconds (monkeypatchable in tests)., Override the clock (tests only)., Restore the production clock., reset_now_fn(), set_now_fn() (+53 more)

### Community 11 - "routes.py"
Cohesion: 0.10
Nodes (46): error_body(), Build the standard error envelope (plan section 4.3)., Compare an exact password against a stored hash; False on malformed., verify_password(), change_password(), _check_csrf(), _client_key(), _generic_login_denied() (+38 more)

### Community 12 - "accounts.py"
Cohesion: 0.19
Nodes (35): parse_if_match(), Return the ``If-Match`` revision tag, or None when absent., account_response(), AccountCreate, AccountEdit, change_active(), check_revision(), create_physician() (+27 more)

### Community 13 - "DDI-Module.md"
Cohesion: 0.06
Nodes (31): 10. Canonical pair keys, 11. Do not force one record per pair, 12. Runtime checking algorithm, 13. Recommended API, 14. Storage choice, 15. What should happen when both monographs exist?, 16. Validation system, 17. Preserve the original interaction description (+23 more)

### Community 14 - "Dev Backend"
Cohesion: 0.07
Nodes (26): 10. Anti-Patterns (Immediate Rejection), 12. Operator Validation Checklist, 1. Backend Feasibility & Risk Index (BFRI), 1. Layered Architecture Is Mandatory, 2. Core Architecture Doctrine, 2. Routes Only Route, 3. Controllers Coordinate, Services Decide, 3. Directory Structure (Canonical) (+18 more)

### Community 15 - "Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement"
Cohesion: 0.07
Nodes (26): Assessments related to other specific side effects of treatment, Assessments related to other specific side effects of treatment (continued), Assessments to monitor physical status and detect concomitant physical conditions, Balancing of Benefits and Harms, Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement, Benefits, Differences of Opinion Among Writing Group Members, Examination, including mental status examination (+18 more)

### Community 16 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native AGENTS.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 17 - "Codebase Design"
Cohesion: 0.09
Nodes (21): 1. In-process, 2. Local-substitutable, 3. Remote but owned (Ports & Adapters), 4. True external (Mock), Deepening, Dependency categories, Seam discipline, Testing strategy: replace, don't layer (+13 more)

### Community 18 - "store.py"
Cohesion: 0.27
Nodes (8): hash_password(), Standard password hashing (stdlib PBKDF2-HMAC-SHA256). No new dependency:…, Hash an exact (untrimmed) password; caller rejects empty input., Identity persistence: users, sessions, singleton admin seed. Usernames are…, base64, hashlib, hmac, secrets

### Community 19 - "6. Model machinery and content packages"
Cohesion: 0.10
Nodes (21): 6. Model machinery and content packages, Common contract for S26–S38, S21 — Safely import and inspect XMLBIF drafts, S22 — Enforce model semantics and admission limits, S23 — Validate every CPT and run reproducible exact inference, S24 — Build model version administration and read-only graph, S25 — Define the reusable question-package contract and review harness, S26 — Draft hospitalization question (+13 more)

### Community 20 - "Appendix C."
Cohesion: 0.10
Nodes (19): Appendix C., Assessment and Determination of Treatment Plan, Grading of the Overall Supporting Body of Research Evidence for Anticholinergic Medications for Acute Dystonia, Grading of the Overall Supporting Body of Research Evidence for Assessment of Possible Schizophrenia, Grading of the Overall Supporting Body of Research Evidence for Efficacy of Assertive Community Treatment, Grading of the Overall Supporting Body of Research Evidence for Evidence-Based Treatment Planning, Grading of the Overall Supporting Body of Research Evidence for Treatments for Akathisia, Grading of the Overall Supporting Body of Research Evidence for Treatments for Parkinsonism (+11 more)

### Community 21 - "Physical examination and item scoring"
Cohesion: 0.10
Nodes (19): 10. Salivation, 1. Gait, 2. Arm dropping, 3. Shoulder shaking, 4. Elbow rigidity, 5. Wrist rigidity (fixation of position), 6. Leg pendulousness, 7. Head dropping (+11 more)

### Community 22 - "UI Context"
Cohesion: 0.12
Nodes (16): Border Radius, Canonical Color System, Color roles, Color usage rules, Current Design Character, Motion, Product Identity and Branding, Shadows (+8 more)

### Community 23 - "create_patient"
Cohesion: 0.14
Nodes (18): create_patient(), _encounter_payload(), list_patients(), _patient_payload(), Any, ge, get, JSONResponse (+10 more)

### Community 24 - "main"
Cohesion: 0.14
Nodes (11): main(), check(), cross_network_reference(), remove_at(), edit(), two_networks(), Run with python3 test_schema.py; requires lxml (already installed here).…, copy (+3 more)

### Community 25 - "test_contracts.py"
Cohesion: 0.27
Nodes (10): _client(), TestClient, test_client_request_id_is_propagated(), test_health_does_not_require_database(), test_oversized_body_returns_413_envelope(), test_ready_reports_incompatible_when_schema_missing(), test_ready_reports_ready_when_database_migrated(), test_ready_reports_unavailable_when_database_unreachable() (+2 more)

### Community 26 - "Appendix D. Strength of Evidence"
Cohesion: 0.13
Nodes (14): Appendix D. Strength of Evidence, TABLE D–10. Supported employment, TABLE D–11. Supportive therapy, TABLE D–12. Early interventions for patients with first-episode psychosis, TABLE D–13. Co-occurring substance use and schizophrenia, TABLE D–1. Pharmacological treatment, TABLE D–2. Assertive community treatment (ACT), TABLE D–3. Cognitive-behavioral therapy (CBT) (+6 more)

### Community 27 - "AGENTS.md"
Cohesion: 0.14
Nodes (12): 1.3 Paths and command conventions, 1.4 Required handoff record, 1. Source order, 2. Owner-confirmed decisions, 2. Sequence and phase gates, 3. Repository audit, 4. Content review and completion gates, Authority, decisions, and starting condition (+4 more)

### Community 28 - "Barnes Akathisia Rating Scale (BARS)"
Cohesion: 0.14
Nodes (13): Administration and physical examination, Assessment tool and documentation, Barnes Akathisia Rating Scale (BARS), Clinical assessment and exclusions, Diagnostic features, Item 1: Objective restlessness (0–3), Item 2: Subjective awareness of restlessness (0–3), Item 3: Distress related to restlessness (0–3) (+5 more)

### Community 29 - "package.json"
Cohesion: 0.08
Nodes (24): @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react, dependencies, react, react-dom (+16 more)

### Community 30 - "MCPConnection"
Cohesion: 0.17
Nodes (8): ABC, MCPConnection, MCPConnectionHTTP, MCP connection using Streamable HTTP., Base class for MCP server connections., Create the connection context based on connection type., Initialize MCP server connection., Clean up MCP server connection resources.

### Community 31 - "Project Knowledge Base"
Cohesion: 0.14
Nodes (13): AGENTS.md, Completion checks, details.md, Grounding, Ignore rules, index.md, Layout, Page conventions (+5 more)

### Community 32 - "MCP Server Best Practices"
Cohesion: 0.07
Nodes (28): Authentication and Authorization, DNS Rebinding Protection, Documentation Requirements, Error Handling, Error Handling, Input Validation, JSON Format (`response_format="json"`), Markdown Format (`response_format="markdown"`, typically default) (+20 more)

### Community 33 - "evaluation.py"
Cohesion: 0.18
Nodes (12): main(), parse_env_vars(), parse_headers(), MCP Server Evaluation Harness This script evaluates MCP servers by running test…, Parse header strings in format 'Key: Value' into a dictionary., Parse environment variable strings in format 'KEY=VALUE' into a dictionary., argparse, asyncio (+4 more)

### Community 34 - "evaluate_single_task"
Cohesion: 0.22
Nodes (13): agent_loop(), evaluate_single_task(), extract_xml_content(), parse_evaluation_file(), Any, Evaluate a single QA pair with the given tools., Run evaluation with MCP server tools., Parse XML evaluation file with qa_pair elements. (+5 more)

### Community 35 - "Test-Driven Development"
Cohesion: 0.15
Nodes (10): Designing for Mockability, When to Mock, Anti-patterns, Rules of the loop, Seams: where tests go, Test-Driven Development, What a good test is, Bad Tests (+2 more)

### Community 36 - "connections.py"
Cohesion: 0.18
Nodes (10): create_connection(), MCPConnectionSSE, Lightweight connection handling for MCP servers., Factory function to create the appropriate MCP connection. Args: transport:…, MCP connection using Server-Sent Events., contextlib, mcp, mcp_client_sse (+2 more)

### Community 37 - "Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement"
Cohesion: 0.17
Nodes (11): Balancing of Benefits and Harms, Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement, Benefits, Differences of Opinion Among Writing Group Members, Guideline Statements and Implementation — Assessment and Determination of Treatment Plan, Harms, Implementation, Patient Preferences (+3 more)

### Community 38 - "STATEMENT 9: Clozapine in Aggressive Behavior"
Cohesion: 0.17
Nodes (11): Balancing of Benefits and Harms, Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement, Benefits, Differences of Opinion Among Writing Group Members, Harms, Implementation, Patient Preferences, Quality Measurement Considerations (+3 more)

### Community 39 - "STATEMENT 14: VMAT2 Medications for Tardive Dyskinesia"
Cohesion: 0.17
Nodes (11): Balancing of Benefits and Harms, Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement, Benefits, Differences of Opinion Among Writing Group Members, Harms, Implementation, Patient Preferences, Quality Measurement Considerations (+3 more)

### Community 40 - "STATEMENT 6: Continuing the Same Medications"
Cohesion: 0.18
Nodes (10): Balancing of Benefits and Harms, Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement, Benefits, Differences of Opinion Among Writing Group Members, Harms, Implementation, Patient Preferences, Quality Measurement Considerations (+2 more)

### Community 41 - "STATEMENT 8: Clozapine in Suicide Risk"
Cohesion: 0.18
Nodes (10): Balancing of Benefits and Harms, Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement, Benefits, Differences of Opinion Among Writing Group Members, Harms, Implementation, Patient Preferences, Quality Measurement Considerations (+2 more)

### Community 42 - "STATEMENT 10: Long-Acting Injectable Antipsychotic Medications"
Cohesion: 0.18
Nodes (10): Balancing of Benefits and Harms, Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement, Benefits, Differences of Opinion Among Writing Group Members, Harms, Implementation, Patient Preferences, Quality Measurement Considerations (+2 more)

### Community 43 - "STATEMENT 11: Anticholinergic Medications for Acute Dystonia"
Cohesion: 0.18
Nodes (10): Balancing of Benefits and Harms, Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement, Benefits, Differences of Opinion Among Writing Group Members, Harms, Implementation, Patient Preferences, Quality Measurement Considerations (+2 more)

### Community 44 - "STATEMENT 12: Treatments for Parkinsonism"
Cohesion: 0.18
Nodes (11): Balancing of Benefits and Harms, Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement, Benefits, Differences of Opinion Among Writing Group Members, Harms, Implementation, Patient Preferences, Quality Measurement Considerations (+3 more)

### Community 45 - "STATEMENT 13: Treatments for Akathisia"
Cohesion: 0.18
Nodes (10): Balancing of Benefits and Harms, Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement, Benefits, Differences of Opinion Among Writing Group Members, Harms, Implementation, Patient Preferences, Quality Measurement Considerations (+2 more)

### Community 46 - "4. Records and assessments"
Cohesion: 0.20
Nodes (10): 4. Records and assessments, S06 — Register and find a patient, S07 — Persist, resume, and discard author-owned drafts, S08 — Draft assessment definitions and implement the evaluation interface, S09 — Implement diagnosis, threshold warning, and bypass, S10 — Implement PANSS without implicit minimum answers, S11 — Implement C-SSRS form and distinct results, S12 — Draft and implement structured history and adverse effects (+2 more)

### Community 47 - "7. Snapshots, MCP, provider, and reasoning"
Cohesion: 0.20
Nodes (10): 7. Snapshots, MCP, provider, and reasoning, S40 — Freeze analysis snapshots and project one question's inputs, S41 — Implement the real private MCP transport and context grants, S42 — Store and test provider settings securely, S43 — Implement bounded provider CPT estimation and tool bridging, S44 — Implement durable leased jobs and global admission, S45 — Run one full synthetic clinical question end to end, S46 — Execute ordered workflows and assemble a complete proposal (+2 more)

### Community 48 - "Columbia-Suicide Severity Rating Scale (C-SSRS)"
Cohesion: 0.20
Nodes (9): 1. Suicidal ideation severity, 2. Intensity of ideation, 3. Suicidal behavior, Columbia-Suicide Severity Rating Scale (C-SSRS), Ideation severity, Intensity and behavior, Interpretation, Questions (+1 more)

### Community 49 - "Glossary-of-Terms.md"
Cohesion: 0.20
Nodes (6): Bayesian-network terminology (BN-04–BN-14), Clinical terms and distinctions, Glossary of Terms, Identifier migration, Naming and state conventions, Outcome migration

### Community 50 - "Guideline Development Process"
Cohesion: 0.20
Nodes (9): External Review, Funding and Approval, Guideline Development Process, Guideline Writing Group Composition, Management of Potential Conflicts of Interest, Rating the Strength of Guideline Statements, Rating the Strength of Supporting Research Evidence, Systematic Review Methodology (+1 more)

### Community 51 - "STATEMENT 3: Evidence-Based Treatment Planning"
Cohesion: 0.20
Nodes (9): Aims of Treatment Planning, Balancing of Benefits and Harms, Benefits, Differences of Opinion Among Writing Group Members, Harms, Implementation, Quality Measurement Considerations, Review of Available Guidelines From Other Organizations (+1 more)

### Community 52 - "STATEMENT 5: Continuing Medications"
Cohesion: 0.20
Nodes (10): Balancing of Benefits and Harms, Balancing of Potential Benefits and Harms in Rating the Strength of the Guideline Statement, Benefits, Differences of Opinion Among Writing Group Members, Harms, Implementation, Patient Preferences, Quality Measurement Considerations (+2 more)

### Community 53 - "Required criteria"
Cohesion: 0.20
Nodes (9): A. Characteristic symptoms, B. Functional decline, C. Duration, D. Mood-disorder and schizoaffective exclusion, Diagnostic overview, E. Substance, medication, and medical exclusion, F. Autism-spectrum and childhood communication disorders, Required criteria (+1 more)

### Community 56 - "compilerOptions"
Cohesion: 0.20
Nodes (9): compilerOptions, jsx, module, moduleResolution, noEmit, skipLibCheck, strict, target (+1 more)

### Community 57 - "Document Types"
Cohesion: 0.22
Nodes (8): API Documentation, Architecture Doc, Document Types, Onboarding Guide, Principles, README, Runbook, Technical Documentation

### Community 58 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 59 - "🚀 High-Level Workflow"
Cohesion: 0.14
Nodes (14): 2.1 Set Up Project Structure, 2.2 Implement Core Infrastructure, 2.3 Implement Tools, 3.1 Code Quality, 3.2 Build and Test, 4.1 Understand Evaluation Purpose, 4.2 Create 10 Evaluation Questions, 4.3 Evaluation Requirements (+6 more)

### Community 60 - "Ponytail"
Cohesion: 0.22
Nodes (8): Boundaries, Intensity, Output, Persistence, Ponytail, Rules, The ladder, When NOT to be lazy

### Community 61 - "Framework"
Cohesion: 0.22
Nodes (8): 1. Requirements Gathering, 2. High-Level Design, 3. Deep Dive, 4. Scale and Reliability, 5. Trade-off Analysis, Framework, Output, System Design

### Community 62 - "test_identity.py"
Cohesion: 0.12
Nodes (31): Clear all throttle state (tests only)., reset_all(), clean_drafts(), fixture, _audit_rows(), _clean_identity(), _client(), _login() (+23 more)

### Community 63 - "Positive and Negative Syndrome Scale (PANSS)"
Cohesion: 0.22
Nodes (8): Approximate total-score anchors, General psychopathology (G), Interpretation, Negative symptoms (N), Positive and Negative Syndrome Scale (PANSS), Positive symptoms (P), Questions, Scoring system

### Community 64 - "Process"
Cohesion: 0.25
Nodes (7): 1. Pin the fixed point, 2. Identify the spec source, 3. Identify the standards sources, 4. Spawn both sub-agents in parallel, 5. Aggregate, Process, Why two axes

### Community 65 - "get_engine"
Cohesion: 0.29
Nodes (8): check_readiness(), database_url_for(), get_engine(), Return the configured URL for a logical role., Return a cached engine for the given URL (or the app role)., Raise ReadinessError(UNAVAILABLE|INCOMPATIBLE_SCHEMA) when not ready., _sqlalchemy_url(), Engine

### Community 66 - "STATEMENT 4: Antipsychotic Medications"
Cohesion: 0.25
Nodes (8): Antipsychotic Medications in First-Episode Schizophrenia, Augmentation Pharmacotherapy, Grading of the Overall Supporting Body of Research Evidence for Efficacy of Antipsychotic Medications, Grading of the Overall Supporting Body of Research Evidence for Harms of Antipsychotic Medications, High Doses of Antipsychotic Medication, STATEMENT 4: Antipsychotic Medications, TABLE C–1. Results of meta-analysis on placebo-controlled trials of antipsychotic treatment, Treatment Approaches to Partial Response or Nonresponse

### Community 68 - "Code Documentation Assistant"
Cohesion: 0.29
Nodes (6): Code Documentation Assistant, Hard Rule, Output Template, Red Flags and Rationalizations, Validation, Workflow

### Community 69 - "Frontend Design"
Cohesion: 0.29
Nodes (6): Design principles, Frontend Design, Ground your designs in the subject matter, More on writing in design, Process: plan, review against the brief, build, critique, Restraint and self-critique

### Community 70 - "5. DDI ingestion, review, and checking"
Cohesion: 0.29
Nodes (7): 5. DDI ingestion, review, and checking, S15 — Parse one source through the ingestion interface, S16 — Extend the parser across real source formats, S17 — Resolve controlled medication concepts and aliases, S18 — Build, review, and publish an immutable DDI release, S19 — Implement deterministic coverage-aware DDI checking, S20 — Integrate medications and DDI into encounter history

### Community 71 - "Foundation and identity"
Cohesion: 0.29
Nodes (7): Foundation and identity, S00 — Establish the execution and content review ledger, S01 — Bootstrap a reproducible development loop, S02 — Establish real persistence and request contracts, S03 — Implement login, sessions, and own credentials, S04 — Implement physician account administration, S05 — Build role navigation and both themes

### Community 72 - "STATEMENT 7: Clozapine in Treatment-Resistant Schizophrenia"
Cohesion: 0.29
Nodes (7): Balancing of Benefits and Harms, Differences of Opinion Among Writing Group Members, Identification of Treatment-Resistant Schizophrenia, Implementation, Quality Measurement Considerations, Review of Available Guidelines From Other Organizations, STATEMENT 7: Clozapine in Treatment-Resistant Schizophrenia

### Community 73 - "ready"
Cohesion: 0.21
Nodes (15): _http_exception_handler(), Exception, JSONResponse, Request, Standard envelope for HTTP errors (shared with handler registration)., Standard 422 envelope with field errors., Safe 500 envelope: no traceback, no secrets., Readiness: database reachable and schema at the expected revision. (+7 more)

### Community 74 - "/agent-browser"
Cohesion: 0.33
Nodes (5): /agent-browser, Observability Dashboard, Specialized skills, Start here, Why agent-browser

### Community 75 - "/architecture"
Cohesion: 0.33
Nodes (5): /architecture, Modes, Output — ADR Format, Tips, Usage

### Community 76 - "graphify reference: query, path, explain"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 80 - "📚 Documentation Library"
Cohesion: 0.33
Nodes (6): Core MCP Documentation (Load First), 📚 Documentation Library, Evaluation Guide (Load During Phase 4), Language-Specific Implementation Guides (Load During Phase 2), Reference Files, SDK Documentation (Load During Phase 1/2)

### Community 81 - "PatientCreate"
Cohesion: 0.50
Nodes (3): PatientCreate, BaseModel, field_validator

### Community 82 - "8. Final plans, shared records, and reporting"
Cohesion: 0.33
Nodes (6): 8. Final plans, shared records, and reporting, S49 — Implement atomic plan signing and immutable snapshots, S50 — Build final-plan editing, comparison, sign, and addenda UI, S51 — Close archive, deactivation, and multi-user race cases, S52 — Complete append-only audit and administration views, S53 — Export lists and printable longitudinal patient reports

### Community 83 - "9. Recovery and Linux operation"
Cohesion: 0.33
Nodes (6): 9. Recovery and Linux operation, S54 — Produce consistent full backups, S55 — Validate and stage restores without touching live state, S56 — Commit restore with maintenance, fencing, and rollback, S57 — Package one-host Linux deployment and upgrades, S58 — Measure capacity and expose useful operational status

### Community 84 - "STATEMENT 7: Clozapine in Treatment-Resistant Schizophrenia"
Cohesion: 0.33
Nodes (6): Electroconvulsive Therapy, Grading of the Overall Supporting Body of Research Evidence for Efficacy of Clozapine in Treatment-Resistant Schizophrenia, Grading of the Overall Supporting Body of Research Evidence for Harms of Clozapine, Other Interventions for Treatment-Resistant Schizophrenia, STATEMENT 7: Clozapine in Treatment-Resistant Schizophrenia, Use of Antipsychotic Medications Other Than Clozapine

### Community 85 - "Commit"
Cohesion: 0.40
Nodes (4): Commit, Commit Contract, Guardrails, Message Style

### Community 88 - ".call_tool"
Cohesion: 0.40
Nodes (3): Any, Retrieve available tools from the MCP server., Call a tool on the MCP server with provided arguments.

### Community 89 - "Phase 1: Deep Research and Planning"
Cohesion: 0.40
Nodes (5): 1.1 Understand Modern MCP Design, 1.2 Study MCP Protocol Documentation, 1.3 Study Framework Documentation, 1.4 Plan Your Implementation, Phase 1: Deep Research and Planning

### Community 91 - "transaction"
Cohesion: 0.13
Nodes (24): discard_encounter(), DiscardRequest, DraftPatch, _get_encounter(), list_encounters(), patch_encounter(), _payload(), Any (+16 more)

### Community 92 - "X-INSIGHT coding sessions"
Cohesion: 0.22
Nodes (8): 10. Integrated release verification, 11. Requirement-to-session acceptance index, 12. Ready-to-paste session instruction, S59 — Prove both workflows using reviewed released content, S60 — Run cross-user, failure, and security acceptance, S61 — Verify desktop usability, both themes, and complete administration, S62 — Complete the release rehearsal and agent handoff, X-INSIGHT coding sessions

### Community 93 - "Medication-Induced Acute Dystonia"
Cohesion: 0.40
Nodes (4): Clinical assessment and exclusions, Diagnostic features, Medication-Induced Acute Dystonia, Urgency and documentation

### Community 94 - "STATEMENT 14: VMAT2 Medications for Tardive Dyskinesia"
Cohesion: 0.40
Nodes (5): Grading of the Overall Supporting Body of Research Evidence for Efficacy of VMAT2 Inhibitors, Grading of the Overall Supporting Body of Research Evidence for Harms of VMAT2 Inhibitors, Psychosocial Interventions, STATEMENT 14: VMAT2 Medications for Tardive Dyskinesia, TABLE C–2. Other systematic reviews of treatments for tardive dyskinesia

### Community 95 - "Guideline Statement Summary"
Cohesion: 0.40
Nodes (4): Assessment and Determination of Treatment Plan, Guideline Statement Summary, Pharmacotherapy, Psychosocial Interventions

### Community 96 - "Tardive Dyskinesia"
Cohesion: 0.40
Nodes (4): Diagnostic features, Differential diagnosis, Research criteria and assessment, Tardive Dyskinesia

### Community 97 - "Quality Checklist"
Cohesion: 0.29
Nodes (7): Advanced Features (where applicable), Code Quality, Implementation Quality, Quality Checklist, Strategic Design, Testing, Tool Configuration

### Community 98 - "Dev Manager"
Cohesion: 0.50
Nodes (3): Dev Manager, Skills, Tools

### Community 99 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 100 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 101 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 102 - "Advanced FastMCP Features"
Cohesion: 0.33
Nodes (6): Advanced FastMCP Features, Context Parameter Injection, Lifespan Management, Resource Registration, Structured Output Types, Transport Options

### Community 103 - "Workflows"
Cohesion: 0.40
Nodes (5): Ingest, Init, Query, Update and maintenance, Workflows

### Community 105 - "STATEMENT 21: Self-Management Skills and Recovery-Focused"
Cohesion: 0.50
Nodes (4): Grading of the Overall Supporting Body of Research Evidence for Efficacy of Self-Management Skills and Recovery-Focused Interventions, Grading of the Overall Supporting Body of Research Evidence for Harms of Self-Management Skills and Recovery-Focused Interventions, Interventions, STATEMENT 21: Self-Management Skills and Recovery-Focused

### Community 114 - "STATEMENT 8: Clozapine in Suicide Risk"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for Efficacy of Clozapine in Individuals With Substantial Risk Factors, Grading of the Overall Supporting Body of Research Evidence for Harms of Clozapine in Individuals With Substantial Risk Factors, STATEMENT 8: Clozapine in Suicide Risk

### Community 115 - "STATEMENT 9: Clozapine in Aggressive Behavior"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for Efficacy of Clozapine in Individuals With Substantial Risk Factors, Grading of the Overall Supporting Body of Research Evidence for Harms of Clozapine in Individuals With Substantial Risk Factors, STATEMENT 9: Clozapine in Aggressive Behavior

### Community 116 - "STATEMENT 16: Cognitive-Behavioral Therapy"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for Efficacy of Cognitive-Behavioral Therapy for Psychosis, Grading of the Overall Supporting Body of Research Evidence for Harms of Cognitive-Behavioral Therapy for Psychosis, STATEMENT 16: Cognitive-Behavioral Therapy

### Community 117 - "STATEMENT 22: Cognitive Remediation"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for Efficacy of Cognitive Remediation, Grading of the Overall Supporting Body of Research Evidence for Harms of Cognitive Remediation, STATEMENT 22: Cognitive Remediation

### Community 118 - "STATEMENT 15: Coordinated Specialty Care Programs"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for Efficacy of Coordinated Specialty Care Programs, Grading of the Overall Supporting Body of Research Evidence for Harms of Coordinated Specialty Care Programs, STATEMENT 15: Coordinated Specialty Care Programs

### Community 119 - "STATEMENT 20: Family Interventions"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for Efficacy of Family Interventions, Grading of the Overall Supporting Body of Research Evidence for Harms of Family Interventions, STATEMENT 20: Family Interventions

### Community 120 - "STATEMENT 17: Psychoeducation"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for Efficacy of Psychoeducation, Grading of the Overall Supporting Body of Research Evidence for Harms of Psychoeducation, STATEMENT 17: Psychoeducation

### Community 121 - "STATEMENT 23: Social Skills Training"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for Efficacy of Social Skills Training, Grading of the Overall Supporting Body of Research Evidence for Harms of Social Skills Training, STATEMENT 23: Social Skills Training

### Community 122 - "STATEMENT 18: Supported Employment Services"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for Efficacy of Supported Employment Services, Grading of the Overall Supporting Body of Research Evidence for Harms of Supported Employment Services, STATEMENT 18: Supported Employment Services

### Community 123 - "STATEMENT 24: Supportive Psychotherapy"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for Efficacy of Supportive Psychotherapy, Grading of the Overall Supporting Body of Research Evidence for Harms of Supportive Psychotherapy, STATEMENT 24: Supportive Psychotherapy

### Community 124 - "STATEMENT 6: Continuing the Same Medications"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for the Efficacy of Continuing the Same Antipsychotic Medication, Grading of the Overall Supporting Body of Research Evidence for the Harms of Continuing the Same Antipsychotic Medication, STATEMENT 6: Continuing the Same Medications

### Community 125 - "STATEMENT 5: Continuing Medications"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for the Efficacy of Continuing Treatment With an Antipsychotic Medication, Grading of the Overall Supporting Body of Research Evidence for the Harms of Continuing Treatment With an Antipsychotic Medication, STATEMENT 5: Continuing Medications

### Community 126 - "STATEMENT 10: Long-Acting Injectable Antipsychotic"
Cohesion: 0.67
Nodes (3): Grading of the Overall Supporting Body of Research Evidence for the Efficacy of LAI Antipsychotic Medications, Grading of the Overall Supporting Body of Research Evidence for the Harms of LAI Antipsychotic Medications, STATEMENT 10: Long-Acting Injectable Antipsychotic

### Community 140 - "Quick Reference"
Cohesion: 0.50
Nodes (4): Key Imports, Quick Reference, Server Initialization, Tool Registration Pattern

### Community 141 - "ReadinessError"
Cohesion: 0.50
Nodes (3): Exception, Database readiness failure with a public code., ReadinessError

### Community 142 - "Code Best Practices"
Cohesion: 0.67
Nodes (3): Code Best Practices, Code Composability and Reusability, Python-Specific Best Practices

### Community 143 - "Tool Implementation"
Cohesion: 0.67
Nodes (3): Tool Implementation, Tool Naming, Tool Structure with FastMCP

### Community 144 - "health"
Cohesion: 0.67
Nodes (3): health(), get, Liveness only; never touches the database.

## Knowledge Gaps
- **844 isolated node(s):** `x-insight`, `name`, `version`, `private`, `type` (+839 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1111 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **32 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `@playwright/test` connect `identity.spec.ts` to `autosave.spec.ts`, `themes.spec.ts`, `registration.spec.ts`, `accessibility.spec.ts`, `discard.spec.ts`, `draft-safety.spec.ts`, `package.json`?**
  _High betweenness centrality (0.012) - this node is a cross-community bridge._
- **Why does `X-INSIGHT — System Design` connect `X-INSIGHT — System Design` to `X-INSIGHT — MCP Server Design`, `App.tsx`?**
  _High betweenness centrality (0.011) - this node is a cross-community bridge._
- **Why does `react` connect `App.tsx` to `package.json`?**
  _High betweenness centrality (0.011) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `physician()` (e.g. with `test_author_discards_draft_with_confirmation()` and `test_author_saves_and_retrieves_draft_across_restart()`) actually correct?**
  _`physician()` has 15 INFERRED edges - model-reasoned connections that need verification._
- **What connects `x-insight`, `name`, `version` to the rest of the system?**
  _844 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `STATEMENT 4: Antipsychotic Medications` be split into smaller, more focused modules?**
  _Cohesion score 0.03571428571428571 - nodes in this community are weakly interconnected._
- **Should `conftest.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07196969696969698 - nodes in this community are weakly interconnected._