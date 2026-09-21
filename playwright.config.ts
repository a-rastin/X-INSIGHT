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
      // S12 e2e-only: the default content dir holds only the awaiting_review
      // history draft (never released), so history/effects PATCH would 422 and
      // GET /content/history 404s. Point the e2e backend at the synthetic
      // released fixture; production default is unchanged (never ships
      // synthetic as released). Relative to cwd=backend.
      env: {
        DATABASE_URL: TEST_DATABASE_URL,
        X_INSIGHT_HISTORY_CONTENT_DIR: "../tests/fixtures/content/history",
      },
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
