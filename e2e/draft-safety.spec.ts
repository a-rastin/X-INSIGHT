import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

function uniquePhysicianUsername(): string {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return `e2esafe${suffix}`.toLowerCase();
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

// S07 slice 3 (T9 browser seam): a failed network/database save is never
// advertised as Saved; the status reports the failure and edits are kept.
test("failed save never shows Saved", async ({ page, request }) => {
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
  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });

  // Block only PATCH saves; GETs must keep working.
  await page.route("**/api/v1/encounters/*", async (route) => {
    if (route.request().method() === "PATCH") {
      await route.abort();
    } else {
      await route.continue();
    }
  });

  const syntheticValue = `synthetic-failed-save-${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  await note.fill(syntheticValue);

  // The failed write must surface as a failure, never as durable.
  await expect(page.getByRole("status")).toContainText(/Save failed/, {
    timeout: 10_000,
  });
  await expect(page.getByRole("status")).not.toContainText(/Saved \(rev/, {
    timeout: 3_000,
  });
  // Edits are retained, not discarded by the failure.
  await expect(note).toHaveValue(syntheticValue);
});

// S07 slice 3 (T9 browser seam): in-app navigation warns while local edits
// remain, and unsaved initial demographics are not advertised as durable.
test("navigation warns with pending edits and unsaved demographics not durable", async ({
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
    age: 32,
    patient_id: patientId,
    clinical_status: "first_time",
  });
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);

  // Unsaved initial demographics are not advertised as durable: the
  // registration form shows no "Saved" text before submit.
  const registerForm = page.getByRole("form", { name: /Register patient/i });
  await expect(registerForm).toBeVisible();
  await expect(registerForm.getByText(/Saved/)).toHaveCount(0);

  await openDraftForPatient(page, patientId);
  const note = page.getByLabel(/Draft note/i);
  await expect(note).toBeVisible();
  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });

  let dialogSeen = false;
  page.on("dialog", async (dialog) => {
    dialogSeen = true;
    await dialog.dismiss();
  });
  const dirtyValue = `synthetic-dirty-${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  await note.fill(dirtyValue);
  // Navigate away immediately, before the ~1s autosave debounce fires.
  await page.getByRole("button", { name: "Close", exact: true }).click();

  // Expected: a confirm dialog warns about the pending edits...
  expect(dialogSeen).toBe(true);
  // ...and the dirty edits are preserved, not silently discarded.
  await expect(page.getByLabel(/Draft note/i)).toHaveValue(dirtyValue);
});
