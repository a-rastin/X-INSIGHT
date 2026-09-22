# X-INSIGHT coding sessions

## Foundation and identity

### S00 — Establish the execution and content review ledger

**Depends:** none. **Requirements:** all, especially FR-30–37/NFR-05. **Seams:** no new tests.

**Read:** plan.md §§1, 5–7, 12; source requirements/design; `BNs/schema.xml`; medical file inventory. **Write:** progress tracker and content review ledger under `content/` when that directory is first needed; no application code.

1. Record the already-confirmed stack, policies, themes, drafting permission and test seams. Do not reopen them as unanswered questions.
2. Reproduce the repository inventory: 11 draft XML files, structural versus executable status, 128 DDI source files unless changed, missing prompts/mappings/templates. Record source hashes and actual discrepancies.
3. Create review entries for assessment wording/periods, history fields/severity, DDI aliases/coverage, each clinical question, and workflow bundles. Include the BN-06 restriction, LAI choice gap, FR-14 regimen mismatch, missing hospitalization/involuntary-care networks, and reference-table assumptions.
4. Define each review package's deliverables and exact approval record; prepare owner questions only for substantive missing content, with concrete proposed choices. Infrastructure remains eligible while responses are pending.

**Verify/exit:** ledger covers every question in plan.md §7.1 and names the owner as reviewer without claiming approval. Handoff identifies the first engineering session and content tasks. No clinical parameters or arbitrary uniform CPTs are created to hide gaps.

### S01 — Bootstrap a reproducible development loop

**Depends:** S00. **Requirements:** NFR-01, NFR-05. **Seams:** T1/T9 smoke only.

**Read:** plan.md §§3, 11–12. **Files:** `backend/pyproject.toml`, `backend/uv.lock`, `web/package.json`, npm lockfile, `B/app.py`, minimal `W/app/`, `compose.yaml`, `Makefile`, `.env.example`, minimal CI configuration.

1. Select compatible Python/Node/PostgreSQL/library versions using primary documentation and a small installation smoke; pin them. Verify pgmpy and MCP SDK compatibility explicitly; do not copy an untested version from this plan.
2. Create the minimum FastAPI process and React/Vite page. Add a failing public health check, then implement the response. Add a browser smoke that loads the X-INSIGHT shell; no fake clinical screens.
3. Create disposable local PostgreSQL and test databases, locked install commands and the Make targets in plan.md §12.2. Targets for not-yet-created suites must report that clearly rather than claim success.
4. Wire formatting, lint/types, build and offline CI startup. Document local ports, environment placeholders and how to stop the stack. Do not seed clinical content.

**Verify:** fresh locked install, health/browser smoke, `make check`; no credentials in tracked files. **Exit/handoff:** another agent can start the same stack from documented commands and knows the pinned runtime versions.

### S02 — Establish real persistence and request contracts

**Depends:** S01. **Requirements:** NFR-04–05, cross-cutting FR-42. **Seams:** T1.

**Read:** plan.md §4. **Files:** `B/db.py`, `B/contracts.py`, `B/operations/audit.py`, initial Alembic migrations, `BT/http/test_contracts.py`.

1. Create application/migration/read-only database roles, connection lifecycle, schema migration entry point and isolated test fixture lifecycle. Do not create every future domain table now.
2. Through public health/readiness, fail on unavailable/incompatible schema and return safe readiness state; implement request correlation and the standard error body without tracebacks.
3. Establish shared revision/idempotency conventions and transaction-scoped audit insertion for subsequent command implementations. Add only storage needed now; first meaningful mutation behavior is tested in S03/S06, not with a test-only production endpoint.
4. Document canonical JSON/hash behavior and UTC serialization at their actual public uses. Add size limits and structured validation errors to the HTTP interface.

**Verify:** migrated fresh database, unavailable-database readiness, no secret traceback, `make check`. **Exit:** all future modules can use one transaction context; audit permissions are prepared without adding a generic repository layer.

### S03 — Implement login, sessions, and own credentials

**Depends:** S02. **Requirements:** FR-01–02, FR-04, NFR-02. **Seams:** T1. **Tests:** `BT/http/test_identity.py`.

**Files/read:** plan.md §§2.1, 4.3, 11; `B/identity/`, identity migration.

1. Red: a fresh database permits `admin/admin`, a second initialization preserves a changed password, and no second admin can be provisioned. Implement singleton seeding and standard password hashing.
2. Red: login returns an opaque cookie session and `/me`; wrong credentials or selected role mismatch cannot grant access. Implement generic errors, active-account checks, CSRF and login throttling.
3. Red: logout/password change revokes prior sessions; advancing a controlled clock does not cause idle/absolute session expiry. Implement credential revision checks without a timeout or complexity rule.
4. Red: admin username mutation/self-registration is denied; empty password input fails without silently trimming passwords. Audit successes/failures with no credentials in event payloads.

**Verify/exit:** HTTP identity suite with real PostgreSQL, cookie behavior on local/HTTPS configuration, masked error inspection. Handoff records session revocation behavior and the authenticated test-fixture interface.

### S04 — Implement physician account administration

**Depends:** S03. **Requirements:** FR-03–04, FR-42. **Seams:** T1. **Tests:** `BT/http/test_physicians.py`.

**Files/read:** plan.md §2.1; `B/identity/` account commands/routes and migration.

1. Red: admin creates/edits a physician and retrieves safe fields; physician cannot list credentials/manage accounts or elevate their role. Preserve stable actor IDs across rename.
2. Red: reset/deactivation revokes existing sessions immediately and inactive users cannot authenticate. Implement revision requirements and reactivation.
3. Implement the deactivation command's explicit retain/discard choice and draft-set revision contract. Until drafts exist, the reviewed set is empty; S51 adds the real draft/job race cases. Do not fabricate draft tables solely for this test.
4. Red: repeated account commands respect idempotency/conflicts, audit has safe attributed events, and no response includes a hash or raw password.

**Verify/exit:** account authorization/revocation checks pass. Handoff specifies the later Cases integration point for confirmed draft discard, explicitly marked incomplete until S51.

### S05 — Build role navigation and both themes

**Depends:** S03–S04. **Requirements:** FR-01, FR-03, NFR-03. **Seams:** T1/T9. **Tests:** `e2e/identity.spec.ts`, `e2e/themes.spec.ts`.

**Read/files:** `docs/dev/ui-context.md`, plan.md §9; `W/app/`, `W/shared/theme.css`, `W/features/identity/`, theme preference route.

1. Red browser journey: login → correct role dashboard; Register shows “Contact administrator”; every physician login shows the exact research warning before proceeding.
2. Add role-owned navigation, identity/sign-out, own password form and admin physician table/forms. Route guards complement server checks, never replace them.
3. Design deliberate light/dark semantic tokens consistent with the approved visual character. Persist theme via `/me/preferences`; check contrast, especially small labels on teal. The owner already authorized palette design.
4. Exercise keyboard focus, associated error labels, reduced motion and generic login errors. Render loading/empty/error states from real endpoints; no placeholder medical recommendations.

**Verify:** both browsers for identity; theme contrast/keyboard evidence and build. **Exit:** administrator can create a physician through the browser; both can log in and change own password/theme.

## 4. Records and assessments

### S06 — Register and find a patient

**Depends:** S03, S05. **Requirements:** FR-10, FR-23. **Seams:** T1/T9. **Tests:** `BT/http/test_patients.py`, `e2e/registration.spec.ts`.

**Files/read:** plan.md §§2.2–2.3, 4; `B/cases/patients.py`, routes/schemas, patient/encounter migration, `W/features/patients/`.

1. Red: valid physician creation atomically returns patient plus registration draft, server timestamp and revision; admin cannot create. Patient ID `0012345678` round-trips unchanged.
2. Red: ages 17/100, decimal ages, non-ASCII digits, malformed ID, missing sex/status, and invalid name characters fail with field errors. Include a valid Unicode-letter name after normalization.
3. Red: simultaneous same-ID requests produce exactly one patient; a duplicate archived ID also conflicts. Repeated idempotent creation returns original IDs.
4. Add directory search by name/ID, clinical-status filter, bounded pagination and demographics form with Next disabled until valid. Results remain shared across physicians.

**Verify/exit:** real concurrent HTTP uniqueness check, browser create/search, migration upgrade. Do not add delete/merge or store the identifier numerically.

### S07 — Persist, resume, and discard author-owned drafts

**Depends:** S06. **Requirements:** FR-16, FR-22, NFR-04. **Seams:** T1/T9. **Tests:** `BT/http/test_drafts.py`, `e2e/autosave.spec.ts`.

**Files/read:** plan.md §§2.3, 4; `B/cases/encounters.py`, `W/features/encounters/` wizard/autosave.

1. Red: author saves and retrieves a draft after application restart; other physician/admin can read but cannot mutate. Add revisions and draft state transitions.
2. Red: stale-tab PATCH fails `412`; client retains unsaved edits and offers reload/reconcile. Implement debounced save, page-transition flush, saving/saved/failed states.
3. Red: failed network/database save never shows Saved; navigation warns while local edits remain. Unsaved initial demographics are not advertised as durable.
4. Red: discard requires explicit confirmation/current revision, removes resumability, retains an audit tombstone and does not delete the patient. Jobs cancellation is integrated once jobs exist.

**Verify/exit:** multi-tab browser case and restart recovery. Handoff documents revision ownership so later assessment pages use the same autosave path, not separate persistence mechanisms.

### S08 — Draft assessment definitions and implement the evaluation interface

**Depends:** S00, S07. **Requirements:** FR-11–13, NFR-05. **Seams:** T2/T1. **Tests:** `BT/assessments/test_definitions.py`.

**Read/files:** plan.md §5; all three assessment source documents; `content/assessments/`, `B/assessments/`, released-definition routes.

1. Draft exact item/schema/period/branching/completeness/result definitions for owner review, with source hashes and uncertainty explicitly identified. Preserve C-SSRS paraphrase status.
2. At T2 implement validated definition loading and `evaluate(definition, answers)` using a tiny synthetic definition first. Red: unanswered/partial/complete/not-assessed are distinguishable and no missing answer becomes zero.
3. Reject undeclared item IDs, invalid values, unknown rule operators and arbitrary executable expressions. Expose only released definitions through authenticated content routes; retain drafts for review.
4. Prepare independent examples for S09–S11 and obtain owner review on the concrete forms/rules. Pending review blocks only the corresponding clinical form implementation; generic infrastructure can finish.

**Exit:** executable definition contract and review packages exist. Mark this session's content gate awaiting_review until approved; do not use this session to invent treatment thresholds.

### S09 — Implement diagnosis, threshold warning, and bypass

**Depends:** S08 diagnosis package approved; S07. **Requirements:** FR-11, FR-16. **Seams:** T2/T1/T9. **Tests:** `BT/assessments/test_diagnosis.py`, `e2e/diagnosis.spec.ts`.

**Files/read:** reviewed definition, `schizophrenia-criteria.md`, plan.md §§2.2, 5; assessment evaluator and `W/features/assessments/diagnosis/`.

1. Red: approved qualifying worked case satisfies every required criterion; a case with only symptom count satisfied does not. Implement the reviewed full criterion logic and live preview.
2. Red: partial answers have no completed threshold result. Save incomplete work without mislabeling it as below threshold.
3. Red: a completed below-threshold case continues only after an attributed warning acknowledgment tied to the assessed revision. Later relevant edits invalidate the acknowledgment.
4. Red: bypass succeeds without any reason field, records actor/time/status, and survives resume. Implement UI that makes bypass distinct from completion and uses the shared autosave contract.

**Verify/exit:** evaluator reference cases, direct HTTP enforcement, browser threshold/bypass/resume. There is no fabricated diagnostic probability.

### S10 — Implement PANSS without implicit minimum answers

**Depends:** S08 PANSS approved; S07. **Requirements:** FR-12, FR-20. **Seams:** T2/T1/T9. **Tests:** `BT/assessments/test_panss.py`, `e2e/panss.spec.ts`.

**Files/read:** `PANSS.md`, reviewed definition; evaluator, PANSS UI and saved answers.

1. Red: fresh form has 30 unanswered items and null total; Skip persists `not_assessed`. Implement explicit selection only.
2. Red: fully answered all-1 yields 7/7/16/30 and all-7 yields 49/49/112/210; implement approved arithmetic and value validation.
3. Red: one missing required item suppresses total, invalid/out-of-range/noninteger input is rejected server-side, resumed answers preserve completeness.
4. Show subscales/items, assessment window and prior encounter score as historical. Add only reviewed interpretation/change rules; do not derive a treatment gate from approximate score bands.

**Verify/exit:** independent literal fixtures, browser skip/partial/resume and source-version persistence. No default “1” values or hidden zero scores.

### S11 — Implement C-SSRS form and distinct results

**Depends:** S08 C-SSRS approved; S07. **Requirements:** FR-13, FR-20. **Seams:** T2/T1/T9. **Tests:** `BT/assessments/test_cssrs.py`, `e2e/cssrs.spec.ts`.

**Files/read:** `CSSRS.md`, owner-selected form/time windows, plan.md §5; C-SSRS evaluator/UI.

1. Red: all unanswered and skipped produce no assessed result; complete explicit negatives produce the reviewed no-ideation result. Implement selected branching/completeness.
2. Red: reviewed worked example with level 3 endorsed gives severity 3 without auto-filling lower responses; intensity/behavior/lethality remain separate.
3. Red: historical versus current answers retain their periods; incomplete required branch has missing-item guidance, not a guessed negative. Implement only approved alert logic.
4. Browser renders persistent review/urgent messages with text and keyboard access; switching pages/autosave cannot erase responses or turn a skip into zero.

**Verify/exit:** source-approved examples, no composite risk score, direct HTTP value/period validation and browser resume.

### S12 — Draft and implement structured history and adverse effects

**Depends:** S08, S07; field review before clinical activation. **Requirements:** FR-14, FR-20–21. **Seams:** T2/T1/T9. **Tests:** `BT/http/test_history.py`, `e2e/history.spec.ts`.

**Read/files:** plan.md §5 and question-input leads, four adverse-effect criteria documents; `content/history/`, `B/cases/` history/effects, history UI.

1. Draft the minimum typed history fields, clinical periods, analysis-visible text label and severity definitions for owner review. Include mapping gaps required by networks; do not add FR-14-excluded medication regimen fields.
2. Red after review: history values persist with provenance, unknown/not-assessed distinct from false; undeclared/excluded fields fail validation.
3. Red: each of four effects accepts present/absent/not-assessed; present requires reviewed severity, absent/not-assessed has null severity. Changing status must explicitly clear an obsolete severity.
4. Add optional phone update and history reconciliation state for follow-up; clearly distinguish analysis-visible history from page notes. Do not automatically mandate complete BARS/SAS/AIMS questionnaires.

**Verify/exit:** author/revision rules inherited from S07, reviewed field fixtures, browser saved-state behavior. Mapping additions later must update the content version and these public checks.

### S13 — Add attributed page notes and prove separation

**Depends:** S07. **Requirements:** FR-16, FR-22. **Seams:** T1/T9. **Tests:** `BT/http/test_notes.py`, `e2e/notes.spec.ts`.

**Files/read:** plan.md §2.3; note storage/commands and reusable wizard note control.

1. Red: author adds a timestamped note to any wizard page and sees it after resume; a retried idempotent command creates one note.
2. Red: another physician/admin cannot author/edit the draft's notes; actor/time are server-derived. Treat notes as append-only entries; correction in a draft can be a new note.
3. Render notes separately from history, with page/author/time, and support the demographics page after initial draft creation. Escape text; test literal markup rendering.
4. Define the explicit serializer exclusion used by future snapshots, but do not create speculative snapshot machinery here. Record S40/S41/S59 as mandatory end-to-end note-noninterference checks.

**Verify/exit:** public HTTP persistence/ownership and browser placement pass. A page note is never relabeled algorithm-visible history.

### S14 — Build shared chart and follow-up draft entry

**Depends:** S09–S13. **Requirements:** FR-20–23. **Seams:** T1/T9. **Tests:** `BT/http/test_followup.py`, `e2e/followup.spec.ts`.

**Files/read:** plan.md §§2.2–2.3; `B/cases/` chart/follow-up commands, `W/features/patients/chart/`. Use a test-only signed baseline fixture until S49 implements signing; S49 is not a dependency of this session.

1. Red: any active physician can read the chart and create their own follow-up against a signed baseline; another physician cannot edit it. Expose other open drafts read-only.
2. Red: history/medications copy with baseline provenance and reconciliation required, but PANSS/C-SSRS start unanswered. Display prior scores/dates distinctly.
3. Red: two physicians can create separate drafts, and each sees a changed baseline indicator after a newer signed record appears. Actual sign reconciliation is enforced in S49/S51.
4. Build chronology, draft badges, phone/history/effect pages, and navigation to review. Until reasoning exists, show unavailable generation honestly; no fake successful proposal.

**Verify/exit:** follow-up creation/resume and shared-read journey. Temporary signed fixtures stay test-only and do not add a bypass-sign production route.

## 5. DDI ingestion, review, and checking

### S15 — Parse one source through the ingestion interface

**Depends:** S02. **Requirements:** FR-14, NFR-05. **Seam:** T3. **Tests:** `BT/ddi/test_ingestion.py`.

**Read/files:** plan.md §6; DDI design §§5–8/17–19; actual `docs/medical-docs/DDI-text/Antidiabetic Agents/Sitagliptin.txt`; `B/ddi/ingestion.py`, CLI entry point, candidate output schema.

1. Record the fixture's original checksum, real category headings, expected counts and representative source spans. Keep the original source unchanged; fixture references/copies must record provenance.
2. Red at `build(...)`: discover the monograph and identify its actual interaction section, ignoring earlier navigation/summary headings. Implement minimal section/state handling.
3. Red: preprocessing preserves original line spans while removing repeated page chrome, handles BOM/line wrapping, and stops before Adverse Effects/Warnings. Do not test the private preprocessor separately.
4. Red: candidate report contains exactly 0/4/92/70 entries by source category, raw text and traceable spans. A deliberately removed entry fails count validation and still produces an anomaly report.

**Verify/exit:** build interface and CLI agree; no SQL/runtime checker yet. Expected counts come from the monograph, not the parser's own totals. Do not call an LLM to obtain passing counts.

### S16 — Extend the parser across real source formats

**Depends:** S15. **Requirements:** FR-14, NFR-05. **Seam:** T3. **Tests:** extend `BT/ddi/test_ingestion.py` only for distinct observed formats.

**Read/files:** representative monographs discovered from at least three different source groups; `B/ddi/ingestion.py` and fixture/source manifest.

1. Inspect the corpus for real heading/continuation/entry variants; select one failing representative at a time. Add a public build assertion for the expected source-derived entries, then support that format.
2. Red: page-break continuation and wrapped entity headings preserve complete text and original span references; next sections are never swallowed as interactions.
3. Red: repeated pair entries and contradictory severity assertions survive ingestion; Sitagliptin/ofloxacin retains both categories. Preserve direction only when explicitly supported, otherwise mark unknown.
4. Run the entire corpus in report-only mode. Every discovered file has passed/failed status, category counts, checksum and diagnostic location. Failures cannot quietly disappear from denominators.

**Verify/exit:** complete 128-file discovery unless sources changed; all anomalies are enumerated, not necessarily resolved. Handoff lists each unsupported format and source evidence for the next review/repair session. Split into S16.a/b if real variants exceed a bounded session.

### S17 — Resolve controlled medication concepts and aliases

**Depends:** S15–S16. **Requirements:** FR-14. **Seam:** T3 through resolved/unresolved concepts in build output; T4 repeats runtime checks in S19. **Tests:** `BT/ddi/test_terminology.py`.

**Files/read:** plan.md §6.1; `content/ddi/aliases.json`, concept schema, normalization implementation inside `B/ddi/`.

1. Draft concepts for bundled selectable medications and interacting entities, separating ingredients, combinations, herbs/foods/substances. Record source-backed brand aliases; request review for uncertain equivalences.
2. Red: canonical/case/whitespace/approved alias variants resolve to one stable ID; ambiguity yields unresolved rather than choosing the first row.
3. Red: look-alike names remain distinct; unknown name stays unknown; salt removal, strength stripping and combination splitting are not applied without reviewed rules. Patient inputs remain drug-only.
4. Red: canonical unordered pair identity is stable under input reversal while the source assertion's subject/object remain unchanged. Export unresolved names and alias collisions for review.

**Verify/exit:** approved aliases, explicit pending decisions, no fuzzy matcher/external terminology dependency. Do not count an unresolved entity as proof of complete source coverage.

### S18 — Build, review, and publish an immutable DDI release

**Depends:** S16–S17, S02. **Requirements:** FR-14, NFR-05. **Seams:** T3/T1. **Tests:** `BT/ddi/test_publish.py`.

**Files/read:** plan.md §6.2; `B/ddi/` publication CLI, DDI migrations, `content/ddi/` review manifest and report.

1. Red: publication rejects count failures, unresolved entities needed by the release, absent provenance and required unreviewed evidence. Implement dataset staging/import as one coherent operation.
2. Draft the corpus report: discovered/processed/pass/fail documents, severity counts, unique pairs, duplicates/conflicts, unknown names, hashes and parser version. Give the owner concrete high-risk/conflict/anomaly review records.
3. Incorporate approved corrections without modifying originals. Preserve independent duplicate-direction evidence and separate source severity from management. Publish only an explicitly approved complete or limited-coverage release.
4. Red: repeated publication of identical content is idempotent; changing a source creates a new candidate version; interrupted/invalid publication leaves the previous released dataset available.

**Verify/exit:** owner-reviewed release hash, reproducible import report and source/alias inventory. If review is pending, mark awaiting_review and continue with synthetic DDI fixtures; do not claim the corpus is ready or omit excluded sources from limitations.

### S19 — Implement deterministic coverage-aware DDI checking

**Depends:** S17–S18 (synthetic release acceptable for mechanics). **Requirements:** FR-14–15. **Seams:** T4/T1. **Tests:** `BT/ddi/test_checker.py`, `BT/http/test_ddi.py`.

**Read/files:** plan.md §6.3; `B/ddi/checker.py`, indexed lookup and `/ddi/check`, catalog search route.

1. Red: A/B and B/A yield the same pair/evidence; three unique drugs yield three pairs; duplicate aliases do not create self-pairs. Implement batched indexed lookup.
2. Red: known evidence produces `interaction_found` with every assertion, highest known severity and conflict/unknown indicators; directional descriptions are retained.
3. Red: no evidence with explicit coverage produces `covered_no_listed_interaction`; no evidence without coverage and all unknown-drug pairs produce `coverage_unavailable`. Zero/one-drug reports remain valid with unresolved warnings.
4. Red: report pins dataset/catalog/fingerprint, refuses invalid dataset/configuration, rejects excluded medication fields, and executes with external network access disabled.

**Verify/exit:** source-backed checker fixture plus all three status fixtures; role/session enforcement. Never use “safe” or synthesize an absence-of-interaction claim from missing rows.

### S20 — Integrate medications and DDI into encounter history

**Depends:** S12, S19. **Requirements:** FR-14–16, FR-20. **Seams:** T1/T9. **Tests:** `BT/http/test_medications.py`, `e2e/ddi.spec.ts`.

**Files/read:** plan.md §§2.2, 6, 9; medication draft storage, history UI, DDI evidence panel.

1. Red browser journey: search/select catalog medication, add explicit unknown label, save/resume drug-only list. Server rejects dose/unit/route/frequency/status fields even if forged.
2. Red: changed medications trigger a fresh versioned report and show pending/error state until the current fingerprint matches. Do not present a stale report as current.
3. Display severity, raw evidence/source location, conflicts, and coverage warnings, including an unknown medication with zero known pairs. Escape all source and user text.
4. Follow-up requires explicit reconciliation of copied medications; previous signed lists/reports remain unchanged. Persist current report reference for later run snapshots.

**Verify/exit:** browser known/unknown/conflict path and HTTP readback; DDI works while provider configuration is absent. Content approval for S18 still gates release of real data.

## 6. Model machinery and content packages

### S21 — Safely import and inspect XMLBIF drafts

**Depends:** S02. **Requirements:** FR-31, FR-37, NFR-05. **Seam:** T5. **Tests:** `BT/models/test_xml_validation.py`.

**Read/files:** plan.md §7.3; `BNs/schema.xml`, existing `BNs/test_schema.py`, sample BN-04 and BN-08; `B/models/validation.py`.

1. Red through validation interface: valid synthetic XML returns ordered parsed nodes/edges and a separate XSD report. Reuse the supplied schema; preserve source bytes/hash.
2. Red: DTD/entity, remote resolution, excessive input, malformed XML and unsupported content fail safely with bounded locations/messages. Configure the parser explicitly; do not rely on defaults.
3. Red: existing draft networks can be stored/inspected as drafts despite missing definitions; graph display must not convert `proposed_parent` properties into authoritative edges.
4. Read/export retains original state/parent order and metadata. Report multiple-network documents or unsupported kinds as nonactivatable under v1 rather than silently selecting/dropping nodes.

**Verify/exit:** new public validation tests plus existing schema checks. XSD success is never labeled executable/clinically valid. Do not alter source XML to make it fit the application.

### S22 — Enforce model semantics and admission limits

**Depends:** S21. **Requirements:** FR-31–32, FR-37, NFR-04. **Seam:** T5. **Tests:** `BT/models/test_model_admission.py`.

**Files/read:** plan.md §7.3; model validation and small synthetic XML fixtures.

1. Red: a valid XSD with a cycle, missing CPT, wrong dimensions, invalid normalization or empty outcomes is nonexecutable with distinct semantic errors. Implement checks after structure validation.
2. Red: valid root/parent ordering and complete finite probabilities pass; unsupported decision/utility nodes remain drafts. Supplied BNs all remain inactive.
3. Red: missing question mappings/prompts/templates, note source paths, unreviewed package, undeclared query/state or unsafe expression prevents activation. Do not make a JSON `reviewed=true` field alone sufficient without a review record.
4. Add configured XML/node/CPT-cell limits and deterministic admission diagnostics. Numeric thresholds are engineering limits selected from actual model measurements, not clinical thresholds.

**Verify/exit:** XSD-valid-but-semantic-invalid regression fixtures and clear import-versus-activation distinctions. Handoff identifies the contract validation hooks S25 will fill without inventing patient mappings.

### S23 — Validate every CPT and run reproducible exact inference

**Depends:** S22. **Requirements:** FR-33–34, NFR-04. **Seam:** T5. **Tests:** `BT/models/test_cpt_inference.py`.

**Files/read:** plan.md §7.4; `B/models/inference.py`, effective-artifact schema, pinned engine adapter.

1. Red: full two-node response yields `.22`, `.70`, and `7/11` for the specified queries. Implement percentage validation/conversion and exact inference without using base-table fallbacks.
2. Red: omitted root/table/row, duplicate row, changed order/state/parent, booleans/strings/nonfinite values, out-of-range values and wrong sums are rejected. Add cases one at a time; never normalize.
3. Red: asymmetric multi-parent fixture detects XMLBIF-to-engine transpose bugs; registered XML/hash stays unchanged while effective XML contains all accepted tables.
4. Red: replay of frozen artifacts matches within tolerance with provider unavailable; impossible evidence and resource exhaustion return explicit errors without approximation. Use a bounded child process where limits require it.

**Verify/exit:** independently worked numerical fixtures, metadata/order preservation, pinned runtime record. If resource isolation is too large, checkpoint S23.a validation/conversion and S23.b bounded inference; both must pass before integration.

### S24 — Build model version administration and read-only graph

**Depends:** S21–S23, S25, S05; execute S25 first. **Requirements:** FR-03, FR-37. **Seams:** T1/T5/T9. **Tests:** `BT/http/test_networks.py`, `e2e/networks.spec.ts`.

**Files/read:** plan.md §7.3; `B/models/registry.py`, registry migrations/routes, `W/features/admin/networks/`.

1. Red: admin imports/edits/exports XML as immutable versions; physician is denied; editing preserves prior bytes/hash and validation reports.
2. Red: graph renders actual ordered nodes/edges/readable states and validation status; no graphical edit operation exists. Use a small established layout dependency only if needed for readable networks.
3. Red: activation rejects incomplete/unreviewed workflow bundles, and valid activation/rollback is atomic with pointer revision and audit. Use synthetic complete bundles until S39.
4. Red: activation of a new version leaves a previously referenced version retrievable; stale pointer mutation fails. Display version history, validation details and explicit activation/rollback confirmation.

**Verify/exit:** admin browser import→inspect→version→activate/rollback journey and direct authorization checks. No draft BN is active by default.

### S25 — Define the reusable question-package contract and review harness

**Depends:** S21–S23; S08/S12 draft content inventory. **Requirements:** FR-30–35. **Seam:** T5. **Tests:** `BT/models/test_question_packages.py`.

**Read/files:** plan.md §§5, 7.1–7.2; `content/questions/` schema/review template, package loader/validator, synthetic package fixtures.

1. Red: a complete synthetic package validates fixed variables/types/states/order, typed patient mappings, gate/missingness rules, all-CPT contract, query, prompt, template, and review references.
2. Red: unknown source path, note mapping, implicit posterior chaining, unapproved double-use of facts, incomplete CPT schema, or arbitrary expression is rejected. Do not invent a generic workflow language.
3. Define the review dossier used in S26–S38: source comparison, explicit graph, complete reference-table provenance, estimation instructions, result mapping/wording, independent numerical and clinical examples, admission measurements and open assumptions.
4. Define template content with escaped-value slots and explicit branches; no LLM prose or unreviewed argmax treatment selection. Through package validation, reject references to undeclared output states and unsupported operators. Runtime section rendering is implemented and tested through the pipeline in S45.

**Verify/exit:** future question sessions change content, not thirteen separate Python pipelines. Draft packages can be validated without being activated; owner review is a separate recorded decision.

### Common contract for S26–S38

These are **content-authoring sessions with implementation-ready outputs**, not permission to activate clinical models. Each depends on S25 and its relevant reviewed assessment/history meanings. If those meanings are pending, draft alternatives and flag them instead of silently choosing.

For each session create `content/questions/<key>/{manifest.json,network.xml,prompt.txt,template.json,examples.json,review.json}`. Preserve original BNs. The package must cover every field in plan.md §7.2, explicit observed/CPT-context usage, true/false/unknown gates, missing/conflict policy, output-to-template mapping, all-CPT response shape including roots, and approved source/reference-table provenance. Propose any necessary history additions as versioned changes for review.

Run the S25 validator and S23 inference harness on independently worked examples through T5. Add one meaningful behavior fixture at a time when expected behavior is agreed. Agent-drafted clinical expected outputs are review candidates until approved; they cannot validate themselves. Hand off a readable rationale and the exact package hash. Use `awaiting_review` until the owner approves. Approval may be batched in S39 after all dossiers are concrete. Unanswered clinical/legal choices block package release, not generic engineering.

### S26 — Draft hospitalization question

**Key:** `hospitalization` (R1). **Requirements:** FR-30–35. **Sources:** guideline assessment/treatment-planning documents, approved diagnosis/suicide/history definitions; no existing corresponding BN.

1. Enumerate the specific hospitalization question, intended setting/time horizon, observed inputs and output meanings. Ask for unresolved setting/disposition policy using a concrete proposal; do not infer admission law or a universal risk cutoff.
2. Draft one fixed discrete graph with stable states and reviewed input definitions. Include only collected patient variables; propose missing structured fields for owner review.
3. Draft estimation prompt, complete reference/response tables with provenance, and predefined physician-review wording for each output/gap. The LLM supplies all CPTs, never the disposition text.
4. Prepare ordinary/urgent/required-missing cases and an independently worked small numerical case. No urgent guidance may depend on waiting for a successful LLM request.

**Exit:** complete review dossier or precise unresolved inputs, not an active placeholder. S39 decides workflow admission after review.

### S27 — Draft pharmacotherapy question

**Key:** `pharmacotherapy` (R2). **Requirements:** FR-14, FR-30–35. **Sources:** BN-04, STATEMENT-04, reviewed catalog/history.

1. Compare BN-04's established-treatment review scope with registration pharmacotherapy selection. Document which nodes/edges cannot satisfy the required question as written, including metadata-only parents.
2. Draft a fixed scope and graph, explicit medication output identifiers tied to the catalog, and source-backed treatment-context definitions. Resolve excluded dose/route/etc. inputs through content redesign, not hidden form fields.
3. Draft outcome-to-template mapping, missing-data behavior and all-CPT estimation instructions. DDI findings remain a separate report; do not substitute DDI lookup for pharmacotherapy inference.
4. Supply worked cases for different relevant patient contexts and unknown required input, with proposed clinical expectations labeled for review and separate independent mathematical fixtures.

**Exit:** new versioned package and source-diff rationale; original BN-04 remains untouched. Do not call the existing draft a complete initial-choice network.

### S28 — Draft involuntary-care question

**Key:** `involuntary_care` (R3). **Requirements:** FR-30–35. **Sources:** owner-supplied jurisdiction/setting criteria plus relevant local clinical documents; no matching BN.

1. Prepare a concrete list of required legal/clinical context and ask the owner for jurisdiction and authoritative criteria. Do not turn a generic symptom or suicide score into legal eligibility.
2. Draft the information-collection graph and explicit unknown behavior. If legal inputs remain unavailable, retain a nonactivatable draft and enumerate exactly what is missing.
3. After source selection, draft fixed states, complete CPT contract, prompt and review-oriented template with source date/version. Clinical and legal review assumptions remain explicit.
4. Prepare meets/does-not-meet/unknown examples supplied or reviewed by the owner, plus independent numerical checks. Seek up-to-date primary legal sources if this session must interpret jurisdictional rules.

**Exit:** reviewed criteria attached before release; no invented legal rule, automatic detention action, or successful “not applicable” used to hide missing content.

### S29 — Draft high-suicide clozapine question

**Key:** `high_suicide_clozapine` (R4). **Requirements:** FR-13, FR-30–35. **Sources:** BN-08, STATEMENT-08, approved C-SSRS/history.

1. Distinguish current urgent findings, high-risk gate, persistent risk despite prior treatment, and the network's review output. Specify periods and structured provenance; a scale level alone is not an unreviewed treatment rule.
2. Resolve BN-08's missing priors and deterministic review-table assumptions under all-CPT estimation. Record every retained/changed state and observation-versus-estimation use.
3. Draft complete prompt/template mapping preserving parallel urgent/review concerns. A false gate is not a negative posterior; unknown required gate pauses the question.
4. Prepare true/false/unknown gate examples and result-rendering examples reviewed by the owner; include a mathematical fixture separate from clinical correctness.

**Exit:** complete package ready for owner review, with urgent assessment handling independent of LLM latency and no fabricated risk percentage presented as scale output.

### S30 — Draft combined LAI indication and choice question

**Key:** `lai_indication_choice` (R5). **Requirements:** FR-30–35. **Sources:** BN-10, STATEMENT-10, reviewed catalog/history/preferences.

1. Identify the exact indication and choice outputs required by FR-30. BN-10's discussion pathway alone is insufficient; draft the missing choice contract and admissible catalog identifiers.
2. Keep one XMLBIF network, one prompt and one question step. Define when choice is rendered after indication, and what absence/uncertainty of preference or prior exposure means.
3. Resolve source input needs without introducing excluded medication regimen fields. Draft full CPT estimation, explicit state ordering and result-to-template branches for indication/no-indication/uncertain choice.
4. Prepare independent fixtures proving choice is suppressed or shown under the reviewed condition while other review findings remain visible. Record owner decisions on product-choice assumptions.

**Exit:** one reviewed combined package, not two networks or a runtime LLM recommendation.

### S31 — Draft aggression clozapine question

**Key:** `aggression_clozapine` (R6). **Requirements:** FR-30–35. **Sources:** BN-09, STATEMENT-09, reviewed history.

1. Specify substantial/persistent aggression and prior-treatment context with source periods and clinician-reported fields. Do not silently equate PANSS hostility with the gate.
2. Draft graph/reference tables and the all-CPT contract, including root distributions and explicit missingness. Resolve deterministic-rule versus estimated-table semantics for review.
3. Draft a predefined review template preserving urgent and parallel concerns, separate from an autonomous treatment decision.
4. Supply true/false/unknown gate and result-mapping examples, with source-based clinical review expectations and independent numerical fixtures.

**Exit:** source-linked package hash and review dossier, including any new approved history field definitions. No missing finding is mapped to “No”.

### S32 — Draft established-case clozapine question

**Key:** `established_case_clozapine` (R7). **Requirements:** FR-10, FR-30–35. **Sources:** BN-07, STATEMENT-07, reviewed treatment-history definitions.

1. Make established clinical status an explicit applicability input. Define the further clinical review criteria, trial adequacy and observation windows without inventing thresholds or forbidden medication details.
2. Distinguish this registration question from F5 no-improvement follow-up; do not share one ambiguous package identity even if sources overlap.
3. Draft complete graph/prompt/CPT/template and source-diff rationale, including monitoring/willingness inputs only when defined and collected.
4. Prepare first-time false-gate, established applicable, and missing trial-context cases. Expected outcomes require owner review; mathematical fixtures remain independently calculable.

**Exit:** distinct registration package and reviewed input inventory. A first-time case does not receive a fake negative clozapine posterior when skipped.

### S33 — Draft tardive-dyskinesia follow-up question

**Key:** `tardive_dyskinesia` (F1). **Requirements:** FR-20–21, FR-30–35. **Sources:** BN-14, STATEMENT-14, tardive-dyskinesia criteria and approved severity definition.

1. Map explicit effect presence and reviewed severity to the network; distinguish absent from not assessed. Do not infer the diagnosis from an unreviewed AIMS total.
2. Resolve source-required context/alternative explanations and missing input policy. Draft any new field for review before using it in a projection.
3. Draft fixed graph, full CPT estimation and templates with all relevant findings retained, avoiding unsupported treatment thresholds.
4. Provide effect-present/absent/not-assessed gate cases and severity/result cases. Validate explicit node/state ordering and one complete package, not copied BN-14 activation metadata.

**Exit:** review dossier and independent examples; original draft's disabled-inference status is not silently bypassed.

### S34 — Draft akathisia follow-up question

**Key:** `akathisia` (F2). **Requirements:** FR-20–21, FR-30–35. **Sources:** BN-13, STATEMENT-13, akathisia criteria.

1. Define how the approved present/absent/not-assessed and severity fields relate to source concepts. BARS item discussion does not authorize an invented summed severity rule.
2. Draft required context, fixed graph/states, missingness and observation/CPT-context usage, explicitly distinguishing motor restlessness from unreviewed differential assumptions.
3. Create full-CPT prompt and deterministic result/template mapping. Preserve source reasoning provenance and parallel review needs.
4. Provide true/false/unknown gates and approved severity/result examples plus numerical checks; request owner resolution for unsupported scoring or treatment mappings.

**Exit:** one distinct reviewable package without requiring a new mandatory scale beyond approved FR-21 content.

### S35 — Draft parkinsonism follow-up question

**Key:** `parkinsonism` (F3). **Requirements:** FR-20–21, FR-30–35. **Sources:** BN-12, STATEMENT-12, parkinsonism criteria.

1. Map reviewed effect/severity/context fields. The SAS source does not define universal mild/moderate/severe score bands; do not create them from historical thresholds.
2. Resolve onset/alternative-cause and other required facts through approved structured history, never page notes. Missing context remains explicit.
3. Draft fixed graph, every CPT contract, prompt, query and result-to-template branches with source-provenance rationale.
4. Prepare present/absent/not-assessed and severity/unknown fixtures. Keep numerical engine evidence separate from owner review of clinical interpretation.

**Exit:** package ready for review; source restrictions and proposed assumptions are visible instead of embedded silently in code.

### S36 — Draft acute-dystonia follow-up question

**Key:** `acute_dystonia` (F4). **Requirements:** FR-20–21, FR-30–35. **Sources:** BN-11, STATEMENT-11, acute-dystonia criteria.

1. Define reviewed presence/severity/onset/context fields and explicit urgent concerns. Do not require completion of inference before displaying a source-approved urgent assessment message.
2. Draft the fixed graph and distinguish source review flags from probabilistic output semantics. Resolve missing priors/all-CPT replacement assumptions in the dossier.
3. Write scoped estimation prompt and predefined result mapping, preserving multiple concerns and no autonomous intervention.
4. Supply effect present/absent/not-assessed and required-context-missing cases, with reviewed clinical expectations and independent CPT/inference fixtures.

**Exit:** acute-dystonia package and exact unresolved content questions if any, with no ad hoc severity scale or fabricated management rule.

### S37 — Draft no-improvement clozapine follow-up question

**Key:** `no_improvement_clozapine` (F5). **Requirements:** FR-20, FR-30–35. **Sources:** BN-07, treatment-resistance guidance, approved PANSS/history/baseline rules.

1. Draft an explicit no-improvement definition: baseline encounter/window, instrument/context and adequate-treatment information. Do not guess a percent-change cutoff or treat missing follow-up score as no improvement.
2. Create a package separate from R7, with its own gate, prompt, network identity and template even if source concepts are reused.
3. Define how outdated baselines and not-assessed severity affect applicability; required ambiguity pauses rather than silently skipping.
4. Supply improvement/no-improvement/unknown and differing-baseline cases, reviewing expected clinical mapping and independently checking mathematics.

**Exit:** precise follow-up gate and package, with source constraints and required field definitions approved before activation.

### S38 — Draft continue-versus-adjust follow-up question

**Key:** `continue_or_adjust` (F6). **Requirements:** FR-20, FR-30–35. **Sources:** BN-04/05/06, STATEMENT-04/05/06, approved history/effects/preferences.

1. Compare overlapping source drafts and propose one clinical question/graph. Specifically present BN-06's electronic decision-support restriction to the owner and obtain an explicit scope/source resolution; copying the draft is not resolution.
2. Draft review outcomes for continuation versus adjustment, with fixed states, patient mappings, observed/CPT-context use and required missingness. Do not interpret treatment conditioning as causal intervention evidence.
3. Supply complete all-CPT prompt and template branches retaining adverse effects/preferences/parallel concerns. No runtime merge of three models.
4. Prepare continuation/adjustment/insufficient-information and stale-baseline cases, plus independent numerical examples.

**Exit:** one package with documented source-resolution decision. If the restriction cannot be resolved, mark the package blocked and preserve the engineering pipeline without claiming FR-30 complete.

### S39 — Review and release both complete workflow bundles

**Depends:** S24–S38; owner decisions on all content. **Requirements:** FR-30–37, NFR-05. **Seams:** T1/T5. **Tests:** `BT/models/test_bundles.py`.

**Files/read:** plan.md §§1.4, 7; all question dossiers; `content/bundles/registration.json`, `followup.json`, content release manifest.

1. Present the thirteen concrete packages and cross-package assumptions for owner review. Record exact hashes/decisions; revise rejected packages and rerun their scoped checks. Do not batch-approve on the owner's behalf.
2. Red: a workflow with a missing/unreviewed question, duplicate key, incompatible mapping/content, unresolved query/template or nonexecutable network cannot activate.
3. Build ordered bundles with seven/six question identities, one combined LAI network, no implicit result chaining, and pinned assessment/history/DDI/template/prompt references.
4. Run admission measurements and independent fixtures for every package; add explicit gate coverage inventory and reviewed reference-table provenance. Activate only through the registry command, recording a new versioned event.

**Verify/exit:** both reviewed complete bundles, reproducible hashes and admission report. If content review is pending, S40–S58 may proceed synthetically; S59/release remains blocked, with specific missing package IDs.

## 7. Snapshots, MCP, provider, and reasoning

### S40 — Freeze analysis snapshots and project one question's inputs

**Depends:** S12–S14, S20, S25; synthetic bundle permitted. **Requirements:** FR-16, FR-32, FR-35, NFR-04. **Seam:** T1 through start/read commands; T8 consumes these snapshots later. **Tests:** `BT/worker/test_snapshots.py`.

**Read/files:** plan.md §§4.2, 8.1; `B/reasoning/snapshots.py`, run/question/evidence migrations and run read/start contract. Queue execution arrives in S44.

1. Red: start from a saved author-owned revision freezes allowed clinical facts and all selected version references; shared notes/names/ID/phone are absent from model-facing projection. Invalid/stale revisions fail without partial snapshot creation.
2. Red: each question receives exactly its represented variables with typed missing/conflict state and source references; a mapping trying to read notes/unrelated history is rejected regardless of prompt wording.
3. Red: note-only edits leave analysis fingerprint unchanged; analytical edits change it and invalidate signing eligibility. Immutable old snapshots remain readable after demographics/history changes.
4. Evaluate gates against saved facts: true/false/required-unknown produce ready/not-applicable/clarification. Persist explicit reasons and forbid undeclared cross-question result inputs.

**Verify/exit:** public run/projection behavior with mixed-content sentinel data. Do not expose a general patient snapshot endpoint to the model or make a temporary direct-record provider path.

### S41 — Implement the real private MCP transport and context grants

**Depends:** S40, S44, S03; execute queue/grant mechanics before this session. **Requirements:** FR-32–35, NFR-02. **Seam:** T6. **Tests:** `BT/mcp/test_scoped_transport.py`.

**Read/files:** plan.md §8.2 and source MCP design; `B/mcp_server/`, worker-side MCP host adapter, grant storage/read-only role configuration.

1. Red: a real SDK client starts the stdio subprocess, discovers exactly the allowed tool, calls with `{}`, and receives the bound stored projection. No direct in-process shortcut satisfies this test.
2. Red: extra arguments/unknown tools, missing/expired/forged grants, mismatched snapshot and inactive actor fail safely. Supply context only from protected worker state, never model arguments.
3. Red: simultaneous patient A/B processes and successive question contexts cannot read one another's sentinel values or notes. Stop/revoke a context before reuse; stderr diagnostics cannot corrupt stdout protocol.
4. Red: oversized projection and database/transport failure return bounded errors; process cleanup revokes access. Final lease/deployment fencing is exercised again in S47.

**Verify/exit:** actual protocol lifecycle on pinned SDK/version, tool schema and scoped-output assertions. No public MCP listener, patient search, write, inference, shell or file tool exists.

### S42 — Store and test provider settings securely

**Depends:** S03–S05, S02. **Requirements:** FR-03, FR-43, NFR-02. **Seams:** T1/T7/T9. **Tests:** `BT/http/test_api_settings.py`, `e2e/provider-settings.spec.ts`.

**Files/read:** plan.md §§8.3, 11; `B/reasoning/provider_config.py`, config migration, admin settings form.

1. Red: admin saves key/base URL/model revision; GET shows masked status only, physician is denied, replacing/clearing key is explicit, stale writes fail. Encrypt stored keys with deployment-held key.
2. Red: forbidden schemes/hosts/redirect targets/resolved addresses fail; explicitly allowed local model endpoint succeeds under operator configuration. Test the actual HTTP client's behavior.
3. Implement the minimum synthetic capability exchange in the provider adapter that S43 will extend: credential/model/tool/JSON support and safe diagnostic. Saving settings is not a claim that capabilities passed; do not create a second permanent provider client path.
4. Red: new config version leaves prior referenced version available; removal has explicit affected-run handling. Browser reflects configured/untested/verified/failed states without exposing secrets.

**Verify/exit:** request/response/log/audit redaction, allowlist behavior, UI replace/clear flow. No live paid model request is part of ordinary CI.

### S43 — Implement bounded provider CPT estimation and tool bridging

**Depends:** S23, S25, S41–S42. **Requirements:** FR-32–33, FR-36, FR-43. **Seam:** T7 with real T6 bridge. **Tests:** `BT/provider/test_estimation.py`.

**Files/read:** plan.md §§8.2–8.3; `B/reasoning/provider.py`, deterministic external HTTP test endpoint.

1. Red: endpoint receives only question prompt, fixed network/CPT contract and persisted projection; returns a strict candidate CPT response. Inspect captured external request, not an internal mock call.
2. Red: permitted tool call crosses real MCP and returns required correlation metadata; disallowed name/args and spoofed context are rejected. Initial patient read also uses MCP.
3. Red: schema-capable and JSON-only endpoints follow their verified capability modes but share the same strict validator. Reject extra prose, ambiguous responses and malformed/truncated/oversized output.
4. Red: timeout/auth/model/capability/rate-limit errors map to explicit retryability; ten-tool-call and context/output budgets are enforced. One adapter attempt never implements hidden nested retries.

**Verify/exit:** deterministic endpoint matrix and secret/field-exclusion checks. Templates never pass through the provider for drafting. Record runtime capability constraints for model admission.

### S44 — Implement durable leased jobs and global admission

**Depends:** S02, S40. **Requirements:** FR-35–36, FR-43, NFR-04. **Seam:** T8. **Tests:** `BT/worker/test_queue.py`.

**Files/read:** plan.md §§8.4–8.5; `B/reasoning/queue.py`, `worker.py`, jobs/attempt/grant migrations. Execute this session before the scoped MCP work in S41.

1. Red: run creation and its first eligible job are atomic; repeated same-fingerprint triggers reuse the run; simultaneous triggers cannot create two active generations for an encounter.
2. Red: two worker instances cannot exceed two global provider slots or execute two questions of one run. Implement short claim transactions, lease/heartbeat and persistent admission.
3. Red: eligible work rotates fairly across physicians and then FIFO within physician; saturation returns a visible busy state without deleting saved drafts/jobs.
4. Red: expired lease is reclaimed; old token cannot commit; restarting a worker retains recorded attempts and terminal artifacts. Implement one `run_once()` entry point used by tests and the polling process. At this stage exercise preparation/claim/recovery with real snapshot/gate logic and a controlled external provider adapter; complete the protocol and estimation stages in S43/S45, without mocking the queue's own collaborators.

**Verify/exit:** concurrent real-PostgreSQL worker checks via public run status; no SQL-row assertions or external request under an open claim transaction. Handoff includes configuration defaults and deterministic clock adapter behavior.

### S45 — Run one full synthetic clinical question end to end

**Depends:** S23, S40–S44. **Requirements:** FR-32–35. **Seams:** T1/T8, exercising T5–T7. **Tests:** `BT/worker/test_single_question.py`.

**Files/read:** plan.md §§7.4, 8–9; `B/reasoning/coordinator.py`, artifact/result/section migrations, template schema from S25 and a small local renderer.

1. Red: public start → worker → real MCP → controlled provider → all-CPT validation → effective XML → exact inference → stored template section is observable through `GET /runs/{id}`.
2. Persist request/projection/prompt/model/attempt provenance, accepted percentages, effective XML/hash and query/result before completing the section. Crash checkpoints cannot produce a successful result without these references.
3. Red: provider structure mutation or missing root table leaves the step unsuccessful and base network bytes unchanged; no registered default enters inference.
4. Red: template output comes only from the reviewed mapping and stored result; returned LLM prose is never used as the recommendation. Expose five required transparency fields from persisted data.

**Verify/exit:** exact mathematical expected values from plan.md's synthetic example with all real owned modules. No clinical release package is required for this engineering proof, but no fake “succeeded” endpoint is acceptable.

### S46 — Execute ordered workflows and assemble a complete proposal

**Depends:** S45, S19, S25; S39 needed only for real content. **Requirements:** FR-15, FR-30–35. **Seams:** T1/T8. **Tests:** `BT/worker/test_workflows.py`.

**Files/read:** plan.md §§7.1, 8.4, 9; coordinator, proposal assembly and DDI snapshot integration.

1. Red: synthetic seven/six-question workflows emit external provider requests in pinned order; next request is absent until prior inference and section commit. No intra-run parallelism.
2. Red: false gate records not-applicable without a provider call; required-unknown stops progression; unrelated applicability facts and previous posteriors are absent from later requests.
3. Red: final proposal succeeds only after every applicable question and a valid pinned DDI report; include skipped reasons and coverage warnings. Partial sections remain readable but incomplete.
4. Red: changed medications/data cannot use an old report or proposal; activating new content does not mutate an already pinned run. One combined LAI step renders both outputs under its mapping.

**Verify/exit:** sequential external-request evidence, persisted proposal/section identities, valid limited-coverage DDI versus failed/unavailable dataset distinction. No LLM proposal-writing request exists.

### S47 — Bound failures and recover at the exact failed stage

**Depends:** S46. **Requirements:** FR-36, FR-43, NFR-04. **Seams:** T1/T8. **Tests:** `BT/worker/test_recovery.py`.

**Files/read:** plan.md §8.5; retry coordinator, attempt ledger, stage resume and fencing.

1. Red: timeout → invalid CPT → rate-limit exhausts three total attempts, retains prior sections and draft, and leaves later questions pending. Implement one shared budget/backoff/Retry-After cap, no nested adapter retries.
2. Red: author retry of unchanged failed stage starts a new bounded batch; inference retry reuses CPTs and rendering retry reuses result. Successful earlier questions produce no new provider requests.
3. Red: worker crash after attempt start or accepted-artifact persistence cannot reset counts or duplicate committed sections; old worker/grant/deployment generation cannot commit after reclaim.
4. Red: analytical edit, discard, archive or deactivation during an outbound request prevents late acceptance/signing; configuration replacement starts a new pinned run. Clarification never triggers guessed values or blind retries.

**Verify/exit:** controlled external failure matrix and process restart, with public run history proving retention and resume. Split into S47.a retry policy/S47.b process races if needed; both are release-critical.

### S48 — Build automatic proposal review and transparency UI

**Depends:** S14, S20, S46–S47. **Requirements:** FR-15–16, FR-35–36, NFR-03. **Seams:** T1/T9. **Tests:** `e2e/proposal-review.spec.ts`.

**Files/read:** plan.md §9; `W/features/reasoning/`, review-entry trigger and run HTTP presentation.

1. Red browser journey: entry flushes autosave and automatically creates/reuses a run; no extra Generate click, no run per keystroke, no trigger while prerequisite acknowledgment/save is missing.
2. Display ordered pending/running/skipped/clarification/failed/completed states, partial retained sections and precise failed-question retry. Poll only active runs with hidden-tab backoff.
3. Show all five transparency fields beside each recommendation, plus sources/missingness/versions. CPT tables and posterior values are clearly different; lazy expansion fetches persisted data without recomputing from current chart.
4. Render final proposal with DDI coverage and separate secondary-plan entry. Failed/stale/partial runs visibly block signing and preserve draft editing/retry.

**Verify/exit:** two-question failure→retry browser case, refresh/resume, exact saved-input display, no note leakage. The subsequent sign session uses this status but enforces eligibility independently server-side.

## 8. Final plans, shared records, and reporting

### S49 — Implement atomic plan signing and immutable snapshots

**Depends:** S46–S47, S14. **Requirements:** FR-15, FR-22, FR-42, NFR-04. **Seam:** T1. **Tests:** `BT/http/test_signing.py`.

**Read/files:** plan.md §§4, 9; `B/cases/signing.py`, secondary-plan/signed-snapshot migrations and routes.

1. Red: author saves a secondary plan tied to a proposal without changing initial text, reads edit history, and signs only a current successful run with all saved revisions/review acknowledgments.
2. Red: absent/failed/partial/stale run, forged manual-plan submission, wrong author/admin, outdated revision or unreconciled baseline is rejected server-side. Recompute eligibility inside the transaction.
3. Red: successful sign atomically freezes full record/notes/meds/DDI/versions/both plans/signer/time and audit; repeated identical command returns the same signature. No partial sign survives a transaction failure.
4. Red: later update routes cannot change signed data, while current patient demographics may change without rewriting historical snapshots. Add original-signer-only attributed addendum with immutable original text.

**Verify/exit:** direct HTTP success and denial matrix using real completed synthetic pipeline results; no test shortcut creating a signable success flag. S51 adds concurrent race coverage.

### S50 — Build final-plan editing, comparison, sign, and addenda UI

**Depends:** S48–S49. **Requirements:** FR-15–16, FR-22, NFR-03. **Seam:** T9. **Tests:** `e2e/signing.spec.ts`.

**Files/read:** plan.md §9; `W/features/plans/`, chart signed-view/addendum UI.

1. Red browser journey: successful proposal appears unchanged beside editable secondary plan; changes persist through reload and visible comparison shows physician edits.
2. Explicit Sign flushes pending saves, collects review/baseline acknowledgments and submits current revisions. Display precise stale/failed eligibility errors without losing edited text.
3. Signed view is read-only, with signer/time, exact historical record and print navigation. Another physician sees the signature but cannot edit or add an original-signer correction.
4. Original signer appends reason/text correction; chronology shows dated addendum separately. Double-click/retry does not duplicate signatures or addenda.

**Verify/exit:** successful registration sign, refresh, separate physician read, original signer addendum, and failed-generation manual-plan denial through UI and server. No “force sign” escape hatch.

### S51 — Close archive, deactivation, and multi-user race cases

**Depends:** S04, S14, S47, S49–S50. **Requirements:** FR-04, FR-22–23, NFR-04. **Seams:** T1/T8/T9. **Tests:** `BT/http/test_record_races.py`, `e2e/shared-records.spec.ts`.

**Files/read:** plan.md §§2.1–2.3, 8.5–9; patient archive, account/deactivation-to-Cases integration and final eligibility checks.

1. Red: archive blocks new encounters/edit/sign, preserves read-only drafts/history, and unarchive restores original-author access. Only admin can archive; no permanent delete route exists.
2. Red: deactivate with retained drafts revokes access and queued work; confirmed discard applies only to the reviewed draft-set revision. Changing that set invalidates confirmation; reactivation does not resurrect discarded drafts.
3. Red: simultaneous sign/save, sign/archive, sign/deactivate and two baseline-related signs have one valid serial outcome, never lost updates or an ineligible signature. Use real concurrent HTTP requests/controlled provider delay.
4. Red: demographic analytical edits during generation make old results stale; note-only changes do not rerun inference but require current sign revision. Reconciled concurrent follow-up drafts retain distinct authors/history.

**Verify/exit:** race suite plus admin archive/deactivation confirmation browser flow. All pending integration items from S04/S07/S14 are closed explicitly.

### S52 — Complete append-only audit and administration views

**Depends:** S24, S42, S49–S51. **Requirements:** FR-03, FR-42. **Seams:** T1/T9. **Tests:** `BT/http/test_audit.py`, `e2e/audit.spec.ts`.

**Files/read:** plan.md §10.1; `B/operations/audit.py`, admin filter/view interface, normal-role database grants.

1. Inventory all required actions and add missing events at the actual transaction/command path. Red: successful mutation plus event are atomic; failed command produces accurate failure metadata without false success.
2. Red through audit HTTP: renamed/deactivated users retain stable attributed histories; run/question/tool/retry and sign events reference correct artifacts without record bodies/keys.
3. Red: physician cannot inspect audit; admin filters by actor/action/time/target with stable pagination; no update/delete interface exists. Verify append-only database grants as a migration/operations check, not a hidden-state behavioral assertion.
4. Build readable admin table/detail view with correlation references, timestamp timezone and bounded metadata. Record backup/restore event hooks for S54–S56.

**Verify/exit:** required-event coverage list and safe audit browser path. Report accurately that database-owner access/restore can replace history; do not claim tamper-proof storage.

### S53 — Export lists and printable longitudinal patient reports

**Depends:** S20, S49–S52. **Requirements:** FR-03, FR-40. **Seams:** T1/T9. **Tests:** `BT/http/test_exports.py`, `e2e/reporting.spec.ts`.

**Files/read:** plan.md §10.1; `B/cases/reporting.py`, administrative CSV endpoints, print CSS.

1. Red: admin downloads patient/physician CSV with stable headers/UTF-8/quoting and no credentials; physicians are denied list exports. Patient ID `0012345678` remains exact text bytes.
2. Red: formula-like user text is neutralized without formula wrappers; quotes/newlines render correctly. Explain spreadsheet text import rather than promising CSV column typing.
3. Red: both roles can view escaped printable patient HTML containing chronology, completeness, histories, meds/DDI coverage, initial/final plans, signatures, notes/addenda and clear draft/signed/current/historical labels.
4. Browser print view has readable page breaks and research labeling in both browsers; authenticated responses are private/no-store. Avoid PDF libraries and dynamic LLM report prose.

**Verify/exit:** malicious text remains inert, export permissions/audit pass, print preview inspected with a multi-encounter fixture.

## 9. Recovery and Linux operation

### S54 — Produce consistent full backups

**Depends:** S39 or representative complete synthetic content; S49, S52–S53. **Requirements:** FR-41–42, NFR-04–05. **Seams:** T10/T1/T9. **Tests:** `BT/recovery/test_backup.py`.

**Read/files:** plan.md §10.2; `B/operations/backup.py`, recovery-job migration, archive manifest, admin backup UI.

1. Red: backup of populated disposable system includes database and all referenced original/effective XML, CPTs, prompts/templates, content/DDI provenance and version/checksum manifest.
2. Red: concurrent mutation cannot make exported XML inconsistent with the database snapshot. Derive exports from the same consistent snapshot, using isolated staging where needed.
3. Red: session credentials and deployment encryption key are excluded as specified; encrypted provider values have an explicit key-reentry/recovery note. Administrator authorization, bounded asynchronous progress/download and safe audit are required.
4. Red: interrupted dump/export produces a failed job and no downloadable “complete” archive; retry does not overwrite a good prior backup. Clean only documented temporary recovery artifacts.

**Verify/exit:** inspect through backup interface/manifest and restore into disposable staging for coherence checks. A downloadable zip alone is insufficient evidence of recoverability.

### S55 — Validate and stage restores without touching live state

**Depends:** S54. **Requirements:** FR-41, NFR-02/04. **Seams:** T10/T1/T9. **Tests:** `BT/recovery/test_restore_validation.py`.

**Files/read:** plan.md §10.3; `B/operations/restore.py` staging phase, restricted restore role, validation/progress UI.

1. Red: valid app-generated archive stages into isolated database, reports backup date/schema/content/checksums/impact, and returns an immutable confirmation digest.
2. Red: path traversal, absolute path/symlink, oversized expansion, corrupt hash, unsupported schema, missing artifact and malformed database content fail before live mutation.
3. Restore untrusted data with restricted permissions and resource limits; uploaded content must not execute as superuser or access host files/programs. Validate singleton identity, references and model/effective-artifact consistency through supported inspection commands.
4. Red: failed staging leaves current patients/login/jobs unchanged; replacing upload or expiry invalidates prior confirmation. UI exposes validation errors and key-reentry consequences, never an enabled premature Commit.

**Verify/exit:** malicious/corrupt archive suite against disposable storage and real live-side read checks. No restore-over-live action exists until S56 implements the whole switch/rollback protocol.

### S56 — Commit restore with maintenance, fencing, and rollback

**Depends:** S55, S47, S52. **Requirements:** FR-41–42, NFR-04. **Seams:** T10/T1/T8/T9. **Tests:** `BT/recovery/test_restore_commit.py`.

**Files/read:** plan.md §10.3; restore coordinator, `deploy/` maintenance/switch scripts, external operator recovery log.

1. Red: only admin confirmation of the exact validated staged digest starts replacement; stale confirmation fails. Quiesce writes/workers, fence deployment generation and take pre-restore backup before switching.
2. Implement phased database-selection switch and coordinated process restart behind maintenance. Red: no mixed old/new read/write traffic is possible; old provider work cannot commit.
3. Red: successful restore revokes all sessions/grants, clears caches, cancels restored nonterminal jobs for explicit restart, records restore in external recovery log and restored audit, then passes login/read/replay before reopening.
4. Inject failures before switch, during restart and at health check. Red: rollback restores the prior database/configuration and readable records; maintenance remains until verified healthy.

**Verify/exit:** actual disposable destructive restore/rollback drill, UI confirmation/progress and documented operator recovery procedure. Never test against the owner's live database or claim multi-database/process switching is one SQL transaction.

### S57 — Package one-host Linux deployment and upgrades

**Depends:** S48–S56; synthetic content allowed for installation mechanics. **Requirements:** NFR-01–02, NFR-05. **Seams:** T1/T8/T9/T10 operational entry points.

**Read/files:** plan.md §§3, 11; `deploy/` Dockerfiles/edge config, `compose.yaml`, environment example, setup/upgrade/runbook documentation.

1. Build pinned production images and Compose topology: edge, HTTP app, worker, PostgreSQL; worker spawns private MCP. Persist database volume; no public DB/MCP ports; browser uses relative origin routes.
2. Verify fresh Linux startup, explicit migrations and one-time admin seed. Missing provider or bundle yields unavailable generation while charts/admin remain usable. HTTPS is enforced outside localhost.
3. Document environment/key handling, backup-before-upgrade, compatible application/schema rollback, migration failure recovery and stopping processes. No default development override or test provider is enabled in production.
4. Restart HTTP/worker/database independently and verify acknowledged draft preservation, queue recovery and health semantics. Container logs contain no record text or secrets.

**Verify/exit:** clean disposable-host install and upgrade from preceding schema state, documented commands and image/runtime versions. Do not deploy to an external/live host as an implicit final step.

### S58 — Measure capacity and expose useful operational status

**Depends:** S57, S47. **Requirements:** FR-43, NFR-01/04. **Seams:** T1/T8/T10.

**Files/read:** plan.md §11; structured metrics/logging, `make test-load` runner, operator runbook.

1. Exercise public interfaces with 10,000 synthetic patients and representative concurrent saves/searches/polls; record host, dataset, duration and p95 latency. Separate provider latency from ordinary requests.
2. Measure every admitted model's complete CPT request/output sizes, exact-inference CPU/memory/time and failure behavior. Configure justified admission/resource limits and preserve rejection diagnostics.
3. Expose safe metrics for save failure, queue age, heartbeat, provider retries/auth failure, inference limits, disk and backup success; demonstrate initial alert conditions without clinical payloads.
4. Verify two-slot global concurrency, fair progress, saturation and bounded caches under load. Tune only measured bottlenecks; do not add a broker/cache/database without evidence.

**Verify/exit:** measured report against provisional targets, explicit misses and remediation tasks. No unmeasured SLA/availability claim; no fabricated benchmark numbers.

## 10. Integrated release verification

### S59 — Prove both workflows using reviewed released content

**Depends:** S39, S18, S09–S12 approvals, S50–S58. **Requirements:** FR-10–16, FR-20–22, FR-30–37, NFR-04–05. **Seams:** T1/T4–T9.

**Tests/files:** `e2e/registration-complete.spec.ts`, `e2e/followup-complete.spec.ts`, `BT/worker/test_released_content.py`, release evidence manifest.

1. Run registration and follow-up through saved assessments/history/DDI, real MCP, controlled provider responses matching **released** network contracts, exact inference, real templates, review/edit/sign and chart. No synthetic substitute for released clinical definitions.
2. Exercise every required question with independently reviewed true/false/unknown cases. Verify all roots/tables required, one combined LAI question and scoped input per step. Provider estimates in CI may be deterministic fixtures; label them as such.
3. Verify note-only changes leave inputs/results eligibility unchanged; analytical changes require new run; all five transparency fields match saved artifacts and both plans remain distinct.
4. If authorized/configured, separately run a synthetic-input live-provider compatibility smoke. Record it separately from deterministic clinical-package acceptance; absence of live credentials is an explicit unrun integration check, never fabricated success.

**Verify/exit:** traceable owner-approved content hashes, complete 13-question coverage and both signed flows. Any missing package/review blocks this gate even if the generic app works.

### S60 — Run cross-user, failure, and security acceptance

**Depends:** S59, S51, S56. **Requirements:** FR-04, FR-16, FR-22, FR-36, FR-41–43, NFR-02/04. **Seams:** T1/T6–T10.

**Tests:** existing race/recovery suites plus `e2e/failure-recovery.spec.ts`; add only missing observable scenarios.

1. Two physicians edit separate encounters while one provider run fails; saves remain responsive and acknowledged drafts survive restarts. Wrong-author reads/writes follow confirmed shared-read/author-write rules.
2. Re-run mixed three-attempt exhaustion, stage resume, lease theft/crash, archive/deactivation and restore generation fencing with externally controlled timing. Completed question artifacts remain unique and preserved.
3. Inspect all actual model/MCP payloads for notes, unrelated sentinel fields and secret leakage; forge tool args/grants, HTTP role/CSRF/revisions, XML entities, provider destinations and archive paths. Assert observable denial/no mutation.
4. Verify mandatory failed/stale/manual-sign denials and output escaping/CSV formula behavior. Record unresolved defects with reproducible requests; fix them at their owning module and rerun affected checks.

**Exit:** cross-cutting gate passes with real owned dependencies. Do not replace a failing concurrency test with sleeps or remove the adversarial case to get green.

### S61 — Verify desktop usability, both themes, and complete administration

**Depends:** S59–S60. **Requirements:** FR-01–04, FR-23, FR-37, FR-40–42, NFR-03. **Seam:** T9.

**Tests/files:** existing Playwright journeys, accessibility evidence and any targeted fixes in owning UI module.

1. Walk physician registration/follow-up and all admin capabilities in current Chrome/Firefox: accounts, password/theme, provider test, network XML/graph/validate/version/activate/rollback, archive, audit, exports, backup/restore staging.
2. Inspect light/dark contrast, keyboard order/focus, labels/errors, zoom, reduced motion, dense tables and print preview. State must have text cues and urgent banners must persist.
3. Exercise empty/loading/error/read-only/unsaved/conflict/partial/failed states, not just happy-path screenshots. Verify explicit discard/deactivate/restore confirmations and every-login research warning.
4. Fix actual usability defects without introducing a second UI runtime or decorative redesign. Add a browser test only where it guards meaningful behavior; avoid brittle full-page snapshots.

**Exit:** dated browser/version checklist, contrast/keyboard/print observations, no fake implemented feature or disabled unexplained action. All NFR-03 conditions covered.

### S62 — Complete the release rehearsal and agent handoff

**Depends:** S58–S61. **Requirements:** all. **Seams:** approved integration/operational seams only.

**Files/read:** plan.md §12, this document's coverage matrix, progress tracker, release/operations documentation.

1. From a clean checkout and empty disposable storage run locked install, migrations, seeding, required suites and production build. Record exact commit/worktree state, locks, images and content hashes.
2. Rehearse full backup → mutation → staged restore → confirmed replacement → login/read/artifact replay, plus failed-switch rollback. Confirm session revocation and unavailable-key reentry behavior; retain safe evidence.
3. Audit every FR/NFR against concrete tests/manual checks below. All sessions and content reviews must be complete; identify any explicitly unrun live-provider/host-specific check. Fix missing requirements before claiming the application ready.
4. Finalize quick start, operator configuration, content update/approval procedure, draft/run failure recovery, restore/key escrow instructions and known limits. Handoff distinguishes engineering acceptance from clinical validation and does not claim high availability.

**Exit:** reproducible self-hosted application build and full requirement evidence, with no unresolved release-critical gate. Commit/live deployment/publication remain separate actions requiring the user's applicable authorization.

## 11. Requirement-to-session acceptance index

Every requirement has an implementation owner and an acceptance location. A grouped session does not mean the grouped requirements can be marked complete together without their individual evidence.

| Requirement | Primary sessions | Final observable evidence |
|---|---|---|
| FR-01 | S03, S05 | Role login, Register contact text, research notice on each physician login; S61 |
| FR-02 | S03 | Singleton admin/admin seed, unchanged username, changed password survives restart |
| FR-03 | S04–S05, S24, S42, S51–S58 | Entire admin capability walkthrough; S61 |
| FR-04 | S03–S04, S51 | Admin-only credentials, revocation, confirmed draft disposition, preserved attribution |
| FR-10 | S06 | Exact demographics, disabled invalid Next, leading-zero ID and duplicate race |
| FR-11 | S08–S09 | Full criteria, live threshold, saved below-threshold warning, reason-free bypass |
| FR-12 | S08, S10 | Unanswered/partial/skip versus completed PANSS reference results |
| FR-13 | S08, S11 | Selected C-SSRS form/periods/completeness and distinct results |
| FR-14 | S12, S15–S20 | Structured history, drug-only persistence, reviewed deterministic DDI and unavailable coverage |
| FR-15 | S46, S48–S50 | Immutable initial proposal with BN/DDI, separate edited secondary plan and sign-off |
| FR-16 | S07, S13, S40–S41 | Acknowledged autosave/restart, confirmed discard, page notes excluded end to end; S59–S60 |
| FR-20 | S14, S33–S38, S50, S59 | Complete new follow-up assessment/history/medications/effects/proposal/sign/chronology |
| FR-21 | S12, S33–S36 | Four explicit tri-state effects with reviewed severity |
| FR-22 | S07, S14, S49–S51 | Shared records, author-only drafts/sign, immutable signed snapshot, original-signer addendum |
| FR-23 | S06, S51 | Name/ID search, clinical-status/archive filters, archive/unarchive without deletion |
| FR-30 | S25–S39, S46, S59 | All seven registration/six follow-up questions and one combined LAI model |
| FR-31 | S21, S25–S39 | One predefined prompt/XMLBIF per question; separate structural validation |
| FR-32 | S22, S40, S43, S46 | Fixed structures/types/states/relevance, scoped inputs and sequential progression |
| FR-33 | S23, S41, S43, S45 | MCP-mediated estimation of every CPT, LLM cannot modify graph or execute it |
| FR-34 | S23, S25, S45–S46 | Effective CPT insertion, exact inference, template section before next question |
| FR-35 | S40–S41, S45, S48 | Automatic run, authoritative scoped MCP, saved/displayed five transparency fields |
| FR-36 | S43–S44, S47–S48 | Three total mixed attempts, retained data/results, explicit failed-stage resume |
| FR-37 | S21–S24, S39 | Graph/XML import/edit/export/validation/version/activation/rollback |
| FR-40 | S53 | Authorized safe CSV and printable HTML; no PDF dependency |
| FR-41 | S54–S56, S62 | Consistent complete artifact backup and actual restore/rollback drill |
| FR-42 | S02–S04, S52, S54–S56 | Append-only safe attributed events and admin view |
| FR-43 | S42–S44, S47, S58 | Configured compatible provider, two global slots, queue fairness/fail-soft behavior |
| NFR-01 | S01, S57–S58, S62 | Clean Linux/VPS install and measured concurrent load |
| NFR-02 | S03, S41–S43, S55–S57, S60 | Auth/no timeout/HTTPS and actual transport/role/input protections |
| NFR-03 | S05, S48, S50, S53, S61 | English Chrome/Firefox workflows, themes, keyboard/contrast/validation/confirmations |
| NFR-04 | S07, S23, S44, S47, S49, S56, S62 | Acknowledged draft survival, exact stored-artifact replay, fenced recovery |
| NFR-05 | S01–S02, S08, S18, S21–S25, S39, S52, S62 | Locked/versioned content/models/templates, XSD, retained provenance/audit/recovery |

## 12. Ready-to-paste session instruction

```text
Implement session Sxx from docs/dev/tasks.md.
Follow docs/dev/plan.md and the confirmed decisions there.
Read current progress, relevant source files, implementation and tests first.
Preserve unrelated changes. Use the session's already-approved public test seams.
Work one observable red → green slice at a time; review/refactor after green.
Do not invent missing clinical rules or activate unreviewed content.
Run the specified checks, record actual evidence and update progress-tracker.md.
Finish with what works, what was checked, remaining blockers and the next session.
Do not auto-commit, publish or deploy to a live host.
```
