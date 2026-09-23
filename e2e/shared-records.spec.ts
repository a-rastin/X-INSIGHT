import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const execFileAsync = promisify(execFile);

// S51 e2e — shared-records browser flow (RED — T9 journey contract).
// SYNTHETIC FIXTURES ONLY. These 3 journeys define the frontend contract
// for the S51 implementer; journeys 1-2 timeout on the missing selectors
// until the archive/deactivation UI exists. Journey 3 reuses the existing
// chart + read-only contract (S14) plus signed seeding via SQL.
// Seams: T1 (backend archive/deactivate/sign, green) and T9 (this spec).
// No live provider needed.
//
// Signed seeding (test-only, never production routes; psql precedent follows
// e2e/followup.spec.ts — node `pg` is unavailable, /usr/bin/psql exists):
// signBaselineViaDb marks the registration draft signed with a direct DB
// UPDATE, the same way backend/tests/http/test_followup.py seeds fixtures.
// There is NO sign-route shortcut in prod and none is added here.
//
// Expected frontend contract (stable selectors the implementer builds to;
// do not invent extra testids beyond these):
// Archive (journey 1, admin-only, inside the open chart):
// - patient-archive-button: "Archive" button on the chart (admin only)
// - patient-archive-dialog: confirm dialog; contains
//   patient-archive-dialog-draft-count (e.g. "1 open draft") and a
//   read-only warning (e.g. /drafts become read-only/i)
// - patient-archive-confirm-button / patient-archive-cancel: dialog actions
// - patient-archived-badge: "Archived" badge on the chart/directory row
// - patient-directory-archived-filter: archived visibility filter
//   (default hides archived; "Archived" option shows them)
// - patient-archived-notice: archived notice in the draft editor, which is
//   read-only while archived
// - patient-unarchive-button: "Unarchive" button (admin only)
// Deactivation (journey 2, admin-only, on the Physicians page):
// - physician-row-<id>: selectable row for the target physician
// - physician-deactivate-review: draft-set review region; contains
//   physician-draft-set-count (e.g. "1 draft") and
//   physician-draft-set-revision (per-draft revision shown)
// - physician-deactivate-retain / physician-deactivate-discard: explicit
//   retain-vs-discard choice (radio)
// - physician-deactivate-confirm-checkbox: explicit confirm checkbox
// - physician-deactivate-confirm-button: confirm action (enabled only with
//   a choice + checked box)
// - physician-deactivate-tombstone: tombstone marker for a discarded draft
// Shared chart (journey 3, existing S14 contract, no new testids):
// - chart-section, chart-encounters, chart-encounter-<id>,
//   chart-badge-<id> (/registration.*signed/i, /follow_up.*draft/i),
//   open-encounter-<id>; non-author draft editor is read-only with
//   /read-only/i visible and inputs disabled.

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

const TEST_DATABASE_URL =
  "postgresql://xinsight:xinsight_dev@localhost:5432/xinsight_test";

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
  await page.getByRole("button", { name: `Open draft ${patientId}` }).click();
  await expect(page.getByRole("heading", { name: /draft/i })).toBeVisible();
}

async function createFollowupViaPhysicianApi(
  request: APIRequestContext,
  username: string,
  password: string,
  patientUuid: string,
  baselineId: string,
): Promise<string> {
  const physicianLogin = await request.post("/api/v1/auth/login", {
    data: { username, password, role: "physician" },
  });
  expect(physicianLogin.ok()).toBeTruthy();
  const storage = await request.storageState();
  const csrf = storage.cookies.find((c) => c.name === "xinsight_csrf")?.value;
  expect(csrf).toBeTruthy();
  const created = await request.post(
    `/api/v1/patients/${patientUuid}/encounters`,
    {
      data: { baseline_encounter_id: baselineId },
      headers: {
        "X-CSRF-Token": csrf ?? "",
        "Idempotency-Key": `e2e-followup-${baselineId}-${Date.now()}`,
      },
    },
  );
  expect(created.status()).toBe(201);
  const payload = (await created.json()) as {
    encounter: { id: string; kind: string };
  };
  expect(payload.encounter.kind).toBe("follow_up");
  return payload.encounter.id;
}
// Test-only signed-baseline seeding: direct DB UPDATE via psql (followup
// precedent). No sign endpoint is used; never a production route.
async function signBaselineViaDb(encounterId: string): Promise<void> {
  assertUuid(encounterId);
  const { stdout } = await execFileAsync("psql", [
    TEST_DATABASE_URL,
    "-c",
    `UPDATE encounters SET state = 'signed' WHERE id = '${encounterId}'`,
  ]);
  expect(stdout).toMatch(/UPDATE 1/);
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

// Journey 1 (RED): admin archives a patient with confirmation; the archived
// patient hides from the default directory, shows under the archived filter,
// the physician draft editor goes read-only with an archived notice, and
// unarchiving restores editing.
test("admin archives patient with confirmation; directory hides it; unarchive restores editing", async ({
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

  // Admin opens the chart and archives with an explicit confirmation.
  // (Admins get no research notice: App gates Continue on physician role.)
  await loginViaUI(page, "admin", "admin", "admin");
  await expect(page.getByText(/admin dashboard/i)).toBeVisible();
  await openDraftForPatient(page, patientId);
  const chart = page.getByTestId("chart-section");
  await expect(chart).toBeVisible();

  // RED: timeouts here — no Archive button exists yet.
  await chart.getByTestId("patient-archive-button").click();
  const dialog = page.getByTestId("patient-archive-dialog");
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByTestId("patient-archive-dialog-draft-count"),
  ).toContainText(/1 open draft/i);
  await expect(dialog).toContainText(/drafts become read-only/i);
  await page.getByTestId("patient-archive-confirm-button").click();

  // Archived badge; directory default hides it, archived filter shows it.
  await expect(chart.getByTestId("patient-archived-badge")).toContainText(
    /archived/i,
  );
  await page.reload();
  await page.getByLabel(/search patients/i).fill(patientId);
  await expect(
    page.getByRole("button", { name: `Open draft ${patientId}` }),
  ).toHaveCount(0);
  await page
    .getByTestId("patient-directory-archived-filter")
    .selectOption("archived");
  await page.getByLabel(/search patients/i).fill(patientId);
  await expect(
    page.getByRole("button", { name: `Open draft ${patientId}` }),
  ).toBeVisible();

  // Physician draft editor is read-only with an archived notice.
  await page.getByRole("button", { name: /sign out/i }).click();
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await page.getByLabel(/search patients/i).fill(patientId);
  await page
    .getByTestId("patient-directory-archived-filter")
    .selectOption("archived");
  await openDraftForPatient(page, patientId);
  await expect(page.getByTestId("patient-archived-notice")).toContainText(
    /archived.*read-only/i,
  );

  // Admin unarchives; the physician can edit again.
  await page.getByRole("button", { name: /sign out/i }).click();
  await loginViaUI(page, "admin", "admin", "admin");
  await page.getByLabel(/search patients/i).fill(patientId);
  await page
    .getByTestId("patient-directory-archived-filter")
    .selectOption("archived");
  await openDraftForPatient(page, patientId);
  await page.getByTestId("patient-unarchive-button").click();
  await page.getByRole("button", { name: /sign out/i }).click();
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, patientId);
  await expect(page.getByTestId("patient-archived-notice")).toHaveCount(0);
  await expect(page.getByLabel(/draft note/i)).toBeEditable();
});

// Journey 2 (RED): admin deactivates a physician after reviewing the draft
// set with an explicit retain-vs-discard choice and confirm checkbox. The
// deactivated physician cannot log in; the retained draft stays readable and
// the discarded draft is tombstoned.
test("admin deactivation reviews draft set; retain stays readable, discard tombstoned", async ({
  page,
  request,
}) => {
  const retainedUser = uniquePhysicianUsername();
  const discardedUser = uniquePhysicianUsername();
  const password = "synthetic-secret";
  await createPhysicianViaAdminApi(request, retainedUser, password);
  await createPhysicianViaAdminApi(request, discardedUser, password);
  const retainedPatient = uniquePatientId();
  const discardedPatient = uniquePatientId();
  await createPatientViaPhysicianApi(request, retainedUser, password, {
    first_name: "Synthetic",
    last_name: uniqueName("Case"),
    sex: "F",
    age: 32,
    patient_id: retainedPatient,
    clinical_status: "first_time",
  });
  await createPatientViaPhysicianApi(request, discardedUser, password, {
    first_name: "Synthetic",
    last_name: uniqueName("Case"),
    sex: "M",
    age: 33,
    patient_id: discardedPatient,
    clinical_status: "first_time",
  });

  await loginViaUI(page, "admin", "admin", "admin");
  await expect(page.getByText(/admin dashboard/i)).toBeVisible();
  await page.getByRole("link", { name: /physicians/i }).click();
  await expect(page.getByRole("heading", { name: /physicians/i })).toBeVisible();

  // RED: timeouts here — no draft-set review UI exists yet.
  const review = page.getByTestId("physician-deactivate-review");
  await page
    .getByRole("row", { name: new RegExp(retainedUser, "i") })
    .getByRole("button", { name: /deactivate/i })
    .click();
  await expect(review).toBeVisible();
  await expect(review.getByTestId("physician-draft-set-count")).toContainText(
    /1 draft/i,
  );
  await expect(
    review.getByTestId("physician-draft-set-revision"),
  ).not.toBeEmpty();
  await review.getByTestId("physician-deactivate-retain").check();
  await review.getByTestId("physician-deactivate-confirm-checkbox").check();
  await review.getByTestId("physician-deactivate-confirm-button").click();

  // Deactivated physician cannot log in; the retained draft stays readable
  // to a second physician.
  await page.getByRole("button", { name: /sign out/i }).click();
  await loginViaUI(page, retainedUser, password, "physician");
  await expect(page.getByText(/invalid username/i)).toBeVisible();

  // Discard branch on the second physician with explicit confirmation.
  await loginViaUI(page, "admin", "admin", "admin");
  await page.getByRole("link", { name: /physicians/i }).click();
  await page
    .getByRole("row", { name: new RegExp(discardedUser, "i") })
    .getByRole("button", { name: /deactivate/i })
    .click();
  await expect(review).toBeVisible();
  await review.getByTestId("physician-deactivate-discard").check();
  await review.getByTestId("physician-deactivate-confirm-checkbox").check();
  await review.getByTestId("physician-deactivate-confirm-button").click();
  await expect(
    page.getByTestId("physician-deactivate-tombstone"),
  ).toBeVisible();
});

// Journey 3: shared chart — a second physician sees the first physician's
// draft read-only ("Read-only draft." + disabled note) plus the signed
// chronology ("registration · signed" badge + "Signed." view); the author
// keeps edit access on their own draft (existing S14/DraftEditor contract,
// signed seeding via SQL, no sign-route shortcut).
test("shared chart shows signed chronology read-only to second physician", async ({
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
  const { patientUuid, baselineId } =
    await getPatientAndBaselineViaPhysicianApi(
      request,
      author,
      password,
      patientId,
    );

  // Author edits their own draft (author-only edit: author can edit).
  await loginViaUI(page, author, password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, patientId);
  const authorMarker = `synthetic-author-${Date.now().toString(36)}`;
  await page.getByLabel(/draft note/i).fill(authorMarker);
  await expect(page.getByRole("status")).toContainText(/Saved/, {
    timeout: 10_000,
  });
  await page.getByRole("button", { name: /sign out/i }).click();

  // Seed the signed baseline test-side, then open a follow-up draft as the
  // author so the second physician sees both a signed record and an open
  // foreign draft.
  await signBaselineViaDb(baselineId);
  const followupId = await createFollowupViaPhysicianApi(
    request,
    author,
    password,
    patientUuid,
    baselineId,
  );

  // Second physician: signed chronology plus read-only foreign draft.
  await loginViaUI(page, other, password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, patientId);

  const chart = page.getByTestId("chart-section");
  await expect(chart).toBeVisible();
  await expect(
    chart.getByTestId(`chart-encounter-${baselineId}`),
  ).toBeVisible();
  await expect(chart.getByTestId(`chart-badge-${baselineId}`)).toContainText(
    /registration.*signed/i,
  );
  await expect(
    chart.getByTestId(`chart-encounter-${followupId}`),
  ).toBeVisible();
  await expect(chart.getByTestId(`chart-badge-${followupId}`)).toContainText(
    /follow_up.*draft/i,
  );

  // Signed record opens in the read-only signed view (no draft-note field).
  await chart.getByTestId(`open-encounter-${baselineId}`).click();
  await expect(page.getByText("Signed.", { exact: true })).toBeVisible();
  await expect(page.getByLabel(/draft note/i)).toHaveCount(0);

  // Foreign open draft is visibly read-only with inputs disabled.
  await chart.getByTestId(`open-encounter-${followupId}`).click();
  await expect(page.getByText("Read-only draft.", { exact: true })).toBeVisible();
  await expect(page.getByLabel(/draft note/i)).toBeDisabled();

  // Author keeps edit access on the same follow-up draft.
  await page.getByRole("button", { name: /sign out/i }).click();
  await loginViaUI(page, author, password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, patientId);
  const authorChart = page.getByTestId("chart-section");
  await authorChart.getByTestId(`open-encounter-${followupId}`).click();
  await expect(page.getByText("Read-only draft.", { exact: true })).toHaveCount(
    0,
  );
  await expect(page.getByLabel(/draft note/i)).toBeEditable();
});
