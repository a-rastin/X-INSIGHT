import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

// S07 slice 4 (RED, T9 browser seam): author-confirmed discard.
// No "Discard draft" button exists yet, so this test fails with a timeout
// waiting for that button.
//
// Agreed UI contract for the main agent to implement:
// - The draft editor shows a button "Discard draft", visible only when the
//   encounter state is draft AND the viewer is the author.
// - Clicking it calls window.confirm("Discard this draft? This cannot be
//   undone."). If the dialog is dismissed, no discard request is sent and
//   the editor (with its edits) stays as-is.
// - On accept, the client POSTs /api/v1/encounters/{id}/discard with
//   If-Match <current revision> and JSON {"confirm": true}, then shows the
//   text "Draft discarded." The discarded draft is shown as a tombstone:
//   the textarea is disabled or gone (never editable), while the patient
//   row stays in the directory. Reloading/reopening shows the discarded
//   tombstone, not a resumable editable draft.

function uniquePhysicianUsername(): string {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return `e2ediscard${suffix}`.toLowerCase();
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

test("author discards draft with confirmation; tombstone stays, patient stays", async ({
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
  await expect(page.getByLabel(/Draft note/i)).toBeVisible();
  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });

  let dialogMessage: string | null = null;
  page.on("dialog", async (dialog) => {
    dialogMessage = dialog.message();
    await dialog.accept();
  });
  await page.getByRole("button", { name: /discard draft/i }).click();

  // Explicit confirmation gate used the agreed prompt text.
  expect(dialogMessage).toMatch(/Discard this draft\? This cannot be undone\./);

  // Tombstone: acknowledged as discarded, never editable again.
  await expect(page.getByText(/draft discarded/i)).toBeVisible({
    timeout: 10_000,
  });
  const note = page.getByLabel(/Draft note/i);
  if ((await note.count()) > 0) {
    await expect(note).toBeDisabled();
  }

  // The patient is retained in the directory, not deleted with the draft.
  await expect(
    page.getByRole("table").getByText(patientId, { exact: true }),
  ).toBeVisible();

  // Reload: the draft is still discarded, not resumable/editable.
  await page.reload();
  await expect(page.getByRole("heading", { name: /patients/i })).toBeVisible();
  const reopenButton = page.getByRole("button", {
    name: `Open draft ${patientId}`,
  });
  if ((await reopenButton.count()) > 0) {
    await reopenButton.first().click();
  }
  await expect(page.getByText(/draft discarded/i)).toBeVisible({
    timeout: 10_000,
  });
  const reopenedNote = page.getByLabel(/Draft note/i);
  if ((await reopenedNote.count()) > 0) {
    await expect(reopenedNote).toBeDisabled();
  }
});
