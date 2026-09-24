import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

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
      "Idempotency-Key": `e2e-ops-${username}-${Date.now()}`,
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

async function dismissResearchNotice(page: Page): Promise<void> {
  const notice = page.getByText(
    "This is a research app and is not intended to be used as the sole basis for treating patients.",
    { exact: true },
  );
  await expect(notice).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();
}

async function gotoOps(page: Page): Promise<void> {
  const link = page.getByRole("link", { name: /ops status/i });
  if ((await link.count()) > 0) {
    await link.first().click();
  } else {
    await page.goto("/ops");
  }
  await expect(page.getByTestId("ops-section")).toBeVisible({
    timeout: 10_000,
  });
}

test.describe.serial("ops status (admin only)", () => {
  test("admin sees safe metrics and text alert labels", async ({ page }) => {
    await loginViaUI(page, "admin", "admin", "admin");
    await gotoOps(page);

    const section = page.getByTestId("ops-section");
    await expect(section).toContainText(/no clinical records or secrets/i);

    await expect(page.getByTestId("ops-queue-age")).toContainText(
      /(no queued work|\d+ seconds)/i,
      { timeout: 10_000 },
    );
    await expect(page.getByTestId("ops-heartbeat-missing")).toContainText(
      /(missing|seen)/i,
    );
    await expect(page.getByTestId("ops-heartbeat-age")).toContainText(
      /(no heartbeat recorded|\d+ seconds)/i,
    );
    await expect(page.getByTestId("ops-provider-retries")).toContainText(
      /^\d+$/,
    );
    await expect(page.getByTestId("ops-provider-auth-failures")).toContainText(
      /^\d+$/,
    );
    await expect(page.getByTestId("ops-inference-rejections")).toContainText(
      /^\d+$/,
    );
    await expect(page.getByTestId("ops-disk-percent")).toContainText(
      /^\d+(\.\d+)?%$/,
    );
    await expect(page.getByTestId("ops-backup-status")).not.toBeEmpty();
    await expect(page.getByTestId("ops-save-failures")).toContainText(/^\d+$/);

    for (const alert of [
      "ops-alert-heartbeat",
      "ops-alert-queue",
      "ops-alert-auth",
      "ops-alert-disk",
    ]) {
      await expect(page.getByTestId(alert)).toContainText(
        /(normal|attention needed)/i,
      );
    }

    // Safe payload: no secret material is rendered.
    await expect(section).not.toContainText(/api_key/i);

    await page.getByTestId("ops-refresh").click();
    await expect(page.getByTestId("ops-queue-age")).toBeVisible({
      timeout: 10_000,
    });
  });

  test("physician has no ops navigation and direct access is denied", async ({
    page,
    request,
  }) => {
    const username = uniqueUsername("e2eopsdoc");
    await createPhysicianViaAdminApi(request, username, "synthetic-secret");
    await loginViaUI(page, username, "synthetic-secret", "physician");
    await dismissResearchNotice(page);
    await expect(page.getByText(/physician dashboard/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /ops status/i })).toHaveCount(
      0,
    );
    await page.goto("/ops");
    await expect(page.getByText("Access denied.", { exact: true })).toBeVisible(
      {
        timeout: 10_000,
      },
    );
    await expect(page.getByTestId("ops-section")).toHaveCount(0);
  });
});
