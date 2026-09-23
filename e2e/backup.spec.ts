import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// S54 admin backup UI (T9). SYNTHETIC CREDENTIALS ONLY.
// Frontend contract the implementer builds to:
// - nav link "Backups" (admin only)
// - backups-section: admin page wrapper
// - backups-create: "Create backup" button
// - backups-status: job progress text (queued/running -> succeeded)
// - backups-error: role=alert failure text
// - backups-download: anchor to the download endpoint with `download`
// - backups-manifest: summary block (backup id, created_at, table/file counts)

function uniqueUsername(prefix: string): string {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return `${prefix}${suffix}`.toLowerCase();
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
      "Idempotency-Key": `e2e-backup-${username}-${Date.now()}`,
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

/** Wait for either job success or a visible error (e.g. 429 slot busy). */
async function settle(page: Page): Promise<"succeeded" | "error"> {
  await page.waitForFunction(
    () => {
      const status =
        document
          .querySelector('[data-testid="backups-status"]')
          ?.textContent?.trim() ?? "";
      const error =
        document
          .querySelector('[data-testid="backups-error"]')
          ?.textContent?.trim() ?? "";
      return /succeeded/i.test(status) || error !== "";
    },
    { timeout: 20_000 },
  );
  const status =
    (await page.getByTestId("backups-status").textContent()) ?? "";
  return /succeeded/i.test(status) ? "succeeded" : "error";
}

test.describe.serial("admin backups", () => {
  test("admin creates a backup, polls to succeeded, sees download + manifest", async ({
    page,
  }) => {
    await loginViaUI(page, "admin", "admin", "admin");
    await gotoBackups(page);

    // The backend admits a single concurrent build (HTTP 429 otherwise), and
    // chromium/firefox run this journey in parallel. A rejection carries no
    // job id and leaves no live job (jobId stays null), so retrying with a
    // fresh Idempotency-Key is safe; a live job never shows the error slot,
    // so it is never abandoned by a retry.
    await page.getByTestId("backups-create").click();
    for (let attempt = 0; attempt < 4; attempt++) {
      const outcome = await settle(page);
      if (outcome === "succeeded") {
        break;
      }
      if (attempt === 3) {
        throw new Error("backup did not succeed after 4 attempts");
      }
      await page.getByTestId("backups-create").click();
    }

    const download = page.getByTestId("backups-download");
    await expect(download).toBeVisible({ timeout: 10_000 });
    const href = await download.getAttribute("href");
    expect(href).toMatch(/\/api\/v1\/backups\/.+\/download/);
    expect(await download.getAttribute("download")).not.toBeNull();

    const manifest = page.getByTestId("backups-manifest");
    await expect(manifest).toBeVisible({ timeout: 10_000 });
    await expect(manifest).toContainText(/backup/i);
    await expect(manifest).toContainText(/created_at|timestamp/i);
    await expect(manifest).toContainText(/tables|files|rows|checksum|sha256/i);
  });

  test("physician has no backups navigation and direct access is denied", async ({
    page,
    request,
  }) => {
    const username = uniqueUsername("e2ebackupdoc");
    await createPhysicianViaAdminApi(request, username, "synthetic-secret");
    await loginViaUI(page, username, "synthetic-secret", "physician");
    await expect(
      page.getByText(
        "This is a research app and is not intended to be used as the sole basis for treating patients.",
        { exact: true },
      ),
    ).toBeVisible();
    await page.getByRole("button", { name: /continue/i }).click();
    await expect(page.getByText(/physician dashboard/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /^backups$/i })).toHaveCount(0);
    await page.goto("/backups");
    await expect(page.getByText("Access denied.", { exact: true })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByTestId("backups-section")).toHaveCount(0);
  });
});
