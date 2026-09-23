import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const execFileAsync = promisify(execFile);

// S53 e2e — printable patient report + admin CSV exports (T9).
// SYNTHETIC FIXTURES ONLY. Seams: T1 (backend reporting routes, green) and
// T9 (this spec). No PDF libraries, no LLM prose, no backend changes.
//
// Seeding (test-only, psql precedent follows e2e/followup.spec.ts):
// signBaselineViaDb marks the registration draft signed with a direct DB
// UPDATE (no sign-route shortcut); the follow-up draft is created through the
// real product API; the malicious note is posted through the real notes API.
// Malicious payload is inert: the server escapes it and the UI embeds the
// report only in a sandboxed srcdoc iframe (never dangerouslySetInnerHTML).
//
// Frontend contract (stable selectors the S53 implementer builds to):
// - print-report-button: "Print report" on the chart (physician + admin)
// - print-report: printable section wrapping the report
// - print-research-notice: exact research notice as plain JSX text
// - print-report-frame: sandboxed srcdoc iframe carrying the escaped report
// - print-report-print: window.print() button
// - export-patients-csv / export-physicians-csv: admin-only directory buttons
// - export-text-import-note: spreadsheet text-import guidance (column as text)
// - export-status: "Export ready: <file>" confirmation

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

function uniqueMarker(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
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

async function physicianLoginViaApi(
  request: APIRequestContext,
  username: string,
  password: string,
): Promise<string> {
  const physicianLogin = await request.post("/api/v1/auth/login", {
    data: { username, password, role: "physician" },
  });
  expect(physicianLogin.ok()).toBeTruthy();
  const storage = await request.storageState();
  const csrf = storage.cookies.find((c) => c.name === "xinsight_csrf")?.value;
  expect(csrf).toBeTruthy();
  return csrf ?? "";
}

async function createPatientViaPhysicianApi(
  request: APIRequestContext,
  username: string,
  password: string,
  patient: Record<string, string | number>,
): Promise<void> {
  const csrf = await physicianLoginViaApi(request, username, password);
  const created = await request.post("/api/v1/patients", {
    data: patient,
    headers: {
      "X-CSRF-Token": csrf,
      "Idempotency-Key": `e2e-patient-${patient.patient_id}-${Date.now()}`,
    },
  });
  expect(created.status()).toBe(201);
}

async function getPatientAndBaselineViaPhysicianApi(
  request: APIRequestContext,
  username: string,
  password: string,
  patientIdText: string,
): Promise<{ patientUuid: string; baselineId: string }> {
  await physicianLoginViaApi(request, username, password);
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
  assertUuid(patient?.id ?? "");
  assertUuid(baseline?.id ?? "");
  return { patientUuid: patient?.id ?? "", baselineId: baseline?.id ?? "" };
}

async function addNoteViaPhysicianApi(
  request: APIRequestContext,
  username: string,
  password: string,
  encounterId: string,
  text: string,
): Promise<void> {
  const csrf = await physicianLoginViaApi(request, username, password);
  const created = await request.post(
    `/api/v1/encounters/${encounterId}/notes`,
    {
      data: { page: "plan", text },
      headers: {
        "X-CSRF-Token": csrf,
        "Idempotency-Key": `e2e-note-${Date.now()}-${Math.floor(Math.random() * 1e9)}`,
      },
    },
  );
  expect(created.status()).toBe(201);
}

async function createFollowupViaPhysicianApi(
  request: APIRequestContext,
  username: string,
  password: string,
  patientUuid: string,
  baselineId: string,
): Promise<string> {
  const csrf = await physicianLoginViaApi(request, username, password);
  const created = await request.post(
    `/api/v1/patients/${patientUuid}/encounters`,
    {
      data: { baseline_encounter_id: baselineId },
      headers: {
        "X-CSRF-Token": csrf,
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

// Journey (a): physician print view shows the multi-encounter chronology with
// draft/signed/current/historical labels plus the research notice; malicious
// note text stays inert (no script execution, escaped text visible).
test("physician print view shows multi-encounter chronology; malicious text inert", async ({
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
  const { patientUuid, baselineId } =
    await getPatientAndBaselineViaPhysicianApi(
      request,
      username,
      password,
      patientId,
    );

  // Malicious note through the real notes API; the server escapes it and the
  // UI embeds the report only in a sandboxed iframe.
  const xssMarker = uniqueMarker("SYN-REPORT-XSS-S53");
  const probe = "__rpt_xss_s53";
  await addNoteViaPhysicianApi(
    request,
    username,
    password,
    baselineId,
    `<script>window.${probe}='pwned'</script> ${xssMarker}`,
  );

  // Multi-encounter fixture: signed baseline + open follow-up draft.
  await signBaselineViaDb(baselineId);
  const followupId = await createFollowupViaPhysicianApi(
    request,
    username,
    password,
    patientUuid,
    baselineId,
  );
  assertUuid(followupId);

  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, patientId);

  await page.getByTestId("print-report-button").click();
  const report = page.getByTestId("print-report");
  await expect(report).toBeVisible();
  await expect(page.getByTestId("print-research-notice")).toContainText(
    RESEARCH_NOTICE,
  );

  const frame = page.frameLocator('[data-testid="print-report-frame"]');
  await expect(frame.getByText(/Encounter chronology/)).toBeVisible();
  await expect(frame.getByText(/States present/)).toContainText(/draft/);
  await expect(frame.getByText(/States present/)).toContainText(/signed/);
  await expect(frame.getByText(/current/).first()).toBeVisible();
  await expect(frame.getByText(/historical/).first()).toBeVisible();
  await expect(frame.getByText(RESEARCH_NOTICE)).toBeVisible();
  // Escaped malicious text renders as literal text, never as markup.
  await expect(frame.getByText(xssMarker)).toBeVisible();
  await expect(frame.getByText("<script>", { exact: false })).toBeVisible();
  await expect(frame.locator("script")).toHaveCount(0);

  // No script executed in the page or the report frame.
  expect(await page.evaluate((name) => (window as unknown as Record<string, unknown>)[name], probe)).toBeUndefined();
});

// Journey (b): admin sees and downloads both CSVs (200 + text/csv); the
// physician sees no list-export buttons and the server denies them with 403.
test("admin exports CSVs; physician export buttons absent and endpoints deny", async ({
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
    sex: "M",
    age: 40,
    patient_id: patientId,
    clinical_status: "established",
  });

  // Admin: buttons visible with text-import guidance; endpoints serve CSV.
  await loginViaUI(page, "admin", "admin", "admin");
  await expect(page.getByText(/admin dashboard/i)).toBeVisible();
  await openDraftForPatient(page, patientId);
  await expect(page.getByTestId("export-patients-csv")).toBeVisible();
  await expect(page.getByTestId("export-physicians-csv")).toBeVisible();
  await expect(page.getByTestId("export-text-import-note")).toContainText(
    /text import.*text/i,
  );

  const patientsCsv = await page.evaluate(async () => {
    const response = await fetch("/api/v1/exports/patients.csv", {
      credentials: "include",
    });
    return {
      status: response.status,
      contentType: response.headers.get("content-type") ?? "",
      body: await response.text(),
    };
  });
  expect(patientsCsv.status).toBe(200);
  expect(patientsCsv.contentType).toContain("text/csv");
  expect(patientsCsv.body.split("\n")[0]).toContain("patient_id");

  const physiciansCsv = await page.evaluate(async () => {
    const response = await fetch("/api/v1/exports/physicians.csv", {
      credentials: "include",
    });
    return {
      status: response.status,
      contentType: response.headers.get("content-type") ?? "",
      body: await response.text(),
    };
  });
  expect(physiciansCsv.status).toBe(200);
  expect(physiciansCsv.contentType).toContain("text/csv");
  expect(physiciansCsv.body.split("\n")[0]).toContain("username");

  // Button click triggers the authenticated download path with confirmation.
  await page.getByTestId("export-patients-csv").click();
  await expect(page.getByTestId("export-status")).toContainText(
    /Export ready: patients\.csv/,
  );
  await page.getByTestId("export-physicians-csv").click();
  await expect(page.getByTestId("export-status")).toContainText(
    /Export ready: physicians\.csv/,
  );

  // Physician: no list-export buttons; the server denies both endpoints.
  await page.getByRole("button", { name: /sign out/i }).click();
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, patientId);
  await expect(page.getByTestId("export-patients-csv")).toHaveCount(0);
  await expect(page.getByTestId("export-physicians-csv")).toHaveCount(0);
  const deniedPatients = await page.evaluate(async () => {
    const response = await fetch("/api/v1/exports/patients.csv", {
      credentials: "include",
    });
    return response.status;
  });
  expect(deniedPatients).toBe(403);
  const deniedPhysicians = await page.evaluate(async () => {
    const response = await fetch("/api/v1/exports/physicians.csv", {
      credentials: "include",
    });
    return response.status;
  });
  expect(deniedPhysicians).toBe(403);
  expect(request).toBeTruthy();
});

// Journey (c): print CSS carries page-break rules without inverting, in both
// themes. Stylesheet/DOM inspection (deterministic across browsers); manual
// print-preview verification note: open the print view, press the Print
// button, and confirm in the preview that sections avoid inner breaks, the
// report frame starts on a fresh page, and the research notice stays visible.
test("print CSS carries page-break rules in both themes without inverting", async ({
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
    age: 35,
    patient_id: patientId,
    clinical_status: "first_time",
  });

  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await openDraftForPatient(page, patientId);
  await page.getByTestId("print-report-button").click();
  await expect(page.getByTestId("print-report")).toBeVisible();

  async function printCssSummary(): Promise<{
    hasInsideAvoid: boolean;
    hasBefore: boolean;
    hasInvert: boolean;
    frameFilter: string;
  }> {
    return page.evaluate(() => {
      let css = "";
      for (const sheet of Array.from(document.styleSheets)) {
        let rules: CSSRuleList | null = null;
        try {
          rules = sheet.cssRules;
        } catch {
          continue;
        }
        if (!rules) {
          continue;
        }
        for (const rule of Array.from(rules)) {
          css += `${rule.cssText}\n`;
        }
      }
      const frame = document.querySelector('[data-testid="print-report-frame"]');
      const frameFilter =
        frame !== null ? getComputedStyle(frame).filter : "missing";
      // Browsers serialize authored page-break-* rules to the canonical
      // break-* properties (e.g. page-break-before: always becomes
      // break-before: page), so both serializations are accepted.
      return {
        hasInsideAvoid: /(page-break-inside|break-inside)\s*:\s*avoid/.test(css),
        hasBefore: /(page-break-before|break-before)\s*:/.test(css),
        hasInvert: /invert\s*\(/.test(css),
        frameFilter,
      };
    });
  }

  const light = await printCssSummary();
  expect(light.hasInsideAvoid).toBe(true);
  expect(light.hasBefore).toBe(true);
  expect(light.hasInvert).toBe(false);
  expect(light.frameFilter).toBe("none");

  // Dark theme: the printable view stays readable with no inversion filter.
  const toggle = page.getByRole("button", { name: /dark|light|theme/i });
  if ((await toggle.count()) > 0) {
    await toggle.first().click();
    await expect(page.getByTestId("print-report")).toBeVisible();
    const dark = await printCssSummary();
    expect(dark.hasInsideAvoid).toBe(true);
    expect(dark.hasBefore).toBe(true);
    expect(dark.hasInvert).toBe(false);
    expect(dark.frameFilter).toBe("none");
  }
});
