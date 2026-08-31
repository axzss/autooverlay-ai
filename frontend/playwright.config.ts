import { defineConfig, devices } from '@playwright/test'

/**
 * E2E regression suite for the AutoOverlay AI frontend.
 *
 * Written after three bugs shipped past `tsc --noEmit` AND `next build` and were
 * caught only when a human opened the app in a browser:
 *   1. lib/api.ts pointed fetch() at http://localhost:8000 — the *visitor's*
 *      machine. Every page returned HTTP 200 while every API call failed.
 *   2. api.getHealth() requested bare '/health', which hits the Next origin
 *      (not a page) and 404'd, so the status card read "unreachable".
 *   3. framer-motion serialised `initial="hidden"` into the server HTML, so
 *      /dashboard shipped as opacity:0 and rendered blank on first load.
 *
 * Every one of those is invisible to a status-code check. HTTP 200 is not
 * evidence a page works, so this suite asserts on visibility, on the network
 * origins the browser actually contacts, and on the raw server HTML.
 *
 * The dev server is expected to already be running on :3000 with the FastAPI
 * backend on :8000 — `webServer.reuseExistingServer` is true and the command is
 * deliberately a no-op-friendly `next dev`. Never run `next build` against this
 * folder while the dev server is up; it corrupts .next and serves 500s for JS
 * chunks.
 */
export default defineConfig({
  testDir: './e2e',
  // `next dev` compiles a route on first request, and during that window the
  // HTML references chunk/CSS URLs that still 404. globalSetup requests every
  // route and waits for its assets to settle, so no assertion has to be relaxed
  // to tolerate a mid-compile page. See e2e/global-setup.ts.
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  // Agent endpoints fan out to Alpaca + Yahoo per symbol; /api/agent/run takes
  // 2-3.5s idle and ~5s when the box is busy, and `next dev` compiles routes on
  // demand. These budgets are deliberately generous so a slow machine reports a
  // real assertion failure rather than a timeout that tells you nothing.
  timeout: 180_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 30_000,
    navigationTimeout: 90_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000/dashboard',
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
