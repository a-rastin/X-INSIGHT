import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

function syntheticXml(name: string, tableA: string, tableB: string): string {
  return (
    `<BIF VERSION="0.3"><NETWORK><NAME>${name}</NAME>` +
    `<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>` +
    `<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>` +
    `<DEFINITION><FOR>A</FOR><TABLE>${tableA}</TABLE></DEFINITION>` +
    `<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>` +
    `<TABLE>${tableB}</TABLE></DEFINITION>` +
    `</NETWORK></BIF>`
  );
}

const REGISTRATION_ORDER = [
  "hospitalization",
  "pharmacotherapy",
  "involuntary_care",
  "high_suicide_clozapine",
  "lai_indication_choice",
  "aggression_clozapine",
  "established_case_clozapine",
];

function uniqueSuffix(): string {
  return `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
}

function uniquePhysicianUsername(): string {
  return `e2enet${uniqueSuffix()}`.toLowerCase();
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
      "Idempotency-Key": `e2e-net-${username}-${Date.now()}`,
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
  // Physicians see the research notice first; continue to the dashboard.
  const cont = page.getByRole("button", { name: /continue/i });
  if ((await cont.count()) > 0) {
    try {
      await cont.first().click({ timeout: 2000 });
    } catch {
      /* admin has no notice */
    }
  }
}

async function gotoNetworks(page: Page): Promise<void> {
  const link = page.getByRole("link", { name: /networks/i });
  if ((await link.count()) > 0) {
    await link.first().click();
  } else {
    await page.goto("/networks");
  }
  await expect(page.getByTestId("networks-section")).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByTestId("networks-xml-input")).toBeVisible({
    timeout: 10_000,
  });
}

async function pageCsrf(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  return cookies.find((c) => c.name === "xinsight_csrf")?.value ?? "";
}

async function apiImportNetwork(page: Page, xml: string): Promise<{ network_id: string; version_id: string }> {
  const csrf = await pageCsrf(page);
  const response = await page.request.post("/api/v1/networks", {
    data: { xml },
    headers: { "X-CSRF-Token": csrf, "Idempotency-Key": `e2e-net-${uniqueSuffix()}` },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as Record<string, string>;
  const networkId = String(body.network_id ?? body.id ?? "");
  const versionId = String(body.version_id ?? "");
  expect(networkId).toBeTruthy();
  expect(versionId).toBeTruthy();
  return { network_id: networkId, version_id: versionId };
}

async function apiGetPointer(page: Page, workflow: string): Promise<{ revision: number; bundle_hash: string | null }> {
  const response = await page.request.get(`/api/v1/model-bundles/${workflow}`);
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { revision: number; bundle_hash: string | null };
  return body;
}

function pinsLines(versionIds: string[]): string {
  return REGISTRATION_ORDER.map((key, i) => `${key}=${versionIds[i]}`).join("\n");
}

async function testIdText(page: Page, testId: string): Promise<string> {
  if ((await page.getByTestId(testId).count()) === 0) {
    return "";
  }
  return (await page.getByTestId(testId).textContent().catch(() => "")) ?? "";
}

async function bundleOutcome(page: Page): Promise<string> {
  const notice = await testIdText(page, "bundle-notice");
  const error = await testIdText(page, "bundle-error");
  return `notice:${notice} ||| error:${error}`;
}

function outcomeSettled(before: string, last: string): boolean {
  if (last === before) {
    return false;
  }
  // Any fresh notice/error text counts (parse errors included); the callers
  // classify stale vs success from the returned text. Split on the separator
  // so the literal "|||" never counts as content; strip the labels too so a
  // bare "notice:"/"error:" with no text does not count as settled.
  const parts = last.split("|||");
  const notice = (parts[0] ?? "").replace("notice:", "").trim();
  const error = (parts[1] ?? "").replace("error:", "").trim();
  return notice.length > 0 || error.length > 0;
}

async function activateViaUI(page: Page, lines: string): Promise<string> {
  await page.getByTestId("bundle-activate-pins").fill(lines);
  const reviewer = page.getByTestId("bundle-activate-reviewer");
  if ((await reviewer.count()) > 0 && (await reviewer.inputValue()) === "") {
    await reviewer.fill("owner");
  }
  const date = page.getByTestId("bundle-activate-date");
  if ((await date.count()) > 0 && (await date.inputValue()) === "") {
    await date.fill("2026-09-22");
  }
  const confirm = page.getByTestId("bundle-activate-confirm");
  if (!(await confirm.isChecked())) {
    await confirm.check();
  }
  const before = await bundleOutcome(page);
  await page.getByTestId("bundle-activate").click();
  let last = before;
  await expect
    .poll(
      async () => {
        last = await bundleOutcome(page);
        return outcomeSettled(before, last) ? "ready" : "pending";
      },
      // Bundle pointer is a singleton shared with the parallel project and
      // the page also serves dozens of version-list reads; allow extra time.
      { timeout: 30_000, intervals: [500, 1000, 2000] },
    )
    .toMatch(/ready/);
  return last;
}

async function rollbackViaUI(page: Page, target: number): Promise<string> {
  await page.getByTestId("bundle-rollback-target").fill(String(target));
  const confirm = page.getByTestId("bundle-rollback-confirm");
  if (!(await confirm.isChecked())) {
    await confirm.check();
  }
  const before = await bundleOutcome(page);
  await page.getByTestId("bundle-rollback").click();
  let last = before;
  await expect
    .poll(
      async () => {
        last = await bundleOutcome(page);
        return outcomeSettled(before, last) ? "ready" : "pending";
      },
      // Same shared-singleton contention as activation.
      { timeout: 30_000, intervals: [500, 1000, 2000] },
    )
    .toMatch(/ready/);
  return last;
}

test.describe.serial("networks admin (import, inspect, version, bundles)", () => {
  test("admin import, inspect, version, activate and rollback journey", async ({ page }) => {
    // Slow shared backend (parallel project + dozens of version reads) can
    // exceed the default 60s test budget across the retry loops below.
    test.setTimeout(180_000);
    // Unique network name per run: parallel projects must never share a
    // network row (same-name imports are independent rows, but "last item"
    // lookup and the v2 race need a deterministic own-network match).
    const runName = `Synthetic_Net_${uniqueSuffix()}`;
    const XML_V1 = syntheticXml(runName, "0.8 0.2", "0.9 0.1 0.3 0.7");
    const XML_V2 = syntheticXml(runName, "0.6 0.4", "0.7 0.3 0.2 0.8");
    await loginViaUI(page, "admin", "admin", "admin");
    await expect(page.getByText(/admin dashboard/i)).toBeVisible();
    await gotoNetworks(page);

    // Import via UI (synthetic 2-node XML inline).
    await page.getByTestId("networks-xml-input").fill(XML_V1);
    await page.getByTestId("networks-import").click();
    await expect(page.getByTestId("networks-notice")).toContainText(/imported/i, {
      timeout: 10_000,
    });
    await expect(page.getByTestId("networks-list")).toContainText(runName, {
      timeout: 10_000,
    });

    // Resolve OUR network/version ids via API by unique key (never "last
    // item", which races the parallel project and prior runs).
    const listResponse = await page.request.get("/api/v1/networks");
    expect(listResponse.ok()).toBeTruthy();
    const listBody = (await listResponse.json()) as { items: { id: string; network_id: string; key: string }[] };
    const own = listBody.items.find((entry) => entry.key === runName);
    expect(own).toBeTruthy();
    const firstNetworkId = String(own?.network_id ?? own?.id);
    const versionsResponse = await page.request.get(`/api/v1/networks/${firstNetworkId}/versions`);
    expect(versionsResponse.ok()).toBeTruthy();
    const versionsBody = (await versionsResponse.json()) as { items: { version_id: string; version_number: number; sha256: string; byte_count: number }[] };
    expect(versionsBody.items.length).toBeGreaterThan(0);
    const v1 = versionsBody.items.find((v) => v.version_number === 1) ?? versionsBody.items[0];
    const v1Id = String(v1.version_id);
    expect(v1Id).toBeTruthy();

    // Version history shows version, short sha, byte count, XSD status.
    const history = page.getByTestId(`network-versions-${firstNetworkId}`);
    await expect(history).toContainText(/version 1/i, { timeout: 10_000 });
    await expect(history).toContainText(/bytes/i);
    await expect(history).toContainText(/xsd/i);

    // Inspect: graph nodes/edges text + validation status.
    await page.getByTestId(`version-inspect-${v1Id}`).click();
    const graph = page.getByTestId(`version-graph-${v1Id}`);
    await expect(graph).toContainText(/A/, { timeout: 15_000 });
    await expect(graph).toContainText(/B/);
    await expect(graph).toContainText(/A to B/);
    await expect(graph).toContainText(/valid|executable|admitted/i);
    // Inline SVG renders boxes (no drag/edit handlers).
    await expect(graph.locator("svg")).toBeVisible();
    await expect(graph.locator("svg text", { hasText: "A" }).first()).toBeVisible();

    // Validation details: xsd report, semantic executable/errors, admission measurements.
    const validation = page.getByTestId(`version-validate-${v1Id}`);
    await expect(validation).toContainText(/xsd/i, { timeout: 15_000 });
    await expect(validation).toContainText(/semantic/i);
    await expect(validation).toContainText(/admission/i);

    // Export link points at exact-XML endpoint; bytes match via API.
    const exportLink = page.getByTestId(`version-export-${v1Id}`);
    await expect(exportLink).toBeVisible();
    const href = await exportLink.getAttribute("href");
    expect(href).toContain(`/api/v1/network-versions/${v1Id}/xml`);
    const xmlResponse = await page.request.get(href ?? "");
    expect(xmlResponse.ok()).toBeTruthy();
    expect(await xmlResponse.text()).toBe(XML_V1);

    // New version via UI (explicit confirm): history grows to v1+v2.
    await page.getByTestId(`network-new-xml-${firstNetworkId}`).fill(XML_V2);
    await page.getByTestId(`network-new-confirm-${firstNetworkId}`).check();
    await page.getByTestId(`network-new-submit-${firstNetworkId}`).click();
    await expect(history).toContainText(/version 2/i, { timeout: 10_000 });

    // Build 7 pins via API (6 more networks) + the first network's v1.
    const extra: string[] = [];
    for (let i = 0; i < 6; i++) {
      const created = await apiImportNetwork(page, XML_V1);
      extra.push(created.version_id);
    }
    const seven = [v1Id, ...extra];
    expect(seven).toHaveLength(7);
    const lines = pinsLines(seven);

    // Activate with retry: the bundle pointer is a singleton shared with the
    // parallel project, so a 412 reloads and retries with a fresh revision.
    // A poll timeout (transient hang under contention) also retries.
    let activatedRevision = 0;
    let activateOutcome = "";
    for (let attempt = 0; attempt < 5; attempt++) {
      try {
        activateOutcome = await activateViaUI(page, lines);
      } catch {
        continue;
      }
      if (/activated/i.test(activateOutcome)) {
        const pointer = await apiGetPointer(page, "registration");
        activatedRevision = pointer.revision;
        break;
      }
      if (!/changed|reload|stale/i.test(activateOutcome)) {
        break;
      }
    }
    expect(activateOutcome).toMatch(/activated/i);
    expect(activatedRevision).toBeGreaterThan(0);
    await expect(page.getByTestId("bundle-pointer")).toContainText(
      new RegExp(`Revision ${activatedRevision}`),
      { timeout: 10_000 },
    );

    // Stale-412 path: bump out-of-band (retrying on races with the parallel
    // project until OUR bump lands), then the UI submit goes stale.
    const csrf = await pageCsrf(page);
    let bumpedRevision = 0;
    for (let attempt = 0; attempt < 5; attempt++) {
      const current = await apiGetPointer(page, "registration");
      const bump = await page.request.post("/api/v1/model-bundles/activate", {
        data: {
          workflow: "registration",
          pins: seven.map((versionId, i) => ({
            question_key: REGISTRATION_ORDER[i],
            network_version_id: versionId,
            review: { decision: "approved", reviewer: "owner", date: "2026-09-22" },
          })),
          expected_revision: current.revision,
        },
        headers: { "X-CSRF-Token": csrf, "Idempotency-Key": `e2e-net-bump-${uniqueSuffix()}` },
      });
      if (bump.ok()) {
        bumpedRevision = ((await bump.json()) as { revision: number }).revision;
        break;
      }
    }
    expect(bumpedRevision).toBeGreaterThan(0);

    // Server only moves forward past our bump, so this submit must 412.
    // Retry transient poll timeouts; a success here would mean the UI
    // pointer refreshed itself, which never happens without a reload.
    let staleOutcome = "";
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        staleOutcome = await activateViaUI(page, lines);
      } catch {
        continue;
      }
      break;
    }
    expect(staleOutcome).toMatch(/changed|reload|stale/i);
    await expect(page.getByTestId("bundle-error")).toContainText(/changed|reload|stale/i);

    // Rollback to the pre-bump revision creates a new activation event.
    // Retry stale/timeout races the same way as activation.
    let rollbackOutcome = "";
    for (let attempt = 0; attempt < 5; attempt++) {
      try {
        rollbackOutcome = await rollbackViaUI(page, activatedRevision);
      } catch {
        continue;
      }
      if (/rolled back/i.test(rollbackOutcome)) {
        break;
      }
      if (!/changed|reload|stale/i.test(rollbackOutcome)) {
        break;
      }
    }
    expect(rollbackOutcome).toMatch(/rolled back/i);
    const pointerAfter = await apiGetPointer(page, "registration");
    expect(pointerAfter.revision).toBeGreaterThan(bumpedRevision);
  });

  test("physician is denied without a section", async ({ page, request }) => {
    const username = uniquePhysicianUsername();
    await createPhysicianViaAdminApi(request, username, "synthetic-secret");
    await loginViaUI(page, username, "synthetic-secret", "physician");
    await page.goto("/networks");
    await expect(page.getByText(/access denied/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("networks-section")).toHaveCount(0);
    await expect(page.getByTestId("networks-xml-input")).toHaveCount(0);
  });

  test("anonymous sees the login prompt", async ({ page }) => {
    await page.goto("/networks");
    await expect(page.getByText(/log in to continue/i)).toBeVisible({ timeout: 10_000 });
  });
});
