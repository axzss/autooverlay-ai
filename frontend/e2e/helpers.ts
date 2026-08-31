import { expect, type Page, type Request, type ConsoleMessage } from '@playwright/test'

/** The five real routes. `/` only client-redirects to /dashboard. */
export const PAGES = [
  { path: '/dashboard', name: 'Dashboard', heading: 'Dashboard' },
  { path: '/assets', name: 'Assets', heading: 'Portfolio Assets & History' },
  { path: '/terminal', name: 'Terminal', heading: 'AI Agent Terminal' },
  { path: '/council', name: 'Council', heading: 'Investment Council' },
  { path: '/settings', name: 'Settings', heading: 'Settings' },
] as const

export const ORIGIN = 'http://localhost:3000'

/**
 * Text that means the frontend could not reach its own backend.
 * These strings come from lib/api.ts (`API <path> unreachable` /
 * `API <path> timed out`) and from the fallback banners that render them.
 */
export const BACKEND_FAILURE_TEXT = /unreachable|timed out|Backend unavailable/i

export interface Collected {
  consoleErrors: string[]
  pageErrors: string[]
  /** Requests to an absolute origin other than the page's own. */
  foreignOrigins: { url: string; origin: string }[]
  /** Every request the browser issued, for diagnostics. */
  allUrls: string[]
  failedRequests: { url: string; failure: string | null }[]
}

/**
 * Attaches collectors for console errors, uncaught page errors and
 * cross-origin requests.
 *
 * Cross-origin detection is the BUG 1 regression signal: a browser fetch to
 * http://localhost:8000 is a request to the *visitor's* machine, which works
 * only on the dev box. Everything the app needs must be same-origin and reach
 * the backend through the next.config.js rewrite.
 *
 * Nothing is allow-listed. If a legitimate third-party origin (fonts, CDN,
 * telemetry) is ever added, add it here with a comment naming it — never
 * silently widen the filter.
 */
export function collect(page: Page): Collected {
  const c: Collected = {
    consoleErrors: [],
    pageErrors: [],
    foreignOrigins: [],
    allUrls: [],
    failedRequests: [],
  }

  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() === 'error') c.consoleErrors.push(msg.text())
  })
  page.on('pageerror', (err: Error) => {
    c.pageErrors.push(`${err.name}: ${err.message}`)
  })
  page.on('request', (req: Request) => {
    const url = req.url()
    c.allUrls.push(url)
    if (!/^https?:/i.test(url)) return // data:, blob:, about: — not network
    const origin = new URL(url).origin
    if (origin !== ORIGIN) c.foreignOrigins.push({ url, origin })
  })
  page.on('requestfailed', (req: Request) => {
    c.failedRequests.push({ url: req.url(), failure: req.failure()?.errorText ?? null })
  })

  return c
}

/** Formats collector state for a readable assertion message. */
export function describeCollected(c: Collected): string {
  const parts: string[] = []
  if (c.foreignOrigins.length)
    parts.push(`cross-origin requests: ${c.foreignOrigins.map((f) => f.url).join(', ')}`)
  if (c.consoleErrors.length) parts.push(`console errors: ${c.consoleErrors.join(' | ')}`)
  if (c.pageErrors.length) parts.push(`page errors: ${c.pageErrors.join(' | ')}`)
  return parts.join('\n') || '(nothing collected)'
}

/**
 * Waits until the page has settled enough to judge it: the heading is painted
 * and the client-side data fetches have had a chance to resolve or fail.
 */
export async function settle(page: Page): Promise<void> {
  await page.waitForLoadState('domcontentloaded')
  // networkidle can hang forever on a dev server with HMR websockets, so this
  // is a bounded wait rather than a hard requirement.
  await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})
}

/** Asserts no visible element on the page is announcing a dead backend. */
export async function expectNoBackendFailureText(page: Page): Promise<void> {
  const failures = page.getByText(BACKEND_FAILURE_TEXT)
  const count = await failures.count()
  const visible: string[] = []
  for (let i = 0; i < count; i++) {
    const el = failures.nth(i)
    if (await el.isVisible()) visible.push(((await el.textContent()) ?? '').trim())
  }
  expect(
    visible,
    `Page ${page.url()} is telling the user the backend is unreachable. ` +
      `That is BUG 1 / BUG 2 behaviour (absolute API base URL, or a health path ` +
      `that bypasses the /api rewrite). Visible text: ${JSON.stringify(visible)}`,
  ).toEqual([])
}

/**
 * The AgentStatusCard on /dashboard, scoped tightly.
 *
 * `locator('div').filter({ has: heading })` is not enough: it also matches the
 * inner flex row holding the icon and the <h2>, and that row contains none of
 * the badges. The card is the `space-y-2` wrapper.
 */
export function agentStatusCard(page: Page) {
  return page
    .locator('div.space-y-2')
    .filter({ has: page.getByRole('heading', { name: /Agent status/i }) })
    .first()
}

/** Matches the agent-run call regardless of how the URL is spelled. */
const isAgentRun = (url: string) => url.includes('/api/agent/run')

/**
 * Blocks until React has hydrated /dashboard, proven by an observable side
 * effect rather than by rendering timing.
 *
 * WHY THIS IS NEEDED — a genuine property of the app, not test scaffolding:
 * "Run Agent Now" ships in the server-rendered HTML, so both `toBeVisible()`
 * and `toBeEnabled()` pass while the page is still just markup. Clicking then
 * does absolutely nothing — no onClick is attached yet, so POST /api/agent/run
 * is never issued and the run silently does not happen. Measured directly: an
 * immediate click after domcontentloaded produced zero POSTs; the same click
 * behind this gate produced the request every time. That is the same family as
 * the three bugs this suite exists for — HTML that looks correct while the page
 * is not yet functional.
 *
 * usePortfolio() and AgentStatusCard both fetch on mount, and those fetches can
 * only happen after hydration, so a completed one is direct evidence the client
 * tree is live. An earlier version watched the status badge instead; that lagged
 * under load and produced a misleading timeout.
 */
export async function waitForDashboardHydration(page: Page): Promise<void> {
  await page.waitForResponse(
    (r) => /\/api\/(portfolio|health)/.test(r.url()) && r.status() === 200,
    { timeout: 60_000 },
  )
}

/**
 * Clicks "Run Agent Now" until the POST actually leaves the browser, then
 * returns the response.
 *
 * A single click is not reliable for the reason described above: in the
 * pre-hydration window the click is swallowed with no request, no error and no
 * feedback. So wait for hydration evidence, then click and confirm the request
 * was actually issued, retrying if it was swallowed. The button disables itself
 * while running, so a duplicate click is a no-op.
 *
 * This only removes a race the test must not lose. It does not weaken any
 * assertion about what the app renders afterwards.
 */
export async function runAgentAndWaitForResponse(page: Page) {
  await waitForDashboardHydration(page)

  const responsePromise = page.waitForResponse(
    (r) => isAgentRun(r.url()) && r.request().method() === 'POST',
    { timeout: 150_000 },
  )

  const button = page.getByRole('button', { name: /Run Agent Now/i })
  let issued = false
  const deadline = Date.now() + 60_000
  let lastError = ''

  while (!issued && Date.now() < deadline) {
    const requestSeen = page
      .waitForRequest((r) => isAgentRun(r.url()) && r.method() === 'POST', { timeout: 6_000 })
      .then(() => true)
      .catch((e: Error) => {
        lastError = e.message
        return false
      })
    await button.click({ timeout: 15_000 }).catch((e: Error) => {
      lastError = e.message
    })
    issued = await requestSeen
  }

  expect(
    issued,
    `clicking "Run Agent Now" never issued POST /api/agent/run. The button is ` +
      `server-rendered, so it looks clickable before React attaches its handler ` +
      `— a real user clicking that early also gets nothing. Last error: ${lastError}`,
  ).toBe(true)

  return responsePromise
}
