import { test, expect, type Page } from '@playwright/test'
import { PAGES } from './helpers'

/**
 * BUG 3 REGRESSION — the dashboard rendered blank on first load.
 *
 * framer-motion serialises its `initial` variant into the server-rendered HTML.
 * With `initial="hidden"` on the fadeUp variant, cards shipped as
 * `opacity:0; transform:translateY(8px)` and stayed invisible until
 * framer-motion booted and animated them in. /dashboard is 257 kB of first-load
 * JS, so that window was long enough for the page to look completely empty.
 * Navigating away and back masked it, because by then React had hydrated.
 *
 * tsc passed. next build passed. Every page returned HTTP 200. The DOM even
 * contained the text — a `toHaveText` assertion would have passed too. Only
 * *visibility* catches it. Fixed in b869874 with useEntranceReady(), which
 * renders a plain div on cold load and only animates on client-side navigation.
 *
 * Three layers of assertion here, deliberately:
 *   A) cold load, fresh context, no prior navigation -> toBeVisible() (Playwright
 *      checks opacity and transform, not just DOM presence)
 *   B) computed opacity immediately after domcontentloaded, before hydration
 *      finishes -> catches a regression at the SSR layer specifically
 *   C) the raw server HTML, fetched without a browser -> no opacity:0 at all
 *
 * MEASURED SENSITIVITY. I reintroduced the bug (forced useEntranceReady() to
 * return true so `initial="hidden"` serialises again) and re-ran this file:
 * layer C failed on all five routes; layers A and B still passed. On a warm local
 * dev server hydration completes inside Playwright's auto-wait window, so the
 * blank-page symptom is not reproducible there — it needed the 257 kB cold first
 * load a real user hit. Layer C is the deterministic detector and the reason this
 * file asserts on raw HTML at all; A and B are kept because they cover the
 * user-visible symptom on slower machines and would catch a CSS-level
 * regression that never touches an inline style.
 */

/**
 * Cumulative computed opacity of an element including every ancestor.
 *
 * An ancestor at opacity:0 makes a child invisible no matter what the child's
 * own opacity says, and framer-motion puts the `initial` variant on the wrapper,
 * not the text. So the whole chain has to be checked.
 *
 * Passed as a real function (not a string): a multi-statement arrow passed as a
 * string is treated by Playwright as a function *body*, which returns undefined.
 */
function cumulativeOpacity(el: Element) {
  let node: Element | null = el
  let opacity = 1
  const chain: string[] = []
  while (node && node.nodeType === 1) {
    const cs = getComputedStyle(node)
    const o = parseFloat(cs.opacity)
    if (!Number.isNaN(o)) opacity *= o
    if (o < 1 || (cs.transform && cs.transform !== 'none')) {
      chain.push(
        `${node.tagName}.${String(node.className || '(no class)').slice(0, 60)} ` +
          `opacity=${cs.opacity} transform=${cs.transform}`,
      )
    }
    node = node.parentElement
  }
  const own = getComputedStyle(el)
  return { opacity, chain, visibility: own.visibility, display: own.display }
}

async function headingLocator(page: Page, heading: string) {
  return page.getByRole('heading', { name: heading, exact: false }).first()
}

test.describe('BUG 3A — cold load: key content is actually VISIBLE', () => {
  for (const p of PAGES) {
    test(`${p.path} paints its heading and content on a cold load`, async ({ browser }) => {
      // A brand-new context guarantees a genuine cold load: no prior navigation,
      // no warm module-scoped hydration flag, empty cache. Navigating away and
      // back is exactly what masked this bug for the original reporter.
      const context = await browser.newContext()
      const page = await context.newPage()
      try {
        await page.goto(p.path, { waitUntil: 'domcontentloaded' })

        const h = await headingLocator(page, p.heading)
        await expect(
          h,
          `"${p.heading}" is in the DOM but not visible on a cold load of ${p.path}. ` +
            `That is BUG 3: framer-motion's initial variant serialised into the ` +
            `server HTML as opacity:0, so the page renders blank until hydration.`,
        ).toBeVisible({ timeout: 15_000 })

        // Not just the heading — at least one content card must be visible too,
        // because the heading on some pages sits outside the animated wrappers.
        const cards = page.locator('.card, [class*="rounded"][class*="border"]')
        const cardCount = await cards.count()
        expect(cardCount, `${p.path} rendered no card-like containers at all`).toBeGreaterThan(0)
        await expect(
          cards.first(),
          `${p.path} rendered card containers but the first one is not visible — ` +
            `an entrance animation left content hidden.`,
        ).toBeVisible({ timeout: 15_000 })
      } finally {
        await context.close()
      }
    })
  }
})

test.describe('BUG 3B — SSR layer: computed opacity is 1 before hydration', () => {
  for (const p of PAGES) {
    test(`${p.path} heading has cumulative opacity 1 at domcontentloaded`, async ({ browser }) => {
      const context = await browser.newContext()
      const page = await context.newPage()
      try {
        // Stop at domcontentloaded: the server HTML plus CSS is applied, but the
        // React bundle has not necessarily finished hydrating. This is precisely
        // the window in which the dashboard used to be blank.
        await page.goto(p.path, { waitUntil: 'domcontentloaded' })

        const h = await headingLocator(page, p.heading)
        await h.waitFor({ state: 'attached', timeout: 15_000 })

        const info = await h.evaluate(cumulativeOpacity)
        expect(
          info.opacity,
          `${p.path}: cumulative computed opacity of "${p.heading}" is ${info.opacity} ` +
            `immediately after domcontentloaded — content ships invisible from the ` +
            `server. Offending chain:\n  ${info.chain.join('\n  ') || '(none reported)'}`,
        ).toBe(1)
        expect(info.visibility, `${p.path}: heading visibility`).not.toBe('hidden')
        expect(info.display, `${p.path}: heading display`).not.toBe('none')
      } finally {
        await context.close()
      }
    })
  }
})

test.describe('BUG 3C — raw server HTML carries no hidden-state styles', () => {
  for (const p of PAGES) {
    test(`${p.path} server HTML has no opacity:0 style attribute`, async ({ request }) => {
      // A plain HTTP request — no browser, no JS, no hydration. This is what a
      // user's browser receives and paints first, and what a crawler sees.
      const res = await request.get(p.path)
      expect(res.status(), `${p.path} must serve 200`).toBe(200)
      const html = await res.text()

      // framer-motion writes the initial variant as an inline style, e.g.
      //   style="opacity:0;transform:translateY(8px)"
      const hidden = html.match(/style="[^"]*opacity:\s*0[^."\d][^"]*"/g) ?? []
      expect(
        hidden,
        `${p.path} server HTML contains inline opacity:0 styles. Content shipped ` +
          `from the server must be visible without JavaScript. Matches: ` +
          `${JSON.stringify(hidden.slice(0, 5))}`,
      ).toEqual([])

      // translateY entrance offsets in the server HTML are the same defect.
      // translateY(-50%) is legitimate — it is the sidebar active-marker's static
      // centring transform, not an entrance animation — so only positive/negative
      // pixel offsets are flagged.
      const shifted = html.match(/translateY\(\s*-?\d+(\.\d+)?px\s*\)/g) ?? []
      expect(
        shifted,
        `${p.path} server HTML contains a pixel translateY offset, which is a ` +
          `framer-motion entrance variant leaking into SSR. Matches: ` +
          `${JSON.stringify(shifted.slice(0, 5))}`,
      ).toEqual([])

      // The heading text must be in the server HTML at all — server-rendered
      // content, not something only JS can produce.
      const needle = p.heading.replace(/&/g, '&amp;')
      expect(
        html.includes(needle) || html.includes(p.heading),
        `${p.path} server HTML does not contain "${p.heading}" — the page depends ` +
          `entirely on client JS to render its own title.`,
      ).toBe(true)
    })
  }
})
