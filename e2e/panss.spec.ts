import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// S10 slice 4 (RED — T10 journey contract, PANSS UI not implemented).
// SYNTHETIC FIXTURES ONLY. These 3 journeys define the frontend contract
// for dev-frontend; they timeout until the PANSS section exists.
// Backend contract (already green): GET /content/assessments/panss 200
// (panss-v1); PATCH /encounters validates panss.answers via evaluate_panss
// (422 on invalid), persists partial/complete/not_assessed verbatim (200).
// Skip shape: draft_data.panss = { not_assessed: True } (no answers key).
// Shared autosave contract: getEncounter/patchEncounter + If-Match,
// ~1s debounce, role=status Saving…/Saved (rev N), read-only for non-author.
//
// Expected frontend contract (proposed stable selectors):
// - section: data-testid="panss-section" (region labelled PANSS)
// - item selects: data-testid="panss-item-P1" … "panss-item-G16"
//   (<select> with explicit empty placeholder option value="", no default 1)
// - window text: "previous 7 days" visible in section
// - prior text: registration single draft shows "no prior" / "prior: none"
//   as historical text only, never prefilled as answers
// - totals: data-testid="panss-positive|panss-negative|panss-general|panss-total"
//   ("—" when incomplete/suppressed, never 0-prefilled; no default 1s)
// - skip: data-testid="panss-skip" (button labelled Skip), persists
//   not_assessed verbatim and survives reload/resume (GET shows not_assessed)
// - partial: section shows /partial|missing/ and total suppressed ("—")
// - full all-1: 7/7/16/30 visible; NO treatment-gate wording
//   ("Mildly ill", "Moderately ill", "Severely ill" must be absent)

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

const PANSS_POSITIVE = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"];
const PANSS_NEGATIVE = ["N1", "N2", "N3", "N4", "N5", "N6", "N7"];
const PANSS_GENERAL = [
  "G1",
  "G2",
  "G3",
  "G4",
  "G5",
  "G6",
  "G7",
  "G8",
  "G9",
  "G10",
  "G11",
  "G12",
  "G13",
  "G14",
  "G15",
  "G16",
];
const PANSS_ALL_30 = [...PANSS_POSITIVE, ...PANSS_NEGATIVE, ...PANSS_GENERAL];

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

async function reopenDraftAfterReload(
  page: Page,
  patientId: string,
): Promise<void> {
  await page.reload();
  const openDraft = page.getByRole("button", {
    name: `Open draft ${patientId}`,
  });
  if ((await openDraft.count()) > 0) {
    await openDraft.first().click();
  }
  await expect(page.getByRole("heading", { name: /draft/i })).toBeVisible();
}

/** Source-version persistence: GET the draft and return its panss block. */
async function getPanssViaApi(
  request: APIRequestContext,
  patientId: string,
): Promise<Record<string, unknown> | null> {
  const listed = await request.get(
    `/api/v1/patients?q=${encodeURIComponent(patientId)}`,
  );
  expect(listed.ok()).toBeTruthy();
  const payload = (await listed.json()) as {
    items: { id: string; patient_id: string }[];
  };
  const patient = payload.items.find((i) => i.patient_id === patientId);
  expect(patient).toBeTruthy();
  const encounters = await request.get(
    `/api/v1/patients/${patient!.id}/encounters`,
  );
  expect(encounters.ok()).toBeTruthy();
  const encPayload = (await encounters.json()) as {
    items: { id: string }[];
  };
  expect(encPayload.items.length).toBeGreaterThan(0);
  const got = await request.get(
    `/api/v1/encounters/${encPayload.items[0].id}`,
  );
  expect(got.ok()).toBeTruthy();
  const full = (await got.json()) as {
    encounter: { draft_data: Record<string, unknown> };
  };
  const panss = full.encounter.draft_data?.["panss"];
  return (panss ?? null) as Record<string, unknown> | null;
}

// (a) Fresh form: 30 explicit-empty selects (no default 1), total null/—;
// Skip persists not_assessed across reload/resume (GET shows not_assessed).
test("fresh PANSS has no defaults and Skip persists not_assessed", async ({
  page,
  request,
}) => {
  const patientId = await setupDraft(page, request);
  const section = page.getByTestId("panss-section");
  await expect(section).toBeVisible({ timeout: 10_000 });
  await expect(section.getByText(/previous 7 days/i)).toBeVisible();
  // Registration single draft: no prior score, or explicit prior-none text;
  // prior history must never prefill answers (all selects stay empty).
  await expect(section.getByText(/no prior|prior.*none/i)).toBeVisible();
  for (const itemId of PANSS_ALL_30) {
    await expect(section.getByTestId(`panss-item-${itemId}`)).toHaveValue("");
  }
  await expect(section.getByTestId("panss-total")).toContainText(/—/);
  await expect(section.getByText(/mildly ill/i)).toHaveCount(0);
  await expect(section.getByText(/moderately ill/i)).toHaveCount(0);
  await expect(section.getByText(/severely ill/i)).toHaveCount(0);

  await section.getByTestId("panss-skip").click();
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });
  await expect(section.getByText(/not assessed|skipped/i)).toBeVisible();

  await reopenDraftAfterReload(page, patientId);
  const resumed = page.getByTestId("panss-section");
  await expect(resumed).toBeVisible({ timeout: 10_000 });
  await expect(resumed.getByText(/not assessed|skipped/i)).toBeVisible();

  // Source-version persistence: server draft carries the skip verbatim.
  const panss = await getPanssViaApi(request, patientId);
  expect(panss).toEqual({ not_assessed: true });
});

// (b) Partial P1=2 only: partial/missing shown, total suppressed, resume kept.
test("partial PANSS suppresses total and resumes selection", async ({
  page,
  request,
}) => {
  const patientId = await setupDraft(page, request);
  const section = page.getByTestId("panss-section");
  await expect(section).toBeVisible({ timeout: 10_000 });

  await section.getByTestId("panss-item-P1").selectOption("2");
  await expect(section.getByText(/partial|missing/i)).toBeVisible({
    timeout: 10_000,
  });
  await expect(section.getByTestId("panss-total")).toContainText(/—/);
  await expect(section.getByTestId("panss-total")).not.toContainText(/\b30\b/);
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });

  await reopenDraftAfterReload(page, patientId);
  const resumed = page.getByTestId("panss-section");
  await expect(resumed).toBeVisible({ timeout: 10_000 });
  await expect(resumed.getByTestId("panss-item-P1")).toHaveValue("2");
  for (const itemId of PANSS_ALL_30.filter((id) => id !== "P1")) {
    await expect(resumed.getByTestId(`panss-item-${itemId}`)).toHaveValue("");
  }
  await expect(resumed.getByText(/partial|missing/i)).toBeVisible();
  await expect(resumed.getByTestId("panss-total")).toContainText(/—/);
});

// (c) Full all-1: 7/7/16/30 visible, no treatment-gate wording.
test("complete PANSS all-1 shows subscale sums without illness gates", async ({
  page,
  request,
}) => {
  await setupDraft(page, request);
  const section = page.getByTestId("panss-section");
  await expect(section).toBeVisible({ timeout: 10_000 });

  for (const itemId of PANSS_ALL_30) {
    await section.getByTestId(`panss-item-${itemId}`).selectOption("1");
  }
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });
  await expect(section.getByTestId("panss-positive")).toContainText(/\b7\b/);
  await expect(section.getByTestId("panss-negative")).toContainText(/\b7\b/);
  await expect(section.getByTestId("panss-general")).toContainText(/\b16\b/);
  await expect(section.getByTestId("panss-total")).toContainText(/\b30\b/);
  await expect(section.getByText(/mildly ill/i)).toHaveCount(0);
  await expect(section.getByText(/moderately ill/i)).toHaveCount(0);
  await expect(section.getByText(/severely ill/i)).toHaveCount(0);
});
