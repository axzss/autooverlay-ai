import { test, expect } from '@playwright/test'
import { PAGES, collect, describeCollected, settle, authenticateDemoUser } from './helpers'

/**
 * Console and uncaught-error hygiene.
 *
 * Nothing is allow-listed. A console error is a real signal: hydration
 * mismatches, failed fetches, React key warnings escalated to errors and
 * uncaught exceptions in effects all surface here and none of them show up in
 * an HTTP status code.
 *
 * If a legitimate error ever fires (a third-party script, a known dev-only
 * warning), add it to an explicit named allow-list here WITH a comment saying
 * what it is and why it is acceptable. Do not widen a regex to make a test green.
 */
test.describe('console hygiene', () => {
  for (const p of PAGES) {
      test(`${p.path} logs no console errors or page errors`, async ({ page }) => {
        const c = collect(page)
        // Protected pages need auth: without it the AuthProvider redirect means
        // we never land on the page that actually does the work.
        const isProtected = ['/terminal', '/settings', '/risk', '/blotter', '/lab'].includes(p.path)
        if (isProtected) {
          await authenticateDemoUser(page).catch(async () => {
            // Rate-limited — wait for window to reset and retry
            await page.waitForTimeout(65_000)
            await authenticateDemoUser(page)
          })
          await page.goto(p.path)
          // Wait for AuthProvider.checkAuth() to succeed (no 401) before measuring
          await expect(page.locator('h1')).toBeVisible({ timeout: 15_000 })
        } else {
          await page.goto(p.path, { waitUntil: 'domcontentloaded' })
        }
        await settle(page)
        // Client effects fire after hydration; give them room to throw.
        await page.waitForTimeout(3000)

        expect(
          { consoleErrors: c.consoleErrors, pageErrors: c.pageErrors },
          `${p.path} produced browser errors during load:\\n${describeCollected(c)}`,
        ).toEqual({ consoleErrors: [], pageErrors: [] })
      })
    }
})

/**
 * Failed network requests. A 404 on a JS chunk is the signature of a corrupted
 * .next directory (which is what happens if `next build` runs while `next dev`
 * is serving the same folder) and produces a silently broken page.
 */
test.describe('asset delivery', () => {
  for (const p of PAGES) {
      test(`${p.path} loads every asset it requests`, async ({ page }) => {
        const bad: string[] = []
        page.on('response', (res) => {
          const url = res.url()
          // Only chunk/asset delivery. API responses have their own tests, and a
          // 404 on bare /health is expected and asserted elsewhere.
          if (/\/_next\/|\.js($|\?)|\.css($|\?)/.test(url) && res.status() >= 400) {
            bad.push(`${res.status()} ${url}`)
          }
        })
        const isProtected = ['/terminal', '/settings', '/risk', '/blotter', '/lab'].includes(p.path)
        if (isProtected) {
          await authenticateDemoUser(page)
          await page.goto(p.path)
          // Wait for AuthProvider.checkAuth() to succeed before measuring
          await expect(page.locator('h1')).toBeVisible({ timeout: 15_000 })
        } else {
          await page.goto(p.path, { waitUntil: 'domcontentloaded' })
        }
        await settle(page)
        expect(
          bad,
          `${p.path} failed to deliver assets. A 4xx/5xx on a _next chunk usually ` +
            `means .next is corrupted — never run \`next build\` while \`next dev\` ` +
            `is serving the same folder.`,
        ).toEqual([])
      })
    }
})
