import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// S13 failing-first (RED — T9 journey contract, notes UI not implemented).
// SYNTHETIC FIXTURES ONLY. These 3 journeys define the frontend contract
// for dev-frontend; they timeout until the NotesSection exists.
// Backend contract assumed (RED, dev-backend): POST
// /api/v1/encounters/{id}/notes {"page","text"} (+ optional
// Idempotency-Key) -> 201 {"note":{id,encounter_id,page,text,
// author_id,author_display,created_at}}; GET .../notes -> 200 {items}.
// Provenance is server-derived; notes are append-only and listed
// separately from draft_data.history.
//
// Expected frontend contract (proposed stable selectors):
// - section: data-testid="notes-section" (region labelled Notes)
// - page select: data-testid="notes-page" (<select> wizard page id,
//   including "demographics" after the registration draft exists)
// - text input: data-testid="notes-text" (textarea/input labelled Note)
// - add button: data-testid="notes-add" (button labelled Add note)
// - list: data-testid="notes-list" containing one entry per note with
//   data-testid="notes-item" each showing page/author/time/text.
// - literal markup (e.g. "<b>note</b>") renders as text (escaped, no <b>).

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

// S13 journey 1 (RED): author adds a note on demographics, reload/resume
// shows it with page/author/time; markup renders as escaped text.
test("author adds a demographics note and it survives resume", async ({
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

  // RED: timeouts here until NotesSection is implemented.
  const section = page.getByTestId("notes-section");
  await expect(section).toBeVisible();
  await section.getByTestId("notes-page").selectOption("demographics");
  const noteText = `synthetic-note-${Date.now().toString(36)}`;
  await section.getByTestId("notes-text").fill(noteText);
  await section.getByTestId("notes-add").click();

  const items = section.getByTestId("notes-item");
  await expect(items.filter({ hasText: noteText }).first()).toBeVisible();
  const first = items.filter({ hasText: noteText }).first();
  await expect(first).toContainText(/demographics/i);
  await expect(first).toContainText(new RegExp(username, "i"));
  await expect(first).toContainText(/\d{4}-\d{2}-\d{2}|:\d{2}/);

  await reopenDraftAfterReload(page, patientId);
  const resumed = page.getByTestId("notes-section");
  await expect(resumed).toBeVisible();
  const resumedItems = resumed.getByTestId("notes-item");
  await expect(resumedItems.filter({ hasText: noteText }).first()).toBeVisible();
  await expect(
    resumedItems.filter({ hasText: noteText }).first(),
  ).toContainText(/demographics/i);
  await expect(resumedItems.filter({ hasText: noteText }).first()).toContainText(
    new RegExp(username, "i"),
  );
});

// S13 journey 2 (RED): literal markup is escaped, never rendered as HTML.
test("note markup renders as escaped text", async ({ page, request }) => {
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

  // RED: timeouts here until NotesSection is implemented.
  const section = page.getByTestId("notes-section");
  await expect(section).toBeVisible();
  await section.getByTestId("notes-page").selectOption("demographics");
  await section.getByTestId("notes-text").fill("<b>note</b>");
  await section.getByTestId("notes-add").click();

  const item = section.getByTestId("notes-item").filter({
    hasText: "<b>note</b>",
  });
  await expect(item.first()).toBeVisible();
  await expect(item.first().locator("b")).toHaveCount(0);

  await reopenDraftAfterReload(page, patientId);
  const resumed = page.getByTestId("notes-section");
  await expect(resumed).toBeVisible();
  const resumedItem = resumed.getByTestId("notes-item").filter({
    hasText: "<b>note</b>",
  });
  await expect(resumedItem.first()).toBeVisible();
  await expect(resumedItem.first().locator("b")).toHaveCount(0);
});

// S13 journey 3 (RED): notes render in their own section, visually
// separate from the history section; note text never appears as history.
test("notes section stays separate from history section", async ({
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

  await openDraftForPatient(page, patientId);

  // RED: timeouts here until NotesSection is implemented.
  const notes = page.getByTestId("notes-section");
  await expect(notes).toBeVisible();
  const noteText = `synthetic-separate-${Date.now().toString(36)}`;
  await notes.getByTestId("notes-page").selectOption("demographics");
  await notes.getByTestId("notes-text").fill(noteText);
  await notes.getByTestId("notes-add").click();
  await expect(
    notes.getByTestId("notes-item").filter({ hasText: noteText }).first(),
  ).toBeVisible();

  const history = page.getByTestId("history-section");
  await expect(history).toBeVisible();
  await expect(history.getByText(noteText)).toHaveCount(0);

  await reopenDraftAfterReload(page, patientId);
  const resumedNotes = page.getByTestId("notes-section");
  await expect(resumedNotes).toBeVisible();
  await expect(
    resumedNotes.getByTestId("notes-item").filter({ hasText: noteText }).first(),
  ).toBeVisible();
  const resumedHistory = page.getByTestId("history-section");
  await expect(resumedHistory).toBeVisible();
  await expect(resumedHistory.getByText(noteText)).toHaveCount(0);
});
async function openDraftForPatient(page: Page, patientId: string): Promise<void> {
  await page.getByLabel(/search patients/i).fill(patientId);
  await page
    .getByRole("button", { name: `Open draft ${patientId}` })
    .click();
  await expect(page.getByRole("heading", { name: /draft/i })).toBeVisible();
}

async function reopenDraftAfterReload(page: Page, patientId: string): Promise<void> {
  await page.reload();
  const openDraft = page.getByRole("button", {
    name: `Open draft ${patientId}`,
  });
  if ((await openDraft.count()) > 0) {
    await openDraft.first().click();
  }
  await expect(page.getByRole("heading", { name: /draft/i })).toBeVisible();
}
