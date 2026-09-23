import { createHash, randomBytes } from "node:crypto";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// S55 staged-restore validation UI (T9). SYNTHETIC CREDENTIALS ONLY.
// Frontend contract the implementer builds to:
// - restores-section: "Staged restores" subsection inside the admin Backups page
// - restores-file: file input (accept .zip), restores-validate: validate button
// - restores-status: idle/validating/staged/failed text
// - restores-error: role=alert failure text (422/409/network)
// - restores-report: success block (backup id, timestamps, schema revision,
//   table/file counts, checksums, live-vs-staged impact)
// - restores-digest: 64-hex confirmation digest span
// - restores-key-note: key re-entry consequences note
// - restores-commit: DISABLED button, never fires a request (S56 owns commit)

const SYNTHETIC_PASSWORD = "synthetic-secret";

function uniqueUsername(prefix: string): string {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return `${prefix}${suffix}`.toLowerCase();
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
      "Idempotency-Key": `e2e-restore-${username}-${Date.now()}`,
    },
  });
  expect(created.status()).toBe(201);
}

/** Create a backup via the admin API (retrying the single-build 429 slot)
 * and return the downloaded archive bytes. Validation itself is synchronous
 * (no slot), so only this backup step retries. */
async function createBackupAndDownload(
  request: APIRequestContext,
): Promise<Buffer> {
  const adminLogin = await request.post("/api/v1/auth/login", {
    data: { username: "admin", password: "admin", role: "admin" },
  });
  expect(adminLogin.ok()).toBeTruthy();
  const storage = await request.storageState();
  const csrf = storage.cookies.find((c) => c.name === "xinsight_csrf")?.value;
  expect(csrf).toBeTruthy();

  let jobId = "";
  for (let attempt = 0; attempt < 8; attempt++) {
    const created = await request.post("/api/v1/backups", {
      data: {},
      headers: {
        "X-CSRF-Token": csrf ?? "",
        "Idempotency-Key": `e2e-restore-backup-${Date.now()}-${attempt}-${randomBytes(4).toString("hex")}`,
      },
    });
    if (created.status() === 429) {
      await new Promise((resolve) => setTimeout(resolve, 5000));
      continue;
    }
    expect(created.status()).toBe(202);
    jobId = ((await created.json()) as { job_id: string }).job_id;
    break;
  }
  expect(jobId).not.toBe("");

  const deadline = Date.now() + 60_000;
  for (;;) {
    const poll = await request.get(`/api/v1/backups/${jobId}`);
    expect(poll.ok()).toBeTruthy();
    const job = (await poll.json()) as { status: string; error?: string };
    if (job.status === "succeeded") {
      break;
    }
    expect(job.status).not.toBe("failed");
    expect(Date.now()).toBeLessThan(deadline);
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  const download = await request.get(`/api/v1/backups/${jobId}/download`);
  expect(download.ok()).toBeTruthy();
  return Buffer.from(await download.body());
}

function writeTmpZip(bytes: Buffer, prefix: string): string {
  const dir = mkdtempSync(join(tmpdir(), "e2e-restore-"));
  const path = join(dir, `${prefix}-${randomBytes(4).toString("hex")}.zip`);
  writeFileSync(path, bytes);
  return path;
}

test.describe.serial("admin staged restores", () => {
  test("valid archive stages and shows digest, key note, disabled commit", async ({
    page,
    request,
  }) => {
    const archive = await createBackupAndDownload(request);
    expect(createHash("sha256").update(archive).digest("hex")).toMatch(
      /^[0-9a-f]{64}$/,
    );
    const zipPath = writeTmpZip(archive, "valid");

    await loginViaUI(page, "admin", "admin", "admin");
    await gotoBackups(page);

    await page.getByTestId("restores-file").setInputFiles(zipPath);
    await page.getByTestId("restores-validate").click();

    const report = page.getByTestId("restores-report");
    await expect(report).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("restores-digest")).toHaveText(
      /^[0-9a-f]{64}$/,
    );
    await expect(page.getByTestId("restores-key-note")).toContainText(
      /re-?entry/i,
    );
    const commit = page.getByTestId("restores-commit");
    await expect(commit).toBeVisible();
    await expect(commit).toBeDisabled();
  });

  test("corrupt archive shows an alert and leaves live data readable", async ({
    page,
    request,
  }) => {
    const archive = await createBackupAndDownload(request);
    const corrupt = Buffer.from(archive);
    corrupt[Math.floor(corrupt.length / 2)] ^= 0xff;
    const zipPath = writeTmpZip(corrupt, "corrupt");

    await loginViaUI(page, "admin", "admin", "admin");
    await gotoBackups(page);

    await page.getByTestId("restores-file").setInputFiles(zipPath);
    await page.getByTestId("restores-validate").click();

    await expect(page.getByTestId("restores-error")).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByTestId("restores-report")).toHaveCount(0);
    await expect(page.getByTestId("restores-digest")).toHaveCount(0);
    const commit = page.getByTestId("restores-commit");
    if ((await commit.count()) > 0) {
      await expect(commit).toBeDisabled();
    }

    await page.goto("/");
    await expect(page.getByText(/dashboard|research app/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("physician sees access denied and no restores section", async ({
    page,
    request,
  }) => {
    const username = uniqueUsername("e2erestoredoc");
    await createPhysicianViaAdminApi(request, username, SYNTHETIC_PASSWORD);
    await loginViaUI(page, username, SYNTHETIC_PASSWORD, "physician");
    await expect(
      page.getByText(
        "This is a research app and is not intended to be used as the sole basis for treating patients.",
        { exact: true },
      ),
    ).toBeVisible();
    await page.getByRole("button", { name: /continue/i }).click();
    await expect(page.getByText(/physician dashboard/i)).toBeVisible();
    await page.goto("/backups");
    await expect(page.getByText("Access denied.", { exact: true })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByTestId("restores-section")).toHaveCount(0);
  });
});
