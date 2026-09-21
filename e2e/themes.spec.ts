import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

function uniquePhysicianUsername(): string {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return `e2etheme${suffix}`.toLowerCase();
}

function uniquePassword(): string {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return `pw-${suffix}`;
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

async function dismissResearchNotice(page: Page): Promise<void> {
  await expect(page.getByText(RESEARCH_NOTICE, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();
}

function themeToggle(page: Page) {
  return page.getByRole("button", { name: /theme|dark|light/i });
}

async function serverTheme(page: Page): Promise<string> {
  const me = await page.request.get("/api/v1/me");
  expect(me.ok()).toBeTruthy();
  const payload = (await me.json()) as { theme?: string };
  expect(payload.theme).toBeTruthy();
  return payload.theme as string;
}

async function documentTheme(page: Page): Promise<string | null> {
  return page.evaluate(() =>
    document.documentElement.getAttribute("data-theme"),
  );
}

async function bodyBackground(page: Page): Promise<string> {
  return page.evaluate(
    () => getComputedStyle(document.body).backgroundColor,
  );
}

// S05 slice-3 (T9 browser seam): theme toggle + server persistence only.
test("theme toggle switches light/dark and persists across reload via the server", async ({
  page,
  request,
}) => {
  const username = uniquePhysicianUsername();
  const password = uniquePassword();
  await createPhysicianViaAdminApi(request, username, password);
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await expect(page.getByText(/physician dashboard/i)).toBeVisible();

  const initialTheme = await serverTheme(page);
  const initialBackground = await bodyBackground(page);

  const toggle = themeToggle(page);
  await expect(toggle).toBeVisible();

  const patchResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/me/preferences") &&
      response.request().method() === "PATCH",
  );
  await toggle.click();
  const patch = await patchResponse;
  expect(patch.ok()).toBeTruthy();

  const toggledTheme = await serverTheme(page);
  expect(toggledTheme).not.toBe(initialTheme);

  await page.reload();
  await expect(page.getByText(/physician dashboard/i)).toBeVisible();

  const reloadedTheme = await serverTheme(page);
  expect(reloadedTheme).toBe(toggledTheme);
  await expect.poll(() => documentTheme(page)).toBe(reloadedTheme);
  const reloadedBackground = await bodyBackground(page);
  expect(reloadedBackground).not.toBe(initialBackground);
});

// S05 slice-3 (T9 browser seam): dark theme keeps the clinical flow readable.
test("dark theme keeps the research warning and role dashboard readable", async ({
  page,
  request,
}) => {
  const username = uniquePhysicianUsername();
  const password = uniquePassword();
  await createPhysicianViaAdminApi(request, username, password);
  await loginViaUI(page, username, password, "physician");
  await expect(page.getByText(RESEARCH_NOTICE, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();
  await expect(page.getByText(/physician dashboard/i)).toBeVisible();

  const toggle = themeToggle(page);
  await expect(toggle).toBeVisible();
  const patchResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/me/preferences") &&
      response.request().method() === "PATCH",
  );
  await toggle.click();
  await patchResponse;
  await expect.poll(() => documentTheme(page)).toBe("dark");

  // Fresh login renders with the persisted dark theme already applied.
  await page.context().clearCookies();
  await loginViaUI(page, username, password, "physician");
  await expect(page.getByText(RESEARCH_NOTICE, { exact: true })).toBeVisible();
  await expect.poll(() => documentTheme(page)).toBe("dark");
  await page.getByRole("button", { name: /continue/i }).click();
  await expect(page.getByText(/physician dashboard/i)).toBeVisible();
  await expect.poll(() => documentTheme(page)).toBe("dark");
});

// S05 slice-3 (T9 browser seam): theme preference requires login.
test("theme preference requires login", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: /log ?in|sign ?in/i }),
  ).toBeVisible();

  let patchIssued = false;
  page.on("request", (req) => {
    if (
      req.url().includes("/api/v1/me/preferences") &&
      req.method() === "PATCH"
    ) {
      patchIssued = true;
    }
  });

  const toggle = themeToggle(page);
  if ((await toggle.count()) > 0) {
    await toggle.first().click();
    await page.waitForTimeout(1000);
    expect(patchIssued).toBe(false);
  }

  await page.reload();
  const me = await page.request.get("/api/v1/me");
  expect(me.status()).toBe(401);
  expect(patchIssued).toBe(false);
});
