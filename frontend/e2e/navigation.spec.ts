import { test, expect } from '@playwright/test'
import { PAGES } from './helpers'

/**
 * Sidebar navigation: clicking each of the five links must change the URL and
 * move the active marker.
 *
 * The active state is driven by usePathname() and rendered as
 * aria-current="page" plus an emerald marker with layoutId. A route change that
 * leaves the marker behind means the nav is lying about where the user is.
 */
test.describe('desktop sidebar navigation', () => {
  test('all five links navigate and the active marker follows', async ({ page }) => {
    await page.goto('/dashboard')
    const sidebar = page.locator('aside')
    await expect(sidebar, 'desktop sidebar must be visible at 1440px').toBeVisible()

    for (const p of PAGES) {
      const link = sidebar.getByRole('link', { name: p.name, exact: true })
      await expect(link, `sidebar must contain a ${p.name} link`).toBeVisible()
      await link.click()

      await expect(page, `clicking ${p.name} must navigate to ${p.path}`).toHaveURL(
        new RegExp(`${p.path}$`),
      )

      // The active marker moved: exactly one link carries aria-current="page",
      // and it is this one.
      const current = sidebar.locator('a[aria-current="page"]')
      await expect(
        current,
        `after navigating to ${p.path} exactly one sidebar link must be marked active`,
      ).toHaveCount(1)
      await expect(
        current,
        `the active sidebar link must be ${p.name}, not something else`,
      ).toHaveAttribute('href', p.path)

      // And the destination page actually painted, not just changed URL.
      await expect(
        page.getByRole('heading', { name: p.heading, exact: false }).first(),
        `${p.path} heading must be visible after client-side navigation`,
      ).toBeVisible({ timeout: 15_000 })
    }
  })

  test('/ redirects to /dashboard', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 15_000 })
    await expect(page.getByRole('heading', { name: 'Dashboard' }).first()).toBeVisible()
  })
})

/**
 * Mobile drawer at 390x844 (iPhone 14 logical viewport).
 *
 * The desktop sidebar is `hidden lg:flex`, so below lg the ONLY way to navigate
 * is the hamburger -> MobileSidebar drawer. If the hamburger does not appear or
 * the drawer does not open, the app is unnavigable on a phone while every page
 * still returns HTTP 200.
 */
test.describe('mobile drawer (390x844)', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('hamburger opens a drawer with nav links, and closes', async ({ page }) => {
    await page.goto('/dashboard')

    // Desktop sidebar must be hidden at this width.
    await expect(
      page.locator('aside'),
      'the desktop sidebar must not be visible on a phone viewport',
    ).toBeHidden()

    const hamburger = page.getByRole('button', { name: /Open navigation menu/i })
    await expect(hamburger, 'hamburger must be visible below lg').toBeVisible()

    await hamburger.click()

    // The drawer is a fixed panel containing the same five nav links.
    const closeBtn = page.getByRole('button', { name: /Close navigation menu/i })
    await expect(closeBtn, 'drawer must open and expose a close button').toBeVisible()

    for (const p of PAGES) {
      await expect(
        page.getByRole('link', { name: p.name, exact: true }),
        `mobile drawer must contain a visible ${p.name} link`,
      ).toBeVisible()
    }

    await closeBtn.click()
    await expect(
      closeBtn,
      'drawer must close when the close button is clicked (AnimatePresence exit)',
    ).toBeHidden({ timeout: 10_000 })
  })

  test('drawer link navigates and closes the drawer', async ({ page }) => {
    await page.goto('/dashboard')
    await page.getByRole('button', { name: /Open navigation menu/i }).click()
    await page.getByRole('link', { name: 'Settings', exact: true }).click()

    await expect(page).toHaveURL(/\/settings$/)
    await expect(
      page.getByRole('button', { name: /Close navigation menu/i }),
      'the drawer must close after navigating',
    ).toBeHidden({ timeout: 10_000 })
    await expect(page.getByRole('heading', { name: 'Settings' }).first()).toBeVisible()
  })

  test('every page renders its heading visibly on a phone viewport', async ({ page }) => {
    for (const p of PAGES) {
      await page.goto(p.path, { waitUntil: 'domcontentloaded' })
      await expect(
        page.getByRole('heading', { name: p.heading, exact: false }).first(),
        `${p.path} must render visibly at 390x844`,
      ).toBeVisible({ timeout: 15_000 })
    }
  })
})
