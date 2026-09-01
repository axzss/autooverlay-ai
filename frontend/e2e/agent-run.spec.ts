import { test, expect } from '@playwright/test'
import { collect, describeCollected, runAgentAndWaitForResponse, authenticateDemoUser } from './helpers'

/**
 * Agent run flow on /dashboard.
 *
 * POST /api/agent/run fans out to Alpaca and Yahoo per symbol and takes 2-3.5s,
 * so these tests get a long timeout. The backend returns 41 flat reasoning
 * lines for an eight-symbol run; lib/reasoning.ts regroups them client-side into
 * one row per symbol with a "raw" toggle back to the untouched trace.
 */
test.describe('agent run flow', () => {
  test.setTimeout(240_000)

  test('run button populates the reasoning panel with grouped per-symbol rows', async ({ page }) => {
    const c = collect(page)
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' })
    const csrfToken = await authenticateDemoUser(page)
    if (!csrfToken) {
      // Rate-limited — wait for window to reset and retry
      await page.waitForTimeout(65_000)
      await authenticateDemoUser(page)
    }
    // After login, navigate to dashboard and wait for hydration
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' })

    const panel = page.locator('.card').filter({ hasText: /Agent Reasoning/i }).first()
    await expect(panel, 'the Agent Reasoning card must render').toBeVisible()

    // Before the run: the empty-state copy, not a fabricated log. This panel used
    // to ship a hardcoded trace claiming an order had executed and a $120 premium
    // had been harvested. None of that ever happened.
    await expect(panel.getByText(/No reasoning trace yet/i)).toBeVisible()

    const runBtn = page.getByRole('button', { name: /Run Agent Now/i })
    await expect(runBtn).toBeVisible()
    await expect(runBtn).toBeEnabled()

    // Visible + enabled is NOT clickable here: the button is server-rendered, so
    // both assertions pass on plain HTML with no onClick attached, and the click
    // is silently swallowed. Measured: clicking immediately after
    // domcontentloaded produced zero POSTs. This helper clicks until the POST is
    // actually observed on the wire.
    const res = await runAgentAndWaitForResponse(page)
    expect(res.status(), 'POST /api/agent/run must succeed').toBe(200)
    const body = await res.json()

    // Footer reconciles what the backend sent against what is displayed:
    // "<n> symbols · <m> trace lines · run <id>".
    const footer = panel.getByText(/trace line/i)
    await expect(footer, 'the reasoning footer must appear once a run completes').toBeVisible({
      timeout: 60_000,
    })
    const footerText = (await footer.textContent()) ?? ''

    const traceLen: number = (body.reasoning_trace ?? []).length
    expect(traceLen, `backend returned no reasoning_trace: ${footerText}`).toBeGreaterThan(0)
    expect(
      footerText,
      `the footer must report the same trace line count the backend returned (${traceLen})`,
    ).toContain(`${traceLen} trace line`)

    // Grouped view: one collapsible row per symbol, fewer rows than raw lines.
    // The backend's 41 lines collapse to 8 symbol rows.
    const symbolRows = panel.locator('button[aria-expanded]')
    const rowCount = await symbolRows.count()
    expect(
      rowCount,
      `the reasoning panel must group the ${traceLen} flat trace lines into ` +
        `per-symbol rows, but rendered ${rowCount} rows. Footer: ${footerText}`,
    ).toBeGreaterThan(0)
    expect(
      rowCount,
      `grouped view must have strictly fewer rows (${rowCount}) than raw trace ` +
        `lines (${traceLen}) — otherwise it is not grouping anything.`,
    ).toBeLessThan(traceLen)

    // The footer's own symbol count must match the rows actually painted.
    const symbolMatch = footerText.match(/(\d+)\s+symbols?/)
    expect(symbolMatch, `footer must state a symbol count: ${footerText}`).not.toBeNull()
    expect(
      Number(symbolMatch![1]),
      `footer claims ${symbolMatch?.[1]} symbols but ${rowCount} rows are rendered`,
    ).toBe(rowCount)

    // Each row must be visible and carry a ticker, not render as an empty shell.
    for (let i = 0; i < rowCount; i++) {
      const row = symbolRows.nth(i)
      await expect(row, `symbol row ${i} must be visible`).toBeVisible()
      const text = ((await row.textContent()) ?? '').trim()
      expect(text.length, `symbol row ${i} rendered empty`).toBeGreaterThan(0)
    }

    // A 'raw' toggle must exist so the untouched backend trace stays inspectable.
    const rawToggle = panel.getByRole('button', { name: /^raw$/i })
    await expect(
      rawToggle,
      `a "raw" toggle must exist — regrouping agent output is only acceptable if ` +
        `the original trace remains one click away.`,
    ).toBeVisible()

    // Toggling shows the flat trace: as many numbered lines as the backend sent.
    await rawToggle.click()
    await expect(panel.getByRole('button', { name: /^grouped$/i })).toBeVisible()
    // Scope to the raw container specifically. A bare `div.flex.gap-2` also
    // matches the panel's own header row (`flex items-center gap-2 …`), which
    // made the count 42 instead of 41 — a locator bug, not a rendering bug.
    const rawContainer = panel.locator('div.font-mono.leading-relaxed')
    const rawLines = rawContainer.locator('> div')
    await expect(
      rawLines,
      `raw view must render all ${traceLen} backend trace lines verbatim`,
    ).toHaveCount(traceLen, { timeout: 20_000 })

    expect(
      { consoleErrors: c.consoleErrors, pageErrors: c.pageErrors },
      `the agent run produced browser errors:\n${describeCollected(c)}`,
    ).toEqual({ consoleErrors: [], pageErrors: [] })
  })

  test('grouped reasoning never renders a line longer than 300 characters', async ({ page }) => {
    // See the note above: domcontentloaded, not 'load'.
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' })
    const csrfToken = await authenticateDemoUser(page)
    if (!csrfToken) {
      // Rate-limited — wait for window to reset and retry
      await page.waitForTimeout(65_000)
      await authenticateDemoUser(page)
    }
    const panel = page.locator('.card').filter({ hasText: /Agent Reasoning/i }).first()
    await expect(panel, 'the Agent Reasoning card must render').toBeVisible()
    // Hydration race — see runAgentAndWaitForResponse.
    const res = await runAgentAndWaitForResponse(page)
    const body = await res.json()
    await expect(panel.getByText(/trace line/i)).toBeVisible({ timeout: 60_000 })

    // Sanity: the backend really does emit an over-long line, so this test is
    // exercising the trimming rather than passing vacuously.
    const backendMax = Math.max(
      ...((body.reasoning_trace ?? []) as string[]).map((l: string) => l.length),
      0,
    )
    expect(
      backendMax,
      `backend no longer emits a long line (max ${backendMax}); this test would ` +
        `pass trivially. Verify the trimming is still needed.`,
    ).toBeGreaterThan(300)

    // Expand every symbol row so gate/citation/verdict detail is in the DOM.
    const rows = panel.locator('button[aria-expanded]')
    const rowCount = await rows.count()
    for (let i = 0; i < rowCount; i++) {
      const row = rows.nth(i)
      if ((await row.getAttribute('aria-expanded')) === 'false' && (await row.isEnabled())) {
        await row.click()
      }
    }

    // Measure leaf text nodes: every string the user actually reads as one line.
    const longLines: string[] = await panel.evaluate((root: Element) => {
      const out: string[] = []
      const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
      let n = walk.nextNode()
      while (n) {
        const t = (n.textContent ?? '').trim()
        if (t.length > 300) out.push(t)
        n = walk.nextNode()
      }
      return out
    })

    expect(
      longLines.map((l) => `${l.length} chars: ${l.slice(0, 120)}…`),
      `the grouped reasoning panel is rendering text runs longer than 300 ` +
        `characters. The "; cited:" tail restates gate lines already shown above ` +
        `and must stay trimmed.`,
    ).toEqual([])
  })
})
