# X-INSIGHT — System Architecture

## 1. Purpose and architectural vocabulary

X-INSIGHT is a research prototype helping physicians/psychiatrists explore treatment options for schizophrenia cases. This revision, dated **2026-09-20**, follows [user requirements](../user-requirements.md); [system design](system-design.md) specifies contracts, validation, data storage and deployment. The application does not independently execute treatment decisions.

The following definitions govern this architecture:

| Level | Meaning | Application to X-INSIGHT |
|---|---|---|
| System | The complete software serving its overall purpose | X-INSIGHT |
| Subsystem | An independent system that holds independent value | A coherent capability with its own useful outcome, owned information and boundary |
| Module | A component of a subsystem that cannot function as a standalone system | A contributing capability that depends on its parent subsystem's context and rules |

Independence means a subsystem can deliver its own defined value without completing the entire X-INSIGHT workflow. It may consume information or services through explicit relationships. It does not mean every subsystem must have its own application, server, database or deployment.

For example, maintaining a patient case record is useful even when proposal generation is unavailable. Conversely, the assessment-entry module is meaningful only within a case and encounter workflow; it is not a separate system.

## 2. System boundary

X-INSIGHT serves one administrator and fewer than ten physicians sharing a patient pool. Its user-facing language is English. The updated requirements specify DSM-5-TR diagnostic criteria, PANSS and C-SSRS assessments, a bundled demo medication catalog and a local DDI database. They no longer impose a synthetic-only patient restriction. After every successful physician login, display the research warning that the app must not be the sole basis for treating patients. Prototype-basic security does not establish clinical validation or PHI hardening.

| Participant | Relationship to X-INSIGHT |
|---|---|
| Physician | Creates and updates records, conducts encounters, reviews generated proposals, edits and signs final plans |
| Administrator | Manages access, network versions and activation, provider configuration, patient archiving, exports, audit inspection and recovery |
| Configured LLM provider | External dependency used for input preparation, designated CPT estimation and proposal wording; it has no authority to finalize records |
| Hosting environment | Provides execution and durable storage for the application; it is outside the functional decomposition |

The internal patient record is authoritative. The external LLM provider does not own the record, execute the authoritative Bayesian inference, alter network structure or non-designated CPTs, or sign plans. The LLM estimates designated CPT values from authorized record context; the application validates and freezes the complete effective tables before inference.

Excluded from this architecture's v1 scope are autonomous treatment, external health-record integration, self-registration, permanent patient deletion, PDF generation and graphical editing of Bayesian networks.

## 3. Subsystem decomposition

X-INSIGHT consists of four proposed subsystems.

| ID | Subsystem | Independent value | Primary owned information |
|---|---|---|---|
| S1 | Case and Encounter Management | Maintains and presents a useful longitudinal patient case record, even without a generated proposal | Patients, encounters, assessments, history, medications, notes, physician final plans and addenda |
| S2 | Research Knowledge Management | Maintains a reusable, inspectable collection of versioned network definitions and supporting content, without requiring a patient encounter or reasoning run | Bayesian network definitions, content versions, validation status and active model selections |
| S3 | Decision Support | Produces an inspectable reasoning result and treatment proposal from a defined case snapshot and selected knowledge versions, without finalizing an encounter | Accepted evidence, patient-specific CPT artifacts, reasoning runs, network results, generated initial proposals and their provenance |
| S4 | Administration and Governance | Maintains an accountable, recoverable operating environment independently of whether an encounter is being conducted | Accounts, access state, provider settings, audit history and recovery operations |

These are logical systems within one product. Their boundaries organize responsibilities; they do not introduce a requirement for four separately installed products.

### 3.1 High-level relationships

Arrows describe information or services supplied to another subsystem.

```mermaid
flowchart TD
    S4[Administration and Governance] -->|Access and operating controls| S1[Case and Encounter Management]
    S4 -->|Access and audit services| S2[Research Knowledge Management]
    S4 -->|Access and provider configuration| S3[Decision Support]
    S2 -->|Assessment and drug content| S1
    S2 -->|Versioned models and templates| S3
    S1 -->|Authorized case snapshot| S3
    S3 -->|Results and initial proposal| S1
    S3 -->|Bounded input, CPT estimation and drafting requests| L[External LLM provider]
    L -->|Candidate inputs, designated CPT values and proposal text| S3
```

All subsystems contribute events to Administration and Governance's audit capability. Those audit relationships are omitted from the diagram for readability. Research Knowledge Management supplies definitions; Decision Support executes reasoning; Case and Encounter Management controls the physician's final record.

## 4. Subsystems and their modules

### 4.1 S1 — Case and Encounter Management

**Purpose:** Maintain the shared case record and coordinate the physician's registration, follow-up and finalization work.

**Independent outcome:** A persisted, searchable and reportable patient case history. Recording and reading remain useful when decision support is unavailable, although signing a new plan is blocked until a valid proposal succeeds.

| Module | Responsibility | Why it is a module |
|---|---|---|
| Patient Registry | Identification, demographics, contact details, search and archive state | Depends on the case identity and record lifecycle |
| Encounter Workflow | Registration and follow-up progression, draft ownership, autosave, resumption and confirmed discard | Coordinates the other case modules around an encounter |
| Assessment and History | DSM-5-TR diagnosis with reason-free bypass, PANSS severity and C-SSRS suicide assessments with not-assessed skip states, adverse effects and structured history | Requires an encounter and content definitions |
| Medication Review | Drug-only medication reconciliation and local interaction reporting, including unavailable coverage; no dose/unit/route/frequency/active-stopped fields | Requires the encounter's medication set and supplied drug knowledge |
| Notes | Timestamped, attributed page notes | Requires a record context and must remain separate from algorithm-visible history |
| Plan Review and Sign-off | Displays initial proposals, captures physician changes, enforces signing prerequisites and records addenda | Requires an encounter, its author and a successful current proposal |
| Record Presentation and Reporting | Patient chart, chronology, patient-list export and printable patient report | Presents authoritative case information under access rules |

**Boundary:** S1 owns the physician's secondary/final plan. It references the generated initial proposal owned by S3 without rewriting it. S1 does not author Bayesian models or determine their inference results.

### 4.2 S2 — Research Knowledge Management

**Purpose:** Preserve the assessment content and model versions on which assessments and reasoning depend.

**Independent outcome:** An inspectable and exportable set of research models and supporting content. Models can be maintained without creating cases or calling an LLM.

| Module | Responsibility | Why it is a module |
|---|---|---|
| Bayesian Model Library | Import, XML editing, read-only graph inspection and export | Depends on model identity, validation and version history |
| Model Validation | Distinguishes structural validity from model consistency and suitability for execution | Produces a judgment about an artifact managed by the library |
| Version and Activation Control | Preserves versions, selects active models and supports rollback | Depends on the managed knowledge collection and validation results |
| Assessment and Drug Content | Owns versioned DSM-5-TR/PANSS/C-SSRS definitions and rules, demo drug catalog and interaction coverage | Supplies definitions consumed by case and reasoning workflows |
| Reasoning Definitions | Owns fixed variable types and relevance mappings, input/output meanings, designated CPT allowlists, applicability rules, uncertainty policies, estimation instructions and proposal templates | Gives executable models and generated results their intended interpretation |

**Boundary:** S2 owns fixed network definitions, versioned default probability tables and the allowlist of designated CPTs. Only designated tables may receive patient-specific LLM estimates; all other tables retain their versioned defaults. S3 owns these run-specific estimates and the complete effective CPT artifact. Administrator XML editing creates a new version rather than changing a historical run. Content ownership does not imply a new graphical content-authoring feature: bundled content is sufficient where no management UI is required.

### 4.3 S3 — Decision Support

**Purpose:** Transform an authorized case snapshot into replayable Bayesian results and an initial treatment proposal that includes Bayesian recommendations and local DDI findings.

**Independent outcome:** A reviewable analysis artifact containing inputs, CPT percentages, results, gaps and provenance. Producing it does not require a physician to sign a plan; S3 cannot sign one itself.

| Module | Responsibility | Why it is a module |
|---|---|---|
| Analysis Coordination | Controls run progression, automatic execution, retries, clarification and failure state | Organizes the reasoning modules around one analysis request |
| Authorized Record Access | Obtains permitted case information through internal MCP tools | Requires the run's authorized case context; it is not another record system |
| Evidence Preparation | Maps facts into designated model inputs and makes missing/conflicting information explicit | Depends on a snapshot and model input definitions |
| CPT Estimation and Validation | Uses MCP-mediated record context to estimate designated CPTs, copies other tables unchanged, validates and freezes complete effective tables | Requires the pinned network definition, CPT allowlist and authorized snapshot |
| Bayesian Inference | Executes fixed network structure with the frozen run-specific CPT set deterministically | Requires validated network versions, effective CPT artifacts and accepted evidence |
| Proposal Generation | Uses templates and LLM assistance to express network results and DDI findings as an initial proposal | Requires validated reasoning outputs and their limitations |
| Result Provenance | Retains input sources, estimated/default CPT origins, complete effective tables, model/content versions and result history for inspection | Gives the analysis artifact its traceability and replay context |

**Boundary:** S3 owns system-generated proposals, not physician decisions. LLM failure cannot remove saved case data. The LLM supplies candidate inputs, designated CPT probabilities and proposal wording. The application rejects changes to fixed definitions or non-designated CPTs, validates accepted estimates, and executes inference. The same patient record can yield different fresh LLM estimates; reproducible replay uses the stored complete CPT artifact, evidence and pinned engine, without another provider request.

The registration and follow-up clinical questions are configurations of this subsystem, not separate subsystems. Hospitalization, medication selection, LAI, Clozapine-related questions, adverse-effect management, continuation/adjustment remain distinct model questions within the same reasoning capability.

### 4.4 S4 — Administration and Governance

**Purpose:** Control access, preserve accountability and support continued operation of X-INSIGHT.

**Independent outcome:** An administered set of users and configuration, inspectable activity history, and recoverable system state. These tasks can be performed without an active clinical encounter or successful LLM call.

| Module | Responsibility | Why it is a module |
|---|---|---|
| Identity and Access | Login, roles, password changes, physician account management and deactivation | Depends on X-INSIGHT's actors and access policies |
| Operating Configuration | Provider key/base URL/model settings and user preferences | Configures other application capabilities rather than producing clinical outputs |
| Audit | Captures and presents append-only activity history | Requires meaningful events supplied by the application |
| Backup and Restore | Preserves and restores coherent system state | Depends on the information and consistency rules of all subsystems |
| Administrative Reporting | Physician-list export and administrative views | Presents governed operational information |

**Boundary:** Administrative authority does not confer the right to sign a physician's encounter. An admin dashboard is an entry point to capabilities across subsystems, not a fifth subsystem. Patient archiving belongs to S1; model editing belongs to S2; S4 supplies the authorization for the administrator to perform those actions.

## 5. Collaboration and ownership rules

| Exchange | Owner supplying the information | Consumer | Architectural rule |
|---|---|---|---|
| Case snapshot | S1 | S3 | Authorized, consistent view; page notes excluded |
| Assessment and drug definitions | S2 | S1 | Content version and coverage remain identifiable |
| Models and reasoning definitions | S2 | S3 | A run pins structure, variable types/relevance, defaults and designated CPT allowlist |
| Complete effective CPT artifact | S3 | Inference and review within S3; presentation in S1 | Estimated designated tables and unchanged defaults are frozen per run, traceable and replayable |
| Evidence, results and initial proposal | S3 | S1 | Generated content retains its identity and provenance |
| Final physician plan | S1 | Chart/report consumers | Original proposal remains distinguishable from physician edits |
| Identity and permissions | S4 | All subsystems | Each action respects role, ownership and active account state |
| Activity events | All subsystems | S4 | Audit records describe actions without replacing domain records |
| Recovery state | All subsystems | S4 | Recovery preserves relationships between records, results and knowledge versions |

Each category of information has one logical owner, even when a common database holds it. A consuming subsystem requests information or an operation through the owner's boundary rather than changing another subsystem's state independently. Historical snapshots preserve the state used for a result or signature; they do not become competing editable master records.

## 6. End-to-end responsibility

The physician begins in S1, which records and preserves the encounter using versioned assessment definitions supplied by S2. When the encounter reaches proposal review, S1 supplies an authorized snapshot to S3. S3 prepares inputs, uses the LLM with internal MCP tools to estimate designated CPTs, validates and freezes the effective tables, executes the relevant networks, and drafts a template-based proposal including DDI findings. Non-designated tables remain at the pinned defaults. Failed steps retain saved data and allow bounded retries.

S1 presents the proposal, extracted inputs and effective CPT percentages for review, clearly separating CPT values from posterior probabilities. The physician edits the secondary plan and explicitly signs it. S1 preserves the signed encounter, while S4 records the relevant actions. Follow-up creates a new encounter rather than changing an earlier signed record.

**Confirmed signing rule:** A physician cannot sign a manual plan when AI proposal generation fails. The draft remains saved for retry. A current successful proposal and physician review are prerequisites for signing; there is no manual bypass.

| Situation | Capabilities that remain available | Boundary on completion |
|---|---|---|
| LLM unavailable or generation fails | Record viewing, draft editing/saving, model maintenance and administration | New plan signing remains blocked |
| Required model/content unavailable or invalid | Record work and corrective knowledge maintenance | Affected reasoning cannot complete |
| Required evidence missing or conflicting | Saved draft and clarification workflow | Affected analysis waits for resolution |
| Analysis inputs change after generation | Continued draft editing and a new analysis | Old proposal cannot justify signing the changed analysis state |

These are capability boundaries, not promises of independent process-level availability. An outage of shared hosting or storage may affect all subsystems.

## 7. System-wide constraints

1. Research scope and the post-login warning apply throughout the product; standard assessments and the demo drug catalog retain identifiable content versions.
2. Shared patient access does not override author-only draft editing and signing.
3. Signed encounters are immutable; corrections are dated, attributed addenda, and subsequent assessments are new encounters.
4. Page notes never influence algorithms. Designated history fields may do so.
5. Variables, types, states, relevance and network structure remain fixed per selected version. The LLM estimates only designated CPTs; the application validates and freezes the complete effective CPT set before deterministic execution.
6. Missing, conflicting and not-assessed information must remain distinguishable from negative findings.
7. Saved drafts survive reasoning failures. Leaving a page does not implicitly discard them.
8. Model/content changes preserve the interpretability of historical results.
9. Account deactivation and patient archiving preserve records and attribution.
10. The internal record remains the single source of truth; MCP is an access mechanism.

Access protection, HTTPS for non-localhost use, the default admin/admin credentials with no password-complexity rules, the no-session-timeout policy, auditability and recovery apply across subsystem boundaries as specified in the requirements and detailed design.

## 8. Architectural rationale

Separate the product by independently useful responsibilities: keeping records, maintaining knowledge, producing analysis, and governing operation. Combining all four would obscure ownership, particularly the distinction between generated proposals and signed plans. Dividing by screens, individual networks, or technical layers would classify supporting components as independent systems even though they do not deliver independent domain value.

The proposed modular application in `system-design.md` can realize these boundaries within a coordinated deployment. This document neither requires microservices nor changes the detailed design's proposed technology stack. Any later physical separation should preserve the same ownership and signing rules.

The cost of these boundaries is explicit coordination: snapshots must agree with analysis results, content versions must remain available, and recovery must preserve their relationships. The benefit is that record maintenance, knowledge evolution and reasoning can change within clear responsibilities.

## 9. Relationship to requirements and detailed design

| Requirement area | Accountable subsystem | Supporting subsystem |
|---|---|---|
| Access and physician administration — FR-01–04 | S4 | S1 for affected drafts |
| Registration, assessments, medication recording and notes — FR-10–16 | S1 | S2 for definitions; S3 for proposals |
| Follow-up, signed records and patient directory — FR-20–23 | S1 | S3 for new proposals; S4 for access |
| Model questions and inference — FR-30–35 | S3 | S2 for models; S1 for records; S4 for provider settings |
| Network management — FR-36 | S2 | S4 for administrator authorization |
| Exports — FR-40 | S1 for patients; S4 for physicians | Access rules apply throughout |
| Backup/restore and audit — FR-41–42 | S4 | All subsystem information owners |
| Provider configuration and queued calls — FR-43 | S4 for configuration; S3 for execution | — |
| Quality constraints — NFR-01–05 | System-wide | Refined in the detailed design |

This architecture groups the existing design's Identity and Operations capabilities into S4, Patient Registry and Encounter capabilities into S1, Assessment and Drug Content and Model Registry into S2, and Reasoning Orchestration into S3. Export responsibilities follow their information owner. This refines the high-level vocabulary without asserting that new functionality has been approved.

Remaining questions in `system-design.md`—including content supply, draft visibility, addendum authority and archive behavior—remain open. They affect policies or lower-level design and do not prevent defining these subsystem boundaries. The prohibition on signing after generation failure is confirmed and is not an open question.

## 10. Decision summary and growth boundaries

The detailed ADRs in [system design, Section 13](system-design.md#13-architecture-decision-records) capture implementation alternatives. The key revised decision is fixed network definitions with LLM-estimated **designated** CPTs and application-owned inference. Fixed CPTs with evidence extraction alone no longer satisfy FR-32; LLM modification of graph structure would also contradict it.

Retaining the complete effective CPT set costs storage and requires probability validation, but makes displayed probabilities and historical inference inspectable. Unchanged tables retain their default-version provenance. A per-run artifact avoids sharing patient-specific probabilities across patients or mutating active models. Mathematical checks do not establish the clinical validity of the LLM estimates.

The proposed modular monolith, database-backed queue and separate worker fit the small shared user pool. Keep LLM calls bounded and queued so failures do not block draft saving. Revisit model/context limits as CPTs grow, worker capacity as queue delays rise, and physical subsystem separation only when measured scale or independent ownership warrants it. A single-host deployment has no high-availability guarantee; backups and tested restore provide recovery.
