import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// S09 slice 4 (RED — T9 journey contract, UI not implemented).
// SYNTHETIC FIXTURES ONLY. These 4 journeys define the frontend contract
// for dev-frontend; they timeout until the diagnosis section exists.
// Shared autosave contract: getEncounter/patchEncounter + If-Match,
// ~1s debounce, role=status Saving…/Saved (rev N). Bypass is distinct
// from completion ("Bypass diagnosis" vs "Complete") and never asks for
// a reason field.

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

async function setupDraft(
  page: Page,
  request: APIRequestContext,
): Promise<string> {
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
  return patientId;
}

// T9-1: partial shows live threshold, no completed threshold, bypass distinct.
test("partial diagnosis shows no threshold with distinct bypass", async ({
  page,
  request,
}) => {
  await setupDraft(page, request);
  const section = page.getByRole("region", { name: /diagnosis/i });
  await expect(section).toBeVisible({ timeout: 10_000 });
  await expect(section.getByText("partial — answer all fields", { exact: true })).toBeVisible();
  await expect(section.getByText(/threshold met/i)).toHaveCount(0);
  await expect(
    section.getByRole("button", { name: /bypass diagnosis/i }),
  ).toBeVisible();
  await expect(
    section.getByRole("button", { name: /^complete$/i }),
  ).toBeVisible();
});

// T9-2: below-threshold needs revision-tied ack checkbox before Continue.
test("below-threshold requires ack tied to revision before Continue", async ({
  page,
  request,
}) => {
  await setupDraft(page, request);
  const section = page.getByRole("region", { name: /diagnosis/i });
  await expect(section).toBeVisible({ timeout: 10_000 });
  // Fresh draft is partial (months empty); fill months to reach a
  // complete below-threshold preview without inventing clinical data.
  await section.getByLabel(/continuous months/i).fill("2");
  await expect(section.getByText("below threshold", { exact: true })).toBeVisible({ timeout: 10_000 });
  const ack = section.getByLabel(/acknowledge.*warning/i);
  await expect(ack).toBeVisible();
  const cont = section.getByRole("button", { name: /continue/i });
  await expect(cont).toBeDisabled();
  await ack.check();
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });
  await expect(cont).toBeEnabled();
});

// T9-3: bypass uses shared autosave Saving…/Saved (rev N), distinct label.
test("bypass uses shared autosave contract", async ({ page, request }) => {
  await setupDraft(page, request);
  const section = page.getByRole("region", { name: /diagnosis/i });
  await expect(section).toBeVisible({ timeout: 10_000 });
  await section.getByRole("button", { name: /bypass diagnosis/i }).click();
  await expect(page.getByRole("status")).toContainText(/Saving/, {
    timeout: 10_000,
  });
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });
  await expect(section.getByText(/bypassed/i)).toBeVisible();
});

// T9-4: reload resumes bypassed status (no reason prompt, no completion).
test("reload resumes bypassed diagnosis", async ({ page, request }) => {
  const patientId = await setupDraft(page, request);
  const section = page.getByRole("region", { name: /diagnosis/i });
  await expect(section).toBeVisible({ timeout: 10_000 });
  await section.getByRole("button", { name: /bypass diagnosis/i }).click();
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });
  await page.reload();
  const openDraft = page.getByRole("button", {
    name: `Open draft ${patientId}`,
  });
  if ((await openDraft.count()) > 0) {
    await openDraft.first().click();
  }
  const resumed = page.getByRole("region", { name: /diagnosis/i });
  await expect(resumed).toBeVisible({ timeout: 10_000 });
  await expect(resumed.getByText(/bypassed/i)).toBeVisible();
});
