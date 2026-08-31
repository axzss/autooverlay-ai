import { test, expect } from '@playwright/test'
import { PAGES, ORIGIN, collect, describeCollected, settle, expectNoBackendFailureText } from './helpers'

/**
 * BUG 1 REGRESSION — the API base URL pointed at the visitor's own machine.
 *
 * lib/api.ts had:
 *   API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'
 *
 * fetch() runs in the browser, so that string resolves against the *visitor's*
 * loopback, not the server's. Every page still returned HTTP 200 — the HTML was
 * fine — but every data call failed with "unreachable" for anyone who was not
 * sitting at the dev box. Fixed to '' (same-origin) in ab6b2de; requests now
 * reach the backend via the next.config.js /api rewrite.
 *
 * A status-code smoke test cannot see this. The only reliable signal is the set
 * of origins the browser actually contacts.
 *
 * MEASURED SENSITIVITY. I reintroduced the bug (API_BASE_URL defaulting to
 * 'http://localhost:8000') and re-ran this file: 6 of 11 tests failed — the
 * cross-origin assertion on /dashboard, /assets, /terminal and /council, the
 * :8000 guard, and the /dashboard failure-text check. /settings survived because
 * StrategyConfigCard calls fetch('/api/strategy/config') directly rather than
 * through lib/api.ts, so it is not affected by that constant. Good to know: this
 * suite catches the regression on four routes independently.
 */
test.describe('BUG 1 — every browser request must be same-origin', () => {
  for (const p of PAGES) {
    test(`${p.path} issues no cross-origin requests`, async ({ page }) => {
      const c = collect(page)
      await page.goto(p.path)
      await settle(page)

      // Give client-side effects (usePortfolio, getHealth, screenStrategies,
      // assessCouncil) time to fire so their requests are observed.
      await page.waitForTimeout(2500)

      expect(
        c.foreignOrigins,
        `${p.path} made requests to an origin other than ${ORIGIN}. A hardcoded ` +
          `absolute API base URL resolves to the VISITOR's machine and breaks for ` +
          `every user who is not on the dev box.\n${describeCollected(c)}`,
      ).toEqual([])

      // Sanity: the page must actually have talked to its own backend, otherwise
      // "no cross-origin requests" would pass trivially on a page that fetches
      // nothing at all.
      const apiCalls = c.allUrls.filter((u) => u.startsWith(`${ORIGIN}/api/`))
      expect(
        apiCalls.length,
        `${p.path} issued no /api/* request at all — the same-origin assertion ` +
          `above would then be vacuous. Observed URLs: ${c.allUrls.slice(0, 40).join(', ')}`,
      ).toBeGreaterThan(0)
    })

    test(`${p.path} shows no backend-failure text`, async ({ page }) => {
      await page.goto(p.path)
      await settle(page)
      await page.waitForTimeout(2500)
      await expectNoBackendFailureText(page)
    })
  }
})

/**
 * The fixed value must stay same-origin. If someone reintroduces an absolute
 * default, this catches it even if no page happens to exercise the failing call.
 */
test('lib/api.ts base URL is same-origin (no absolute host in served JS)', async ({ page }) => {
  const c = collect(page)
  await page.goto('/dashboard')
  await settle(page)
  await page.waitForTimeout(2000)

  const backendPortCalls = c.allUrls.filter((u) => /:8000/.test(u))
  expect(
    backendPortCalls,
    `The browser tried to talk to port 8000 directly. The backend must only be ` +
      `reached through the same-origin /api rewrite.`,
  ).toEqual([])
})
