import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const execFileAsync = promisify(execFile);

// S48 (RED — T9 journey contract, proposal-review UI not implemented).
// SYNTHETIC FIXTURES ONLY. These 4 journeys pin the frontend contract for
// the S48 implementer; they timeout on the missing selectors until built.
// Seams: T1 (backend run routes, green) and T9 (this spec, e2e).
//
// data-testid contract the implementer builds to (stable selectors):
// - proposal-review-section: the review region (visible on draft open/entry)
// - proposal-run-status: run-level status / prerequisite message line
// - proposal-question-<key>: per-question container, in bundle order
// - proposal-question-state-<key>: per-question state label
// - proposal-retry-<key>: precise retry button, failed question only
// - proposal-section-<key>: retained/completed rendered section container
// - proposal-cpt-<key>: CPT percentages, labeled "CPT", never "posterior"
// - proposal-result-<key>: deterministic result, labeled "posterior"
// - proposal-inputs-<key>: exact saved patient inputs for the question
// - proposal-proposal: immutable initial proposal text (no inputs inside)
// - proposal-ddi: pinned DDI coverage/limitations
// - proposal-secondary-plan: SEPARATE editable textarea (distinct control)
// - proposal-sign-blocked: visible sign gate message on failed/partial runs
//
// Seeding (test-only, never production routes; psql precedent follows
// e2e/followup.spec.ts — node `pg` is unavailable, /usr/bin/psql exists):
// 1. seedSyntheticBundlePointerViaDb inserts a synthetic 2-question bundle
//    pointer (pins.questions = syn_q_one, syn_q_two, no gates/mappings, so
//    both evaluate ready). The UI's entry POST /encounters/{id}/runs then
//    creates a REAL run through the real backend (202, no provider needed;
//    no worker runs e2e so jobs stay put until reseeded).
// 2. Per-question states are seeded as reasoning_jobs / run_questions
//    (projection gates) / run_question_artifacts / run_proposals rows keyed
//    to the run_id captured from the UI's own entry POST response (public
//    HTTP discovery). No live provider, no stub server, no clinical content.
// 3. Retry is exercised against the real POST /runs/{id}/retry route.
// 4. Bundle order is pins order: syn_q_one before syn_q_two.

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

const TEST_DATABASE_URL =
  "postgresql://xinsight:xinsight_dev@localhost:5432/xinsight_test";

const SYN_Q1 = "syn_q_one";
const SYN_Q2 = "syn_q_two";
const SYN_BUNDLE_HASH = "synthetic-e2e-bundle-s48";

function uniquePhysicianUsername(): string {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return `e2edoc${suffix}`.toLowerCase();
}

function uniquePatientId(): string {
  const base = Date.now() % 10_000_000;
  const rand = Math.floor(Math.random() * 1000);
  return `${String(base).padStart(7, "0")}${String(rand).padStart(3, "0")}`;
}

function uniqueName(prefix: string): string {
  let n = Date.now() + Math.floor(Math.random() * 1e9);
  let suffix = "";
  for (let i = 0; i < 5; i += 1) {
    suffix += String.fromCharCode(97 + (n % 26));
    n = Math.floor(n / 26);
  }
  return `${prefix}${suffix}`;
}

function uniqueMarker(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
}

function assertUuid(value: string): void {
  expect(value).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
  );
}

function sqlQuote(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

async function psql(command: string): Promise<string> {
  const { stdout } = await execFileAsync("psql", [TEST_DATABASE_URL, "-c", command]);
  return stdout;
}

// Test-only synthetic bundle pointer: lets the entry POST create a real run
// with two ready synthetic questions. Labeled synthetic; never clinical.
async function seedSyntheticBundlePointerViaDb(): Promise<void> {
  const pins = JSON.stringify({ questions: [{ question_key: SYN_Q1 }, { question_key: SYN_Q2 }] });
  const stdout = await psql(
    "INSERT INTO model_bundle_pointers (workflow, revision, bundle_hash, pins) VALUES (" +
      `${sqlQuote("registration")}, 1, ${sqlQuote(SYN_BUNDLE_HASH)}, ` +
      `CAST(${sqlQuote(pins)} AS JSONB)) ` +
      "ON CONFLICT (workflow) DO UPDATE SET revision = 1, " +
      "bundle_hash = EXCLUDED.bundle_hash, pins = EXCLUDED.pins, updated_at = now()",
  );
  expect(stdout).toMatch(/INSERT 0 1|UPDATE 1/);
}

async function createPhysicianViaAdminApi(
  request: APIRequestContext,
  username: string,
  password: string,
): Promise<void> {
  const adminLogin = await request.post("/api/v1/auth/login", {
    data: { username: "admin", password: "admin", role: "admin" },
  });
  expect(adminLogin.ok()).toBeTruthy();
  const storage = await request.storageState();
  const csrf = storage.cookies.find((c) => c.name === "xinsight_csrf")?.value;
  expect(csrf).toBeTruthy();
  const created = await request.post("/api/v1/physicians", {
    data: { username, password },
    headers: {
      "X-CSRF-Token": csrf ?? "",
      "Idempotency-Key": `e2e-${username}-${Date.now()}`,
    },
  });
  expect(created.status()).toBe(201);
}

async function createPatientViaPhysicianApi(
  request: APIRequestContext,
  username: string,
  password: string,
  patient: Record<string, string | number>,
): Promise<void> {
  const physicianLogin = await request.post("/api/v1/auth/login", {
    data: { username, password, role: "physician" },
  });
  expect(physicianLogin.ok()).toBeTruthy();
  const storage = await request.storageState();
  const csrf = storage.cookies.find((c) => c.name === "xinsight_csrf")?.value;
  expect(csrf).toBeTruthy();
  const created = await request.post("/api/v1/patients", {
    data: patient,
    headers: {
      "X-CSRF-Token": csrf ?? "",
      "Idempotency-Key": `e2e-patient-${patient.patient_id}-${Date.now()}`,
    },
  });
  expect(created.status()).toBe(201);
}

interface DraftContext {
  username: string;
  password: string;
  patientId: string;
  patientUuid: string;
  encounterId: string;
  authorId: string;
}

async function setupPhysicianDraft(
  request: APIRequestContext,
): Promise<DraftContext> {
  const username = uniquePhysicianUsername();
  const password = "synthetic-secret";
  await createPhysicianViaAdminApi(request, username, password);
  const patientId = uniquePatientId();
  await createPatientViaPhysicianApi(request, username, password, {
    first_name: "Synthetic",
    last_name: uniqueName("Case"),
    sex: "F",
    age: 30,
    patient_id: patientId,
    clinical_status: "first_time",
  });
  const physicianLogin = await request.post("/api/v1/auth/login", {
    data: { username, password, role: "physician" },
  });
  expect(physicianLogin.ok()).toBeTruthy();
  const me = (await (await request.get("/api/v1/me")).json()) as { id: string };
  assertUuid(me.id);
  const listed = await request.get("/api/v1/patients", { params: { q: patientId } });
  expect(listed.ok()).toBeTruthy();
  const patients = (await listed.json()) as {
    items: Array<{ id: string; patient_id: string }>;
  };
  const patient = patients.items.find((p) => p.patient_id === patientId);
  expect(patient).toBeTruthy();
  const encounters = await request.get(`/api/v1/patients/${patient?.id}/encounters`);
  expect(encounters.ok()).toBeTruthy();
  const body = (await encounters.json()) as {
    items: Array<{ id: string; kind: string }>;
  };
  const baseline = body.items.find((e) => e.kind === "registration");
  expect(baseline).toBeTruthy();
  return {
    username,
    password,
    patientId,
    patientUuid: patient?.id ?? "",
    encounterId: baseline?.id ?? "",
    authorId: me.id,
  };
}

async function getRunViaPhysicianApi(
  request: APIRequestContext,
  username: string,
  password: string,
  runId: string,
): Promise<{
  revision: number;
  status: string;
  stale: boolean;
  questionKeys: string[];
}> {
  const physicianLogin = await request.post("/api/v1/auth/login", {
    data: { username, password, role: "physician" },
  });
  expect(physicianLogin.ok()).toBeTruthy();
  const response = await request.get(`/api/v1/runs/${runId}`);
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as {
    run: { revision: number; status: string };
    stale: boolean;
    projections: Array<{ question_key: string }>;
  };
  return {
    revision: body.run.revision,
    status: body.run.status,
    stale: body.stale,
    questionKeys: body.projections.map((p) => p.question_key),
  };
}

async function loginViaUI(
  page: Page,
  username: string,
  password: string,
  role: string,
): Promise<void> {
  await page.goto("/");
  await page.getByLabel(/username/i).fill(username);
  await page.getByLabel(/password/i).fill(password);
  const roleField = page.getByLabel(/role/i);
  if ((await roleField.count()) > 0) {
    await roleField.first().selectOption(role).catch(async () => {
      await roleField.first().fill(role);
    });
  }
  await page.getByRole("button", { name: /log ?in|sign ?in/i }).click();
}

async function dismissResearchNotice(page: Page): Promise<void> {
  await expect(page.getByText(RESEARCH_NOTICE, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();
}

async function openDraftForPatient(page: Page, patientId: string): Promise<void> {
  await page.getByLabel(/search patients/i).fill(patientId);
  await page.getByRole("button", { name: `Open draft ${patientId}` }).click();
  await expect(page.getByRole("heading", { name: /draft/i })).toBeVisible();
}

async function reopenDraftAfterReload(page: Page, patientId: string): Promise<void> {
  await page.reload();
  await openDraftForPatient(page, patientId);
}

function isRunPost(url: string, method: string): boolean {
  return method === "POST" && /\/api\/v1\/encounters\/[^/]+\/runs$/.test(url);
}

function isRetryPost(url: string, method: string): boolean {
  return method === "POST" && /\/api\/v1\/runs\/[^/]+\/retry$/.test(url);
}

function isRunGet(url: string, method: string): boolean {
  return method === "GET" && /\/api\/v1\/runs\/[^/]+$/.test(url);
}

interface CollectedRunPost {
  runId: string | null;
  status: number;
}

// Persistent collectors: attach BEFORE openDraftForPatient (entry fires on
// section visibility). Response bodies resolve async; poll via waitForCount.
function collectRunPosts(page: Page, posts: CollectedRunPost[]): void {
  page.on("response", (resp) => {
    const req = resp.request();
    if (!isRunPost(req.url(), req.method())) {
      return;
    }
    resp
      .json()
      .then((body) => {
        const runId = (body as { run_id?: unknown }).run_id;
        posts.push({ runId: typeof runId === "string" ? runId : null, status: resp.status() });
      })
      .catch(() => posts.push({ runId: null, status: resp.status() }));
  });
}

function collectRetryPosts(page: Page, posts: Array<{ body: unknown }>): void {
  page.on("request", (req) => {
    if (!isRetryPost(req.url(), req.method())) {
      return;
    }
    try {
      posts.push({ body: JSON.parse(req.postData() ?? "null") });
    } catch {
      posts.push({ body: null });
    }
  });
}

function collectRunGets(page: Page, stamps: number[]): void {
  page.on("request", (req) => {
    if (isRunGet(req.url(), req.method())) {
      stamps.push(Date.now());
    }
  });
}

async function waitForLength(
  page: Page,
  arr: unknown[],
  count: number,
  timeout = 15_000,
): Promise<void> {
  const start = Date.now();
  while (arr.length < count) {
    if (Date.now() - start > timeout) {
      throw new Error(`timed out waiting for ${count} entries (have ${arr.length})`);
    }
    await page.waitForTimeout(250);
  }
}

function distinctRunIds(posts: CollectedRunPost[]): string[] {
  return [...new Set(posts.map((p) => p.runId).filter((id): id is string => id !== null))];
}

// Test-only state seeding onto a real run (no FKs between run tables, so
// INSERTs are safe; unique constraints make reseeds idempotent).
async function seedJobStateViaDb(args: {
  runId: string;
  encounterId: string;
  authorId: string;
  questionKey: string;
  ordinal: number;
  stage: string;
  status: string;
  failure: Record<string, unknown> | null;
}): Promise<void> {
  assertUuid(args.runId);
  const failure = args.failure === null ? "NULL" : `CAST(${sqlQuote(JSON.stringify(args.failure))} AS JSONB)`;
  const stdout = await psql(
    "INSERT INTO reasoning_jobs (run_id, encounter_id, author_id, question_key, ordinal, stage, status, failure_details) VALUES (" +
      `'${args.runId}', '${args.encounterId}', '${args.authorId}', ` +
      `${sqlQuote(args.questionKey)}, ${args.ordinal}, ${sqlQuote(args.stage)}, ${sqlQuote(args.status)}, ${failure}) ` +
      "ON CONFLICT (run_id, question_key) DO UPDATE SET stage = EXCLUDED.stage, " +
      "status = EXCLUDED.status, failure_details = EXCLUDED.failure_details, updated_at = now()",
  );
  expect(stdout).toMatch(/INSERT 0 1|UPDATE 1/);
}

async function deleteJobsViaDb(runId: string): Promise<void> {
  assertUuid(runId);
  await psql(`DELETE FROM reasoning_jobs WHERE run_id = '${runId}'`);
}

async function setProjectionGateViaDb(
  runId: string,
  questionKey: string,
  applicability: string,
  reason: string,
): Promise<void> {
  assertUuid(runId);
  const stdout = await psql(
    "UPDATE run_questions SET projection = jsonb_set(jsonb_set(projection, " +
      `'{applicability}', to_jsonb(${sqlQuote(applicability)}::text)), ` +
      `'{applicability_reason}', to_jsonb(${sqlQuote(reason)}::text)) ` +
      `WHERE run_id = '${runId}' AND question_key = ${sqlQuote(questionKey)}`,
  );
  expect(stdout).toMatch(/UPDATE 1/);
}

async function setProjectionFactsMarkerViaDb(
  runId: string,
  questionKey: string,
  marker: string,
): Promise<void> {
  assertUuid(runId);
  const stdout = await psql(
    "UPDATE run_questions SET projection = jsonb_set(projection, " +
      `'{facts,SYNTHETIC_INPUT_MARKER}', to_jsonb(${sqlQuote(marker)}::text)) ` +
      `WHERE run_id = '${runId}' AND question_key = ${sqlQuote(questionKey)}`,
  );
  expect(stdout).toMatch(/UPDATE 1/);
}

// Succeeded artifact copies the persisted projection (never live chart
// values); accepted percentages + posterior + provenance are synthetic.
// NOTE: GET /runs/{id} surfaces only prompt/template_version/engine +
// source_paths/missingness (runs.py _section_payload); provenance.prompt_version
// is never surfaced. The syn-p1 marker therefore lives in the surfaced prompt
// text below (production-compatible seed), not just in provenance.
async function seedSucceededArtifactViaDb(
  runId: string,
  questionKey: string,
  ordinal: number,
): Promise<void> {
  assertUuid(runId);
  const accepted = JSON.stringify({
    question_key: questionKey,
    network_version: "syn-net-v1",
    tables: [
      {
        node_id: "SYN_A",
        parent_ids: [],
        states: ["no", "yes"],
        rows: [{ parent_states: [], percentages: [62.5, 37.5] }],
      },
    ],
  });
  const result = JSON.stringify({ SYN_A_yes_posterior_pct: 41.25 });
  const provenance = JSON.stringify({
    network_version: "syn-net-v1",
    source_paths: ["encounters.draft_data.history"],
    missingness: { SYN_A: "observed" },
    engine: { name: "synthetic-exact", version: "s48" },
    prompt_version: "syn-p1",
    template_version: "syn-t1",
  });
  const stdout = await psql(
    "INSERT INTO run_question_artifacts (run_id, question_key, ordinal, stage, status, " +
      "request, projection, prompt, model, accepted, effective_xml, effective_hash, " +
      "query, result, rendered_section, template_version, provenance) " +
      "SELECT " +
      `'${runId}', ${sqlQuote(questionKey)}, ${ordinal}, 'succeeded', 'succeeded', ` +
      `CAST('{}' AS JSONB), projection, 'SYNTHETIC PROMPT s48 syn-p1', CAST('{}' AS JSONB), ` +
      `CAST(${sqlQuote(accepted)} AS JSONB), '<synthetic/>', 'synthetic-hash', ` +
      `CAST('{}' AS JSONB), CAST(${sqlQuote(result)} AS JSONB), ` +
      `${sqlQuote(`SYNTHETIC SECTION ${questionKey} s48`)}, 'syn-t1', ` +
      `CAST(${sqlQuote(provenance)} AS JSONB) ` +
      `FROM run_questions WHERE run_id = '${runId}' AND question_key = ${sqlQuote(questionKey)} ` +
      "ON CONFLICT (run_id, question_key) DO UPDATE SET status = 'succeeded', " +
      "accepted = EXCLUDED.accepted, result = EXCLUDED.result, " +
      "rendered_section = EXCLUDED.rendered_section, provenance = EXCLUDED.provenance, " +
      "projection = EXCLUDED.projection, updated_at = now()",
  );
  expect(stdout).toMatch(/INSERT 0 1|UPDATE 1/);
}

async function seedSucceededProposalViaDb(runId: string): Promise<void> {
  assertUuid(runId);
  // Production shape: ddi_report lives INSIDE the proposal JSON
  // (proposal.py assembled dd, UI reads proposal.ddi_report). GET never
  // selects the run_proposals.ddi_report column, so the seed embeds the same
  // report in both places; the column write is retained for parity.
  const ddiReport = {
    dataset_version: "synthetic-e2e-ddi-s48",
    pairs: [],
    limitations: ["SYNTHETIC DDI coverage unavailable for pair syn-a:syn-b"],
  };
  const proposal = JSON.stringify({
    title: "SYNTHETIC INITIAL PROPOSAL s48",
    sections: [
      { question_key: SYN_Q1, text: `SYNTHETIC SECTION ${SYN_Q1} s48` },
      { question_key: SYN_Q2, text: `SYNTHETIC SECTION ${SYN_Q2} s48` },
    ],
    coverage_note: "SYNTHETIC limited coverage",
    limitations: ["SYNTHETIC limitation one"],
    ddi_report: ddiReport,
  });
  const ddi = JSON.stringify(ddiReport);
  const stdout = await psql(
    "INSERT INTO run_proposals (run_id, status, proposal, ddi_report) VALUES (" +
      `'${runId}', 'succeeded', CAST(${sqlQuote(proposal)} AS JSONB), ` +
      `CAST(${sqlQuote(ddi)} AS JSONB)) ` +
      "ON CONFLICT (run_id) DO UPDATE SET status = 'succeeded', " +
      "proposal = EXCLUDED.proposal, ddi_report = EXCLUDED.ddi_report, updated_at = now()",
  );
  expect(stdout).toMatch(/INSERT 0 1|UPDATE 1/);
}

async function clearProposalViaDb(runId: string): Promise<void> {
  assertUuid(runId);
  await psql(`DELETE FROM run_proposals WHERE run_id = '${runId}'`);
}

async function setRunStatusViaDb(runId: string, status: string): Promise<void> {
  assertUuid(runId);
  const stdout = await psql(
    `UPDATE runs SET status = ${sqlQuote(status)}, updated_at = now() WHERE id = '${runId}'`,
  );
  expect(stdout).toMatch(/UPDATE 1/);
}

// Journey 1 (RED): entry flushes autosave and auto-creates/reuses one run.
// Blocked-while-unsaved is asserted as "no additional run POST + visible
// prerequisite/pending state", so it holds regardless of which clinical
// prerequisites the implementer additionally gates on.
test("entry flushes autosave and auto-creates/reuses a run", async ({ page, request }) => {
  await seedSyntheticBundlePointerViaDb();
  const ctx = await setupPhysicianDraft(request);
  await loginViaUI(page, ctx.username, ctx.password, "physician");
  await dismissResearchNotice(page);

  const runPosts: CollectedRunPost[] = [];
  collectRunPosts(page, runPosts);
  await openDraftForPatient(page, ctx.patientId);

  // RED: timeouts here until ProposalReviewSection exists.
  const section = page.getByTestId("proposal-review-section");
  await expect(section).toBeVisible();

  // Entry flushes autosave through the shared Saved (rev N) contract.
  await page
    .getByTestId("history-item-synthetic_flag_true")
    .selectOption("known_true");
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });

  // One automatic run, no extra Generate button.
  await waitForLength(page, runPosts, 1);
  expect(distinctRunIds(runPosts)).toHaveLength(1);
  const runId = distinctRunIds(runPosts)[0] ?? "";
  assertUuid(runId);
  await expect(page.getByTestId("proposal-run-status")).not.toBeEmpty();
  await expect(section.getByRole("button", { name: /generate/i })).toHaveCount(0);

  // Unsaved edits block: while Saving…, a prerequisite/pending state is
  // visible and no additional run is triggered.
  await page.getByLabel(/draft note/i).fill(`synthetic-dirty-${Date.now().toString(36)}`);
  await expect(page.getByRole("status")).toContainText(/Saving/i, { timeout: 10_000 });
  await expect(page.getByTestId("proposal-run-status")).toContainText(
    /prerequisite|unsaved|not saved|saving|pending|waiting/i,
  );
  const postsWhileDirty = runPosts.length;
  await page.waitForTimeout(2000);
  expect(runPosts.length).toBe(postsWhileDirty);

  // Flush + keystrokes never mint a second run.
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });
  await page.getByLabel(/draft note/i).fill(`synthetic-key-a-${Date.now().toString(36)}`);
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });
  await page.getByLabel(/draft note/i).fill(`synthetic-key-b-${Date.now().toString(36)}`);
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });
  expect(distinctRunIds(runPosts)).toEqual([runId]);

  // Re-entry reuses the run (202): exactly one more POST, same run_id.
  const beforeReentry = runPosts.length;
  await reopenDraftAfterReload(page, ctx.patientId);
  await expect(page.getByTestId("proposal-review-section")).toBeVisible();
  await waitForLength(page, runPosts, beforeReentry + 1);
  expect(distinctRunIds(runPosts)).toEqual([runId]);
});

// Journey 2 (RED): ordered states, precise retry, polling stops at terminal.
test("ordered question states with precise retry and terminal polling stop", async ({
  page,
  request,
}) => {
  await seedSyntheticBundlePointerViaDb();
  const ctx = await setupPhysicianDraft(request);
  await loginViaUI(page, ctx.username, ctx.password, "physician");
  await dismissResearchNotice(page);

  const runPosts: CollectedRunPost[] = [];
  collectRunPosts(page, runPosts);
  const runGets: number[] = [];
  collectRunGets(page, runGets);
  const retryPosts: Array<{ body: unknown }> = [];
  collectRetryPosts(page, retryPosts);
  await openDraftForPatient(page, ctx.patientId);

  // RED: timeouts here until ProposalReviewSection exists.
  await expect(page.getByTestId("proposal-review-section")).toBeVisible();
  await waitForLength(page, runPosts, 1);
  const runId = distinctRunIds(runPosts)[0] ?? "";
  expect(runId, "entry POST must yield a run_id (synthetic bundle pointer seeded)").toBeTruthy();
  assertUuid(runId);
  const initial = await getRunViaPhysicianApi(request, ctx.username, ctx.password, runId);
  expect(initial.questionKeys).toEqual([SYN_Q1, SYN_Q2]);

  // Phase 1: active states render in bundle order; polling stays alive.
  await seedJobStateViaDb({
    runId,
    encounterId: ctx.encounterId,
    authorId: ctx.authorId,
    questionKey: SYN_Q1,
    ordinal: 0,
    stage: "inferring",
    status: "running",
    failure: null,
  });
  await seedJobStateViaDb({
    runId,
    encounterId: ctx.encounterId,
    authorId: ctx.authorId,
    questionKey: SYN_Q2,
    ordinal: 1,
    stage: "preparing_question",
    status: "queued",
    failure: null,
  });
  await reopenDraftAfterReload(page, ctx.patientId);
  // Rows only: the prefix selector would also match the nested
  // proposal-question-state-<key> children (4 nodes), so scope to the exact
  // row testids. Locator order is DOM order, which pins bundle order.
  await expect(page.getByTestId(`proposal-question-${SYN_Q1}`)).toBeVisible();
  await expect(page.getByTestId(`proposal-question-${SYN_Q2}`)).toBeVisible();
  const order = await page
    .locator(
      `[data-testid="proposal-question-${SYN_Q1}"], [data-testid="proposal-question-${SYN_Q2}"]`,
    )
    .all();
  expect(order).toHaveLength(2);
  expect(await order[0].getAttribute("data-testid")).toBe(`proposal-question-${SYN_Q1}`);
  expect(await order[1].getAttribute("data-testid")).toBe(`proposal-question-${SYN_Q2}`);
  await expect(page.getByTestId(`proposal-question-state-${SYN_Q1}`)).toContainText(
    /running|inferring/i,
  );
  await expect(page.getByTestId(`proposal-question-state-${SYN_Q2}`)).toContainText(
    /pending|queued/i,
  );
  const getsBefore = runGets.length;
  await page.waitForTimeout(5000);
  expect(runGets.length).toBeGreaterThan(getsBefore);

  // Phase 2: gate states with reasons (jobs removed so gates decide).
  await deleteJobsViaDb(runId);
  await setProjectionGateViaDb(
    runId,
    SYN_Q1,
    "not_applicable",
    "SYNTHETIC not applicable reason s48",
  );
  await setProjectionGateViaDb(
    runId,
    SYN_Q2,
    "needs_clarification",
    "SYNTHETIC clarification field s48",
  );
  await reopenDraftAfterReload(page, ctx.patientId);
  await expect(page.getByTestId(`proposal-question-${SYN_Q1}`)).toContainText(
    /not applicable|skipped/i,
  );
  await expect(page.getByTestId(`proposal-question-${SYN_Q1}`)).toContainText(
    "SYNTHETIC not applicable reason s48",
  );
  await expect(page.getByTestId(`proposal-question-${SYN_Q2}`)).toContainText(
    /clarification/i,
  );
  await expect(page.getByTestId(`proposal-question-${SYN_Q2}`)).toContainText(
    "SYNTHETIC clarification field s48",
  );

  // Phase 3: failed + retained completed section; precise retry; poll stop.
  await setProjectionGateViaDb(runId, SYN_Q1, "ready", "SYNTHETIC ready s48");
  await setProjectionGateViaDb(runId, SYN_Q2, "ready", "SYNTHETIC ready s48");
  await seedJobStateViaDb({
    runId,
    encounterId: ctx.encounterId,
    authorId: ctx.authorId,
    questionKey: SYN_Q1,
    ordinal: 0,
    stage: "estimating_cpts",
    status: "failed",
    failure: { error: "SYNTHETIC_ESTIMATION_TIMEOUT", retryable: true },
  });
  await seedJobStateViaDb({
    runId,
    encounterId: ctx.encounterId,
    authorId: ctx.authorId,
    questionKey: SYN_Q2,
    ordinal: 1,
    stage: "rendering",
    status: "succeeded",
    failure: null,
  });
  await seedSucceededArtifactViaDb(runId, SYN_Q2, 1);
  await setRunStatusViaDb(runId, "failed");
  await reopenDraftAfterReload(page, ctx.patientId);
  await expect(page.getByTestId(`proposal-question-state-${SYN_Q1}`)).toContainText(/failed/i);
  // Partial run: the completed section stays retained and readable.
  await expect(page.getByTestId(`proposal-section-${SYN_Q2}`)).toContainText(
    `SYNTHETIC SECTION ${SYN_Q2} s48`,
  );
  await expect(page.getByTestId(`proposal-retry-${SYN_Q1}`)).toBeVisible();
  await expect(page.getByTestId(`proposal-retry-${SYN_Q2}`)).toHaveCount(0);

  // Terminal state stops polling: no new run GETs over the wait window.
  await page.waitForTimeout(1000);
  const terminalGets = runGets.length;
  expect(terminalGets).toBeGreaterThan(0);
  await page.waitForTimeout(6000);
  expect(runGets.length).toBe(terminalGets);

  // Precise retry issues POST /runs/{id}/retry with the exact contract body.
  const live = await getRunViaPhysicianApi(request, ctx.username, ctx.password, runId);
  await page.getByTestId(`proposal-retry-${SYN_Q1}`).click();
  await waitForLength(page, retryPosts, 1);
  expect(retryPosts[0]?.body).toEqual({
    question_key: SYN_Q1,
    failed_stage: "estimating_cpts",
    expected_run_revision: live.revision,
  });
  await expect(page.getByTestId(`proposal-question-state-${SYN_Q1}`)).toContainText(
    /queued|retry/i,
    { timeout: 10_000 },
  );
});

// Journey 3 (RED): five transparency fields, persisted inputs, note isolation.
test("completed sections show persisted transparency fields without note leakage", async ({
  page,
  request,
}) => {
  await seedSyntheticBundlePointerViaDb();
  const ctx = await setupPhysicianDraft(request);
  await loginViaUI(page, ctx.username, ctx.password, "physician");
  await dismissResearchNotice(page);

  const runPosts: CollectedRunPost[] = [];
  collectRunPosts(page, runPosts);
  await openDraftForPatient(page, ctx.patientId);

  // RED: timeouts here until ProposalReviewSection exists.
  await expect(page.getByTestId("proposal-review-section")).toBeVisible();
  await waitForLength(page, runPosts, 1);
  const runId = distinctRunIds(runPosts)[0] ?? "";
  expect(runId, "entry POST must yield a run_id (synthetic bundle pointer seeded)").toBeTruthy();
  assertUuid(runId);

  const inputMarker = uniqueMarker("SYN-INPUT");
  await setProjectionFactsMarkerViaDb(runId, SYN_Q1, inputMarker);
  await seedSucceededArtifactViaDb(runId, SYN_Q1, 0);
  await reopenDraftAfterReload(page, ctx.patientId);

  const section = page.getByTestId(`proposal-section-${SYN_Q1}`);
  await section.click().catch(() => undefined);
  // All five transparency fields beside the recommendation.
  await expect(page.getByTestId(`proposal-question-${SYN_Q1}`)).toBeVisible();
  await expect(section).toContainText("syn-net-v1");
  await expect(page.getByTestId(`proposal-inputs-${SYN_Q1}`)).toContainText(inputMarker);
  const cpt = page.getByTestId(`proposal-cpt-${SYN_Q1}`);
  await expect(cpt).toContainText("62.5");
  await expect(cpt).toContainText(/CPT/i);
  await expect(cpt).not.toContainText(/posterior/i);
  const result = page.getByTestId(`proposal-result-${SYN_Q1}`);
  await expect(result).toContainText("41.25");
  await expect(result).toContainText(/posterior/i);
  await expect(result).not.toContainText(/CPT/i);
  // Sources, missingness, versions travel with the persisted section.
  await expect(section).toContainText("encounters.draft_data.history");
  await expect(section).toContainText("observed");
  await expect(section).toContainText("syn-p1");
  await expect(section).toContainText("syn-t1");

  // Page-note text never leaks into the proposal-review/projections display.
  const noteText = uniqueMarker("SYN-NOTE-LEAK");
  await page.getByTestId("notes-text").fill(noteText);
  await page.getByTestId("notes-add").click();
  await expect(page.getByTestId("notes-list")).toContainText(noteText);
  await expect(page.getByTestId("proposal-review-section")).not.toContainText(noteText);
  await expect(page.getByTestId(`proposal-inputs-${SYN_Q1}`)).not.toContainText(noteText);

  // Refresh loads the same persisted inputs, not recomputed chart values.
  // Disclosure (expanded/collapsed) is in-memory UI state only, so re-expand
  // after the reload before asserting the persisted values.
  await reopenDraftAfterReload(page, ctx.patientId);
  await expect(page.getByTestId(`proposal-section-${SYN_Q1}`)).toBeVisible();
  await page.getByTestId(`proposal-section-${SYN_Q1}`).click().catch(() => undefined);
  await expect(page.getByTestId(`proposal-inputs-${SYN_Q1}`)).toContainText(inputMarker);
  await expect(page.getByTestId(`proposal-cpt-${SYN_Q1}`)).toContainText("62.5");
});

// Journey 4 (RED): final proposal + secondary plan; failed/partial blocks sign.
test("final proposal renders with a separate secondary plan; failed runs block signing", async ({
  page,
  request,
}) => {
  await seedSyntheticBundlePointerViaDb();
  const ctx = await setupPhysicianDraft(request);
  await loginViaUI(page, ctx.username, ctx.password, "physician");
  await dismissResearchNotice(page);

  const runPosts: CollectedRunPost[] = [];
  collectRunPosts(page, runPosts);
  await openDraftForPatient(page, ctx.patientId);

  // RED: timeouts here until ProposalReviewSection exists.
  await expect(page.getByTestId("proposal-review-section")).toBeVisible();
  await waitForLength(page, runPosts, 1);
  const runId = distinctRunIds(runPosts)[0] ?? "";
  expect(runId, "entry POST must yield a run_id (synthetic bundle pointer seeded)").toBeTruthy();
  assertUuid(runId);

  // Succeeded run: immutable initial proposal + DDI + separate secondary plan.
  await seedSucceededArtifactViaDb(runId, SYN_Q1, 0);
  await seedSucceededArtifactViaDb(runId, SYN_Q2, 1);
  await seedSucceededProposalViaDb(runId);
  await setRunStatusViaDb(runId, "succeeded");
  await reopenDraftAfterReload(page, ctx.patientId);
  const proposal = page.getByTestId("proposal-proposal");
  await expect(proposal).toContainText("SYNTHETIC INITIAL PROPOSAL s48");
  await expect(proposal.locator("textarea, input")).toHaveCount(0);
  await expect(page.getByTestId("proposal-ddi")).toContainText(/coverage|limitation/i);
  await expect(page.getByTestId("proposal-ddi")).toContainText("SYNTHETIC DDI coverage unavailable");
  const secondary = page.getByTestId("proposal-secondary-plan");
  await expect(secondary).toBeVisible();
  await expect(secondary).toBeEditable();
  await secondary.fill("SYNTHETIC secondary plan s48");
  await expect(secondary).toHaveValue("SYNTHETIC secondary plan s48");
  await expect(page.getByTestId("proposal-sign-blocked")).toBeHidden();

  // Failed/partial run: signing visibly blocked, editing + retry preserved.
  await clearProposalViaDb(runId);
  await setRunStatusViaDb(runId, "failed");
  await seedJobStateViaDb({
    runId,
    encounterId: ctx.encounterId,
    authorId: ctx.authorId,
    questionKey: SYN_Q1,
    ordinal: 0,
    stage: "estimating_cpts",
    status: "failed",
    failure: { error: "SYNTHETIC_ESTIMATION_TIMEOUT", retryable: true },
  });
  await reopenDraftAfterReload(page, ctx.patientId);
  await expect(page.getByTestId("proposal-sign-blocked")).toBeVisible();
  await expect(page.getByTestId("proposal-sign-blocked")).toContainText(
    /cannot sign|blocked|failed|incomplete/i,
  );
  await page.getByLabel(/draft note/i).fill(`synthetic-still-editable-${Date.now().toString(36)}`);
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });
  await expect(page.getByTestId(`proposal-retry-${SYN_Q1}`)).toBeVisible();
});
