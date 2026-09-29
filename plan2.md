# X-INSIGHT remaining work and next plan

Audit date: 2026-09-24. Sources: [AGENTS.md](AGENTS.md), [plan](docs/dev/plan.md), [tasks](docs/dev/tasks.md), [progress tracker](docs/dev/progress-tracker.md), and targeted implementation, migration, test, content, and deployment inspection.

**The application has substantial implemented functionality, but it is not release-ready. The next engineering session should repair the verification baseline. In parallel with that workstream, finish the missing clinical content and release packages. Do not proceed directly to S62.**

This is a remaining-work plan, not a replacement for the approved product contract. Existing owner approvals remain valid for their approved versions. Suggested contract changes below require an explicit decision before implementation.

## 1. What already exists

The starting audit in AGENTS.md is historical: there are now backend/frontend lockfiles, a FastAPI application, React UI, a worker/private MCP implementation, and 25 numbered migrations through `0025`.

The tracker records working identity, patient registration, drafts/autosave, assessments, shared charts, DDI mechanics, model administration/inference, sequential reasoning/retry, proposal review, signing/addenda, archive/deactivation, audit, exports, recovery interfaces, and operational UI. Corresponding implementation and test files exist. These are substantial engineering assets to finish and validate, not features to rebuild.

Recorded evidence includes real PostgreSQL, real MCP subprocesses, deterministic inference, controlled external-provider tests, and Chromium/Firefox journeys. However, scoped passes and synthetic workflows do not establish completion of the full release gates. Historical test results below are distinguished from checks rerun during this audit.

## 2. Confirmed remaining work

| Area | Current evidence | Work still required |
|---|---|---|
| Verification baseline / S01–S04 | Fresh `make check` fails with 33 Ruff errors. Direct mypy reports four `RowMapping` errors in `identity/accounts.py`. Full pytest collection fails on three duplicate module names. S04's original tracker entry remains `in_progress`, although S51 closed its draft/job integration. | Repair lint, formatting/types, collection and reproducible suite execution; then reconcile S04's status against its complete exit criteria. |
| CI | [CI](.github/workflows/ci.yml) calls `make verify` without npm installation, PostgreSQL provisioning/migration, or browser setup. [Makefile](Makefile) `verify` runs static checks and backend tests only. | Make clean-checkout CI provision its real owned dependencies and run the required offline gates, including browser coverage and recovery evidence. No live provider credentials. |
| Missing question / S28 | No `content/questions/involuntary_care/` exists. Twelve of thirteen question directories exist. | Obtain jurisdiction, setting and authoritative criteria; draft R3 and its independent examples, validate and obtain review. Missing R3 must continue to disable a complete registration bundle. |
| Invalid reviewed package / S32 | Fresh T5 package validation rejects `established_case_clozapine`: `undeclared_template_state`. The recorded mismatch is `ReviewCurrentClozapine` versus declared `ReviewCurrentTreatment`. | Prepare a corrected derived version, verify intended branch meaning, rerun validation and examples, and record approval for the changed package hash. Do not weaken the validator. |
| Reviewed versus released content / S12, S26–S39 | Twelve question dossiers record owner review/approval, but all retain `clinical_activation_allowed: false`. History approval is recorded; only its reviewed dossier exists, not the runtime `history.json`. No `content/bundles/` files exist. | Materialize versioned executable history and question packages, verify runtime mappings and template compatibility, then build and release both pinned bundles through the registry. Preserve prior approvals; seek review only for new or changed meanings/content. |
| DDI release / S17–S18 | `content/ddi/aliases.json` is still draft, reviewer null, with nine concepts. S18 explicitly records **no approved real DDI release**. Source inventory still has 128 files / 8,091,001 bytes. S16 recorded 64 passing and 64 failing documents. | Rebuild the corpus report; resolve source/parser anomalies and names; prepare high-risk/conflict/coverage review records; obtain an explicit full or limited-coverage release decision and publish reproducibly. Parser success is not clinical review. |
| Audit / S52 | Tracker admits missing per-question/per-tool audit events. No `record_audit` call sites were found in worker/coordinator/queue/MCP host. | Complete the required-event inventory and add safe attributed question/stage/tool events at the owning operations. Verify through admin audit HTTP, including failures and retries. |
| Database guarantees / S02, S49, S52, S57 | Connection roles still fall back to one URL; production Compose supplies the same database identity to app/worker. No role-provisioning grants were found in migrations/deploy. Migration `0021` explicitly omits foreign keys for signing tables. | Provision separate application, migration/recovery and read-only MCP privileges; enforce immutable artifact/signed-record permissions and required referential constraints. Test setup convenience must not determine production integrity. |
| Recovery / S54–S56 | Implemented restore replaces tables in the current DB, not a staged database-selection switch. Restart is engine disposal, not coordinated process restart. Maintenance blocks patient/encounter mutations but leaves other mutations available. | Close the gap against plan §10.3: isolated staging, complete write fencing, process coordination, verified rollback and login/read/replay before reopening. If retaining table replacement is proposed, obtain an explicit architecture decision; a tracker description alone does not amend the contract. |
| Portable account recovery | Backup omits password hashes; restore preserves matching live hashes and gives staged-only users unusable values. | Demonstrate recovery onto empty replacement storage, including an accessible administrator. Resolve credential recovery semantics explicitly; same-database restore tests do not prove portable recovery. |
| Deployment / S57 | Production Compose and scripts exist, but recorded clean-host drill is unrun. Inspection finds concrete packaging defects, listed below. | Correct packaging and run a fresh disposable Linux install, upgrade, restart and rollback drill. |
| Capacity / S58 | Recorded largest load is 1,000 patients through TestClient on a development host; full 10,000-patient target is unrun. `save_failures()` literally returns zero. | Instrument real save failures; run representative HTTP load through the deployed edge, measure complete admitted models, inference limits and two-worker concurrency/fairness. Record misses honestly. |
| Integrated release / S59–S62 | S59 has no task card or completion entry. S60 assumed it satisfied despite missing content. S61 records rerun-green failures and no single full passing browser run. S62 has no completion evidence. | Restore an explicit S59 gate, stabilize failures, run reviewed-content acceptance, then complete S60/S61 release verification and S62 rehearsal. Preserve earlier engineering evidence without treating it as release acceptance. |

Assessment files for diagnosis, PANSS and C-SSRS currently declare `released`, with approvals recorded in the tracker. Do not reopen those approvals generically. S11's recorded limitation—no dedicated intensity/behavior/lethality inputs—still needs checking against the approved C-SSRS definition and required user workflow before final acceptance.

## 3. Deployment and recovery findings to address

These are source-inspection findings, not claims that a production stack was executed:

1. [nginx.conf](deploy/edge/nginx.conf) starts with `upstream` and `server` blocks, but Compose mounts it as `/etc/nginx/nginx.conf`. A main nginx configuration needs the appropriate `events`/`http` structure, or this file should be included in the proper context.
2. TLS certificate paths are referenced, but [production Compose](deploy/compose.prod.yaml) supplies no certificate mount. Only PostgreSQL has persistent storage; recovery staging/operator logs/maintenance state are not shared or persisted across app/worker containers.
3. [Backend Dockerfile](backend/Dockerfile) copies dependency files and `src`, but not migrations, Alembic configuration, the XML schema, or content. Validate every runtime schema/content path and make explicit migration/release packaging work on a clean host. Images use tags, not the digest pins required by the original bootstrap plan; the image build also installs unpinned `uv`.
4. Production app/worker share the bootstrap database identity instead of configured least-privilege identities. Private MCP transport alone does not make database access read-only.
5. [restore-switch.sh](deploy/restore-switch.sh) prints instructions; it does not execute a switch, restart or restore drill. Process-local engine disposal cannot substitute for restarting/fencing both deployed processes.
6. Backup build jobs run in daemon threads; the tracker leaves interrupted-build recovery and staging retention unfinished. Add bounded lifecycle cleanup for temporary recovery artifacts without deleting clinical/audit history.

Prior tracker entries say Docker was unavailable. `/usr/bin/docker` exists during this audit; daemon availability and the deployment drill were not tested. Reassess the environment instead of carrying forward the old tool-absence claim.

## 4. Recommended execution order

Each numbered item is a work package; split larger packages into coherent three-to-five-slice coding sessions. Use existing T1–T10 seams, one observable red→green behavior at a time. Do not implement all of this in one session.

1. **Repair verification first — S01/S04 completion.** Resolve the current static and collection failures, make test isolation deterministic, and establish a reproducible full backend baseline. Complete the CI setup using disposable PostgreSQL. This work needs no clinical decision.
2. **Repair signing and browser reliability — S49/S60/S61.** Reproduce the recorded `Pinned-network-XML-missing` signing failure with pinned-artifact evidence. Resolve shared-database/reset and cold-start contention; avoid unexplained sleeps, blanket retries or acceptance based only on reruns. Preserve the owner's S51 fresh-reconciliation decision.
3. **Finish content in a separate workstream — S12/S17/S18/S28/S32/S39.** Draft missing R3 inputs for review; correct R7; turn approved history/question dossiers into executable releases; finish DDI review. Validate every collected field through saved draft → scoped projection → CPT request → template output. Build registration (7) and follow-up (6) bundles with exact hashes and no synthetic active defaults. Follow-up can progress through its own gate without waiting for R3, provided all shared dependencies pass.
4. **Close audit and storage guarantees — S02/S49/S52.** Add missing events, privileges and constraints, with upgrade checks and public behavior evidence. Do this before relying on production restore/security acceptance.
5. **Complete recovery and production deployment — S54–S57.** Resolve the restore-contract discrepancy and portable account recovery, fix packaging, then execute actual disposable-host installation/restart/restore/rollback. Keep maintenance and recovery control independent of replaced data.
6. **Complete operational measurements — S58.** Record 10,000-patient deployed load, save/search p95, worker fairness/saturation, real save-failure telemetry, per-model full-CPT size and bounded exact-inference measurements. Use synthetic patient records and controlled providers for engineering tests.
7. **Run S59, then S60/S61 release acceptance, then S62.** Only begin final acceptance once both real content bundles and DDI/history dependencies meet their gates. Earlier synthetic runs remain useful regression evidence.

The owner decisions needed for dependent work are: R3 jurisdiction/setting/authoritative criteria; DDI coverage/release scope; approval of changed clinical package versions; and any proposed departure from the approved restore design. No new approval is needed for the already-approved T1–T10 seams or previously approved unchanged content.

## 5. Concrete next session

**Outcome:** a reproducible verification baseline that can discover application failures reliably. Scope: S01/S04 verification repair, NFR-05 and the account checks for FR-03/04. Seams: existing T1; T9 when completing CI browser setup. No new public interface is proposed.

First observed failure: `make check` stops at Ruff with 33 errors. Separately, full pytest collection stops on three import-file mismatches; mypy reports four account typing errors.

1. Correct reported lint/format/type defects without changing account permissions or weakening assertions. Existing compiler/linter failures are the red evidence; no tests of Markdown or typing constants are needed.
2. Correct pytest module collection with the smallest compatible configuration/package change; prove all assessment and HTTP tests are collected, without excluding duplicate-name files.
3. Run backend suites against explicitly disposable storage, serially where they share state. Fix fixture isolation and owning-module regressions revealed by the complete run. If the signing defect requires a separate session, save a precise reproducible checkpoint rather than marking the baseline complete.
4. Provision clean CI dependencies and its database; run migrations and the documented offline checks. Include browser setup/acceptance in the agreed CI gate, retaining external-provider control.

Checks, from the repository root:

```sh
make check
make test-backend TEST=tests/http/test_physicians.py
make test-backend TEST=tests/http/test_identity.py
make test-backend
make verify
```

Run browser/recovery checks when wiring the expanded CI gate and after affected behavior changes. Do not invoke `make test-load` until its target storage is explicitly disposable: current load tooling can target the development database.

Exit: no static/collection errors; reproducible complete backend evidence; clean-checkout CI setup; honest remaining failures; updated S04/verification handoff. No commit or deployment is implicit.

## 6. Proposed missing S59 task card

**S59 — Verify both workflows with released content.** Depends on released S12/S18/S26–S39 content and completed S46–S50 mechanics. Requirements: FR-14–16, FR-20–22, FR-30–36, NFR-04–05. Seams: T1/T4–T9. This restores the gate already required by AGENTS.md and plan §12.3; it does not introduce a new clinical rule or test seam.

1. Record immutable hashes, source/review provenance and activation evidence for all thirteen question packages, assessments, history, catalog/DDI and both ordered bundles.
2. Run registration and follow-up from saved user inputs through actual worker/MCP/provider protocol, all-CPT validation, exact inference, deterministic templates, physician review and signing. Patient records may be synthetic; released clinical packages cannot be replaced by synthetic stand-ins. A controlled provider is acceptable for offline engineering acceptance; its canned answers are not an independent clinical oracle.
3. Cover true/false/required-unknown applicability, missingness, DDI coverage states, all five transparency fields, note noninterference and rejection of failed/stale/manual-only signing. Use independently worked numerical fixtures and owner-reviewed clinical examples.
4. Replay stored artifacts without provider access, preserve original XML/hashes, and demonstrate signed chronology for both workflows. Link every requirement to concrete evidence and list any separately unrun live-provider check.

Exit: both workflows pass with their released packages and no unresolved content gate. Otherwise S59 remains blocked/in-progress and S62 cannot claim release completion.

## 7. Audit evidence and limits

Fresh checks on 2026-09-24:

| Check | Result |
|---|---|
| `git status --short` | Pre-existing changes in `docs/dev/tasks.md` and graphify outputs/cache; preserved. The existing tasks change removes S59 from S61's direct dependency only; S60 still depends on S59. |
| Graph navigation | Queried existing graph and read wiki index. Broad query was noisy/truncated; direct source inspection supplied the findings above. Graph/wiki coverage differs, so neither was used as a completion ledger. |
| `make check` | Initial sandbox attempt could not write uv cache; authorized rerun reached Ruff and failed with **33 errors**. Later chained checks did not run in that target. |
| `cd backend && .venv/bin/mypy src` | **4 errors**, all in `identity/accounts.py` at lines 303, 350, 403, 479; 63 source files checked. |
| `cd backend && .venv/bin/pytest tests --collect-only -q` | **471 collected, 3 collection errors**: HTTP versus assessment `test_cssrs`, `test_diagnosis`, `test_panss`. This is not a test pass count. |
| T5 `validate_package(*load_package(path))`, all 12 question directories | **11 valid; R7 invalid** with `undeclared_template_state`. Validation alone does not grant activation or clinical validity. |
| Content/source inventory | 12 question packages, all activation-disabled; 3 assessment files marked released; DDI aliases draft; 128 DDI source files, 8,091,001 bytes. |

No application behavior, migrations or clinical content were changed. No database mutation tests, full browser run, load benchmark, production activation, live-provider request or deployment/restore drill was performed in this audit. Existing runtime/database activation state was not queried; statements about release state rely on repository artifacts and explicit tracker records.

Reconcile tracker statuses only after their evidence is complete. Preserve historical entries and add a current summary that distinguishes implemented mechanics, reviewed content, released content and verified operation. There is also no S00 completion entry or dedicated complete content-review ledger visible; consolidate the existing dossiers/approvals into that ledger without inventing missing reviews.
