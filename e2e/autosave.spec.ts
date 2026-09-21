import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

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

// S07 slice 2 (T9 browser seam): author autosave via If-Match + ETag flow.
test("author autosave persists across reload", async ({ page, request }) => {
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

  const note = page.getByLabel(/Draft note/i);
  await expect(note).toBeVisible();
  const syntheticValue = `synthetic-autosave-${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  await note.fill(syntheticValue);

  // Autosave debounce (~1s) + PATCH with If-Match current revision.
  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });

  await page.reload();
  // Draft editor either stays open or requires reopening after reload.
  const openDraft = page.getByRole("button", {
    name: `Open draft ${patientId}`,
  });
  if ((await openDraft.count()) > 0) {
    await openDraft.first().click();
  }
  await expect(page.getByLabel(/Draft note/i)).toHaveValue(syntheticValue);
});

// S07 slice 2 (T9 browser seam): stale revision keeps edits and offers reload.
// After clicking "Reload draft", the textarea retains the unsaved valueB
// (edits preserved, not overwritten by the server value) and status still
// reports the stale condition.
test("stale tab keeps edits and offers reload", async ({ page, request }) => {
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

  // Tab A: open the draft first (holds revision N).
  await openDraftForPatient(page, patientId);

  // Tab B: same session (shared context cookies), same draft, same revision N.
  const tabB = await page.context().newPage();
  await tabB.goto("/");
  await openDraftForPatient(tabB, patientId);

  const valueA = `synthetic-autosave-${Date.now().toString(36)}a${Math.floor(Math.random() * 1e6).toString(36)}`;
  await page.getByLabel(/Draft note/i).fill(valueA);
  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });

  // Tab B still holds the old revision, so its autosave must hit 412.
  const valueB = `synthetic-autosave-${Date.now().toString(36)}b${Math.floor(Math.random() * 1e6).toString(36)}`;
  await tabB.getByLabel(/Draft note/i).fill(valueB);
  await expect(tabB.getByRole("status")).toContainText(/Stale revision/, {
    timeout: 10_000,
  });
  await expect(tabB.getByRole("button", { name: /Reload draft/i })).toBeVisible();
  // Edits retained, not overwritten by tab A's server value.
  await expect(tabB.getByLabel(/Draft note/i)).toHaveValue(valueB);

  // Reload refetches but preserves unsaved edits in the textarea.
  await tabB.getByRole("button", { name: /Reload draft/i }).click();
  await expect(tabB.getByLabel(/Draft note/i)).toHaveValue(valueB);
  await expect(tabB.getByRole("status")).toContainText(/Stale revision/);
  await tabB.close();
});
