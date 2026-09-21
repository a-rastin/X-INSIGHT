import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// S11 slice 4 (RED — T10 journey contract, C-SSRS UI not implemented).
// SYNTHETIC FIXTURES ONLY. These 4 journeys define the frontend contract
// for dev-frontend; they timeout until the C-SSRS section exists.
// Backend contract (already green): evaluate_cssrs with L1-L5
// {endorsed bool, period current/historical}, optional intensity/behavior/
// lethality, flags {no_ideation, clinical_review, high_risk}, severity max
// endorsed. PATCH /encounters validates cssrs block
// ({answers:{L1..}} or {not_assessed:True}) and persists verbatim (200).
// Skip shape: draft_data.cssrs = {not_assessed: True} (no answers key).
// Released content: content/assessments/cssrs.json (cssrs-v1).
// Shared autosave contract: getEncounter/patchEncounter + If-Match,
// ~1s debounce, role=status Saving…/Saved (rev N), read-only for non-author.
//
// Proposed stable selectors (frontend contract):
// - section: data-testid="cssrs-section" (region labelled C-SSRS)
// - item selects: data-testid="cssrs-item-L1" … "cssrs-item-L5"
//   (<select> with explicit empty placeholder option value="", options
//   Yes value="yes" / No value="no", no defaults)
// - period selects: data-testid="cssrs-period-L1" … "cssrs-period-L5"
//   (<select> current/historical, required when endorsed Yes; visible or
//   enabled once the matching item is Yes)
// - window text: current/historical/window/period wording visible in section
// - severity: data-testid="cssrs-severity" ("—" when unanswered/skipped,
//   never 0-prefilled; ordinal 0-5 once answered; no composite text)
// - review flag: data-testid="cssrs-review-flag" (clinical review message,
//   persistent; role=alert or visible text)
// - urgent flag: data-testid="cssrs-urgent-flag" (urgent/high-risk message,
//   role=alert with text, keyboard focusable, not color-only)
// - skip: data-testid="cssrs-skip" (button labelled Skip), persists
//   not_assessed verbatim and survives reload/resume (GET shows not_assessed)
// - missing guidance: /missing|partial|unanswered/ text while incomplete

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

const CSSRS_LEVELS = ["L1", "L2", "L3", "L4", "L5"];

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

/** Source-version persistence: GET the draft and return its cssrs block. */
async function getCssrsViaApi(
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
  const cssrs = full.encounter.draft_data?.["cssrs"];
  return (cssrs ?? null) as Record<string, unknown> | null;
}

// (1) Fresh form: 5 explicit-empty selects (no defaults), severity —, no
// composite text; Skip persists not_assessed across reload/resume.
test("fresh C-SSRS has no defaults and Skip persists not_assessed", async ({
  page,
  request,
}) => {
  const patientId = await setupDraft(page, request);
  const section = page.getByTestId("cssrs-section");
  await expect(section).toBeVisible({ timeout: 10_000 });
  await expect(section.getByText(/current|historical|window|period/i).first()).toBeVisible();
  for (const level of CSSRS_LEVELS) {
    await expect(section.getByTestId(`cssrs-item-${level}`)).toHaveValue("");
  }
  await expect(section.getByTestId("cssrs-severity")).toContainText(/—/);
  await expect(section.getByText(/composite|risk score/i)).toHaveCount(0);

  await section.getByTestId("cssrs-skip").click();
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });
  await expect(section.getByText(/not assessed|skipped/i)).toBeVisible();

  await reopenDraftAfterReload(page, patientId);
  const resumed = page.getByTestId("cssrs-section");
  await expect(resumed).toBeVisible({ timeout: 10_000 });
  await expect(resumed.getByText(/not assessed|skipped/i)).toBeVisible();

  // Source-version persistence: server draft carries the skip verbatim.
  const cssrs = await getCssrsViaApi(request, patientId);
  expect(cssrs).toEqual({ not_assessed: true });
});

// (2) Complete explicit negatives: all L1-L5 No gives no-ideation result.
test("complete explicit C-SSRS negatives give no-ideation result", async ({
  page,
  request,
}) => {
  const patientId = await setupDraft(page, request);
  const section = page.getByTestId("cssrs-section");
  await expect(section).toBeVisible({ timeout: 10_000 });

  for (const level of CSSRS_LEVELS) {
    await section.getByTestId(`cssrs-item-${level}`).selectOption("no");
  }
  await expect(section.getByTestId("cssrs-severity")).toContainText(/\b0\b/, {
    timeout: 10_000,
  });
  await expect(
    section.getByText(/no-ideation|no ideation|routine/i).first(),
  ).toBeVisible();
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });

  await reopenDraftAfterReload(page, patientId);
  const resumed = page.getByTestId("cssrs-section");
  await expect(resumed).toBeVisible({ timeout: 10_000 });
  for (const level of CSSRS_LEVELS) {
    await expect(resumed.getByTestId(`cssrs-item-${level}`)).toHaveValue("no");
  }
  await expect(resumed.getByTestId("cssrs-severity")).toContainText(/\b0\b/);
  await expect(
    resumed.getByText(/no-ideation|no ideation|routine/i).first(),
  ).toBeVisible();
  void request;
  void patientId;
});

// (3) Level-3 endorsed: severity 3 without autofill + persistent review.
test("level-3 endorsed gives severity 3 without autofill and persistent review", async ({
  page,
  request,
}) => {
  const patientId = await setupDraft(page, request);
  const section = page.getByTestId("cssrs-section");
  await expect(section).toBeVisible({ timeout: 10_000 });

  await section.getByTestId("cssrs-item-L3").selectOption("yes");
  await section.getByTestId("cssrs-period-L3").selectOption("current");
  await section.getByTestId("cssrs-item-L4").selectOption("no");
  await section.getByTestId("cssrs-item-L5").selectOption("no");
  // L1/L2 left empty: must not be autofilled from the higher endorsement.
  await expect(section.getByTestId("cssrs-item-L1")).toHaveValue("");
  await expect(section.getByTestId("cssrs-item-L2")).toHaveValue("");
  await expect(section.getByTestId("cssrs-severity")).toContainText(/\b3\b/, {
    timeout: 10_000,
  });
  await expect(section.getByTestId("cssrs-review-flag")).toBeVisible();
  await expect(section.getByTestId("cssrs-review-flag")).toContainText(
    /clinical review/i,
  );
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });

  await reopenDraftAfterReload(page, patientId);
  const resumed = page.getByTestId("cssrs-section");
  await expect(resumed).toBeVisible({ timeout: 10_000 });
  await expect(resumed.getByTestId("cssrs-item-L3")).toHaveValue("yes");
  await expect(resumed.getByTestId("cssrs-period-L3")).toHaveValue("current");
  await expect(resumed.getByTestId("cssrs-item-L1")).toHaveValue("");
  await expect(resumed.getByTestId("cssrs-item-L2")).toHaveValue("");
  await expect(resumed.getByTestId("cssrs-severity")).toContainText(/\b3\b/);
  await expect(resumed.getByTestId("cssrs-review-flag")).toBeVisible();
  await expect(resumed.getByTestId("cssrs-review-flag")).toContainText(
    /clinical review/i,
  );
  void request;
});

// (4) High-risk + autosave safety: L4 Yes current shows an urgent flag and
// reload cannot erase responses or turn skip into zero.
test("high-risk C-SSRS flag survives reload and autosave cannot erase it", async ({
  page,
  request,
}) => {
  const patientId = await setupDraft(page, request);
  const section = page.getByTestId("cssrs-section");
  await expect(section).toBeVisible({ timeout: 10_000 });

  await section.getByTestId("cssrs-item-L4").selectOption("yes");
  await section.getByTestId("cssrs-period-L4").selectOption("current");
  const urgent = section.getByTestId("cssrs-urgent-flag");
  await expect(urgent).toBeVisible({ timeout: 10_000 });
  await expect(urgent).toContainText(/urgent|high-risk|high risk/i);
  // Urgent flag is a text alert, not color-only: role=alert carries text.
  await expect(page.getByRole("alert").getByText(/urgent|high-risk|high risk/i).first()).toBeVisible();
  // Keyboard-focusable: the flag itself accepts focus.
  await urgent.focus();
  await expect(urgent).toBeFocused();
  await expect(section.getByTestId("cssrs-severity")).toContainText(/\b4\b/);
  await expect(page.getByRole("status")).toContainText(/Saved \(rev \d+\)/, {
    timeout: 10_000,
  });

  // Page switch (reload + resume) must not erase responses or coerce to 0.
  await reopenDraftAfterReload(page, patientId);
  const resumed = page.getByTestId("cssrs-section");
  await expect(resumed).toBeVisible({ timeout: 10_000 });
  await expect(resumed.getByTestId("cssrs-item-L4")).toHaveValue("yes");
  await expect(resumed.getByTestId("cssrs-period-L4")).toHaveValue("current");
  await expect(resumed.getByTestId("cssrs-severity")).toContainText(/\b4\b/);
  await expect(resumed.getByTestId("cssrs-severity")).not.toContainText(/\b0\b/);
  const resumedUrgent = resumed.getByTestId("cssrs-urgent-flag");
  await expect(resumedUrgent).toBeVisible();
  await expect(resumedUrgent).toContainText(/urgent|high-risk|high risk/i);
  void request;
});
