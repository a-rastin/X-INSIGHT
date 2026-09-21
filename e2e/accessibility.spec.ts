import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const GENERIC_LOGIN_ERROR = "Invalid username, password, or role.";
const RESEARCH_NOTICE =
  "This is a research app and is not intended to be used as the sole basis for treating patients.";

function uniquePhysicianUsername(prefix = "e2ea11y"): string {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return `${prefix}${suffix}`.toLowerCase();
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

async function activeDescriptor(page: Page): Promise<string> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el) return "none";
    const text = (el.textContent ?? "").trim().slice(0, 80).replace(/\s+/g, " ");
    return `${el.tagName}#${el.id} text=${text}`;
  });
}

async function focusedOutline(page: Page): Promise<{ width: string; style: string }> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el) return { width: "0px", style: "none" };
    const computed = getComputedStyle(el);
    return { width: computed.outlineWidth, style: computed.outlineStyle };
  });
}

async function tabUntil(
  page: Page,
  matches: (descriptor: string) => boolean,
  maxTabs = 20,
): Promise<string[]> {
  const progression: string[] = [];
  for (let i = 0; i < maxTabs; i += 1) {
    await page.keyboard.press("Tab");
    const descriptor = await activeDescriptor(page);
    progression.push(descriptor);
    if (matches(descriptor)) return progression;
  }
  return progression;
}

// S05 slice-4 (T9 browser seam): keyboard operability + visible focus.
test("keyboard Tab reaches Log in and theme toggle; Enter/Space activates the toggle", async ({
  page,
  request,
}) => {
  const username = uniquePhysicianUsername();
  const password = uniquePassword();
  await createPhysicianViaAdminApi(request, username, password);

  await page.goto("/");
  await expect(page.getByRole("button", { name: /log ?in|sign ?in/i })).toBeVisible();

  const loginProgression = await tabUntil(page, (d) => /BUTTON.*Log in/i.test(d));
  expect(loginProgression.some((d) => /BUTTON.*Log in/i.test(d))).toBe(true);
  const loginOutline = await focusedOutline(page);
  expect(loginOutline.style).not.toBe("none");
  expect(Number.parseFloat(loginOutline.width)).toBeGreaterThan(0);

  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);
  await expect(page.getByText(/physician dashboard/i)).toBeVisible();

  const toggle = themeToggle(page);
  await expect(toggle).toBeVisible();
  const meBefore = await page.request.get("/api/v1/me");
  expect(meBefore.ok()).toBeTruthy();
  const themeBefore = ((await meBefore.json()) as { theme: string }).theme;

  const toggleProgression = await tabUntil(page, (d) => /BUTTON.*theme/i.test(d));
  expect(toggleProgression.some((d) => /BUTTON.*theme/i.test(d))).toBe(true);
  const toggleOutline = await focusedOutline(page);
  expect(toggleOutline.style).not.toBe("none");
  expect(Number.parseFloat(toggleOutline.width)).toBeGreaterThan(0);

  const firstPatch = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/me/preferences") &&
      response.request().method() === "PATCH",
  );
  await page.keyboard.press("Space");
  expect((await firstPatch).ok()).toBeTruthy();
  await expect
    .poll(async () => ((await (await page.request.get("/api/v1/me")).json()) as { theme: string }).theme)
    .not.toBe(themeBefore);

  await expect(toggle).toBeVisible();
  await toggle.focus();
  const secondPatch = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/me/preferences") &&
      response.request().method() === "PATCH",
  );
  await page.keyboard.press("Enter");
  expect((await secondPatch).ok()).toBeTruthy();
  await expect
    .poll(async () => ((await (await page.request.get("/api/v1/me")).json()) as { theme: string }).theme)
    .toBe(themeBefore);
});

// S05 slice-4 (T9 browser seam): associated labels on the login form.
test("login inputs have associated labels", async ({ page }) => {
  await page.goto("/");
  const usernameInput = page.getByLabel(/username/i);
  const passwordInput = page.getByLabel(/password/i);
  await expect(usernameInput).toBeVisible();
  await expect(passwordInput).toBeVisible();
  await expect(usernameInput).toHaveAccessibleName(/username/i);
  await expect(passwordInput).toHaveAccessibleName(/password/i);

  const association = await page.evaluate(() => {
    const labels = Array.from(document.querySelectorAll("label"));
    return labels.map((label) => {
      const htmlFor = label.getAttribute("for") ?? label.getAttribute("htmlFor") ?? "";
      const target = htmlFor ? document.getElementById(htmlFor) : null;
      return {
        text: (label.textContent ?? "").trim(),
        htmlFor,
        targetTag: target?.tagName ?? null,
      };
    });
  });
  const usernameLabel = association.find((l) => /username/i.test(l.text));
  const passwordLabel = association.find((l) => /password/i.test(l.text));
  expect(usernameLabel?.htmlFor).toBeTruthy();
  expect(passwordLabel?.htmlFor).toBeTruthy();
  expect(usernameLabel?.targetTag).toBe("INPUT");
  expect(passwordLabel?.targetTag).toBe("INPUT");
});

// S05 slice-4 (T9 browser seam): generic login error without field disclosure.
test("failed login shows a generic role=alert error", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel(/username/i).fill("definitely-not-a-user");
  await page.getByLabel(/password/i).fill("wrong-secret");
  await page.getByRole("button", { name: /log ?in|sign ?in/i }).click();

  const alert = page.getByRole("alert");
  await expect(alert).toBeVisible();
  await expect(alert).toHaveText(GENERIC_LOGIN_ERROR);
  const text = (await alert.textContent()) ?? "";
  expect(text.toLowerCase()).not.toContain("password is wrong");
  expect(text.toLowerCase()).not.toContain("user not found");
  expect(text.toLowerCase()).not.toContain("username does not exist");
  expect(text.toLowerCase()).not.toContain("incorrect password");

  const describedBy = await page.evaluate(() => ({
    username: document.getElementById("username")?.getAttribute("aria-describedby"),
    password: document.getElementById("password")?.getAttribute("aria-describedby"),
  }));
  expect(describedBy.username).toBe("login-error");
  expect(describedBy.password).toBe("login-error");
});

// S05 slice-4 (T9 browser seam): physicians table loading then real content.
test("physicians table renders loading then content from the real endpoint", async ({
  page,
}) => {
  await loginViaUI(page, "admin", "admin", "admin");
  await expect(page.getByText(/admin dashboard/i)).toBeVisible();

  await page.route("**/api/v1/physicians?*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.continue();
  });
  await page.goto("/physicians");
  await expect(page.getByText(/loading/i).first()).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
});

// S05 slice-4 (T9 browser seam): physicians table empty state.
test("physicians table empty state", async ({ page }) => {
  await loginViaUI(page, "admin", "admin", "admin");
  await expect(page.getByText(/admin dashboard/i)).toBeVisible();

  await page.route("**/api/v1/physicians?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ schema_version: 1, items: [], next_cursor: null }),
    });
  });
  await page.goto("/physicians");
  await expect(page.getByText("No physicians yet.")).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);
});

// S05 slice-4 (T9 browser seam): physicians table error state.
test("physicians table error state on 500", async ({ page }) => {
  await loginViaUI(page, "admin", "admin", "admin");
  await expect(page.getByText(/admin dashboard/i)).toBeVisible();

  await page.route("**/api/v1/physicians?*", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "boom" }),
    });
  });
  await page.goto("/physicians");
  const alert = page.getByRole("alert");
  await expect(alert).toBeVisible();
  await expect(alert).toContainText(/could not load physicians/i);
});

// S05 slice-4 (T9 browser seam): wrong-password change shows the password error alert.
test("wrong-password change shows the password error alert", async ({
  page,
  request,
}) => {
  const username = uniquePhysicianUsername();
  const password = uniquePassword();
  await createPhysicianViaAdminApi(request, username, password);
  await loginViaUI(page, username, password, "physician");
  await dismissResearchNotice(page);

  await page.getByLabel(/current password/i).fill("wrong-current");
  await page.getByLabel(/new password/i).fill(uniquePassword());
  await page.getByRole("button", { name: /change password|update password/i }).click();

  const alert = page.getByRole("alert");
  await expect(alert).toBeVisible();
  await expect(alert).toContainText(/could not change the password/i);
});

// S05 slice-4 (T9 browser seam): served CSS honors prefers-reduced-motion.
test("served CSS honors prefers-reduced-motion", async ({ page }) => {
  await page.goto("/");
  const found = await page.evaluate(async () => {
    const matches = (text: string) => /prefers-reduced-motion/.test(text);
    for (const sheet of Array.from(document.styleSheets)) {
      try {
        const rules = sheet.cssRules;
        for (const rule of Array.from(rules)) {
          if (matches(rule.cssText)) return true;
          if (rule instanceof CSSMediaRule && /prefers-reduced-motion/.test(rule.conditionText)) {
            return true;
          }
        }
      } catch {
        continue;
      }
    }
    const links = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).map(
      (el) => (el as HTMLLinkElement).href,
    );
    for (const href of links) {
      try {
        const response = await fetch(href);
        const text = await response.text();
        if (matches(text)) return true;
      } catch {
        continue;
      }
    }
    return false;
  });
  expect(found).toBe(true);
});
