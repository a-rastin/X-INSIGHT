import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// S12 slice C (RED — T9 journey contract, History/Effects UI not implemented).
// SYNTHETIC FIXTURES ONLY. These 2 journeys define the frontend contract
// for dev-frontend; they timeout until HistorySection/EffectsSection exist.
// Backend contract (green): PATCH /encounters validates draft_data.history
// (declared fields only, known=boolean / unknown|not_assessed=null) and
// draft_data.effects (all four FR-21 IDs, present requires reviewed severity,
// absent/not_assessed severity null, explicit clear on status change),
// stamps server provenance, 422 leaves revision/draft_data unchanged.
// Backend contract (RED, Slice A/B — dev-backend): excluded FR-14 regimen
// fields (dose/unit/route/frequency/active/stopped) in medication payloads,
// PATCH /patients/{id} phone update, history_reconciliation shape guard,
// GET /content/history released-only exposure. History/effects PATCH in this
// e2e environment (default content dir: history-effects-v0.1-draft is
// awaiting_review, never released) returns 422 until the history content is
// released or the e2e server is pointed at a released definition; the specs
// below therefore additionally require that release/env before they can go
// green. No BARS/SAS/AIMS full-scale UI is expected (FR-21: supporting
// sources only, never mandated questionnaires).
// Shared autosave contract (S07 path, reused — no separate persistence):
// getEncounter/patchEncounter + If-Match, ~1s debounce, role=status
// Saving…/Saved (rev N), reload preserves, read-only for non-author.
//
// Expected frontend contract (proposed stable selectors):
// - section: data-testid="history-section" (region labelled History)
// - section: data-testid="effects-section" (region labelled Adverse effects)
// - history controls: per-field inputs named data-testid="history-item-<id>"
//   (exact field ids await history content release; this spec only asserts
//   the section renders and participates in the shared Saved status)
// - effect status selects: data-testid="effects-status-tardive_dyskinesia",
//   "effects-status-akathisia", "effects-status-parkinsonism",
//   "effects-status-acute_dystonia" (<select> present/absent/not_assessed)
// - effect severity selects: data-testid="effects-severity-<id>" (reviewed
//   severity enum when present; hidden or empty when absent/not_assessed)

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

const EFFECT_IDS = [
  "tardive_dyskinesia",
  "akathisia",
  "parkinsonism",
  "acute_dystonia",
] as const;

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

// S12 slice C journey 1 (RED): History + Effects saved-state via S07 path.
// Sets all four effects to absent (severity null, no unreleased severity ids),
// expects shared Saving…/Saved (rev N), reload preserves absent states.
test("history and effects saved-state persists across reload", async ({
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
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);

  await openDraftForPatient(page, patientId);

  // RED: timeouts here until HistorySection/EffectsSection are implemented.
  await expect(page.getByTestId("history-section")).toBeVisible();
  await expect(page.getByTestId("effects-section")).toBeVisible();

  for (const id of EFFECT_IDS) {
    await page.getByTestId(`effects-status-${id}`).selectOption("absent");
  }

  // Shared S07 autosave contract: debounce (~1s) + If-Match PATCH.
  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });

  await page.reload();
  const openDraft = page.getByRole("button", {
    name: `Open draft ${patientId}`,
  });
  if ((await openDraft.count()) > 0) {
    await openDraft.first().click();
  }
  await expect(page.getByTestId("history-section")).toBeVisible();
  await expect(page.getByTestId("effects-section")).toBeVisible();
  for (const id of EFFECT_IDS) {
    await expect(page.getByTestId(`effects-status-${id}`)).toHaveValue(
      "absent",
    );
  }
});

// S12 slice C journey 2 (RED): non-author sees read-only History + Effects.
// Reuses the S07 read-only contract (disabled controls + "Read-only" text).
test("non-author sees read-only history and effects", async ({
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
  await loginViaUI(page, other, password, "physician");
  await dismissResearchNotice(page);

  await openDraftForPatient(page, patientId);

  // RED: timeouts here until HistorySection/EffectsSection are implemented.
  await expect(page.getByTestId("history-section")).toBeVisible();
  await expect(page.getByTestId("effects-section")).toBeVisible();
  await expect(page.getByText(/read-only/i).first()).toBeVisible();
  for (const id of EFFECT_IDS) {
    await expect(page.getByTestId(`effects-status-${id}`)).toBeDisabled();
  }
});
