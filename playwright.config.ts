import { defineConfig } from "@playwright/test";

const TEST_DATABASE_URL =
  "postgresql://xinsight:xinsight_dev@localhost:5432/xinsight_test";

// Minimal S05 harness: backend API on :8000 (disposable test DB, migrated)
// plus Vite dev server on :5173 (proxies /api/v1 to :8000).
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  use: {
    baseURL: "http://localhost:5173",
  },
  webServer: [
    {
      command:
        "uv run alembic upgrade head && PYTHONPATH=src uv run uvicorn x_insight.app:app --port 8000",
      cwd: "backend",
      env: { DATABASE_URL: TEST_DATABASE_URL },
      port: 8000,
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "npm run dev",
      cwd: "web",
      port: 5173,
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
  projects: [{ name: "chromium" }, { name: "firefox" }],
});
