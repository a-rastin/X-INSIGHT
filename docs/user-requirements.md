# User Requirements

## X-INSIGHT

X-INSIGHT is a research prototype helping physicians/psychiatrists explore treatment options for schizophrenia cases.

**Users:** one administrator, <10 physicians. Shared patient pool. English only.

**Physician flow:** register patient -> assess -> review AI proposal -> finalize and sign plan. Follow-up: re-assess -> review proposal -> sign.

## Functional Requirements

### Users & log-in

**FR-01:** Login with role, username, password; redirect to role dashboard. After a psychiatrist logs in successfully, show a warning that this is a research app and is not intended to be used as the sole basis for treating patients. Register button shows "Contact administrator".

**FR-02:** Single admin account `admin`; username immutable. Default password `admin`. No complexity rules.

**FR-03:** Admin change own password, theme toggle (dark/light mode), manage API settings (key, base URL, model), manage Bayesian networks, manage physicians, view/export patients, backup/restore, view audit log.

**FR-04:** Admin creates physician accounts; no self-registration. Admin can edit physician credentials and deactivate accounts. Deactivation keeps records; unfinished drafts discarded only after confirmation. Physicians change own password only.

### New patient registration

**FR-10:** `Demographics:` first/last name (letters only, required), sex M/F (required), age 18–99 (required), Patient ID 10-digit string unique app-wide with leading zeros preserved (required), visit datetime auto-logged, status first-time vs established. Before creating a new patient, the app checks the 10-digit Patient ID against all previous patients; if it matches an existing ID, registration is denied. Next disabled until valid.
FR-11 Diagnosis: Standard Schizophrenia diagnosis criteria based on DSM-5-TR; live threshold indicator. Below threshold: save and allow treatment generation only with warning. Bypass without reason allowed.
FR-12 Severity: Standard PANSS questionare for schizophrenia severity. starts unanswered; skip = "not assessed". Scores computed only when required items complete (revises source minimum-defaults).
FR-13 Suicide: Standard questionnaire with explicitly nonclinical score; labeled demonstration-only.
FR-14 History: structured fields. Meds from bundled demo catalog without dose, unit, route, frequency, active/stopped. Interaction report from local bundled DB; unknown drugs marked "coverage unavailable".
FR-15 Initial proposal = system-generated; secondary plan = physician-edited final with changes and sign-off recorded.
FR-16 Notes on every page: timestamped, physician-attributed; never influence algorithms. Drafts auto-saved and resumable; explicit Discard needs confirmation (revises source discard-on-exit).

## 4. Functional Requirements — follow-up and records
FR-20 Follow-up encounter: update phone, re-assess severity and suicide, update history and meds, record adverse effects, review initial proposal, edit plan, sign secondary plan and log encounter.
FR-21 Adverse effects: present/absent/not-assessed for tardive dyskinesia, akathisia, parkinsonism, acute dystonia, plus severity. No standardized scale in v1.
FR-22 Any physician may create encounters and update demographics; only draft author may edit or sign that draft. Signed encounters immutable; corrections via dated attributed addenda; follow-ups are new encounters.
FR-23 Patient list search by name, Patient ID, clinical-status filter. Admin can archive/unarchive; no permanent deletion in v1.

## 5. Functional Requirements — reasoning pipeline
FR-30 One Bayesian network per clinical question. Registration: hospitalization, pharmacotherapy, involuntary care, high-suicide Clozapine, LAI indication+choice, aggression Clozapine, established-case Clozapine. Follow-up: tardive dyskinesia, akathisia, parkinsonism, acute dystonia, no-improvement Clozapine, continue-vs-adjust, taper feasibility.
FR-31 Networks stored as xmlbif; XSD validates structure only (nodes, states, CPT syntax).
FR-32 App executes networks deterministically. Core CPTs stay fixed. LLM maps patient record to evidence for designated inputs, including documented uncertainty format; unsupported inputs stay unknown (Q13:B, Q19:A).
FR-33 App runs internal MCP server exposing patient-record tools; internal DB is single source of truth. Runs execute automatically; extracted inputs shown alongside results for review.
FR-34 LLM also drafts proposal text from network outputs using predefined templates; all output labeled synthetic. Missing or conflicting data marked explicitly; required inputs request clarification, otherwise network missing-data handling applies.
FR-35 LLM failure: retry 2–3 times, then fail that step with clear error; saved data retained; physician may retry later.
FR-36 Network management v1: view graph, import/edit/export XML, validate, version, activate, roll back. No graphical editing.

## 6. Functional Requirements — reporting and ops
FR-40 Exports: CSV for patient/physician lists; printable HTML per-patient report. No PDF in v1.
FR-41 Backup/restore: admin downloads full backup (database + network XML) and restores from file.
FR-42 Audit log append-only: logins, network runs, plan sign-offs, admin actions; viewable by admin.
FR-43 API settings: OpenAI-compatible key, base URL, model name; concurrent users supported with queued LLM calls and fail-soft errors.

## 7. Non-Functional Requirements
NFR-01 Deployable self-hosted and on cloud VPS Linux; concurrent multi-user. Research prototype, flexible/adaptive model.
NFR-02 Security (prototype-basic): auth, no session timeout, HTTPS required for non-localhost. No PHI hardening in v1; synthetic patients only.
NFR-03 Privacy: Patient IDs stored plaintext as 10-digit strings; no national-ID meaning assumed.
NFR-04 Usability: English only, desktop latest Chrome/Firefox, theme toggle, explicit validation and confirmations.
NFR-05 Reliability: drafts preserved across failures; deterministic BN execution reproducible for same inputs+version.
NFR-06 Maintainability: versioned networks and templates; XSD validation; audit log.
