# X-INSIGHT — MCP Server Design

*X-INSIGHT · research prototype · component design*

**The MCP server** — Read-only patient-record tooling, CPT elicitation, and the boundary between what the model decides and what the app computes.

**Legend:** 🟠 amber = model-driven, not reproducible · 🟢 teal = deterministic, reproducible

**Covers:** FR-32 · FR-33 · FR-34 · FR-35 · FR-42 · FR-43 · NFR-04

---

## Contents

1. [Scope and assumptions](#1-scope-and-assumptions)
2. [What it must do](#2-what-it-must-do)
3. [Architecture](#3-architecture)
4. [Deployment shape and transport](#4-deployment-shape-and-transport)
5. [Run context and scoping](#5-run-context-and-scoping)
6. [Tool catalog](#6-tool-catalog)
7. [Run protocol](#7-run-protocol)
8. [Validation rules](#8-validation-rules)
9. [Determinism and reproducibility](#9-determinism-and-reproducibility)
10. [Concurrency and queueing](#10-concurrency-and-queueing)
11. [Errors and retries](#11-errors-and-retries)
12. [Data model](#12-data-model)
13. [Internal API](#13-internal-api)
14. [Transparency panel](#14-transparency-panel)
15. [Audit](#15-audit)
16. [Security](#16-security)
17. [Load and cost](#17-load-and-cost)
18. [Trade-offs](#18-trade-offs)
19. [What to revisit](#19-what-to-revisit)

---

## 1. Scope and assumptions

*Covers FR-32 · FR-33 · FR-34 · FR-35 · FR-43. Consumes FR-30, FR-31, FR-36. Feeds FR-15, FR-20, FR-42.*

This design covers the internal MCP server and the machinery immediately around it: the tools it exposes, how a Bayesian-network run is driven, where model output stops and deterministic computation starts, and how failures are contained. It does not cover the assessment UI, the network editor, or backup/restore, except where they touch the run.

### Assumptions, stated so they can be argued with

1. **The configured LLM endpoint does not speak MCP.** FR-43 specifies an OpenAI-compatible key, base URL and model. Such endpoints expose function calling, not MCP. The application therefore acts as MCP host *and* client, and bridges MCP tool definitions into the endpoint's tool schema. The "MCP server" is real, but its only client in v1 is X-INSIGHT itself.
2. **One deployable unit.** Monolith plus embedded MCP server on one Linux VPS (NFR-01). No external broker, no service mesh. Ten users does not justify either.
3. **One relational database is the single source of truth** (FR-33). PostgreSQL assumed; SQLite is viable at this scale with the caveats in §10.
4. **Network structure is frozen at authoring time.** Nodes, states and arcs come from versioned xmlbif (FR-31, FR-36). The model supplies numbers, never topology (FR-32).
5. **Clinical notes are invisible to the pipeline.** FR-16 says notes never influence algorithms. This is enforced at the query layer, not by prompt instruction — no tool can return note text.
6. **Volume.** ≤10 physicians, ~80 encounters/day, 13 networks defined (7 registration, 6 follow-up). Target: a full 7-network registration set completes in under three minutes; a single network under 45 s at p50.

### Non-goals for v1

No write access to the clinical record from the model. No graphical network editing. No PHI hardening beyond the redaction in §16. No horizontal scale-out. No streaming of partial marginals to the UI.

---

## 2. What it must do

*FR-32 · FR-33 · FR-34 · FR-35*

| # | Capability | Source |
|---|---|---|
| F1 | Expose read-only patient-record tools over MCP, scoped to exactly one patient and one encounter per run | FR-33 |
| F2 | Publish the network contract — the nodes, states and parent configurations the model is required to fill — so the fill task is closed-form rather than open-ended | FR-31, FR-32 |
| F3 | Accept extracted evidence and proposed CPT probabilities, validate them against the contract, reject and re-prompt on failure | FR-32 |
| F4 | Freeze a snapshot and hand it to a deterministic inference engine | FR-32, NFR-04 |
| F5 | Render proposal text from versioned templates against network output | FR-34 |
| F6 | Record every extracted input, every probability and every tool call for the review panel and the audit log | FR-33, FR-42 |
| F7 | Retry two or three times, then fail that step alone, keeping saved data intact and the run retryable later | FR-35 |
| F8 | Queue calls across concurrent users and fail soft | FR-43 |

---

## 3. Architecture

*FR-33 · FR-43 · NFR-01*

```
┌──────────────────────────────────────────────────────────────────────────┐
│  X-INSIGHT  ·  single deployable  ·  Linux VPS                           │
│                                                                          │
│  ┌──────────┐    ┌──────────────────┐    ┌────────────────────────────┐  │
│  │ Web UI   │───▶│ Encounter svc    │───▶│ Run orchestrator           │  │
│  │ Chrome / │    │ FR-10 … FR-22    │    │  FIFO queue + worker pool  │  │
│  │ Firefox  │◀───│                  │◀───│  leases · backoff · budget │  │
│  └────┬─────┘    └──────────────────┘    └──────┬─────────────────────┘  │
│       │ transparency panel (§14)                │                        │
│       │                                         ▼                        │
│       │                             ┌────────────────────────┐           │
│       │                             │ MCP host / client      │           │
│       │                             │ bridge  MCP ↔ OpenAI   │           │
│       │                             └────┬──────────────┬────┘           │
│       │                     tool calls   │              │ HTTPS          │
│       │                                  ▼              ▼                │
│       │                      ┌──────────────────┐  ┌──────────┐          │
│       │                      │ MCP SERVER       │  │ LLM      │──────────┼──▶ OpenAI-
│       │                      │ "record"         │  │ gateway  │          │   compatible
│       │                      │ read-only tools  │  │ FR-43    │          │   endpoint
│       │                      └────┬─────────┬───┘  └──────────┘          │
│       │                           │         │                            │
│       │        ┌──────────────────┘         └───────────┐                │
│       │        ▼                                        ▼                │
│       │  ┌───────────────────┐               ┌──────────────────────┐    │
│       │  │ Record access     │               │ BN registry          │    │
│       │  │ read-only views   │               │ xmlbif · XSD ·       │    │
│       │  │ notes EXCLUDED    │               │ versions · manifest  │    │
│       │  └─────────┬─────────┘               └──────────┬───────────┘    │
│       │            ▼                                    ▼                │
│       │  ┌────────────────────────────────────────────────────────────┐  │
│       └──│ Database — single source of truth   +   append-only audit  │  │
│          └──────────────────────────┬─────────────────────────────────┘  │
│                                     │ frozen snapshot                    │
│                      ┌──────────────┴───────────────┐                    │
│                      │ Inference engine             │  no network I/O    │
│                      │ Template renderer  FR-34     │  no clock, no RNG  │
│                      └──────────────────────────────┘                    │
└──────────────────────────────────────────────────────────────────────────┘
```
*Fig 1 — Component layout. The MCP server sits between the model and the record and never touches the inference engine directly.*

### The one structural idea worth defending

The model has two jobs — read the record, and produce numbers — and it should never do anything else. Everything downstream of the frozen snapshot is ordinary arithmetic the app can rerun forever. Drawing that line sharply is what makes NFR-04 satisfiable at all, and it is why the MCP server is read-only: the only thing the model can write is a CPT proposal, into a run scratchpad, subject to validation.

---

## 4. Deployment shape and transport

*FR-33 · NFR-01 · NFR-02*

| Option | For | Against |
|---|---|---|
| In-process registry, no MCP wire protocol | Fastest, no process management, trivial deploy | Not actually an MCP server; no external client can attach for debugging or evaluation; FR-33 says "runs internal MCP server" |
| stdio subprocess per run | Strong isolation, canonical MCP shape | Process churn at ~500 runs/day; awkward to share a DB connection pool; no concurrency benefit here |
| **Loopback Streamable HTTP, one long-lived server** | Real MCP; attachable by any MCP client for debugging; one connection pool; clean auth seam via per-run bearer token | An extra listener to secure (mitigated: bind 127.0.0.1 only) |

**Recommendation:** implement the tools once as a library, and expose that library two ways — directly to the in-process bridge, and over Streamable HTTP bound to `127.0.0.1` for anything external. Same code, same validation, same audit path. The production path uses the in-process call to avoid pointless serialization; the HTTP path exists so an engineer can point a general-purpose MCP client at a test patient and inspect exactly what the model sees. In a research prototype that debugging affordance is worth more than the listener costs.

---

## 5. Run context and scoping

*FR-33 · NFR-02*

Every run is bound to a `run_context` before the model is invoked:

```
run_context = {
  run_id            uuid
  run_group_id      uuid          # all networks for one encounter
  patient_ref       opaque id     # not the 10-digit Patient ID
  encounter_id      uuid
  encounter_type    registration | follow_up
  network_id        text
  network_version   int           # pinned at enqueue, never re-resolved
  snapshot_id       uuid          # frozen record read-set, see §9
  phase             elicitation | drafting
  scope             set of tool names allowed in this phase
}
```

### No tool takes a patient identifier

This is the single most important access-control decision. Tools resolve the patient from the run context on the server side. There is no `patient_id` argument anywhere in the catalog, no list endpoint and no search endpoint. A model that hallucinates another patient's record cannot express that hallucination as a tool call, so cross-patient leakage is structurally impossible rather than prompt-dependent.

### Phase-scoped tool sets

The drafting phase (FR-34) does not need the C-SSRS item responses; it needs the marginals, the medication list and the interaction report. Narrowing `scope` per phase keeps the drafting model from reintroducing raw clinical claims the network never reasoned over.

---

## 6. Tool catalog

*FR-33 · FR-14 · FR-16 · FR-21*

### Contract and context

| Tool | Returns | Notes |
|---|---|---|
| `get_network_contract` | network id and version, clinical question, every node with its states, parents and full parent-configuration list, which nodes are evidence nodes, which are targets, which require elicitation | Makes the fill task closed-form. Called first, always. |
| `get_patient_context` | sex, age, first-time vs established, encounter type and datetime, count of prior encounters | No name. No Patient ID. See §16. |

### Clinical record — read only

| Tool | Returns | Source |
|---|---|---|
| `get_diagnosis` | DSM-5-TR criterion items as met / not met / unknown, threshold status, whether the physician bypassed it and any recorded reason | FR-11 |
| `get_severity_assessment` | PANSS items with scores or `null`, subscale and total scores only when the required items are complete, otherwise `{"assessed": false}` | FR-12 |
| `get_suicide_assessment` | C-SSRS items, ideation severity, behaviour flags, derived band — or `{"assessed": false}` | FR-13 |
| `get_clinical_history` | illness duration, prior hospitalisations, prior antipsychotic trials and outcomes, treatment resistance markers, substance use, comorbidity, family history, adherence, aggression history, prior involuntary care | FR-14 |
| `get_medications` | active and stopped medications with drug, class, dose, unit, route, frequency, dates, catalog id or `null` for off-catalog entries | FR-14 |
| `get_interaction_report` | interacting pairs with severity, mechanism and source, plus a list of drugs the bundled database does not cover | FR-14, FR-15 |
| `get_adverse_effects` | tardive dyskinesia, akathisia, parkinsonism, acute dystonia — each present / absent / not assessed, with severity where present | FR-21 |
| `get_encounter_timeline` | prior encounters: date, type, severity total, signed-plan summary, recorded changes | FR-20, FR-22 |
| `get_last_signed_plan` | structured final plan from the previous encounter: medications, LAI status, clozapine status, monitoring, non-pharmacological elements | FR-15 |
| `get_treatment_response` | change in severity across encounters and physician-recorded response, for the no-improvement and continue-vs-adjust networks | FR-30 |

### Scratchpad writes

| Tool | Effect |
|---|---|
| `submit_evidence` | Records observed states for evidence nodes. Validated synchronously; returns per-item errors the model can act on. |
| `submit_cpt` | Records one node's full conditional table. Validated synchronously. One call per node keeps payloads small and makes repair local. |
| `finalize_elicitation` | Completeness check. Returns the list of anything still missing, or confirms the run can proceed to inference. |

### Deliberately absent

| Not exposed | Why |
|---|---|
| Any tool returning clinical notes | FR-16 — notes never influence algorithms. Enforced by excluding the column from the read-only views, not by instruction. |
| Any tool taking `patient_id`, or listing/searching patients | §5 scoping. Cross-patient access has no expressible form. |
| Any write to the clinical record, plan or encounter | Only a physician signs a plan (FR-15, FR-22). The model writes to the run scratchpad and nowhere else. |
| Full name, Patient ID, exact dates of birth | Never needed for probability reasoning; see §16. |

MCP resources and prompts are also published (the network contract as a resource, the FR-34 templates as prompts) for the benefit of native MCP clients. Because the OpenAI-compatible bridge can only carry tools, every resource is mirrored as a tool so both paths behave identically.

---

## 7. Run protocol

*FR-32 · FR-33 · FR-34*

```
UI        Orchestrator      MCP server       LLM            Engine      DB
 │ assessment saved
 ├─────────▶│ create run-group: 7 runs QUEUED, record snapshot frozen ──▶│
 │          │ lease run · pin network_version ───────────────────────────│
 │          ├─ bind run_context (phase = elicitation)
 │          │
 │          ├──────────────────────────────▶ chat(tools = bridged MCP)
 │          │           ◀── get_network_contract ─────────┤
 │          │           ├── nodes · states · configs ─────▶
 │          │           ◀── get_severity_assessment ──────┤        (amber)
 │          │           ◀── get_suicide_assessment ───────┤
 │          │           ◀── get_clinical_history ─────────┤
 │          │           ◀── submit_evidence ──────────────┤
 │          │           ├── ok  ·or·  per-item errors ────▶
 │          │           ◀── submit_cpt(node) × N ─────────┤
 │          │           ├── ok  ·or·  validation errors ──▶
 │          │           ◀── finalize_elicitation ─────────┤
 │          │
 │          ├─ FREEZE SNAPSHOT ═══════════════════════════════════════▶│
 │          ├───────────────────────────────────────▶ infer ───────────│  (teal)
 │          │◀──────────────── marginals + inference_hash ─────┤
 │          │
 │          ├─ phase = drafting, scope narrowed
 │          ├──────────────────────────────▶ chat(template slots) ─────  (amber)
 │          ├─ status COMPLETE · audit written ──────────────────────▶│
 │◀─────────┤ SSE: run complete
```
*Fig 2 — One network run. Steps in amber are model-driven; the inference step in teal is pure computation over frozen inputs.*

### Phase C in detail: which CPTs the model actually fills

FR-32 says the model determines the probability values. Taken literally that means every cell of every table, on every run, for all thirteen networks. That is expensive, high-variance, and wasteful where the clinical literature already pins a conditional.

The design therefore adds an **elicitation manifest**: a small versioned file stored alongside each xmlbif, listing which nodes are patient-elicited. Nodes not listed keep the probabilities authored in the xmlbif. This is legitimate under FR-31 — the XSD validates structure only, so the authored CPT values are available as defaults — and it is the single biggest lever on cost, latency and reproducibility. A network can set the manifest to "everything" and get the literal reading of FR-32.

> This is an extension to the written requirement, not a reinterpretation of it. Flagged for the clinical lead: which conditionals, if any, should be fixed by evidence rather than inferred per patient?

### Structural budget

Elicitation cost is the product of parent-state counts. Authoring guidance: no more than three parents per elicited node, and no more than 27 parent configurations per node. Nodes exceeding it are rejected at import with a clear message rather than discovered as a timeout at runtime. Root nodes (priors) are batched into one call; each non-root elicited node gets its own call.

---

## 8. Validation rules

*FR-32 · FR-12 · FR-13 · NFR-03*

### Evidence

```
E1  Node must appear in the contract's evidence_nodes list.
E2  State must be one of the node's declared states — exact string match.
E3  If the underlying assessment is "not assessed", the node stays UNOBSERVED.
    An observation for such a node is rejected. The model does not impute.
E4  One observation per node. Duplicates rejected.
E5  Every observation must carry evidence_refs naming tools called in this run.
```

E3 is a clinical rule, not a technical one. FR-12 and FR-13 make "not assessed" a first-class state of the record; collapsing it into a guessed value would silently manufacture certainty the physician never recorded.

### Conditional probability tables

Submitted shape:

```json
{
  "node_id": "HospitalizationIndicated",
  "rows": [
    {
      "parents": { "SuicideRisk": "high", "AggressionRisk": "present" },
      "probabilities": { "yes": 0.93, "no": 0.07 },
      "rationale": "C-SSRS ideation level 5 with stated plan; documented
                    physical aggression at intake.",
      "evidence_refs": [ "get_suicide_assessment.ideation_severity",
                         "get_clinical_history.aggression_history" ]
    }
  ]
}
```

| Rule | Check | On failure |
|---|---|---|
| V1 | Node exists in the pinned network version and is marked elicited | Reject, repairable |
| V2 | Parent configurations exactly match the declared cross-product — none missing, none extra | Reject with the missing list, repairable |
| V3 | Probability keys exactly match the declared states | Reject with the expected keys, repairable |
| V4 | Every value in [0, 1] | Reject, repairable |
| V5 | Each row sums to 1.0 ± 0.02 | Within tolerance: normalise, store `normalization_delta`. Outside: reject, repairable. |
| V6 | Clamp to [0.001, 0.999] and renormalise | Applied silently, recorded |
| V7 | Round to four decimal places, store as exact decimal, never binary float | Applied |
| V8 | `rationale` non-empty and ≤500 chars; every `evidence_ref` names a tool actually invoked in this run | Reject, repairable |

V6 exists because a hard zero is an irreversible claim: no amount of downstream evidence can move a state the model wrote off at elicitation time. Clamping keeps the network correctable.

V8 is the cheapest available guard against confident fabrication. A rationale citing a tool the model never called is caught by the server, not by a reviewer reading the transparency panel at the end of a clinic day.

---

## 9. Determinism and reproducibility

*NFR-04 · FR-32*

NFR-04 requires deterministic, reproducible execution for the same inputs and version. Language-model output is not reproducible, so the requirement is met by defining precisely where "inputs" begins.

```
inference_hash = SHA-256(
    network_id
  ‖ network_version
  ‖ canonical_json(cpt_snapshot)        # decimal strings, sorted keys
  ‖ canonical_json(evidence_snapshot)
  ‖ engine_version
)

Guarantee:  same inference_hash  ⇒  bit-identical marginals, forever.
```

### What is frozen, and when

- **Record snapshot** — taken once when the run *group* is created, before any model call. All seven registration networks then read an identical record, and re-reading a tool a week later returns what the model saw, not what the record says now.
- **Network version** — pinned at enqueue. If an admin activates a new version mid-run, the run completes against the pinned version and the change is noted; it does not silently switch.
- **CPT snapshot** — written at `finalize_elicitation`, immutable thereafter.

### Engine constraints

Single-threaded junction-tree inference over exact decimals with a fixed elimination order derived deterministically from node ids. No floating-point reduction order dependence, no RNG, no clock, no network I/O, no parallel accumulation. Re-running inference over a stored snapshot is a supported operation and should be exercised as a test on every deploy.

> **Say this plainly in the interface.** The elicitation is not reproducible; the inference is. The transparency panel should not imply otherwise, and the research disclaimer from FR-01 belongs on every proposal.

Best-effort measures on the model side — temperature 0, top-p 1, a fixed seed where the endpoint honours one — reduce variance but are not guarantees and are not relied on anywhere in this design.

---

## 10. Concurrency and queueing

*FR-43 · NFR-01*

```
run_queue  (durable table, not an in-memory list)

  lease:   SELECT … WHERE status='QUEUED'
           ORDER BY fairness_key, enqueued_at
           FOR UPDATE SKIP LOCKED  LIMIT 1

  workers:            W = 2   (configurable)
  LLM in-flight:      2       (semaphore, independent of W)
  rate limit:         token bucket, RPM from admin API settings
  lease TTL:          5 min, heartbeat every 30 s
  crash recovery:     expired lease → QUEUED, attempt count preserved
```

### Fairness across physicians

A registration enqueues seven runs at once. Strict FIFO would make a second physician wait behind all seven. `fairness_key` round-robins across distinct submitting physicians before falling back to enqueue time, so a one-network follow-up is not stuck behind someone else's full registration set. With ten users this costs one index and prevents the most likely complaint.

### Run groups

Runs are grouped per encounter. The UI shows group progress; a failed member does not fail the group; the physician can open the completed proposals while one is still retrying.

> **SQLite caveat.** `SKIP LOCKED` does not exist. On SQLite, run the queue in-process with a single writer and WAL mode. That works at this scale but ties the queue to one process — a real constraint on the "deployable on a cloud VPS" story if the app is ever run behind more than one worker process.

---

## 11. Errors and retries

*FR-35 · FR-43 · NFR-04*

Two separate budgets. A **repair budget** of 2 handles validation failures inside a single model conversation — the server returns a structured error and the model corrects itself, which is cheap and usually works. An **attempt budget** of 3 (initial plus two retries, per FR-35) handles transport and endpoint failures and restarts the conversation.

| Code | Cause | Retry | Handling |
|---|---|---|---|
| `LLM_TIMEOUT` | No response in 90 s | yes | Attempt budget. Backoff 2 s, 8 s, jittered. |
| `LLM_5XX` | Endpoint error | yes | Attempt budget, same backoff. |
| `LLM_RATE_LIMIT` | 429 | yes | Honour `Retry-After`; does not consume an attempt. |
| `LLM_AUTH` | 401 / 403 | no | Fail immediately. Message names the API settings page. Admin alerted; all queued runs paused rather than burned. |
| `LLM_MODEL_NOT_FOUND` | 404 on model name | no | Same as above. |
| `LLM_CONTEXT_OVERFLOW` | Prompt too long | once | Retry with one node per call and trimmed history. Then fail. |
| `CPT_VALIDATION_FAILED` | §8 rules | yes | Repair budget first. Exhausted → consumes an attempt. |
| `EVIDENCE_INVALID` | §8 E-rules | yes | Repair budget. |
| `INCOMPLETE_ELICITATION` | Nodes left unfilled | yes | Repair budget; server returns the missing list. |
| `MCP_TOOL_ERROR` | DB unavailable | yes | Attempt budget. |
| `NETWORK_VERSION_CHANGED` | Activation during run | yes | Abort, requeue against the pinned version. |
| `ENGINE_ERROR` | Inference fault | no | Bug. Snapshot preserved for reproduction — it is fully replayable. |

### Failing soft

A failed run marks that network alone as unavailable. The encounter stays editable, the assessment data is untouched (FR-35, NFR-04), other proposals render, and the physician can still write and sign the secondary plan without any proposal at all — nothing in FR-15 or FR-22 makes a successful run a precondition for signing. Manual retry creates a new attempt row rather than overwriting history.

The UI message says what failed and what to do: *"Proposal unavailable for involuntary care — the model did not respond. Retry, or continue without it."*

---

## 12. Data model

*FR-33 · FR-42 · NFR-04 · NFR-05*

```
record_snapshot     id · encounter_id · taken_at · payload_json · content_hash

bn_run_group        id · encounter_id · snapshot_id · created_by · created_at

bn_run              id · run_group_id · network_id · network_version
                    manifest_version · question_key
                    status  QUEUED|LEASED|ELICITING|INFERRING|DRAFTING|
                            COMPLETE|FAILED|CANCELLED
                    attempt_count · repair_count · lease_expires_at
                    error_code · error_message
                    enqueued_at · started_at · finished_at

bn_run_tool_call    id · run_id · attempt · seq · tool_name
                    arguments_json · result_hash · result_json
                    latency_ms · ok · error_code

bn_run_evidence     run_id · node_id · state · evidence_refs
                    rationale · source_tool

bn_run_cpt          run_id · node_id · parent_config_json · state
                    probability_decimal · normalization_delta
                    clamped bool · rationale · evidence_refs

bn_run_result       run_id · node_id · marginal_json
                    engine_version · inference_hash · computed_at

bn_run_llm_call     id · run_id · attempt · phase · model · base_url_host
                    prompt_tokens · completion_tokens · finish_reason
                    http_status · latency_ms          -- no prompt bodies

proposal_draft      id · encounter_id · template_id · template_version
                    rendered_text · source_run_ids · created_at
```

`bn_run_cpt` and `bn_run_evidence` together are the reproducibility snapshot and the transparency payload — the same rows serve both, which is why they store rationale and references rather than bare numbers. `bn_run_llm_call` deliberately records metadata only; prompt and completion bodies are reconstructible from the snapshot plus the tool-call log, and storing them doubles the PHI surface for no benefit.

---

## 13. Internal API

*FR-33 · FR-35 · FR-43*

```
POST /api/encounters/{eid}/run-groups      202  { run_group_id, runs[] }
GET  /api/run-groups/{gid}                 200  status rollup + per-run state
GET  /api/runs/{rid}                       200  status, marginals, error
GET  /api/runs/{rid}/transparency          200  §14 payload
POST /api/runs/{rid}/retry                 202  new attempt
POST /api/runs/{rid}/cancel                202
GET  /api/encounters/{eid}/proposal        200  drafted text + provenance
GET  /api/events?encounter_id={eid}        SSE  run status stream

admin
GET  /api/admin/mcp/tools                  200  live tool schemas
POST /api/admin/mcp/dry-run                200  run any tool against a
                                                chosen patient, no LLM
POST /api/admin/runs/{rid}/replay          200  re-infer from snapshot,
                                                assert inference_hash match
```

The two admin endpoints are development infrastructure that belongs in the product. `dry-run` answers "what does the model actually see for this patient" in one click. `replay` turns NFR-04 from an aspiration into something testable on demand.

---

## 14. Transparency panel

*FR-33 · FR-15*

FR-33 requires extracted inputs and CPT percentages shown alongside results. The panel is assembled entirely from stored rows — nothing is recomputed for display, so what a physician reviews is exactly what the engine consumed.

```json
{
  "run": { "question": "Hospitalization indicated",
           "network": "hospitalization", "version": 4,
           "status": "COMPLETE", "duration_ms": 21340 },

  "extracted_inputs": [
    { "node": "SuicideRisk", "state": "high",
      "from": "get_suicide_assessment.ideation_severity = 5",
      "why": "Active ideation with specific plan." },
    { "node": "SocialSupport", "state": null,
      "from": "not assessed", "why": "Left unobserved." }
  ],

  "probabilities": [
    { "node": "HospitalizationIndicated",
      "given": { "SuicideRisk": "high", "AggressionRisk": "present" },
      "table": { "yes": "93%", "no": "7%" },
      "why": "C-SSRS level 5 with plan; aggression documented at intake.",
      "adjusted": { "normalized_by": "0.4%", "clamped": false } } ],

  "result": [
    { "node": "HospitalizationIndicated",
      "marginal": { "yes": "88%", "no": "12%" } } ],

  "tool_calls": [ { "seq": 1, "tool": "get_network_contract", "ms": 4 } ],

  "caveat": "Probabilities were produced by a language model from this
             patient's record and are not reproducible between runs.
             The network computation over them is."
}
```

Unobserved nodes are shown, not hidden. A physician needs to see that the network reached its conclusion without knowing anything about social support just as much as they need to see the inputs it did have.

---

## 15. Audit

*FR-42*

Append-only, admin-viewable. The audit log stays lean by recording references and hashes; full payloads live in the run tables.

| Event | Fields beyond the common envelope |
|---|---|
| `BN_RUN_ENQUEUED` | run_group_id, network_id, version, triggering physician |
| `MCP_TOOL_CALLED` | tool, argument hash, result hash, latency, ok |
| `CPT_SNAPSHOT_FROZEN` | node count, cell count, snapshot hash |
| `INFERENCE_COMPLETED` | inference_hash, engine_version, duration |
| `BN_RUN_FAILED` | error_code, attempt_count, last message |
| `PROPOSAL_DRAFTED` | template_id, template_version, source run ids |
| `API_SETTINGS_CHANGED` | which fields; never the key itself |
| `NETWORK_ACTIVATED` | network_id, from version, to version |

Common envelope: event id, timestamp, actor (physician id or `system`), on-behalf-of physician for system events, run id where applicable. Every model-initiated action is attributable to the physician whose click started it.

---

## 16. Security

*NFR-02 · FR-43 · FR-16*

- **Loopback only.** The MCP HTTP adapter binds `127.0.0.1`. Per-run bearer token, TTL equal to the lease, invalidated when the run terminates.
- **Read-only database role** for the record access layer. The MCP server physically cannot write to clinical tables; the scratchpad uses a separate connection.
- **Notes excluded at the view level** (FR-16), so the exclusion survives prompt changes and new tools.
- **Egress allowlist** to the host in the configured base URL, and nothing else.
- **API key** encrypted at rest with a key from the environment, masked on read, never written to logs or audit entries.
- **Prompt injection.** Record fields are free text and reach the model. The blast radius is bounded by construction — no write tools, no patient identifiers in any signature, no egress from tools — so the worst case is a distorted proposal, which the transparency panel is designed to expose. Tool results are wrapped in a fixed data envelope rather than concatenated into the prompt.

> **One recommendation beyond the requirement.** NFR-02 rules out PHI hardening in v1, but the name and 10-digit Patient ID (FR-10) are never needed for probability reasoning. Replacing them with a per-run opaque `patient_ref` costs one mapping table and keeps direct identifiers from leaving the VPS on every one of the ~500 daily calls to a third-party endpoint. This is cheap now and awkward to retrofit.

---

## 17. Load and cost

*NFR-01 · FR-43*

```
10 physicians × ~8 encounters/day        ≈  80 encounters/day
registration 7 runs · follow-up 6 runs   ≈  500–560 runs/day

per run    ~6 read-tool calls  (served from the group snapshot)
           ~1 + N elicited-node calls
           ~8 LLM round-trips, ~6k prompt tokens each
           ≈ 50k tokens

per day    ≈ 25–30M tokens
```

Compute and storage are trivial — a 2-vCPU VPS is comfortable, and a year of runs is a few gigabytes. The cost driver is entirely token volume, which is why two decisions in this design matter more than any infrastructure choice:

- **The group record snapshot** (§9) collapses seven networks' worth of record reads into one, and makes the reads consistent as a side effect.
- **The elicitation manifest** (§7) is a direct multiplier on token spend. Pinning half the conditionals roughly halves the bill and the variance together.

---

## 18. Trade-offs

| Decision | Chosen because | Cost of the choice |
|---|---|---|
| MCP server in-process, with a loopback HTTP mirror | Zero process management on the hot path; real MCP available for debugging and evaluation | Two invocation paths to keep in sync — mitigated by sharing one tool library |
| CPTs submitted node-by-node via tool calls, not as one JSON response | Validation errors return immediately and repair is local to one node; payloads stay small | More round-trips, so more latency and tokens per run |
| Elicitation manifest instead of filling every CPT | Large reduction in cost, latency and run-to-run variance; lets established conditionals be fixed by evidence | Extends FR-32; needs clinical sign-off on which nodes are pinned |
| Record snapshot frozen per run group | All networks see one consistent record; replay is exact | An edit made while runs are in flight is not picked up until the group is re-run |
| Per-network fail-soft rather than all-or-nothing | A single flaky call should not cost a physician six good proposals | Partial result sets need clear labelling or they mislead |
| Clamping probabilities away from 0 and 1 | Keeps the network correctable by later evidence | Slightly distorts a genuinely categorical conditional |
| Requiring rationale and evidence references on every row | Makes fabricated grounding a server-side validation failure, and makes FR-33's review panel meaningful | Materially more output tokens |
| Redacting names and Patient ID from the model | Removes direct identifiers from all egress at near-zero cost | Goes beyond NFR-02's stated scope |
| PostgreSQL over SQLite | Real queue semantics with `SKIP LOCKED`; multi-process safe | One more service to install and back up (FR-41) |

---

## 19. What to revisit

1. **An evaluation harness, early.** A set of synthetic vignettes with expected marginal bands, run against every network version, manifest version and template version. Without it there is no way to tell a prompt change from a clinical regression. This is the highest-value thing not yet in the requirements.
2. **A calibration study.** Compare model-elicited CPTs against expert-elicited ones on the same cases. This is the scientific question the prototype exists to answer, and the data model in §12 is already shaped to collect it. Build the export before the first physician logs in.
3. **The fallback position.** If calibration is poor, the architecture already supports the safer design — set every manifest to elicit nothing, and the model's role shrinks to evidence extraction over expert-authored networks. That should be a configuration change, not a rewrite, and it is worth verifying that it is.
4. **Structured output** for CPT submission once the endpoint supports constrained decoding, which would eliminate most of the repair loop in §11.
5. **An external queue** (Redis or equivalent) if the app ever runs more than one worker process, or if run volume grows past a few thousand a day.
6. **Streaming progress** — surfacing extracted evidence in the UI before inference finishes makes a 45-second wait feel supervised rather than opaque.
7. **Session timeout, per-user record scoping, and full PHI hardening** before this system sees identifiable data from real patients. NFR-02 defers these knowingly; the deferral should expire at the same moment the prototype stops being a prototype.