import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const execFileAsync = promisify(execFile);

// S14 slice 4 (RED — T9 journey contract, chart + follow-up UI not implemented).
// SYNTHETIC FIXTURES ONLY. These 2 journeys define the frontend contract
// for dev-frontend; they timeout until the chart + follow-up UI exist.
// Seams: T1 (backend, green — slices 1-3: follow-up create/copy/changed-baseline)
// and T9 (this slice, e2e). No side channels in the product: the spec seeds
// signed baselines test-side only via direct DB UPDATE (see signBaselineViaDb),
// because there is NO sign endpoint until S49 and no production route may be
// added for signing. Never commit credentials beyond the test DB URL already
// in playwright.config.ts.
//
// Seeding mechanism: shells out to `psql $TEST_DATABASE_URL -c "UPDATE ..."`.
// Chosen after inspecting this environment: /usr/bin/psql exists, while node
// `pg` is NOT installed in web/node_modules (require.resolve('pg') fails),
// so a pg-client helper is not available without adding a dependency — psql
// needs none. TEST_DATABASE_URL matches playwright.config.ts
// (postgresql://xinsight:xinsight_dev@localhost:5432/xinsight_test), the same
// disposable DB the e2e webServer backend migrates and serves.
//
// Backend contract (green, backend/tests/http/test_followup.py):
// POST /patients/{id}/encounters {baseline_encounter_id} -> 201 follow_up
// draft (signed baseline required, 409 otherwise); history + medications copy
// verbatim with restamped provenance; history_reconciliation opens pending;
// PANSS/C-SSRS never copy; `baseline_changed` flags a newer signed record
// read-side only.
//
// Expected frontend contract (stable selectors dev-frontend implements;
// do not invent extra testids):
// - api.ts: Encounter += baseline_encounter_id: string|null;
//   baseline_changed: boolean; new createFollowup(patientUuid, baselineId).
// - Chart: section data-testid="chart-section" (region Chart); list
//   data-testid="chart-encounters" with per-encounter
//   data-testid="chart-encounter-<id>" + badge data-testid="chart-badge-<id>"
//   (text contains kind and state, e.g. "registration · signed");
//   changed-baseline flag data-testid="chart-baseline-changed" with text
//   /Baseline changed.*reconcile/i; per signed encounter Start-follow-up
//   button data-testid="start-followup-<id>" (physician only); per-encounter
//   open button data-testid="open-encounter-<id>".
// - DraftEditor: existing read-only contract for non-author; follow-up shows
//   data-testid="followup-baseline-note" (/Copied from baseline.*reconcile/i),
//   data-testid="prior-scores" (prior PANSS/C-SSRS rendered as historical with
//   dates, never as new answers), data-testid="generation-status" with exact
//   text "Proposal generation unavailable."
// - Existing selectors/flows ("Open draft <pid>", autosave Saved,
//   history/effects/notes/phone) keep working.

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

const TEST_DATABASE_URL =
  "postgresql://xinsight:xinsight_dev@localhost:5432/xinsight_test";

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
  await page
    .getByRole("button", { name: `Open draft ${patientId}` })
    .click();
  await expect(page.getByRole("heading", { name: /draft/i })).toBeVisible();
}

async function reopenDraftAfterReload(page: Page, patientId: string): Promise<void> {
  await page.reload();
  await page.getByLabel(/search patients/i).fill(patientId);
  const openDraft = page.getByRole("button", {
    name: `Open draft ${patientId}`,
  });
  if ((await openDraft.count()) > 0) {
    await openDraft.first().click();
  }
  await expect(page.getByRole("heading", { name: /draft/i })).toBeVisible();
}

// Test-only signed-baseline seeding: direct DB UPDATE via psql. There is no
// sign endpoint until S49, so the spec marks the registration draft signed
// the same way backend/tests/http/test_followup.py does (SQL, fixture setup
// only). Never a production route.
function assertUuid(value: string): void {
  expect(value).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
  );
}

async function signBaselineViaDb(encounterId: string): Promise<void> {
  assertUuid(encounterId);
  // UUIDs match strict hex-dash shape, so inline interpolation is safe;
  // psql -v :"var" substitution does not fire under -c in this environment.
  const { stdout } = await execFileAsync("psql", [
    TEST_DATABASE_URL,
    "-c",
    `UPDATE encounters SET state = 'signed' WHERE id = '${encounterId}'`,
  ]);
  expect(stdout).toMatch(/UPDATE 1/);
}

async function insertNewerSignedRecordViaDb(patientUuid: string): Promise<void> {
  assertUuid(patientUuid);
  const { stdout } = await execFileAsync("psql", [
    TEST_DATABASE_URL,
    "-c",
    "INSERT INTO encounters (patient_id, kind, author_id, state) " +
      `VALUES ('${patientUuid}', 'registration', NULL, 'signed')`,
  ]);
  expect(stdout).toMatch(/INSERT 0 1/);
}

async function getPatientAndBaselineViaPhysicianApi(
  request: APIRequestContext,
  username: string,
  password: string,
  patientIdText: string,
): Promise<{ patientUuid: string; baselineId: string }> {
  const physicianLogin = await request.post("/api/v1/auth/login", {
    data: { username, password, role: "physician" },
  });
  expect(physicianLogin.ok()).toBeTruthy();
  const listed = await request.get("/api/v1/patients", {
    params: { q: patientIdText },
  });
  expect(listed.ok()).toBeTruthy();
  const patients = (await listed.json()) as {
    items: Array<{ id: string; patient_id: string }>;
  };
  const patient = patients.items.find((p) => p.patient_id === patientIdText);
  expect(patient).toBeTruthy();
  const encounters = await request.get(
    `/api/v1/patients/${patient?.id}/encounters`,
  );
  expect(encounters.ok()).toBeTruthy();
  const body = (await encounters.json()) as {
    items: Array<{ id: string; kind: string }>;
  };
  const baseline = body.items.find((e) => e.kind === "registration");
  expect(baseline).toBeTruthy();
  return { patientUuid: patient?.id ?? "", baselineId: baseline?.id ?? "" };
}

async function createFollowupViaPhysicianApi(
  request: APIRequestContext,
  username: string,
  password: string,
  patientUuid: string,
  baselineId: string,
): Promise<string> {
  const physicianLogin = await request.post("/api/v1/auth/login", {
    data: { username, password, role: "physician" },
  });
  expect(physicianLogin.ok()).toBeTruthy();
  const storage = await request.storageState();
  const csrf = storage.cookies.find((c) => c.name === "xinsight_csrf")?.value;
  expect(csrf).toBeTruthy();
  const created = await request.post(
    `/api/v1/patients/${patientUuid}/encounters`,
    {
      data: { baseline_encounter_id: baselineId },
      headers: {
        "X-CSRF-Token": csrf ?? "",
        "Idempotency-Key": `e2e-followup-${baselineId}-${Date.now()}`,
      },
    },
  );
  expect(created.status()).toBe(201);
  const payload = (await created.json()) as {
    encounter: { id: string; kind: string };
  };
  expect(payload.encounter.kind).toBe("follow_up");
  return payload.encounter.id;
}

// S14 slice 4 journey 1 (RED): physician starts a follow-up from a signed
// baseline and resumes it. Sets one history field on the registration draft,
// signs the baseline test-side, starts the follow-up from the chart, edits,
// and resumes via the per-encounter open button with edits preserved.
test("physician starts a follow-up from a signed baseline and resumes it", async ({
  page,
  request,
}) => {
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
  const { baselineId } = await getPatientAndBaselineViaPhysicianApi(
    request,
    username,
    password,
    patientId,
  );

  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, patientId);

  // Existing flows keep working: history select + shared Saved status.
  await expect(page.getByTestId("history-section")).toBeVisible();
  await page
    .getByTestId("history-item-synthetic_flag_true")
    .selectOption("known_true");
  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });

  // Seed the signed baseline test-side (no sign endpoint until S49).
  await signBaselineViaDb(baselineId);

  // RED: timeouts here until the chart exists.
  await reopenDraftAfterReload(page, patientId);
  const chart = page.getByTestId("chart-section");
  await expect(chart).toBeVisible();
  await expect(chart.getByTestId("chart-encounters")).toBeVisible();
  await expect(chart.getByTestId(`chart-encounter-${baselineId}`)).toBeVisible();
  await expect(chart.getByTestId(`chart-badge-${baselineId}`)).toContainText(
    /registration.*signed/i,
  );

  await chart.getByTestId(`start-followup-${baselineId}`).click();

  // Follow-up draft opens with the baseline-copy + freshness contract.
  await expect(page.getByTestId("followup-baseline-note")).toContainText(
    /Copied from baseline.*reconcile/i,
  );
  await expect(page.getByTestId("prior-scores")).toContainText(/historical/i);
  // Prior scores render as history only — never prefilled as new answers.
  await expect(page.getByTestId("panss-item-P1")).toHaveValue("");
  await expect(page.getByTestId("history-reconciliation-status")).toHaveValue(
    "pending",
  );
  await expect(page.getByTestId("generation-status")).toHaveText(
    "Proposal generation unavailable.",
  );

  // Author edits the follow-up; shared autosave path persists them.
  const followupText = `synthetic-followup-${Date.now().toString(36)}`;
  await page.getByLabel(/draft note/i).fill(followupText);
  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });

  // Reload and resume via the per-encounter open button; edits preserved.
  const listed = await getPatientAndBaselineViaPhysicianApi(
    request,
    username,
    password,
    patientId,
  );
  void listed;
  await reopenDraftAfterReload(page, patientId);
  const resumedChart = page.getByTestId("chart-section");
  await expect(resumedChart).toBeVisible();
  const followupEntry = resumedChart.getByTestId(/^chart-encounter-/).nth(1);
  const followupEntryId =
    (await followupEntry.getAttribute("data-testid"))?.replace(
      "chart-encounter-",
      "",
    ) ?? "";
  expect(followupEntryId).not.toBe("");
  await expect(
    resumedChart.getByTestId(`chart-badge-${followupEntryId}`),
  ).toContainText(/follow_up.*draft/i);
  await resumedChart.getByTestId(`open-encounter-${followupEntryId}`).click();
  await expect(page.getByTestId("followup-baseline-note")).toContainText(
    /Copied from baseline.*reconcile/i,
  );
  await expect(page.getByLabel(/draft note/i)).toHaveValue(followupText);
});

// S14 slice 4 journey 2 (RED): shared chart is read-only for non-author with
// badges. The author seeds patient + follow-up; a second physician sees both
// badges but cannot edit; admin can view the chart but gets no start button.
// The changed-baseline indicator is T1-covered; because the DB helper
// trivially allows inserting a newer signed row, it is asserted here too.
test("shared chart is read-only for non-author with badges", async ({
  page,
  request,
}) => {
  const author = uniquePhysicianUsername();
  const other = uniquePhysicianUsername();
  const password = "synthetic-secret";
  await createPhysicianViaAdminApi(request, author, password);
  await createPhysicianViaAdminApi(request, other, password);
  const patientId = uniquePatientId();
  await createPatientViaPhysicianApi(request, author, password, {
    first_name: "Synthetic",
    last_name: uniqueName("Case"),
    sex: "F",
    age: 31,
    patient_id: patientId,
    clinical_status: "first_time",
  });
  const { patientUuid, baselineId } =
    await getPatientAndBaselineViaPhysicianApi(
      request,
      author,
      password,
      patientId,
    );
  await signBaselineViaDb(baselineId);
  const followupId = await createFollowupViaPhysicianApi(
    request,
    author,
    password,
    patientUuid,
    baselineId,
  );
  await insertNewerSignedRecordViaDb(patientUuid);

  // Non-author physician: both badges visible, follow-up opens read-only.
  await loginViaUI(page, other, password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, patientId);

  // RED: timeouts here until the chart exists.
  const chart = page.getByTestId("chart-section");
  await expect(chart).toBeVisible();
  await expect(chart.getByTestId(`chart-encounter-${baselineId}`)).toBeVisible();
  await expect(chart.getByTestId(`chart-badge-${baselineId}`)).toContainText(
    /registration.*signed/i,
  );
  await expect(chart.getByTestId(`chart-encounter-${followupId}`)).toBeVisible();
  await expect(chart.getByTestId(`chart-badge-${followupId}`)).toContainText(
    /follow_up.*draft/i,
  );
  await expect(chart.getByTestId("chart-baseline-changed")).toContainText(
    /Baseline changed.*reconcile/i,
  );

  await chart.getByTestId(`open-encounter-${followupId}`).click();
  await expect(page.getByText(/read-only/i).first()).toBeVisible();
  await expect(
    page.getByTestId("history-item-synthetic_flag_true"),
  ).toBeDisabled();
  await expect(
    page.getByTestId("history-reconciliation-status"),
  ).toBeDisabled();

  // Admin can view the chart badges but gets no start-follow-up button.
  // (Admins get no research notice: App gates Continue on physician role.)
  await page.getByRole("button", { name: /sign out/i }).click();
  await loginViaUI(page, "admin", "admin", "admin");
  await expect(page.getByText(/admin dashboard/i)).toBeVisible();
  await openDraftForPatient(page, patientId);
  const adminChart = page.getByTestId("chart-section");
  await expect(adminChart).toBeVisible();
  await expect(
    adminChart.getByTestId(`chart-badge-${baselineId}`),
  ).toContainText(/registration.*signed/i);
  await expect(
    adminChart.getByTestId(`chart-badge-${followupId}`),
  ).toContainText(/follow_up.*draft/i);
  await expect(
    adminChart.locator("[data-testid^='start-followup-']"),
  ).toHaveCount(0);
});
