import { randomBytes } from "node:crypto";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// S56 digest-gated restore commit + reopen (T9). SYNTHETIC CREDENTIALS ONLY.
// Destructive drill runs only against the disposable xinsight_test database
// with unique synthetic ids. Failure-injection rollback is covered by backend
// tests, never here.
// Frontend contract:
// - restores-confirm: text input, label "Confirmation digest", placeholder =
//   staged digest; restores-commit enabled only on exact match, never fires
//   otherwise (no auto-commit)
// - restores-commit-status: committing/committed/failed text status
// - restores-commit-report + restores-pre-backup on success
// - restores-maintenance: role=alert banner while maintenance holds writes
// - restores-confirm-error: field error for stale digests (409)
// - restores-commit-error: role=alert for commit failures (e.g. rolled back)
// - restores-reopen: reopen button; restores-reopen-status shows
//   reopened vs reopen failed (maintenance stays active)

test.describe.configure({ timeout: 180_000, mode: "serial" });

/** Set by the commit journey so afterEach can best-effort clear maintenance.
 * Per-worker module state; chromium/firefox run in separate workers. */
let cleanupRestoreId: string | null = null;

test.afterEach(async ({ request }) => {
  if (cleanupRestoreId === null) {
    return;
  }
  const restoreId = cleanupRestoreId;
  cleanupRestoreId = null;
  try {
    const csrf = await adminCsrf(request);
    await request.post(`/api/v1/restores/${restoreId}/reopen`, {
      data: {},
      headers: {
        "X-CSRF-Token": csrf,
        "Idempotency-Key": `e2e-reopen-cleanup-${Date.now()}-${randomBytes(4).toString("hex")}`,
      },
    });
  } catch {
    /* best effort: never fail the run from cleanup */
  }
});

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
  await expect(page.getByText(/dashboard|research app/i).first()).toBeVisible({
    timeout: 10_000,
  });
}

async function gotoBackups(page: Page): Promise<void> {
  const link = page.getByRole("link", { name: /^backups$/i });
  if ((await link.count()) > 0) {
    await link.first().click();
  } else {
    await page.goto("/backups");
  }
  await expect(page.getByTestId("backups-section")).toBeVisible({
    timeout: 10_000,
  });
}

/** Fresh admin login on the API context (login stays available under
 * maintenance; re-login also recovers from commit session revocation). */
async function adminCsrf(request: APIRequestContext): Promise<string> {
  const login = await request.post("/api/v1/auth/login", {
    data: { username: "admin", password: "admin", role: "admin" },
  });
  expect(login.ok()).toBeTruthy();
  const storage = await request.storageState();
  const csrf = storage.cookies.find((c) => c.name === "xinsight_csrf")?.value;
  expect(csrf).toBeTruthy();
  return csrf ?? "";
}

function uniqueUsername(prefix: string): string {
  const suffix = `${Date.now().toString(36)}${randomBytes(3).toString("hex")}`.toLowerCase();
  return `${prefix}${suffix}`;
}

function uniqueLetters(prefix: string): string {
  const suffix = randomBytes(4)
    .toString("hex")
    .replace(/[0-9]/g, (d) => "abcdefghij"[Number(d)]);
  return `${prefix}${suffix}`;
}

function uniquePatientId(): string {
  return `7${randomBytes(5).toString("hex").replace(/[a-f]/g, (c) => String("abcdef".indexOf(c)))}`.slice(0, 10);
}

async function createPhysicianViaAdminApi(
  request: APIRequestContext,
  username: string,
  password: string,
): Promise<void> {
  // A peer project's commit revokes all sessions; a 401 races a fresh login,
  // so re-login and retry before failing.
  let lastStatus = 0;
  for (let attempt = 0; attempt < 3; attempt++) {
    const csrf = await adminCsrf(request);
    const created = await request.post("/api/v1/physicians", {
      data: { username, password },
      headers: {
        "X-CSRF-Token": csrf,
        "Idempotency-Key": `e2e-restore-commit-${username}-${Date.now()}-${attempt}`,
      },
    });
    lastStatus = created.status();
    if (lastStatus === 401 || lastStatus === 403) {
      continue;
    }
    expect(lastStatus).toBe(201);
    return;
  }
  throw new Error(`could not create physician (last status ${lastStatus})`);
}

async function physicianCsrf(
  request: APIRequestContext,
  username: string,
  password: string,
): Promise<string> {
  const login = await request.post("/api/v1/auth/login", {
    data: { username, password, role: "physician" },
  });
  expect(login.ok()).toBeTruthy();
  const storage = await request.storageState();
  const csrf = storage.cookies.find((c) => c.name === "xinsight_csrf")?.value;
  expect(csrf).toBeTruthy();
  return csrf ?? "";
}

async function createPatientResponse(
  request: APIRequestContext,
  username: string,
  password: string,
  patientId: string,
) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const csrf = await physicianCsrf(request, username, password);
    const response = await request.post("/api/v1/patients", {
      data: {
        first_name: uniqueLetters("Restore"),
        last_name: uniqueLetters("Commit"),
        sex: "F",
        age: 33,
        patient_id: patientId,
        clinical_status: "first_time",
      },
      headers: {
        "X-CSRF-Token": csrf,
        "Idempotency-Key": `e2e-restore-commit-${patientId}-${Date.now()}-${attempt}`,
      },
    });
    // A peer project's commit revokes all sessions; retry once with a fresh
    // login instead of failing the drill.
    if ((response.status() === 401 || response.status() === 403) && attempt < 2) {
      continue;
    }
    return response;
  }
  throw new Error("could not reach patient writes");
}

/** Refresh the page-context admin session without navigation (commit revokes
 * pre-commit sessions, so the staged UI state would be lost on re-login). */
async function reloginPageAsAdmin(page: Page): Promise<void> {
  const ok = await page.evaluate(async () => {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: "admin",
        password: "admin",
        role: "admin",
      }),
    });
    return response.ok;
  });
  expect(ok).toBeTruthy();
}

/** Create a backup via the admin API (retrying the single-build 429 slot)
 * and return the downloaded archive bytes. */
async function createBackupAndDownload(
  request: APIRequestContext,
): Promise<Buffer> {
  let csrf = await adminCsrf(request);
  let jobId = "";
  for (let attempt = 0; attempt < 10; attempt++) {
    const created = await request.post("/api/v1/backups", {
      data: {},
      headers: {
        "X-CSRF-Token": csrf,
        "Idempotency-Key": `e2e-restore-commit-backup-${Date.now()}-${attempt}-${randomBytes(4).toString("hex")}`,
      },
    });
    if (created.status() === 401 || created.status() === 403) {
      // A peer project's commit revoked our session; log in again.
      csrf = await adminCsrf(request);
      continue;
    }
    if (created.status() === 429) {
      await new Promise((resolve) => setTimeout(resolve, 5000));
      continue;
    }
    expect(created.status()).toBe(202);
    jobId = ((await created.json()) as { job_id: string }).job_id;
    break;
  }
  expect(jobId).not.toBe("");

  const deadline = Date.now() + 90_000;
  for (;;) {
    const poll = await request.get(`/api/v1/backups/${jobId}`);
    if (poll.status() === 401 || poll.status() === 403) {
      await adminCsrf(request);
      continue;
    }
    expect(poll.ok()).toBeTruthy();
    const job = (await poll.json()) as { status: string };
    if (job.status === "succeeded") {
      break;
    }
    expect(job.status).not.toBe("failed");
    expect(Date.now()).toBeLessThan(deadline);
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  for (let attempt = 0; attempt < 3; attempt++) {
    const download = await request.get(`/api/v1/backups/${jobId}/download`);
    if (download.status() === 401 || download.status() === 403) {
      await adminCsrf(request);
      continue;
    }
    expect(download.ok()).toBeTruthy();
    return Buffer.from(await download.body());
  }
  throw new Error("could not download the backup");
}

function writeTmpZip(bytes: Buffer, prefix: string): string {
  const dir = mkdtempSync(join(tmpdir(), "e2e-restore-commit-"));
  const path = join(dir, `${prefix}-${randomBytes(4).toString("hex")}.zip`);
  writeFileSync(path, bytes);
  return path;
}

async function validateArchiveViaApi(
  request: APIRequestContext,
  bytes: Buffer,
) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const csrf = await adminCsrf(request);
    const response = await request.post("/api/v1/restores/validate", {
      multipart: {
        archive: { name: "backup.zip", mimeType: "application/zip", buffer: bytes },
      },
      headers: {
        "X-CSRF-Token": csrf,
        "Idempotency-Key": `e2e-restore-commit-validate-${Date.now()}-${attempt}-${randomBytes(4).toString("hex")}`,
      },
    });
    if ((response.status() === 401 || response.status() === 403) && attempt < 2) {
      continue;
    }
    return response;
  }
  throw new Error("could not reach restore validation");
}

async function getPatientsViaPhysician(
  request: APIRequestContext,
  username: string,
  password: string,
) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const csrf = await physicianCsrf(request, username, password);
    const response = await request.get(
      `/api/v1/patients?archived=false&limit=100`,
      { headers: { "X-CSRF-Token": csrf } },
    );
    if ((response.status() === 401 || response.status() === 403) && attempt < 2) {
      continue;
    }
    return response;
  }
  throw new Error("could not read the patient directory");
}

test.describe.serial("admin restore commit", () => {
  test("digest gating, commit, maintenance notice, reopen, writes work", async ({
    page,
    request,
  }) => {
    cleanupRestoreId = null;
    const archive = await createBackupAndDownload(request);
    const zipPath = writeTmpZip(archive, "commit");

    await loginViaUI(page, "admin", "admin", "admin");
    await gotoBackups(page);
    await page.getByTestId("restores-file").setInputFiles(zipPath);
    await page.getByTestId("restores-validate").click();
    await expect(page.getByTestId("restores-report")).toBeVisible({
      timeout: 30_000,
    });
    const digest = await page.getByTestId("restores-digest").innerText();
    expect(digest).toMatch(/^[0-9a-f]{64}$/);

    // Gating: mismatched digest keeps Commit disabled with an explanation and
    // fires no request; the exact digest enables it.
    const commit = page.getByTestId("restores-commit");
    await expect(commit).toBeDisabled();
    await expect(page.getByTestId("restores-commit-status")).toHaveCount(0);
    await page.getByLabel(/confirmation digest/i).fill("0".repeat(64));
    await expect(commit).toBeDisabled();
    await expect(page.locator("#restores-commit-note")).toContainText(
      /stays disabled/i,
    );
    await expect(page.getByTestId("restores-commit-status")).toHaveCount(0);
    await expect(page.getByTestId("restores-confirm")).toHaveAttribute(
      "placeholder",
      digest,
    );
    await page.getByLabel(/confirmation digest/i).fill(digest);
    await expect(commit).toBeEnabled();

    // Commit (peer-project validation crosstalk can supersede our stage; a
    // stale rejection re-validates and retries instead of failing).
    let committedRestoreId = "";
    let preBackupId = "";
    for (let attempt = 0; attempt < 3; attempt++) {
      const responsePromise = page.waitForResponse(
        (r) =>
          r.url().includes("/api/v1/restores/commit") &&
          r.request().method() === "POST",
        { timeout: 120_000 },
      );
      await commit.click();
      const response = await responsePromise;
      if (response.status() === 202) {
        const body = (await response.json()) as {
          restore_id: string;
          pre_restore_backup_id: string | null;
        };
        committedRestoreId = body.restore_id;
        preBackupId = body.pre_restore_backup_id ?? "";
        cleanupRestoreId = committedRestoreId;
        break;
      }
      await expect(page.getByTestId("restores-confirm-error")).toBeVisible({
        timeout: 20_000,
      });
      const fieldText = await page
        .getByTestId("restores-confirm-error")
        .innerText();
      expect(fieldText).toMatch(/stale|superseded|expired|digest/i);
      if (attempt === 2) {
        throw new Error(`commit still stale after retries: ${fieldText}`);
      }
      await page.getByTestId("restores-validate").click();
      await expect(page.getByTestId("restores-report")).toBeVisible({
        timeout: 30_000,
      });
      const fresh = await page.getByTestId("restores-digest").innerText();
      expect(fresh).toMatch(/^[0-9a-f]{64}$/);
      await page.getByLabel(/confirmation digest/i).fill(fresh);
      await expect(commit).toBeEnabled();
    }
    expect(committedRestoreId).not.toBe("");
    expect(preBackupId).not.toBe("");

    // Committed report: status text, pre-restore backup id, maintenance alert.
    await expect(page.getByTestId("restores-commit-status")).toHaveText(
      /committed/i,
    );
    await expect(page.getByTestId("restores-commit-report")).toBeVisible();
    await expect(page.getByTestId("restores-pre-backup")).toHaveText(
      preBackupId,
    );
    await expect(page.getByTestId("restores-maintenance")).toBeVisible();

    // Writes are held under maintenance (a peer may have reopened first, in
    // which case the write already succeeds — still asserted below).
    const heldUser = uniqueUsername("e2eheld");
    await createPhysicianViaAdminApi(request, heldUser, "synthetic-secret");
    const heldWrite = await createPatientResponse(
      request,
      heldUser,
      "synthetic-secret",
      uniquePatientId(),
    );
    if (heldWrite.status() === 503) {
      expect((await heldWrite.json()) as { code: string }).toMatchObject({
        code: "MAINTENANCE",
      });
    } else {
      expect(heldWrite.status()).toBe(201);
    }

    // Reopen (fresh login: commit revoked pre-commit sessions), then writes
    // work again.
    await reloginPageAsAdmin(page);
    const reopen = page.getByTestId("restores-reopen");
    await expect(reopen).toBeVisible();
    await reopen.click();
    const reopened = page.getByTestId("restores-reopen-status");
    try {
      await expect(reopened).toHaveText(/reopened/i, { timeout: 60_000 });
    } catch {
      // A peer commit revoked our fresh session after re-login; retry once.
      await reloginPageAsAdmin(page);
      await reopen.click();
      await expect(reopened).toHaveText(/reopened/i, { timeout: 60_000 });
    }
    await expect(page.getByTestId("restores-maintenance")).toHaveCount(0);

    const openUser = uniqueUsername("e2eopen");
    await createPhysicianViaAdminApi(request, openUser, "synthetic-secret");
    const openPatientId = uniquePatientId();
    const openWrite = await createPatientResponse(
      request,
      openUser,
      "synthetic-secret",
      openPatientId,
    );
    expect(openWrite.status()).toBe(201);
    const directory = await getPatientsViaPhysician(request, openUser, "synthetic-secret");
    expect(directory.ok()).toBeTruthy();
    const items = ((await directory.json()) as { items: { patient_id: string }[] })
      .items;
    expect(items.some((item) => item.patient_id === openPatientId)).toBeTruthy();
    cleanupRestoreId = null;
  });

  test("stale digest commit attempt shows a field error, live data unchanged", async ({
    page,
    request,
  }) => {
    const password = "synthetic-secret";
    const physician = uniqueUsername("e2estale");
    await createPhysicianViaAdminApi(request, physician, password);
    const livePatientId = uniquePatientId();
    const liveWrite = await createPatientResponse(
      request,
      physician,
      password,
      livePatientId,
    );
    expect(liveWrite.status()).toBe(201);

    const archive = await createBackupAndDownload(request);
    const zipPath = writeTmpZip(archive, "stale");

    await loginViaUI(page, "admin", "admin", "admin");
    await gotoBackups(page);
    await page.getByTestId("restores-file").setInputFiles(zipPath);
    await page.getByTestId("restores-validate").click();
    await expect(page.getByTestId("restores-report")).toBeVisible({
      timeout: 30_000,
    });
    const digest = await page.getByTestId("restores-digest").innerText();
    expect(digest).toMatch(/^[0-9a-f]{64}$/);
    await page.getByLabel(/confirmation digest/i).fill(digest);
    const commit = page.getByTestId("restores-commit");
    await expect(commit).toBeEnabled();

    // A newer validation supersedes our staged restore, so our exact-typed
    // digest is now stale at the server.
    const supersede = await validateArchiveViaApi(request, archive);
    expect(supersede.ok()).toBeTruthy();

    const responsePromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v1/restores/commit") &&
        r.request().method() === "POST",
      { timeout: 120_000 },
    );
    await commit.click();
    const response = await responsePromise;
    expect(response.status()).toBe(409);
    await expect(page.getByTestId("restores-confirm-error")).toContainText(
      /superseded|stale|digest/i,
      { timeout: 20_000 },
    );
    await expect(page.getByTestId("restores-commit-report")).toHaveCount(0);
    await expect(page.getByTestId("restores-maintenance")).toHaveCount(0);

    // Live directory unchanged and writes never held.
    const directory = await getPatientsViaPhysician(request, physician, password);
    expect(directory.ok()).toBeTruthy();
    const items = ((await directory.json()) as { items: { patient_id: string }[] })
      .items;
    expect(items.some((item) => item.patient_id === livePatientId)).toBeTruthy();
    const followupWrite = await createPatientResponse(
      request,
      physician,
      password,
      uniquePatientId(),
    );
    expect(followupWrite.status()).toBe(201);
  });
});
