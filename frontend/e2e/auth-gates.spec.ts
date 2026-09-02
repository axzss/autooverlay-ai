import { test, expect } from '@playwright/test'
import { authenticateDemoUser } from './helpers'

/**
 * Auth gate e2e tests — mutation-verified like bug1/2/3.
 *
 * These tests assert:
 * 1. Public pages accessible without login (dashboard, assets, council)
 * 2. Protected pages redirect to /login when unauthenticated
 * 3. Login works and sets session
 * 4. Protected pages accessible after login
 * 5. CSRF required for mutating endpoints
 * 6. Logout clears session and redirects
 * 7. Session persists across navigation
 * 8. Rate limiting on login endpoint
 *
 * IMPORTANT: Playwright runs with workers=1 (fullyParallel=false), so tests
 * share a single browser context. The in-process rate limiter in auth.py
 * allows 5 logins/min — we must not exhaust that across tests. The rate-limit
 * test is last and waits 65s for the window to reset.
 */

test.describe('Auth gates', () => {
  const BASE = process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000'

  test.beforeEach(async ({ page }) => {
    // Clear any existing session
    await page.context().clearCookies()
    await page.context().clearPermissions()
  })

  test('public pages load without login', async ({ page }) => {
    for (const path of ['/dashboard', '/assets', '/council']) {
      const response = await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
      expect(response?.status()).toBe(200)
      // Should NOT redirect to login
      expect(page.url()).not.toContain('/login')
    }
  })

  test('protected pages redirect to login when unauthenticated', async ({ page }) => {
    for (const path of ['/terminal', '/settings']) {
      await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
      // Client-side redirect fires after AuthProvider.checkAuth resolves (401 → null user)
      await page.waitForURL('**/login', { timeout: 30_000 })
      expect(page.url()).toContain('/login')
    }
  })

  test('login works with correct credentials', async ({ page }) => {
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await expect(page.locator('h1')).toContainText('AutoOverlay AI')

    await page.fill('input#username', 'DitJiZak_IT_BOYS')
    await page.fill('input#password', 'alpacaitboys')
    await page.click('button[type="submit"]')

    // Should redirect to dashboard after successful login
    await page.waitForURL('**/dashboard', { timeout: 15_000 })
    expect(page.url()).toContain('/dashboard')
  })

  test('login fails with wrong password', async ({ page }) => {
    // NOTE: This test fires a login attempt that counts toward the 5/min rate
    // limit on the same IP (localhost). Since tests run sequentially with
    // workers=1, this attempt will count. The rate-limiting test at the end
    // waits 65s for the window to reset before firing its own 5 attempts.
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await page.fill('input#username', 'DitJiZak_IT_BOYS')
    await page.fill('input#password', 'WRONG')
    await page.click('button[type="submit"]')

    // Should show error, stay on login page
    await expect(page.locator('text=Invalid credentials')).toBeVisible({ timeout: 15_000 })
    expect(page.url()).toContain('/login')
  })

  test('protected pages accessible after login', async ({ page }) => {
    // Use authenticateDemoUser (page.evaluate fetch) instead of form login
    // to avoid exhausting the rate limiter across tests.
    await page.goto('/login', { waitUntil: 'domcontentloaded' })
    await authenticateDemoUser(page)
    // Navigate to dashboard and wait for auth + hydration to settle
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('a:has-text("Terminal")')).toBeVisible({ timeout: 30_000 })

    // Now protected pages should work
    for (const path of ['/terminal', '/settings']) {
      await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
      await page.waitForURL(`**${path}`, { timeout: 15_000 })
      expect(page.url()).toContain(path)
      expect(page.url()).not.toContain('/login')
    }
  })

  test('logout clears session and redirects to login', async ({ page }) => {
    // Login via form so AuthProvider sets up the full auth state.
    // We use a fresh page.context() to ensure no rate-limit pollution from
    // other tests — the 5/min limiter is in-process and shared across the
    // worker, so we add a brief backoff if needed.
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await page.fill('input#username', 'DitJiZak_IT_BOYS')
    await page.fill('input#password', 'alpacaitboys')
    await page.click('button[type="submit"]')
    const loginRes = await page.waitForResponse((r) => r.url().includes('/api/auth/login'), { timeout: 15_000 })
    // If rate-limited, wait for the window to reset and retry
    if (loginRes.status() === 429) {
      await page.waitForTimeout(65_000)
      await page.fill('input#username', 'DitJiZak_IT_BOYS')
      await page.fill('input#password', 'alpacaitboys')
      await page.click('button[type="submit"]')
    }
    await page.waitForURL('**/dashboard', { timeout: 15_000 })

    // Wait for AuthProvider to finish loading so header renders the logout button
    await expect(page.locator('a:has-text("Terminal")')).toBeVisible({ timeout: 20_000 })

    // Click logout button in header (icon-only, has LogOut svg)
    await page.click('header button:has(svg[data-lucide="log-out"])', { timeout: 10_000 })
    // Wait for redirect to login
    await page.waitForURL('**/login', { timeout: 15_000 })
    expect(page.url()).toContain('/login')

    // Protected page should now redirect
    await page.goto(`${BASE}/terminal`, { waitUntil: 'domcontentloaded' })
    await page.waitForURL('**/login', { timeout: 30_000 })
    expect(page.url()).toContain('/login')
  })

  test('CSRF required for mutating endpoints', async ({ page }) => {
    // Login via form so AuthProvider's syncCsrf stores the token in module state
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await page.fill('input#username', 'DitJiZak_IT_BOYS')
    await page.fill('input#password', 'alpacaitboys')
    await page.click('button[type="submit"]')
    // If rate-limited, wait for the window to reset and retry
    const loginRes = await page.waitForResponse((r) => r.url().includes('/api/auth/login'), { timeout: 15_000 })
    if (loginRes.status() === 429) {
      await page.waitForTimeout(65_000)
      await page.fill('input#username', 'DitJiZak_IT_BOYS')
      await page.fill('input#password', 'alpacaitboys')
      await page.click('button[type="submit"]')
    }
    await page.waitForURL('**/dashboard', { timeout: 15_000 })

    // Wait for AuthProvider to finish loading so header renders
    await expect(page.locator('a:has-text("Terminal")')).toBeVisible({ timeout: 20_000 })

    // Go to terminal
    await page.goto(`${BASE}/terminal`, { waitUntil: 'domcontentloaded' })
    await page.waitForURL('**/terminal', { timeout: 15_000 })

    // POST /api/agent/run WITHOUT a CSRF header should get 403.
    // We use page.evaluate to bypass api.ts which auto-attaches the token
    // from AuthProvider's module state.
    const noCsrfStatus = await page.evaluate(async () => {
      const res = await fetch('/api/agent/run', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbols: ['AAPL'] }),
      })
      return res.status
    })
    expect(noCsrfStatus, 'POST without CSRF must be rejected').toBe(403)

    // Verify session cookie is set — check via API (cookie is HttpOnly)
    const meStatus = await page.evaluate(async () => {
      const res = await fetch('/api/auth/me', { credentials: 'include' })
      return res.status
    })
    expect(meStatus, 'session must be active after login').toBe(200)
  })

  test('session persists across navigation', async ({ page }) => {
    // Login via form so AuthProvider picks up the session
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await page.fill('input#username', 'DitJiZak_IT_BOYS')
    await page.fill('input#password', 'alpacaitboys')
    await page.click('button[type="submit"]')
    // If rate-limited, wait for the window to reset and retry
    const loginRes = await page.waitForResponse((r) => r.url().includes('/api/auth/login'), { timeout: 15_000 })
    if (loginRes.status() === 429) {
      await page.waitForTimeout(65_000)
      await page.fill('input#username', 'DitJiZak_IT_BOYS')
      await page.fill('input#password', 'alpacaitboys')
      await page.click('button[type="submit"]')
    }
    await page.waitForURL('**/dashboard', { timeout: 15_000 })
    await expect(page.locator('a:has-text("Terminal")')).toBeVisible({ timeout: 20_000 })

    // Navigate around (domcontentloaded, not networkidle — HMR socket)
    await page.goto(`${BASE}/assets`, { waitUntil: 'domcontentloaded' })
    await expect(page.locator('h1')).toContainText('Portfolio Assets & History')

    await page.goto(`${BASE}/council`, { waitUntil: 'domcontentloaded' })
    await expect(page.locator('h1')).toContainText('Investment Council')

    await page.goto(`${BASE}/terminal`, { waitUntil: 'domcontentloaded' })
    await page.waitForURL('**/terminal', { timeout: 15_000 })
    await expect(page.locator('h1')).toContainText('AI Agent Terminal')

    // Back to dashboard - should still be logged in
    await page.goto(`${BASE}/dashboard`, { waitUntil: 'domcontentloaded' })
    expect(page.url()).toContain('/dashboard')
    expect(page.url()).not.toContain('/login')
  })

  test('sidebar shows Sign In when unauthenticated', async ({ page }) => {
    await page.goto(`${BASE}/dashboard`, { waitUntil: 'domcontentloaded' })
    // Wait for AuthProvider loading to resolve so sidebar renders links (not skeleton).
    // AuthProvider.checkAuth fetches /api/auth/me (401 for unauth) — this takes
    // time and the sidebar shows skeleton until loading=false.
    await expect(page.locator('a:has-text("Sign In")')).toBeVisible({ timeout: 30_000 })
    // Check sidebar has Sign In link
    await expect(page.locator('a:has-text("Sign In")')).toBeVisible()
    // Protected nav items should NOT be visible
    await expect(page.locator('a:has-text("Terminal")')).not.toBeVisible()
    await expect(page.locator('a:has-text("Settings")')).not.toBeVisible()
  })

  test('sidebar shows protected nav when authenticated', async ({ page }) => {
    // Use authenticateDemoUser to bypass form login and rate limit
    await page.goto('/login', { waitUntil: 'domcontentloaded' })
    try {
      await authenticateDemoUser(page)
    } catch {
      // Rate-limited — wait for window to reset and retry
      await page.waitForTimeout(65_000)
      await authenticateDemoUser(page)
    }
    // Navigate to dashboard and wait for AuthProvider loading to resolve
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' })

    // Wait for AuthProvider to set user and render the full sidebar
    await expect(page.locator('a:has-text("Terminal")')).toBeVisible({ timeout: 30_000 })

    // Check sidebar now has protected items
    await expect(page.locator('a:has-text("Terminal")')).toBeVisible()
    await expect(page.locator('a:has-text("Settings")')).toBeVisible()
    // Sign In should be gone
    await expect(page.locator('a:has-text("Sign In")')).not.toBeVisible()

    // Username should be in header
    await expect(page.locator('text=DitJiZak_IT_BOYS')).toBeVisible()
  })

  test('rate limiting on login endpoint', async ({ page }) => {
    // This test fires 6 bad login attempts, exceeding the 5/min limit.
    // CRITICAL: Run it LAST. The backend rate limiter allows 5 logins/min
    // from the same IP (localhost). All prior tests shared the same IP, so
    // we wait for the 60s window to fully expire before probing.
    await page.waitForTimeout(65_000)

    // Make 5 failed attempts — each goes through the UI form.
    // Space them out to ensure the rate limiter counts each one.
    for (let i = 0; i < 5; i++) {
      await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
      await page.fill('input#username', 'DitJiZak_IT_BOYS')
      await page.fill('input#password', 'WRONG')
      await page.click('button[type="submit"]')
      // Wait for the error message to confirm the attempt was processed
      // Use a longer timeout and don't fail if it doesn't appear (rate limit might kick in early)
      await expect(page.locator('text=Invalid credentials')).toBeVisible({ timeout: 10_000 }).catch(() => {})
      await page.waitForTimeout(12_000) // 12s between attempts = 5 in 60s
    }

    // 6th attempt should be rate limited
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await page.fill('input#username', 'DitJiZak_IT_BOYS')
    await page.fill('input#password', 'WRONG')
    await page.click('button[type="submit"]')

    // Should get 429 or rate limit message
    await expect(page.locator('text=Too many login attempts')).toBeVisible({ timeout: 10_000 })
  })
})