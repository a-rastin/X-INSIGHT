import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const SYNTHETIC_KEY = "synthetic-e2e-key-001";
const PLACEHOLDER = "****";
const UNROUTABLE_URL = "http://127.0.0.1:9";

function uniquePhysicianUsername(): string {
  const suffix = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return `e2eprov${suffix}`.toLowerCase();
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
      "Idempotency-Key": `e2e-prov-${username}-${Date.now()}`,
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
  // Wait for the login round-trip before navigating further (dashboard for
  // both roles; physicians see the research notice first).
  await expect(page.getByText(/dashboard|research app/i).first()).toBeVisible({
    timeout: 10_000,
  });
}

async function gotoProviderSettings(page: Page): Promise<void> {
  const link = page.getByRole("link", { name: /provider settings/i });
  if ((await link.count()) > 0) {
    await link.first().click();
  } else {
    await page.goto("/provider-settings");
  }
  await expect(page.getByTestId("provider-settings-section")).toBeVisible({
    timeout: 10_000,
  });
  // The section renders a loading skeleton first; wait for the loaded state
  // (key status) so fills are not clobbered by the initial fetch.
  await expect(page.getByTestId("provider-key-status")).toBeVisible({
    timeout: 10_000,
  });
}

async function outcomeText(page: Page, testId: string): Promise<string> {
  if ((await page.getByTestId(testId).count()) === 0) {
    return "";
  }
  return (
    (await page.getByTestId(testId).textContent().catch(() => "")) ?? ""
  );
}

/** Click Save and wait until the notice/error differs from before (a real outcome). */
async function clickSaveAndAwaitOutcome(page: Page): Promise<string> {
  const beforeNotice = await outcomeText(page, "provider-notice");
  const beforeError = await outcomeText(page, "provider-error");
  await page.getByTestId("provider-save").click();
  let last = "";
  await expect
    .poll(
      async () => {
        const notice = await outcomeText(page, "provider-notice");
        const error = await outcomeText(page, "provider-error");
        last = `notice:${notice} ||| error:${error}`;
        const settled =
          /saved|changed|reload|requires|invalid|access denied|could not/i.test(
            last,
          );
        const changed = notice !== beforeNotice || error !== beforeError;
        return settled && changed ? "ready" : "pending";
      },
      { timeout: 15_000 },
    )
    .toMatch(/ready/);
  return last;
}

/**
 * Singleton settings are shared across parallel browser projects, so a save
 * can lose a revision race (412) when the other project writes concurrently.
 * The UI refreshes the revision on conflict; re-fill and retry the save.
 */
async function saveFormResolvingConflicts(
  page: Page,
  args: { baseUrl: string; model: string; apiKey?: string },
): Promise<void> {
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.getByTestId("provider-base-url").fill(args.baseUrl);
    await page.getByTestId("provider-model").fill(args.model);
    if (args.apiKey !== undefined) {
      const replace = page.getByTestId("provider-replace");
      if (
        (await page.getByTestId("provider-key").count()) === 0 &&
        (await replace.count()) > 0
      ) {
        await replace.first().click();
      }
      await page.getByTestId("provider-key").fill(args.apiKey);
    }
    let outcome = "";
    try {
      outcome = await clickSaveAndAwaitOutcome(page);
    } catch {
      continue; // No outcome observed; retry with a fresh read.
    }
    if (/changed|reload/i.test(outcome)) {
      continue; // Revision refreshed by the UI; retry with a fresh revision.
    }
    return;
  }
  throw new Error("Could not save provider settings without a revision conflict.");
}

/** Clear-key PUTs race the same way; retry arm+confirm until Missing. */
async function clearKeyResolvingConflicts(page: Page): Promise<void> {
  for (let attempt = 0; attempt < 5; attempt++) {
    await page.getByTestId("provider-clear").click();
    await page.waitForTimeout(200);
    const status =
      (await page.getByTestId("provider-key-status").textContent().catch(() => "")) ??
      "";
    if (/missing/i.test(status)) {
      return;
    }
    await page.getByTestId("provider-clear").click();
    try {
      await expect(page.getByTestId("provider-key-status")).toContainText(
        /missing/i,
        { timeout: 8_000 },
      );
      return;
    } catch {
      /* conflict or interleave: revision refreshed, retry arm+confirm */
    }
  }
  await expect(page.getByTestId("provider-key-status")).toContainText(/missing/i, {
    timeout: 8_000,
  });
}

/** Save, then assert the masked state; re-save when the parallel project
 *  mutates the singleton between our save and the assertion. */
async function saveAndExpectMaskedState(
  page: Page,
  args: { baseUrl: string; model: string; apiKey?: string },
  keyExpect: RegExp,
  statusExpect: RegExp,
): Promise<void> {
  for (let attempt = 0; attempt < 4; attempt++) {
    await saveFormResolvingConflicts(page, args);
    try {
      await expect(page.getByTestId("provider-key-status")).toContainText(
        keyExpect,
        { timeout: 5_000 },
      );
      await expect(page.getByTestId("provider-status")).toContainText(
        statusExpect,
        { timeout: 5_000 },
      );
      return;
    } catch {
      /* parallel project mutated the singleton; re-save and re-check */
    }
  }
  await expect(page.getByTestId("provider-key-status")).toContainText(keyExpect, {
    timeout: 10_000,
  });
  await expect(page.getByTestId("provider-status")).toContainText(statusExpect, {
    timeout: 10_000,
  });
}

/** Out-of-band revision bump for the stale-write check; retried on races. */
async function bumpRevisionOutOfBand(page: Page): Promise<void> {
  for (let attempt = 0; attempt < 5; attempt++) {
    const probe = await page.request.get("/api/v1/api-settings");
    if (!probe.ok()) {
      continue;
    }
    const csrf =
      (await page.context().cookies()).find((c) => c.name === "xinsight_csrf")
        ?.value ?? "";
    const etag = (probe.headers()["etag"] ?? "").replace(/"/g, "");
    if (!csrf || !etag) {
      continue;
    }
    const bump = await page.request.put("/api/v1/api-settings", {
      data: {
        base_url: "https://provider.example/v1",
        model: "synthetic-model-bumped",
        key_action: "unchanged",
      },
      headers: { "X-CSRF-Token": csrf, "If-Match": etag },
    });
    if (bump.ok()) {
      return;
    }
  }
  throw new Error("Could not bump the provider revision out-of-band.");
}

test.describe.serial("provider settings (admin only, masked)", () => {
  test("admin sees masked settings, replace/clear key flow, stale write conflicts", async ({
    page,
  }) => {
    await loginViaUI(page, "admin", "admin", "admin");
    await expect(page.getByText(/admin dashboard/i)).toBeVisible();
    await gotoProviderSettings(page);

    const section = page.getByTestId("provider-settings-section");
    // Key value is never rendered anywhere on the page.
    await expect(section).not.toContainText(SYNTHETIC_KEY);

    // Replace flow reveals the key input: placeholder is the redacted
    // marker and the field starts empty (never prefilled from the server).
    const replaceFirst = page.getByTestId("provider-replace");
    if (
      (await page.getByTestId("provider-key").count()) === 0 &&
      (await replaceFirst.count()) > 0
    ) {
      await replaceFirst.first().click();
    }
    const revealed = page.getByTestId("provider-key");
    await expect(revealed).toBeVisible({ timeout: 10_000 });
    await expect(revealed).toHaveAttribute("placeholder", PLACEHOLDER);
    await expect(revealed).toHaveValue("");

    // Replace flow: the key input carries the redacted placeholder and
    // starts empty (a configured key stays hidden until Replace is chosen).
    await saveAndExpectMaskedState(
      page,
      {
        baseUrl: "https://provider.example/v1",
        model: "synthetic-model-e2e",
        apiKey: SYNTHETIC_KEY,
      },
      /configured/i,
      /untested/i,
    );
    const keyInput = page.getByTestId("provider-key");
    if ((await keyInput.count()) > 0) {
      // After a replace-save the input resets; placeholder stays redacted.
      await expect(keyInput).toHaveAttribute("placeholder", PLACEHOLDER);
    }

    const status = page.getByTestId("provider-status");
    await expect(status).toContainText(/untested|failed|verified/i, {
      timeout: 10_000,
    });
    // Synthetic key never leaks into rendered content.
    await expect(section).not.toContainText(SYNTHETIC_KEY);

    // Placeholder **** is never sent as a key: saving it must fail loudly.
    const replaceButton = page.getByTestId("provider-replace");
    if ((await replaceButton.count()) > 0) {
      await replaceButton.first().click().catch(() => undefined);
    }
    const keyAgain = page.getByTestId("provider-key");
    if ((await keyAgain.count()) > 0) {
      await expect(keyAgain).toHaveAttribute("placeholder", PLACEHOLDER);
      await expect(keyAgain).toHaveValue("");
      await keyAgain.fill(PLACEHOLDER);
      await page.getByTestId("provider-save").click();
      await expect(page.getByTestId("provider-error")).toBeVisible({
        timeout: 10_000,
      });
      // Secret placeholder still never rendered as a value leak beyond the input.
      await expect(section).not.toContainText(SYNTHETIC_KEY);
    }

    // Clear flow requires an explicit confirm step.
    await expect(page.getByTestId("provider-clear")).toBeVisible();
    await clearKeyResolvingConflicts(page);

    // Stale write: fill the form, bump the revision out-of-band, then save
    // stale via UI.
    // NOTE: the stale save must carry a real key so it reaches the server
    // (an empty/placeholder key fails client-side before any PUT).
    await page.getByTestId("provider-base-url").fill("https://provider.example/v1");
    await page.getByTestId("provider-model").fill("synthetic-model-stale");
    const staleReplace = page.getByTestId("provider-replace");
    if (
      (await page.getByTestId("provider-key").count()) === 0 &&
      (await staleReplace.count()) > 0
    ) {
      await staleReplace.first().click();
    }
    await page.getByTestId("provider-key").fill("synthetic-e2e-key-002");
    await bumpRevisionOutOfBand(page);
    await page.getByTestId("provider-save").click();
    await expect(page.getByTestId("provider-error")).toContainText(
      /changed|conflict|stale|reload/i,
      { timeout: 10_000 },
    );
  });

  test("physician is denied without a form", async ({ page, request }) => {
    const username = uniquePhysicianUsername();
    const password = "synthetic-secret";
    await createPhysicianViaAdminApi(request, username, password);
    await loginViaUI(page, username, password, "physician");
    await expect(
      page.getByText(
        "This is a research app and is not intended to be used as the sole basis for treating patients.",
        { exact: true },
      ),
    ).toBeVisible();
    await page.getByRole("button", { name: /continue/i }).click();
    await page.goto("/provider-settings");
    await expect(page.getByText(/access denied/i)).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByTestId("provider-settings-section")).toHaveCount(0);
    await expect(page.getByTestId("provider-base-url")).toHaveCount(0);
  });

  test("test button reports failed without exposing the secret", async ({
    page,
  }) => {
    await loginViaUI(page, "admin", "admin", "admin");
    await gotoProviderSettings(page);

    // Point at an unroutable loopback endpoint (e2e allow-local only):
    // the capability probe fails safely with Failed status, no live provider.
    // The singleton is shared across parallel projects: re-save + re-probe
    // until the Failed state from our unroutable URL is observed.
    let sawFailed = false;
    for (let attempt = 0; attempt < 3 && !sawFailed; attempt++) {
      await saveFormResolvingConflicts(page, {
        baseUrl: UNROUTABLE_URL,
        model: "synthetic-model-e2e",
        apiKey: "synthetic-e2e-key-003",
      });
      await expect(page.getByTestId("provider-status")).toContainText(
        /untested|failed|verified/i,
        { timeout: 10_000 },
      );

      await page.getByTestId("provider-test").click();
      try {
        await expect(page.getByTestId("provider-status")).toContainText(
          /failed/i,
          { timeout: 30_000 },
        );
        sawFailed = true;
      } catch {
        /* interleaved save by the parallel project changed the URL; retry */
      }
    }
    expect(sawFailed).toBeTruthy();
    const section = page.getByTestId("provider-settings-section");
    await expect(section).not.toContainText(SYNTHETIC_KEY);
    // No secret echo in diagnostics either.
    const body = (await section.textContent()) ?? "";
    expect(body).not.toContain("synthetic-e2e-key");
  });
});
