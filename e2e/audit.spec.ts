import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

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
      "Idempotency-Key": `e2e-audit-${username}-${Date.now()}`,
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
  await expect(page.getByText(RESEARCH_NOTICE, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();
}

async function gotoAudit(page: Page): Promise<void> {
  const link = page.getByRole("link", { name: /^audit$/i });
  if ((await link.count()) > 0) {
    await link.first().click();
  } else {
    await page.goto("/audit");
  }
  await expect(page.getByTestId("audit-section")).toBeVisible({
    timeout: 10_000,
  });
}

test.describe.serial("audit trail (admin only)", () => {
  test("admin sees physician.create with actor/target/request-id correlation", async ({
    page,
    request,
  }) => {
    const username = uniqueUsername("e2eaudit");
    await createPhysicianViaAdminApi(request, username, "synthetic-secret");
    await loginViaUI(page, "admin", "admin", "admin");
    await gotoAudit(page);

    await page.getByTestId("audit-filter-target").fill(username);
    await page.getByTestId("audit-apply").click();
    const table = page.getByTestId("audit-table");
    await expect(table).toContainText("physician.create", { timeout: 10_000 });
    await expect(table).toContainText(username);
    await expect(table).toContainText("admin");

    const row = page.getByTestId("audit-row").first();
    const rowRequest =
      ((await row.getByTestId("audit-request-id").textContent()) ?? "").trim();
    expect(rowRequest.length).toBeGreaterThan(0);

    await row.click();
    const detail = page.getByTestId("audit-detail");
    await expect(detail).toBeVisible({ timeout: 10_000 });
    await expect(detail).toContainText("physician.create");
    await expect(detail).toContainText(username);
    await expect(detail).toContainText(rowRequest);
    await expect(page.getByTestId("audit-detail-time")).toContainText(
      /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/,
    );
  });

  test("physician has no audit navigation and direct access is denied", async ({
    page,
    request,
  }) => {
    const username = uniqueUsername("e2eauditdoc");
    await createPhysicianViaAdminApi(request, username, "synthetic-secret");
    await loginViaUI(page, username, "synthetic-secret", "physician");
    await dismissResearchNotice(page);
    await expect(page.getByText(/physician dashboard/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /^audit$/i })).toHaveCount(0);
    await page.goto("/audit");
    await expect(page.getByText("Access denied.", { exact: true })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByTestId("audit-section")).toHaveCount(0);
  });

  test("admin operation filter narrows the table", async ({
    page,
    request,
  }) => {
    const username = uniqueUsername("e2eauditop");
    await createPhysicianViaAdminApi(request, username, "synthetic-secret");
    await loginViaUI(page, "admin", "admin", "admin");
    await gotoAudit(page);

    await page.getByTestId("audit-filter-target").fill(username);
    await page.getByTestId("audit-filter-operation").fill("physician.create");
    await page.getByTestId("audit-apply").click();
    await expect(page.getByTestId("audit-table")).toContainText(
      "physician.create",
      { timeout: 10_000 },
    );
    await expect(page.getByTestId("audit-table")).toContainText(username);

    await page.getByTestId("audit-filter-operation").fill("no.such.operation");
    await page.getByTestId("audit-apply").click();
    await expect(page.getByTestId("audit-empty")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByTestId("audit-row")).toHaveCount(0);
  });

  test("selecting an event shows timestamp and bounded metadata", async ({
    page,
    request,
  }) => {
    const username = uniqueUsername("e2eauditmeta");
    await createPhysicianViaAdminApi(request, username, "synthetic-secret");
    await loginViaUI(page, "admin", "admin", "admin");
    await gotoAudit(page);

    await page.getByTestId("audit-filter-target").fill(username);
    await page.getByTestId("audit-apply").click();
    await page.getByTestId("audit-row").first().click();
    const detail = page.getByTestId("audit-detail");
    await expect(detail).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("audit-detail-time")).toContainText(
      /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/,
    );
    const body = page.getByTestId("audit-detail-body");
    await expect(body).toBeVisible();
    const text = (await body.textContent()) ?? "";
    // Client-side ~8 KiB bound (plus a small note allowance).
    expect(text.length).toBeLessThan(9216);
  });
});
