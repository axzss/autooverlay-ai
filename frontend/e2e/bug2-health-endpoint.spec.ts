import { test, expect } from '@playwright/test'
import { agentStatusCard, settle } from './helpers'

/**
 * BUG 2 REGRESSION — the health check requested bare /health and 404'd.
 *
 * api.getHealth() called '/health'. From the browser that is the *Next* origin,
 * where no such page exists, so it 404'd and AgentStatusCard rendered
 * "Backend unreachable" while the FastAPI backend was perfectly healthy.
 *
 * The backend serves health bare at :8000/health, and next.config.js maps
 * /api/health -> :8000/health precisely because the Next rewrite only proxies
 * paths under /api. Fixed in 69cdf8c.
 *
 * Note the asymmetry asserted below: /api/health returning 200 and /health
 * returning 404 are BOTH correct. The 404 is not a bug — /health is not a page.
 *
 * MEASURED SENSITIVITY. I reintroduced the bug (getHealth() calling '/health')
 * and re-ran this file: the card test failed — no OK badge, "Backend
 * unreachable" rendered instead. The two API-level tests still passed, which is
 * the point: the endpoints themselves were never broken, only the path the
 * client chose, so the browser-level assertion is the one that catches it.
 */
test.describe('BUG 2 — health check must go through the /api rewrite', () => {
  test('GET /api/health returns 200 with a healthy payload', async ({ request }) => {
    const res = await request.get('/api/health')
    expect(
      res.status(),
      `GET /api/health must be 200 — this is the path the browser uses and the ` +
        `only one the Next rewrite proxies to the backend.`,
    ).toBe(200)
    const body = await res.json()
    expect(body.status, `/api/health payload: ${JSON.stringify(body)}`).toBe('ok')
  })

  test('GET /health returns 404 (correct — it is not a Next page)', async ({ request }) => {
    const res = await request.get('/health')
    expect(
      res.status(),
      `Bare /health should 404 from the Next origin. If this ever returns 200, ` +
        `a page or rewrite was added and the reasoning behind api.getHealth() ` +
        `using /api/health needs revisiting.`,
    ).toBe(404)
  })

  test('/dashboard agent status card reports healthy, not unreachable', async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' })
    // Wait for the health fetch to resolve rather than waiting for full
    // networkidle, which stalls on the dev HMR socket forever.
    await page.waitForResponse(
      (r) => r.url().includes('/api/health') && r.status() === 200,
      { timeout: 15_000 },
    ).catch(() => {}) // health fetch may have already completed before we attach

    const heading = page.getByRole('heading', { name: /Agent status/i })
    await expect(heading, 'the Agent status card must render').toBeVisible()

    // Scope to the card itself, not the whole page: the Header has its own
    // animate-pulse dot ("VPS: ONLINE") that pulses forever, so a page-wide
    // skeleton check could never pass. See agentStatusCard() for why a plain
    // `filter({ has: heading })` is too loose.
    const card = agentStatusCard(page)

    // The error branch renders "Backend unreachable (<message>)". It must not appear.
    await expect(
      page.getByText(/Backend unreachable/i),
      `AgentStatusCard is showing "Backend unreachable". That is exactly BUG 2: ` +
        `a health request that misses the /api rewrite 404s and is reported as a ` +
        `dead backend even when the backend is healthy.`,
    ).toHaveCount(0)

    // Positive assertion: the OK badge must actually be painted, not merely
    // absent-of-error. The card renders the status text uppercased. The badge
    // is a span containing a colored dot + the text node. Match the inline
    // span that carries the background class and contains the literal "OK".
    await expect(
      card.locator('span.bg-[#052e16], span.bg-\\[\\\\#052e16\\\\]').filter({ hasText: /^OK$/i })
        .first(),
      'the Backend status badge must read OK',
    ).toBeVisible({ timeout: 20_000 })

    // Alpaca row. b4edc57 relabelled this: the row label went "Alpaca configured"
    // -> "Alpaca" and the badge went TRUE/FALSE -> "Paper trading live" / "Mock
    // mode". Same underlying field (health.alpaca_configured), friendlier words.
    // Assert the current copy, and assert the configured state specifically —
    // credentials are present in this environment, so "Mock mode" here would mean
    // the health payload lost alpaca_configured.
    await expect(card.getByText('Alpaca', { exact: true })).toBeVisible()
    await expect(
      card.getByText(/Paper trading live/i),
      'Alpaca credentials are configured in this environment, so the badge must ' +
        'read "Paper trading live" — "Mock mode" means health.alpaca_configured ' +
        'came back false or missing.',
    ).toBeVisible()

    // The loading skeleton inside THIS card must have resolved — a card stuck in
    // skeleton state is indistinguishable from a broken one to a user.
    await expect(
      card.locator('.animate-pulse'),
      'the Agent status card must leave its loading skeleton',
    ).toHaveCount(0, { timeout: 15_000 })
  })
})
