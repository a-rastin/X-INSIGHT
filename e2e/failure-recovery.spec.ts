import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const execFileAsync = promisify(execFile);

// S60 failure recovery (T9). SYNTHETIC FIXTURES ONLY — no live provider, no
// clinical content. Seeding follows the S48 pattern: a synthetic 2-question
// bundle pointer lets the UI's own entry POST /encounters/{id}/runs create a
// real run; failed/succeeded states are seeded as reasoning_jobs /
// run_questions / run_question_artifacts rows keyed to that run_id, plus
// UPDATE runs SET status. Only existing stable selectors are used.

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";
const TEST_DATABASE_URL = "postgresql://xinsight:xinsight_dev@localhost:5432/xinsight_test";
const SYN_Q1 = "syn_q_one";
const SYN_Q2 = "syn_q_two";
const SYN_BUNDLE_HASH = "synthetic-e2e-bundle-s60";

function uniquePhysicianUsername(): string {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return `e2edoc${suffix}`.toLowerCase();
}
function uniquePatientId(): string {
  return `${String(Date.now() % 10_000_000).padStart(7, "0")}${String(Math.floor(Math.random() * 1000)).padStart(3, "0")}`;
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
function assertUuid(value: string): void {
  expect(value).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
}
function sqlQuote(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}
async function psql(command: string): Promise<string> {
  const { stdout } = await execFileAsync("psql", [TEST_DATABASE_URL, "-c", command]);
  return stdout;
}
async function seedSyntheticBundlePointerViaDb(): Promise<void> {
  const pins = JSON.stringify({ questions: [{ question_key: SYN_Q1 }, { question_key: SYN_Q2 }] });
  const stdout = await psql(
    `INSERT INTO model_bundle_pointers (workflow, revision, bundle_hash, pins) VALUES ('registration', 1, ${sqlQuote(SYN_BUNDLE_HASH)}, CAST(${sqlQuote(pins)} AS JSONB)) ` +
      "ON CONFLICT (workflow) DO UPDATE SET revision = 1, bundle_hash = EXCLUDED.bundle_hash, pins = EXCLUDED.pins, updated_at = now()",
  );
  expect(stdout).toMatch(/INSERT 0 1|UPDATE 1/);
}
async function physicianApiLogin(request: APIRequestContext, username: string, password: string): Promise<string> {
  const login = await request.post("/api/v1/auth/login", { data: { username, password, role: "physician" } });
  expect(login.ok()).toBeTruthy();
  const csrf = (await request.storageState()).cookies.find((c) => c.name === "xinsight_csrf")?.value;
  expect(csrf).toBeTruthy();
  return csrf ?? "";
}
async function createPhysicianViaAdminApi(request: APIRequestContext, username: string, password: string): Promise<void> {
  const adminLogin = await request.post("/api/v1/auth/login", {
    data: { username: "admin", password: "admin", role: "admin" },
  });
  expect(adminLogin.ok()).toBeTruthy();
  const csrf = (await request.storageState()).cookies.find((c) => c.name === "xinsight_csrf")?.value;
  expect(csrf).toBeTruthy();
  const created = await request.post("/api/v1/physicians", {
    data: { username, password },
    headers: { "X-CSRF-Token": csrf ?? "", "Idempotency-Key": `e2e-${username}-${Date.now()}` },
  });
  expect(created.status()).toBe(201);
}
interface DraftContext {
  username: string;
  password: string;
  patientId: string;
  encounterId: string;
  authorId: string;
}
async function setupPhysicianDraft(request: APIRequestContext): Promise<DraftContext> {
  const username = uniquePhysicianUsername();
  const password = "synthetic-secret";
  await createPhysicianViaAdminApi(request, username, password);
  const patientId = uniquePatientId();
  const csrf = await physicianApiLogin(request, username, password);
  const created = await request.post("/api/v1/patients", {
    data: { first_name: "Synthetic", last_name: uniqueName("Case"), sex: "F", age: 30, patient_id: patientId, clinical_status: "first_time" },
    headers: { "X-CSRF-Token": csrf, "Idempotency-Key": `e2e-patient-${patientId}-${Date.now()}` },
  });
  expect(created.status()).toBe(201);
  const me = (await (await request.get("/api/v1/me")).json()) as { id: string };
  assertUuid(me.id);
  const listed = await request.get("/api/v1/patients", { params: { q: patientId } });
  expect(listed.ok()).toBeTruthy();
  const patient = ((await listed.json()) as { items: Array<{ id: string; patient_id: string }> }).items.find(
    (p) => p.patient_id === patientId,
  );
  expect(patient).toBeTruthy();
  const encounters = await request.get(`/api/v1/patients/${patient?.id}/encounters`);
  expect(encounters.ok()).toBeTruthy();
  const baseline = ((await encounters.json()) as { items: Array<{ id: string; kind: string }> }).items.find(
    (e) => e.kind === "registration",
  );
  expect(baseline).toBeTruthy();
  return { username, password, patientId, encounterId: baseline?.id ?? "", authorId: me.id };
}
async function loginViaUI(page: Page, username: string, password: string, role: string): Promise<void> {
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
interface CollectedRunPost {
  runId: string | null;
}
function collectRunPosts(page: Page, posts: CollectedRunPost[]): void {
  page.on("response", (resp) => {
    const req = resp.request();
    if (!(req.method() === "POST" && /\/api\/v1\/encounters\/[^/]+\/runs$/.test(req.url()))) return;
    resp
      .json()
      .then((body) => {
        const runId = (body as { run_id?: unknown }).run_id;
        posts.push({ runId: typeof runId === "string" ? runId : null });
      })
      .catch(() => posts.push({ runId: null }));
  });
}
async function waitForLength(page: Page, arr: unknown[], count: number, timeout = 15_000): Promise<void> {
  const start = Date.now();
  while (arr.length < count) {
    if (Date.now() - start > timeout) throw new Error(`timed out waiting for ${count} (have ${arr.length})`);
    await page.waitForTimeout(250);
  }
}
async function seedJobStateViaDb(args: {
  runId: string; encounterId: string; authorId: string; questionKey: string;
  ordinal: number; stage: string; status: string; failure: Record<string, unknown> | null;
}): Promise<void> {
  assertUuid(args.runId);
  const failure = args.failure === null ? "NULL" : `CAST(${sqlQuote(JSON.stringify(args.failure))} AS JSONB)`;
  const stdout = await psql(
    `INSERT INTO reasoning_jobs (run_id, encounter_id, author_id, question_key, ordinal, stage, status, failure_details) VALUES ('${args.runId}', '${args.encounterId}', '${args.authorId}', ${sqlQuote(args.questionKey)}, ${args.ordinal}, ${sqlQuote(args.stage)}, ${sqlQuote(args.status)}, ${failure}) ` +
      "ON CONFLICT (run_id, question_key) DO UPDATE SET stage = EXCLUDED.stage, status = EXCLUDED.status, failure_details = EXCLUDED.failure_details, updated_at = now()",
  );
  expect(stdout).toMatch(/INSERT 0 1|UPDATE 1/);
}
async function seedFailedRunViaDb(args: { runId: string; encounterId: string; authorId: string }): Promise<void> {
  assertUuid(args.runId);
  for (const key of [SYN_Q1, SYN_Q2]) {
    const stdout = await psql(
      `UPDATE run_questions SET projection = jsonb_set(jsonb_set(projection, '{applicability}', to_jsonb('ready'::text)), '{applicability_reason}', to_jsonb('SYNTHETIC ready s60'::text)) WHERE run_id = '${args.runId}' AND question_key = ${sqlQuote(key)}`,
    );
    expect(stdout).toMatch(/UPDATE 1/);
  }
  await seedJobStateViaDb({ ...args, questionKey: SYN_Q1, ordinal: 0, stage: "estimating_cpts", status: "failed", failure: { error: "SYNTHETIC_ESTIMATION_TIMEOUT", retryable: true } });
  await seedJobStateViaDb({ ...args, questionKey: SYN_Q2, ordinal: 1, stage: "rendering", status: "succeeded", failure: null });
  const accepted = JSON.stringify({ question_key: SYN_Q2, network_version: "syn-net-v1", tables: [{ node_id: "SYN_A", parent_ids: [], states: ["no", "yes"], rows: [{ parent_states: [], percentages: [62.5, 37.5] }] }] });
  const result = JSON.stringify({ SYN_A_yes_posterior_pct: 41.25 });
  const provenance = JSON.stringify({ network_version: "syn-net-v1", source_paths: ["encounters.draft_data.history"], missingness: { SYN_A: "observed" }, engine: { name: "synthetic-exact", version: "s60" }, prompt_version: "syn-p1", template_version: "syn-t1" });
  const artifact = await psql(
    "INSERT INTO run_question_artifacts (run_id, question_key, ordinal, stage, status, request, projection, prompt, model, accepted, effective_xml, effective_hash, query, result, rendered_section, template_version, provenance) " +
      `SELECT '${args.runId}', ${sqlQuote(SYN_Q2)}, 1, 'succeeded', 'succeeded', CAST('{}' AS JSONB), projection, 'SYNTHETIC PROMPT s60 syn-p1', CAST('{}' AS JSONB), ` +
      `CAST(${sqlQuote(accepted)} AS JSONB), '<synthetic/>', 'synthetic-hash', CAST('{}' AS JSONB), CAST(${sqlQuote(result)} AS JSONB), ` +
      `${sqlQuote(`SYNTHETIC SECTION ${SYN_Q2} s60`)}, 'syn-t1', CAST(${sqlQuote(provenance)} AS JSONB) ` +
      `FROM run_questions WHERE run_id = '${args.runId}' AND question_key = ${sqlQuote(SYN_Q2)} ` +
      "ON CONFLICT (run_id, question_key) DO UPDATE SET status = 'succeeded', accepted = EXCLUDED.accepted, result = EXCLUDED.result, rendered_section = EXCLUDED.rendered_section, provenance = EXCLUDED.provenance, projection = EXCLUDED.projection, updated_at = now()",
  );
  expect(artifact).toMatch(/INSERT 0 1|UPDATE 1/);
  const run = await psql(`UPDATE runs SET status = 'failed', updated_at = now() WHERE id = '${args.runId}'`);
  expect(run).toMatch(/UPDATE 1/);
}
async function getEncounterViaApi(
  request: APIRequestContext, username: string, password: string, encounterId: string,
): Promise<{ revision: number; draft_data: Record<string, unknown> }> {
  await physicianApiLogin(request, username, password);
  const response = await request.get(`/api/v1/encounters/${encounterId}`);
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as {
    encounter: { revision: number; draft_data: Record<string, unknown> };
  };
  return body.encounter;
}
// Out-of-band server-side edit through the real PATCH route (bumps revision
// so the UI's next autosave hits a genuine 412).
async function bumpNoteViaApi(
  request: APIRequestContext, username: string, password: string, encounterId: string, note: string,
): Promise<number> {
  const current = await getEncounterViaApi(request, username, password, encounterId);
  // Single-session CSRF: re-read after the final login (each login rotates
  // the session; S50 harness precedent). Mirror the UI payload: strip
  // server-stamped provenance (history/effects validators accept exactly
  // {definition_version, values}; the backend re-stamps on write, same as a
  // real concurrent editor's autosave).
  const freshCsrf = (await request.storageState()).cookies.find((c) => c.name === "xinsight_csrf")?.value;
  expect(freshCsrf).toBeTruthy();
  const draftData = JSON.parse(JSON.stringify(current.draft_data)) as Record<string, unknown>;
  for (const key of ["history", "effects"]) {
    const block = draftData[key];
    if (typeof block === "object" && block !== null && !Array.isArray(block)) {
      delete (block as Record<string, unknown>).provenance;
    }
  }
  draftData.note = note;
  const patched = await request.patch(`/api/v1/encounters/${encounterId}`, {
    data: { draft_data: draftData },
    headers: { "X-CSRF-Token": freshCsrf ?? "", "If-Match": String(current.revision), "Idempotency-Key": `e2e-bump-${encounterId}-${Date.now()}` },
  });
  expect(patched.status()).toBe(200);
  const revision = ((await patched.json()) as { encounter: { revision: number } }).encounter.revision;
  expect(revision).toBeGreaterThan(current.revision);
  return revision;
}

// Journey 1: failure isolation across two physicians. A's run fails; B's
// saves stay responsive and both drafts' acknowledged writes survive reload;
// B sees A's draft read-only.
test("two physicians separate encounters, one run fails, saves stay responsive and survive reload, wrong-author read-only", async ({ page, request }) => {
  await seedSyntheticBundlePointerViaDb();
  const ctxA = await setupPhysicianDraft(request);
  const ctxB = await setupPhysicianDraft(request);

  await loginViaUI(page, ctxA.username, ctxA.password, "physician");
  await dismissResearchNotice(page);
  const runPostsA: CollectedRunPost[] = [];
  collectRunPosts(page, runPostsA);
  await openDraftForPatient(page, ctxA.patientId);
  await expect(page.getByTestId("proposal-review-section")).toBeVisible();
  await waitForLength(page, runPostsA, 1);
  const runIdA = [...new Set(runPostsA.map((p) => p.runId).filter((id): id is string => id !== null))][0] ?? "";
  assertUuid(runIdA);
  await seedFailedRunViaDb({ runId: runIdA, encounterId: ctxA.encounterId, authorId: ctxA.authorId });

  // A's failed state survives reload: Run failed + precise retry + sign gate.
  await reopenDraftAfterReload(page, ctxA.patientId);
  await expect(page.getByTestId("proposal-review-section")).toBeVisible();
  await expect(page.getByTestId("proposal-run-status")).toContainText(/run failed/i);
  await expect(page.getByTestId(`proposal-retry-${SYN_Q1}`)).toBeVisible();
  await expect(page.getByTestId(`proposal-retry-${SYN_Q2}`)).toHaveCount(0);
  await expect(page.getByTestId("proposal-sign-blocked")).toBeVisible();
  await expect(page.getByTestId("proposal-sign-blocked")).toContainText(/blocked|failed/i);

  // B's separate encounter stays responsive despite A's failure.
  await page.getByRole("button", { name: /sign out/i }).click();
  await loginViaUI(page, ctxB.username, ctxB.password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, ctxB.patientId);
  await expect(page.getByTestId("proposal-review-section")).toBeVisible();
  const markerB = `synthetic-failure-iso-${Date.now().toString(36)}`;
  await page.getByLabel(/draft note/i).fill(markerB);
  const statusB = page.getByRole("status");
  await expect(statusB).toContainText(/Saved \(rev \d+\)/, { timeout: 10_000 });
  const revBefore = Number(((await statusB.textContent()) ?? "").match(/rev (\d+)/)?.[1] ?? "0");
  expect(revBefore).toBeGreaterThan(0);

  // Reload preserves B's acknowledged write (no silent loss).
  await reopenDraftAfterReload(page, ctxB.patientId);
  await expect(page.getByLabel(/draft note/i)).toHaveValue(markerB);
  const persistedB = await getEncounterViaApi(request, ctxB.username, ctxB.password, ctxB.encounterId);
  expect(persistedB.revision).toBeGreaterThanOrEqual(revBefore);

  // B opening A's draft sees it read-only with inputs disabled.
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await openDraftForPatient(page, ctxA.patientId);
  const chart = page.getByTestId("chart-section");
  await expect(chart).toBeVisible();
  await chart.getByTestId(`open-encounter-${ctxA.encounterId}`).click();
  await expect(page.getByText("Read-only draft.", { exact: true })).toBeVisible();
  await expect(page.getByLabel(/draft note/i)).toBeDisabled();
});

// Journey 2: the failed run blocks signing, retry resumes without
// duplicating the completed section, and a stale If-Match edit is fenced
// with Reload-draft preserving the unsaved edits.
test("failed run blocks sign, retry resumes without duplicate, stale edit fenced", async ({ page, request }) => {
  await seedSyntheticBundlePointerViaDb();
  const ctx = await setupPhysicianDraft(request);
  await loginViaUI(page, ctx.username, ctx.password, "physician");
  await dismissResearchNotice(page);
  const runPosts: CollectedRunPost[] = [];
  collectRunPosts(page, runPosts);
  await openDraftForPatient(page, ctx.patientId);
  await expect(page.getByTestId("proposal-review-section")).toBeVisible();
  await waitForLength(page, runPosts, 1);
  const runId = [...new Set(runPosts.map((p) => p.runId).filter((id): id is string => id !== null))][0] ?? "";
  assertUuid(runId);
  await seedFailedRunViaDb({ runId, encounterId: ctx.encounterId, authorId: ctx.authorId });
  await reopenDraftAfterReload(page, ctx.patientId);

  // Failed run visibly blocks signing; attempting to sign stays blocked.
  await expect(page.getByTestId("proposal-sign-blocked")).toBeVisible();
  await expect(page.getByTestId("proposal-sign-blocked")).toContainText(/blocked|failed/i);
  await page.getByTestId("signing-sign-button").click();
  await expect(page.getByTestId("signing-status")).toContainText(/blocked|failed/i);

  // Retry re-queues the failed question; the completed section is retained
  // exactly once (no duplicate) and needs no retry control.
  await page.getByTestId(`proposal-retry-${SYN_Q1}`).click();
  await expect(page.getByTestId(`proposal-question-state-${SYN_Q1}`)).toContainText(/queued|pending/i, { timeout: 10_000 });
  const completed = page.getByTestId(`proposal-section-${SYN_Q2}`);
  await expect(completed).toHaveCount(1);
  await expect(completed).toContainText(`SYNTHETIC SECTION ${SYN_Q2} s60`);
  await expect(page.getByTestId(`proposal-retry-${SYN_Q2}`)).toHaveCount(0);

  // Stale If-Match edit is fenced: a server-side bump makes the UI's next
  // autosave return Stale revision with the server value surfaced.
  const serverMarker = `synthetic-server-${Date.now().toString(36)}`;
  await bumpNoteViaApi(request, ctx.username, ctx.password, ctx.encounterId, serverMarker);
  const staleMarker = `synthetic-stale-${Date.now().toString(36)}`;
  await page.getByLabel(/draft note/i).fill(staleMarker);
  await expect(page.getByRole("status")).toContainText(/Stale revision/, { timeout: 15_000 });
  await expect(page.getByRole("button", { name: /reload draft/i })).toBeVisible();
  await expect(page.getByText(/server value/i)).toContainText(serverMarker);

  // Reload draft preserves the unsaved edits (no silent overwrite).
  await page.getByRole("button", { name: /reload draft/i }).click();
  await expect(page.getByLabel(/draft note/i)).toHaveValue(staleMarker);
  await expect(page.getByRole("status")).toContainText(/Stale revision/);
});
