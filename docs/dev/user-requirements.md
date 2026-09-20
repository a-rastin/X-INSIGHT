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

**FR-10:** `Demographics` first/last name (letters only, required), sex M/F (required), age 18–99 (required), Patient ID 10-digit string unique app-wide with leading zeros preserved (required), visit datetime auto-logged, status first-time vs established. Before creating a new patient, the app checks the 10-digit Patient ID against all previous patients; if it matches an existing ID, registration is denied. Next disabled until valid.

**FR-11:** `Diagnosis` Standard Schizophrenia diagnosis criteria based on DSM-5-TR; live threshold indicator. Below threshold: save and allow treatment generation only with warning. Bypass without reason allowed.

**FR-12"** `Severity` Standard PANSS questionare for schizophrenia severity. starts unanswered; skip = "not assessed". Scores computed only when required items complete (revises source minimum-defaults).

**FR-13:** `Suicide` Standard questionnaire (CSSRS). starts unanswered; skip = "not assessed". Scores computed only when required items complete.

**FR-14:** `History` structured fields. Meds from bundled demo catalog without dose, unit, route, frequency, active/stopped. Interaction report from local bundled DB; unknown drugs marked "coverage unavailable".

**FR-15:** `Initial treatment proposal`= system-generated; includes DDI (drug-drug interaction) checker and Bayesian Networks recommendations. `secondary treatment plan` = physician-edited final with changes and sign-off recorded.

**FR-16:** Notes on every page: timestamped, physician-attributed; never influence algorithms. Drafts auto-saved and resumable; explicit Discard needs confirmation (revises source discard-on-exit).

### Follow-up and records

**FR-20:** `Follow-up encounter` update phone, re-assess severity and suicide, update history and meds, record adverse effects, review initial proposal, edit plan, sign secondary plan and log encounter.

**FR-21:** Adverse effects: present/absent/not-assessed for tardive dyskinesia, akathisia, parkinsonism, acute dystonia, plus severity.

**FR-22:** Any physician may create encounters and update demographics; only draft author may edit or sign that draft. Signed encounters immutable; corrections via dated attributed addenda; follow-ups are new encounters.

**FR-23:** Patient list search by name, Patient ID, clinical-status filter. Admin can archive/unarchive; no permanent deletion in v1.

### Reasoning pipeline

**FR-30:** One Bayesian network per clinical question. `Registration`: hospitalization, pharmacotherapy, involuntary care, high-suicide Clozapine, LAI indication+choice, aggression Clozapine, established-case Clozapine. `Follow-up`: tardive dyskinesia, akathisia, parkinsonism, acute dystonia, no-improvement Clozapine, continue-vs-adjust.

**FR-31:** Each clinical question has a predefined prompt and a corresponding Bayesian network stored as XMLBIF. XSD validation covers structure only (nodes, states, and CPT syntax).

**FR-32:** The app processes clinical questions sequentially. For each question, it sends the LLM the question-specific prompt, the structure of the corresponding Bayesian network, and only the patient variables represented in that network. Network variables, variable types, states, and relevance remain fixed.

**FR-33:** In the MCP environment, the LLM estimates the percentage values for the network's Conditional Probability Tables (CPTs) from the supplied patient-variable values, such as age and underlying conditions, and returns the estimates to the app. The LLM does not execute or modify the network structure.

**FR-34:** The app inserts the returned CPT values into the corresponding Bayesian network and executes the network deterministically. The resulting question-specific recommendation is used to generate the relevant part of the initial treatment proposal using predefined templates. The pipeline then repeats for the next clinical question until all applicable questions are processed.

**FR-35:** The app runs an internal MCP server that exposes patient-record tools; the internal database is the single source of truth. Each run starts automatically and records the question, network version, patient inputs supplied to the LLM, returned CPT percentages, and network result. These details are shown alongside the recommendation for physician review and transparency.

**FR-36:** If an LLM request fails or returns invalid CPT values, the app retries two to three times, then stops the affected clinical-question step with a clear error. Saved patient data and completed question results are retained, and the physician may retry the failed step later.

**FR-37:** Network management v1: view graph, import/edit/export XML, validate, version, activate, roll back. No graphical editing.

### Reporting and ops

**FR-40:** Exports: CSV for patient/physician lists; printable HTML per-patient report. No PDF in v1.

**FR-41:** Backup/restore: admin downloads full backup (database + network XML) and restores from file.

**FR-42:** Audit log append-only: logins, network runs, plan sign-offs, admin actions; viewable by admin.

**FR-43:** API settings: OpenAI-compatible key, base URL, model name; concurrent users supported with queued LLM calls and fail-soft errors.

## Non-Functional Requirements

**NFR-01:** Deployable self-hosted and on cloud VPS Linux; concurrent multi-user. Research prototype, flexible/adaptive model.

**NFR-02:** Security (prototype-basic): auth, no session timeout, HTTPS required for non-localhost. No PHI hardening in v1.

**NFR-03:** Usability: English only, desktop latest Chrome/Firefox, theme toggle, explicit validation and confirmations.

**NFR-04:** Reliability: drafts preserved across failures; deterministic BN execution reproducible for same inputs+version.

**NFR-05:** Maintainability: versioned networks and templates; XSD validation; audit log.
