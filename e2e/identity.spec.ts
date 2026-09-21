import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

function uniquePhysicianUsername(): string {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return `e2edoc${suffix}`.toLowerCase();
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

// S05 slice-1 (T9 browser seam): role navigation entry points only.
test("admin login lands on admin dashboard", async ({ page }) => {
  await loginViaUI(page, "admin", "admin", "admin");
  await expect(page.getByText(/admin dashboard/i)).toBeVisible();
});

test("physician login shows the research warning before proceeding", async ({
  page,
  request,
}) => {
  const username = uniquePhysicianUsername();
  const password = "synthetic-secret";
  await createPhysicianViaAdminApi(request, username, password);
  await loginViaUI(page, username, password, "physician");
  await expect(page.getByText(RESEARCH_NOTICE, { exact: true })).toBeVisible();
});

test("register page directs to the administrator", async ({ page }) => {
  await page.goto("/register");
  await expect(page.getByText(/contact administrator/i)).toBeVisible();
});

// S05 slice-2 (T9 browser seam): account management through the browser only.
function uniquePassword(): string {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return `pw-${suffix}`;
}

async function dismissResearchNotice(page: Page): Promise<void> {
  await expect(page.getByText(RESEARCH_NOTICE, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();
}

test("admin creates a physician through the browser", async ({ page }) => {
  const username = uniquePhysicianUsername();
  const password = uniquePassword();
  await loginViaUI(page, "admin", "admin", "admin");
  await expect(page.getByText(/admin dashboard/i)).toBeVisible();
  await page.getByRole("link", { name: /physicians/i }).click();
  await page.getByLabel(/username/i).fill(username);
  await page.getByLabel(/password/i).fill(password);
  await page
    .getByRole("button", { name: /create physician|add physician|create/i })
    .click();
  await expect(page.getByRole("table")).toContainText(username);
  await page.context().clearCookies();
  await loginViaUI(page, username, password, "physician");
  await expect(page.getByText(RESEARCH_NOTICE, { exact: true })).toBeVisible();
});

test("physician cannot see admin navigation", async ({ page, request }) => {
  const username = uniquePhysicianUsername();
  const password = uniquePassword();
  await createPhysicianViaAdminApi(request, username, password);
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await expect(page.getByText(/physician dashboard/i)).toBeVisible();
  await expect(
    page.getByRole("link", { name: /physicians/i }),
  ).toHaveCount(0);
  await page.goto("/physicians");
  await expect(
    page.getByText(/access denied|not authorized|forbidden/i),
  ).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);
});

test("own password change through the browser", async ({ page, request }) => {
  const username = uniquePhysicianUsername();
  const oldPassword = uniquePassword();
  const newPassword = uniquePassword();
  await createPhysicianViaAdminApi(request, username, oldPassword);
  await loginViaUI(page, username, oldPassword, "physician");
  await dismissResearchNotice(page);
  await page.getByLabel(/current password/i).fill(oldPassword);
  await page.getByLabel(/new password/i).fill(newPassword);
  await page
    .getByRole("button", { name: /change password|update password/i })
    .click();
  await expect(page.getByText(/password changed/i)).toBeVisible();
  await page.context().clearCookies();
  await loginViaUI(page, username, oldPassword, "physician");
  await expect(page.getByText(/invalid/i)).toBeVisible();
  await page.context().clearCookies();
  await loginViaUI(page, username, newPassword, "physician");
  await expect(page.getByText(RESEARCH_NOTICE, { exact: true })).toBeVisible();
});

test("sign-out returns to login", async ({ page, request }) => {
  const username = uniquePhysicianUsername();
  const password = uniquePassword();
  await createPhysicianViaAdminApi(request, username, password);
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await expect(page.getByText(/physician dashboard/i)).toBeVisible();
  await page.getByRole("button", { name: /sign out|log out/i }).click();
  await expect(page.getByLabel(/username/i)).toBeVisible();
  await expect(page.getByText(/physician dashboard/i)).toHaveCount(0);
  await page.goto("/");
  await expect(page.getByLabel(/username/i)).toBeVisible();
  await expect(
    page.getByRole("button", { name: /log ?in|sign ?in/i }),
  ).toBeVisible();
});
