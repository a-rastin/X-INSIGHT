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

// S06 slice-4 (T9 browser seam): demographics form + shared directory search.
test("physician registers a patient and finds it via directory search", async ({
  page,
  request,
}) => {
  const username = uniquePhysicianUsername();
  const password = "synthetic-secret";
  await createPhysicianViaAdminApi(request, username, password);
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  const patientId = uniquePatientId();
  const firstName = uniqueName("Anna");
  const lastName = uniqueName("Muller");
  await page.getByLabel(/first name/i).fill(firstName);
  await page.getByLabel(/last name/i).fill(lastName);
  await page.getByLabel(/^sex$/i).selectOption("F");
  await page.getByLabel(/^age$/i).fill("30");
  await page.getByLabel(/patient id/i).fill(patientId);
  await page.getByLabel("Clinical status", { exact: true }).selectOption("first_time");
  await page.getByRole("button", { name: /register patient|next/i }).click();
  await expect(page.getByText(patientId).first()).toBeVisible();
  await page.getByLabel(/search patients/i).fill("0000000000");
  await expect(page.getByText(patientId)).toHaveCount(0);
  await page.getByLabel(/search patients/i).fill(patientId);
  await expect(page.getByText(patientId).first()).toBeVisible();
});

test("registration submit stays disabled until demographics are valid", async ({
  page,
  request,
}) => {
  const username = uniquePhysicianUsername();
  const password = "synthetic-secret";
  await createPhysicianViaAdminApi(request, username, password);
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  const submit = page.getByRole("button", { name: /register patient|next/i });
  await expect(submit).toBeDisabled();
  await page.getByLabel(/first name/i).fill("Anna");
  await page.getByLabel(/last name/i).fill("Muller");
  await page.getByLabel(/^sex$/i).selectOption("F");
  await page.getByLabel(/^age$/i).fill("17");
  await page.getByLabel(/patient id/i).fill("abc");
  await page.getByLabel("Clinical status", { exact: true }).selectOption("first_time");
  await expect(submit).toBeDisabled();
  await page.getByLabel(/^age$/i).fill("30");
  await page.getByLabel(/patient id/i).fill(uniquePatientId());
  await expect(submit).toBeEnabled();
});

test("directory results are shared across physicians", async ({
  page,
  request,
}) => {
  const password = "synthetic-secret";
  const docA = uniquePhysicianUsername();
  const docB = `${uniquePhysicianUsername()}b`;
  await createPhysicianViaAdminApi(request, docA, password);
  await createPhysicianViaAdminApi(request, docB, password);
  const patientId = uniquePatientId();
  await createPatientViaPhysicianApi(request, docA, password, {
    first_name: "Shared",
    last_name: uniqueName("Case"),
    sex: "F",
    age: 33,
    patient_id: patientId,
    clinical_status: "first_time",
  });
  await loginViaUI(page, docB, password, "physician");
  await dismissResearchNotice(page);
  await page.getByLabel(/search patients/i).fill(patientId);
  await expect(page.getByText(patientId).first()).toBeVisible();
});
