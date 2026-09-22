import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const execFileAsync = promisify(execFile);

// S20 (RED — T9 journey contract, MedicationsSection + DDI panel missing).
// SYNTHETIC FIXTURES ONLY. These 3 journeys pin the frontend contract for
// dev-frontend; they timeout on the missing selectors until implemented.
// Backend contract (RED until dev-backend lands test_medications.py):
// drug-only PATCH {catalog_drug_id}|{unknown_label}, forged regimen fields
// 422, ddi_report reference persisted verbatim, follow-up copies meds (never
// the report) with pending reconciliation, GET /ddi/current discovery.
//
// Seeding: direct SQL via `psql $TEST_DATABASE_URL -c "INSERT ..."` (mirrors
// e2e/followup.spec.ts: /usr/bin/psql exists, node `pg` is unavailable, so
// no new dependency). Seeded version is fixed (e2e-ddi-v1) with
// ON CONFLICT DO NOTHING so parallel journeys share it safely. Test-only
// seeding; never a production route. Signed baselines use the same UPDATE
// idiom as followup.spec.ts (no sign endpoint until S49).
//
// Expected frontend contract (stable selectors dev-frontend implements):
// - section data-testid="medications-section" (region labelled Medications)
// - input data-testid="medications-search",
//   results data-testid="medications-search-results",
//   per-result button data-testid="medications-add-<concept_id>"
// - unknown input data-testid="medications-unknown-input",
//   add button data-testid="medications-unknown-add"
// - list data-testid="medications-list"
// - DDI: button data-testid="ddi-check", status data-testid="ddi-status",
//   report data-testid="ddi-report", conflicts data-testid="ddi-conflicts"
// - follow-up notice data-testid="medications-reconcile-notice"
// - chart reuse from S14: start-followup-<id>, open-encounter-<id>.

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

const TEST_DATABASE_URL =
  "postgresql://xinsight:xinsight_dev@localhost:5432/xinsight_test";

const SYN_A = "synthetic-med-a";
const SYN_B = "synthetic-med-b";
const DDI_VERSION = "e2e-ddi-v1";
const EVIDENCE_ONE = "SYNTHETIC_EVIDENCE_ONE synthetic-med-a + synthetic-med-b";
const EVIDENCE_TWO = "SYNTHETIC_EVIDENCE_TWO conflicting severity AB pair";

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

function assertUuid(value: string): void {
  expect(value).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
  );
}

function sqlQuote(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

async function seedDdiReleaseViaDb(): Promise<void> {
  const evidence = JSON.stringify([
    {
      pair_key: "synthetic-med-a:synthetic-med-b",
      source_severity: "monitor_closely",
      management: null,
      direction: null,
      source_path: "SYNTHETIC-ddi.txt",
      span: { start_line: 1, end_line: 2 },
      raw_text: EVIDENCE_ONE,
    },
    {
      pair_key: "synthetic-med-a:synthetic-med-b",
      source_severity: "serious",
      management: null,
      direction: null,
      source_path: "SYNTHETIC-ddi.txt",
      span: { start_line: 3, end_line: 4 },
      raw_text: EVIDENCE_TWO,
    },
  ]);
  const { stdout } = await execFileAsync("psql", [
    TEST_DATABASE_URL,
    "-c",
    "INSERT INTO ddi_dataset_releases (version, dataset_hash, " +
      "source_inventory, terminology_provenance, review_record, " +
      "corrections, coverage, evidence) VALUES (" +
      `${sqlQuote(DDI_VERSION)}, ` +
      `${sqlQuote("synthetic-hash-e2e-ddi-v1")}, ` +
      `${sqlQuote("[]")}, ` +
      `${sqlQuote('{"terminology_version":"synthetic-catalog-e2e-ddi-v1","synthetic_fixture":true}')}, ` +
      `${sqlQuote('{"synthetic_fixture":true,"reviewer":"dr-synthetic"}')}, ` +
      `${sqlQuote("[]")}, ` +
      `${sqlQuote('{"scope":"limited","exclusions":[]}')}, ` +
      `CAST(${sqlQuote(evidence)} AS JSONB)) ` +
      "ON CONFLICT (version) DO NOTHING",
  ]);
  expect(stdout).toMatch(/INSERT 0 [01]/);
}

async function signBaselineViaDb(encounterId: string): Promise<void> {
  assertUuid(encounterId);
  const { stdout } = await execFileAsync("psql", [
    TEST_DATABASE_URL,
    "-c",
    `UPDATE encounters SET state = 'signed' WHERE id = '${encounterId}'`,
  ]);
  expect(stdout).toMatch(/UPDATE 1/);
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

// Journey 1 (RED): known + unknown medications save and resume.
test("known + unknown medications save and resume", async ({
  page,
  request,
}) => {
  await seedDdiReleaseViaDb();
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
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, patientId);

  // RED: timeouts here until MedicationsSection exists.
  await expect(page.getByTestId("medications-section")).toBeVisible();
  await page.getByTestId("medications-search").fill(SYN_A);
  await expect(page.getByTestId("medications-search-results")).toBeVisible();
  await page.getByTestId(`medications-add-${SYN_A}`).click();
  await page.getByTestId("medications-unknown-input").fill("synthetic-unknown-x");
  await page.getByTestId("medications-unknown-add").click();

  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });

  await page.reload();
  await openDraftForPatient(page, patientId);
  const list = page.getByTestId("medications-list");
  await expect(list).toContainText(SYN_A);
  await expect(list).toContainText("synthetic-unknown-x");
  await expect(list).toContainText(/coverage unavailable/i);
});

// Journey 2 (RED): changed meds show pending, stale report never current.
test("changed medications show pending then current report", async ({
  page,
  request,
}) => {
  await seedDdiReleaseViaDb();
  const username = uniquePhysicianUsername();
  const password = "synthetic-secret";
  await createPhysicianViaAdminApi(request, username, password);
  const patientId = uniquePatientId();
  await createPatientViaPhysicianApi(request, username, password, {
    first_name: "Synthetic",
    last_name: uniqueName("Case"),
    sex: "F",
    age: 31,
    patient_id: patientId,
    clinical_status: "first_time",
  });
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, patientId);

  // RED: timeouts here until the DDI panel exists.
  await expect(page.getByTestId("medications-section")).toBeVisible();
  await page.getByTestId("medications-search").fill(SYN_A);
  await page.getByTestId(`medications-add-${SYN_A}`).click();
  // The AB conflict evidence requires both pair members; one med alone
  // correctly yields zero pairs, so add the second before checking.
  await page.getByTestId("medications-search").fill(SYN_B);
  await page.getByTestId(`medications-add-${SYN_B}`).click();
  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });
  await page.getByTestId("ddi-check").click();
  await expect(page.getByTestId("ddi-status")).toContainText(/current/i);
  await expect(page.getByTestId("ddi-report")).toContainText(EVIDENCE_ONE);
  await expect(page.getByTestId("ddi-conflicts")).toBeVisible();

  await page.getByTestId("medications-unknown-input").fill("synthetic-unknown-x");
  await page.getByTestId("medications-unknown-add").click();
  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });
  await expect(page.getByTestId("ddi-status")).toContainText(
    /medications changed/i,
  );
  // Stale report is hidden while pending — never presented as current.
  await expect(page.getByTestId("ddi-report")).toBeHidden();

  await page.getByTestId("ddi-check").click();
  await expect(page.getByTestId("ddi-status")).toContainText(/current/i);
  await expect(page.getByTestId("ddi-report")).toContainText(
    /coverage unavailable/i,
  );
});

// Journey 3 (RED): markup in an unknown label is escaped; follow-up keeps
// the baseline list/report unchanged behind a reconcile notice.
test("escaping + follow-up reconciliation", async ({ page, request }) => {
  await seedDdiReleaseViaDb();
  const username = uniquePhysicianUsername();
  const password = "synthetic-secret";
  await createPhysicianViaAdminApi(request, username, password);
  const patientId = uniquePatientId();
  await createPatientViaPhysicianApi(request, username, password, {
    first_name: "Synthetic",
    last_name: uniqueName("Case"),
    sex: "F",
    age: 32,
    patient_id: patientId,
    clinical_status: "first_time",
  });
  const markup = "<img src=x onerror=alert(1)>";
  const { patientUuid, baselineId } =
    await getPatientAndBaselineViaPhysicianApi(
      request,
      username,
      password,
      patientId,
    );
  assertUuid(patientUuid);
  assertUuid(baselineId);

  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, patientId);

  // RED: timeouts here until MedicationsSection exists.
  await expect(page.getByTestId("medications-section")).toBeVisible();
  await page.getByTestId("medications-unknown-input").fill(markup);
  await page.getByTestId("medications-unknown-add").click();
  await expect(page.getByTestId("medications-list")).toContainText(markup);
  await expect(
    page.locator('section[data-testid="medications-section"] img'),
  ).toHaveCount(0);
  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });

  // Sign test-side only after the draft edits (open draft requires a draft;
  // a signed encounter renders the read-only non-draft view). Then reload so
  // the chart shows the signed badge with Start follow-up.
  await signBaselineViaDb(baselineId);
  await page.reload();
  await page.getByLabel(/search patients/i).fill(patientId);
  const openDraft = page.getByRole("button", {
    name: `Open draft ${patientId}`,
  });
  if ((await openDraft.count()) > 0) {
    await openDraft.first().click();
  }
  await expect(page.getByTestId("chart-section")).toBeVisible();
  await expect(page.getByTestId(`chart-badge-${baselineId}`)).toContainText(
    /registration.*signed/i,
  );

  // S14 chart selectors (exist in App.tsx): start the follow-up, expect the
  // reconcile notice until history_reconciliation is confirmed.
  await page.getByTestId(`start-followup-${baselineId}`).click();
  await expect(page.getByTestId("medications-reconcile-notice")).toBeVisible();
  await page
    .getByTestId(`open-encounter-${baselineId}`)
    .click()
    .catch(() => undefined);
});
