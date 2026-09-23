import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const execFileAsync = promisify(execFile);

// S50 (RED — T9 journey contract, signing UI not implemented).
// SYNTHETIC FIXTURES ONLY. These 4 journeys pin the frontend contract for
// the S50 implementer; they timeout on the missing selectors until built.
// Seams: T1 (backend signing routes, green) and T9 (this spec, e2e).
//
// data-testid contract the frontend implementer builds to (stable selectors):
// - signing-section: review region wrapping proposal + secondary + sign
// - signing-proposal: immutable initial proposal text (no textarea/input inside)
// - signing-secondary-plan: editable textarea for author on draft;
//   read-only/disabled when signed or non-author
// - signing-comparison: visible diff/comparison showing physician edits vs
//   proposal (contains both proposal excerpt and edited text marker)
// - signing-review-ack: checkbox for review acknowledgment
// - signing-baseline-ack: checkbox for follow-up baseline (absent on registration)
// - signing-sign-button: explicit Sign button
// - signing-status: sign eligibility / error line (stale/failed messages)
// - signing-signed-view: read-only signed container with signer/time
// - signing-signer, signing-time: provenance
// - signing-print: print navigation link/button
// - signing-addendum-reason, signing-addendum-text, signing-addendum-submit,
//   signing-addenda-list, signing-addendum-item: original-signer correction UI
//
// Seeding (test-only, never production routes; psql precedent follows
// e2e/proposal-review.spec.ts — node `pg` is unavailable, /usr/bin/psql exists):
// 1. seedSyntheticBundlePointerViaDb inserts a synthetic 2-question bundle
//    pointer (pins.questions = syn_q_one, syn_q_two, no gates/mappings, so
//    both evaluate ready). The UI's entry POST /encounters/{id}/runs then
//    creates a REAL run through the real backend (no provider needed; no
//    worker runs e2e so jobs stay put until reseeded).
// 2. Succeeded states are seeded as run_question_artifacts / run_proposals rows
//    keyed to the run_id captured from the UI's own entry POST response
//    (public HTTP discovery), exactly like S48 journey 4. No live provider,
//    no stub server, no clinical content.
// 3. Journey 1 persistence MUST go through the UI textarea into the SERVER
//    secondary-plan route (PATCH/GET /encounters/{id}/secondary-plan), never
//    draft_data.secondary_plan (S48 legacy path). The spec asserts the server
//    route value after reload, so it fails red until S50 migrates the wiring.

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

const TEST_DATABASE_URL =
  "postgresql://xinsight:xinsight_dev@localhost:5432/xinsight_test";

const SYN_Q1 = "syn_q_one";
const SYN_Q2 = "syn_q_two";
const SYN_BUNDLE_HASH = "synthetic-e2e-bundle-s50";
const SYN_PROPOSAL_TITLE = "SYNTHETIC INITIAL PROPOSAL s50";

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

async function physicianCsrfViaApi(
  request: APIRequestContext,
  username: string,
  password: string,
): Promise<string> {
  const physicianLogin = await request.post("/api/v1/auth/login", {
    data: { username, password, role: "physician" },
  });
  expect(physicianLogin.ok()).toBeTruthy();
  const storage = await request.storageState();
  const csrf = storage.cookies.find((c) => c.name === "xinsight_csrf")?.value;
  expect(csrf).toBeTruthy();
  return csrf ?? "";
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

interface CollectedRunPost {
  runId: string | null;
  status: number;
}

// Persistent collectors: attach BEFORE openDraftForPatient (entry fires on
// section visibility). Response bodies resolve async; poll via waitForLength.
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

// Succeeded artifact copies the persisted projection (never live chart
// values); accepted percentages + posterior + provenance are synthetic.
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
    engine: { name: "synthetic-exact", version: "s50" },
    prompt_version: "syn-p1",
    template_version: "syn-t1",
  });
  const stdout = await psql(
    "INSERT INTO run_question_artifacts (run_id, question_key, ordinal, stage, status, " +
      "request, projection, prompt, model, accepted, effective_xml, effective_hash, " +
      "query, result, rendered_section, template_version, provenance) " +
      "SELECT " +
      `'${runId}', ${sqlQuote(questionKey)}, ${ordinal}, 'succeeded', 'succeeded', ` +
      `CAST('{}' AS JSONB), projection, 'SYNTHETIC PROMPT s50 syn-p1', CAST('{}' AS JSONB), ` +
      `CAST(${sqlQuote(accepted)} AS JSONB), '<synthetic/>', 'synthetic-hash', ` +
      `CAST('{}' AS JSONB), CAST(${sqlQuote(result)} AS JSONB), ` +
      `${sqlQuote(`SYNTHETIC SECTION ${questionKey} s50`)}, 'syn-t1', ` +
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
  // (proposal.py assembled dd, UI reads proposal.ddi_report).
  const ddiReport = {
    dataset_version: "synthetic-e2e-ddi-s50",
    pairs: [],
    limitations: ["SYNTHETIC DDI coverage unavailable for pair syn-a:syn-b"],
  };
  const proposal = JSON.stringify({
    title: SYN_PROPOSAL_TITLE,
    sections: [
      { question_key: SYN_Q1, text: `SYNTHETIC SECTION ${SYN_Q1} s50` },
      { question_key: SYN_Q2, text: `SYNTHETIC SECTION ${SYN_Q2} s50` },
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

async function setRunStatusViaDb(runId: string, status: string): Promise<void> {
  assertUuid(runId);
  const stdout = await psql(
    `UPDATE runs SET status = ${sqlQuote(status)}, updated_at = now() WHERE id = '${runId}'`,
  );
  expect(stdout).toMatch(/UPDATE 1/);
}

async function seedSucceededRunViaDb(
  runId: string,
): Promise<void> {
  await seedSucceededArtifactViaDb(runId, SYN_Q1, 0);
  await seedSucceededArtifactViaDb(runId, SYN_Q2, 1);
  await seedSucceededProposalViaDb(runId);
  await setRunStatusViaDb(runId, "succeeded");
}

async function getSecondaryPlanViaApi(
  request: APIRequestContext,
  username: string,
  password: string,
  encounterId: string,
): Promise<{ revision: number; text: string | null }> {
  await physicianCsrfViaApi(request, username, password);
  const response = await request.get(`/api/v1/encounters/${encounterId}/secondary-plan`);
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as {
    secondary_plan?: { revision: number; text: string } | null;
    current?: { revision: number; text: string } | null;
  };
  const current = body.secondary_plan ?? body.current ?? null;
  return {
    revision: current?.revision ?? 0,
    text: current?.text ?? null,
  };
}

// Journey 1 (RED, S50.1): successful proposal appears unchanged beside an
// editable secondary plan; edits persist through reload via the SERVER
// secondary-plan route and a visible comparison shows physician edits.
test("proposal beside editable secondary persists via server with comparison", async ({
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

  // RED: timeouts here until the S50 signing section exists.
  await expect(page.getByTestId("signing-section")).toBeVisible();

  // A REAL succeeded run: entry POST creates it, artifacts reseeded onto it.
  await waitForLength(page, runPosts, 1);
  const runId = distinctRunIds(runPosts)[0] ?? "";
  expect(runId, "entry POST must yield a run_id (synthetic bundle pointer seeded)").toBeTruthy();
  assertUuid(runId);
  await seedSucceededRunViaDb(runId);
  await reopenDraftAfterReload(page, ctx.patientId);

  // Immutable initial proposal: text present, no editable controls inside.
  const proposal = page.getByTestId("signing-proposal");
  await expect(proposal).toContainText(SYN_PROPOSAL_TITLE);
  await expect(proposal.locator("textarea, input")).toHaveCount(0);

  // Editable secondary plan beside it, wired to the server route.
  const secondary = page.getByTestId("signing-secondary-plan");
  await expect(secondary).toBeVisible();
  await expect(secondary).toBeEditable();
  const marker = uniqueMarker("SYN-SECONDARY-S50");
  await secondary.fill(marker);
  await expect(secondary).toHaveValue(marker);

  // Persistence is through reload via the SERVER route, not draft_data.
  await page.waitForTimeout(2000);
  await reopenDraftAfterReload(page, ctx.patientId);
  await expect(page.getByTestId("signing-secondary-plan")).toHaveValue(marker);
  const serverPlan = await getSecondaryPlanViaApi(
    request,
    ctx.username,
    ctx.password,
    ctx.encounterId,
  );
  expect(serverPlan.text).not.toBeNull();
  expect(serverPlan.text ?? "").toContain(marker);

  // Visible comparison shows physician edits against the proposal.
  const comparison = page.getByTestId("signing-comparison");
  await expect(comparison).toBeVisible();
  await expect(comparison).toContainText(marker);
  await expect(comparison).toContainText(SYN_PROPOSAL_TITLE);
});

// Journey 2 (RED, S50.2): explicit Sign flushes pending saves, collects
// review/baseline acknowledgments and submits current revisions; a
// failed-generation run blocks signing with a precise eligibility error and
// no force-sign escape hatch exists.
test("explicit sign submits current revisions; failed generation blocks sign", async ({
  page,
  request,
}) => {
  await seedSyntheticBundlePointerViaDb();

  // Part A: successful registration sign through the UI.
  const ctx = await setupPhysicianDraft(request);
  await loginViaUI(page, ctx.username, ctx.password, "physician");
  await dismissResearchNotice(page);

  const runPosts: CollectedRunPost[] = [];
  collectRunPosts(page, runPosts);
  await openDraftForPatient(page, ctx.patientId);

  // RED: timeouts here until the S50 signing section exists.
  await expect(page.getByTestId("signing-section")).toBeVisible();
  await waitForLength(page, runPosts, 1);
  const runId = distinctRunIds(runPosts)[0] ?? "";
  assertUuid(runId);
  await seedSucceededRunViaDb(runId);
  await reopenDraftAfterReload(page, ctx.patientId);

  const secondaryMarker = uniqueMarker("SYN-SECONDARY-SIGN-S50");
  await page.getByTestId("signing-secondary-plan").fill(secondaryMarker);
  await page.getByTestId("signing-review-ack").check();
  // Registration has no follow-up baseline acknowledgment.
  await expect(page.getByTestId("signing-baseline-ack")).toHaveCount(0);
  await page.getByTestId("signing-sign-button").click();

  const signedView = page.getByTestId("signing-signed-view");
  await expect(signedView).toBeVisible();
  await expect(page.getByTestId("signing-signer")).toContainText(ctx.username);
  await expect(page.getByTestId("signing-time")).not.toBeEmpty();
  // No force-sign escape hatch anywhere on the page.
  await expect(page.getByRole("button", { name: /force/i })).toHaveCount(0);

  // Part B: failed-generation variant — fresh draft, failed run, no proposal.
  await page.context().clearCookies();
  const failed = await setupPhysicianDraft(request);
  await loginViaUI(page, failed.username, failed.password, "physician");
  await dismissResearchNotice(page);

  const failedRunPosts: CollectedRunPost[] = [];
  collectRunPosts(page, failedRunPosts);
  await openDraftForPatient(page, failed.patientId);
  await expect(page.getByTestId("signing-section")).toBeVisible();
  await waitForLength(page, failedRunPosts, 1);
  const failedRunId = distinctRunIds(failedRunPosts)[0] ?? "";
  assertUuid(failedRunId);
  await seedJobStateViaDb({
    runId: failedRunId,
    encounterId: failed.encounterId,
    authorId: failed.authorId,
    questionKey: SYN_Q1,
    ordinal: 0,
    stage: "estimating_cpts",
    status: "failed",
    failure: { error: "SYNTHETIC_ESTIMATION_TIMEOUT", retryable: true },
  });
  await setRunStatusViaDb(failedRunId, "failed");
  await reopenDraftAfterReload(page, failed.patientId);

  // Sign visibly blocked with a precise eligibility error; edited text kept.
  await expect(page.getByTestId("signing-status")).toContainText(
    /blocked|failed|cannot sign|no proposal/i,
  );
  const preservedMarker = uniqueMarker("SYN-SECONDARY-FAILED-S50");
  await page.getByTestId("signing-secondary-plan").fill(preservedMarker);
  const signButton = page.getByTestId("signing-sign-button");
  if ((await signButton.count()) > 0) {
    await signButton.first().click();
    await expect(page.getByTestId("signing-status")).toContainText(
      /blocked|failed|cannot sign|no proposal/i,
    );
  }
  await expect(page.getByTestId("signing-secondary-plan")).toHaveValue(preservedMarker);
  await expect(page.getByTestId("signing-signed-view")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /force/i })).toHaveCount(0);

  // Direct server denial: POST /sign on the failed run returns 409.
  // NOTE (S50 harness fix): the CSRF token must be read AFTER the last
  // login — getSecondaryPlanViaApi logs in again and rotates the session,
  // so a token captured before it is stale and the POST would 403.
  const encounterRes = await request.get(`/api/v1/encounters/${failed.encounterId}`);
  expect(encounterRes.ok()).toBeTruthy();
  const encounterBody = (await encounterRes.json()) as {
    encounter: { revision: number };
  };
  const plan = await getSecondaryPlanViaApi(
    request,
    failed.username,
    failed.password,
    failed.encounterId,
  );
  const csrf = await physicianCsrfViaApi(request, failed.username, failed.password);
  const signRes = await request.post(`/api/v1/encounters/${failed.encounterId}/sign`, {
    data: {
      encounter_revision: encounterBody.encounter.revision,
      run_id: failedRunId,
      secondary_plan_revision: plan.revision,
      review_acknowledgments: ["SYNTHETIC reviewed s50"],
      baseline_acknowledgment: false,
    },
    headers: {
      "X-CSRF-Token": csrf,
      "If-Match": String(encounterBody.encounter.revision),
      "Idempotency-Key": `e2e-sign-denied-${Date.now()}`,
    },
  });
  expect(signRes.status()).toBe(409);
});

// Journey 3 (RED, S50.3): signed view is read-only with signer/time and print
// navigation; another physician sees the signature but cannot edit or add an
// original-signer correction.
test("signed view is read-only; cross-physician sees signature without controls", async ({
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

  // RED: timeouts here until the S50 signing section exists.
  await expect(page.getByTestId("signing-section")).toBeVisible();
  await waitForLength(page, runPosts, 1);
  const runId = distinctRunIds(runPosts)[0] ?? "";
  assertUuid(runId);
  await seedSucceededRunViaDb(runId);
  await reopenDraftAfterReload(page, ctx.patientId);

  await page.getByTestId("signing-secondary-plan").fill(uniqueMarker("SYN-SECONDARY-RO-S50"));
  await page.getByTestId("signing-review-ack").check();
  await page.getByTestId("signing-sign-button").click();
  await expect(page.getByTestId("signing-signed-view")).toBeVisible();

  // Reload: read-only signed view with provenance and print navigation.
  await reopenDraftAfterReload(page, ctx.patientId);
  await expect(page.getByTestId("signing-signed-view")).toBeVisible();
  await expect(page.getByTestId("signing-secondary-plan")).toBeDisabled();
  await expect(page.getByTestId("signing-sign-button")).toHaveCount(0);
  await expect(page.getByTestId("signing-signer")).toContainText(ctx.username);
  await expect(page.getByTestId("signing-time")).not.toBeEmpty();
  await expect(page.getByTestId("signing-print")).toBeVisible();

  // Second physician: sees the signature, gets no edit/addendum controls.
  const otherUsername = uniquePhysicianUsername();
  await createPhysicianViaAdminApi(request, otherUsername, "synthetic-secret");
  await page.context().clearCookies();
  await loginViaUI(page, otherUsername, "synthetic-secret", "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, ctx.patientId);

  await expect(page.getByTestId("signing-signed-view")).toBeVisible();
  await expect(page.getByTestId("signing-signer")).toContainText(ctx.username);
  await expect(page.getByTestId("signing-secondary-plan")).toBeDisabled();
  await expect(page.getByTestId("signing-sign-button")).toHaveCount(0);
  await expect(page.getByTestId("signing-addendum-reason")).toHaveCount(0);
  await expect(page.getByTestId("signing-addendum-text")).toHaveCount(0);
  await expect(page.getByTestId("signing-addendum-submit")).toHaveCount(0);
});

// Journey 4 (RED, S50.4): original signer appends a reason/text correction;
// chronology shows the dated addendum separately; double-click/retry does not
// duplicate signatures or addenda.
test("original signer addendum appears dated; double submit does not duplicate", async ({
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

  // RED: timeouts here until the S50 signing section exists.
  await expect(page.getByTestId("signing-section")).toBeVisible();
  await waitForLength(page, runPosts, 1);
  const runId = distinctRunIds(runPosts)[0] ?? "";
  assertUuid(runId);
  await seedSucceededRunViaDb(runId);
  await reopenDraftAfterReload(page, ctx.patientId);

  await page.getByTestId("signing-secondary-plan").fill(uniqueMarker("SYN-SECONDARY-ADD-S50"));
  await page.getByTestId("signing-review-ack").check();
  await page.getByTestId("signing-sign-button").click();
  await expect(page.getByTestId("signing-signed-view")).toBeVisible();

  // Original-signer correction with an attributed reason.
  const reason = uniqueMarker("SYN-ADDENDUM-REASON-S50");
  const correction = uniqueMarker("SYN-ADDENDUM-CORRECTION-S50");
  await page.getByTestId("signing-addendum-reason").fill(reason);
  await page.getByTestId("signing-addendum-text").fill(correction);
  await page.getByTestId("signing-addendum-submit").dblclick();

  const addendaList = page.getByTestId("signing-addenda-list");
  await expect(addendaList).toBeVisible();
  await expect(page.getByTestId("signing-addendum-item")).toHaveCount(1);
  const item = page.getByTestId("signing-addendum-item").first();
  await expect(item).toContainText(reason);
  await expect(item).toContainText(correction);
  // Dated chronology entry (server-stamped ISO date carries the year).
  await expect(item).toContainText(/\d{4}/);

  // Retry/reload never duplicates the addendum.
  await reopenDraftAfterReload(page, ctx.patientId);
  await expect(page.getByTestId("signing-addenda-list")).toBeVisible();
  await expect(page.getByTestId("signing-addendum-item")).toHaveCount(1);
  await expect(page.getByTestId("signing-addendum-item").first()).toContainText(reason);
});
