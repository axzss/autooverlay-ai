import { request as pwRequest, type FullConfig } from '@playwright/test'

/**
 * Warms the Next dev server before any test runs.
 *
 * `next dev` compiles a route on its first request. During that window the HTML
 * is served but the chunk and CSS URLs it references 404 — I measured
 * /_next/static/chunks/main-app.js, app-pages-internals.js,
 * app/<route>/page.js and css/app/layout.css all returning 404 on a cold route,
 * then 200 a moment later.
 *
 * That is a dev-server artifact, not a product defect, and it is not what this
 * suite is testing — but it wrecks every assertion downstream of it. With no CSS
 * the Tailwind `hidden lg:flex` on the desktop sidebar does nothing so the
 * sidebar is "visible" at 390px; with no JS bundle React never hydrates so no
 * /api/* call is ever made, no client redirect fires, and every page logs five
 * "Failed to load resource: 404" console errors.
 *
 * So: request each route, then re-request every asset its HTML references until
 * they all return 200. This removes the race WITHOUT relaxing any assertion —
 * the 404 assertions stay armed, they just no longer fire on a compile that had
 * not finished. Under `next start` this warmup is a no-op.
 */
async function warm(baseURL: string): Promise<void> {
  const ctx = await pwRequest.newContext({ baseURL })
  const routes = ['/dashboard', '/assets', '/terminal', '/council', '/settings', '/']

  try {
    for (const route of routes) {
      let assetsOk = false
      for (let attempt = 0; attempt < 12 && !assetsOk; attempt++) {
        const res = await ctx.get(route)
        const html = await res.text()
        const assets = [
          ...new Set((html.match(/\/_next\/static\/(?:chunks|css)\/[^"\\]+/g) ?? [])),
        ]
        if (assets.length === 0) {
          await new Promise((r) => setTimeout(r, 500))
          continue
        }
        const codes = await Promise.all(
          assets.map(async (a) => (await ctx.get(a)).status()),
        )
        assetsOk = codes.every((c) => c === 200)
        if (!assetsOk) {
          const failing = assets.filter((_, i) => codes[i] !== 200)
          // eslint-disable-next-line no-console
          console.log(
            `[warmup] ${route}: ${failing.length}/${assets.length} assets still compiling ` +
              `(attempt ${attempt + 1})`,
          )
          await new Promise((r) => setTimeout(r, 1200))
        }
      }
      if (!assetsOk) {
        throw new Error(
          `[warmup] ${route} never served all of its _next assets with 200. The dev ` +
            `server may have a corrupted .next directory — this happens when ` +
            `\`next build\` runs against the same folder while \`next dev\` is serving ` +
            `it. Restart the dev server before trusting this suite.`,
        )
      }
    }

    // The backend must be reachable through the rewrite, or the whole suite is
    // measuring the wrong thing. Fail loudly here rather than 40 tests later.
    const health = await ctx.get('/api/health')
    if (health.status() !== 200) {
      throw new Error(
        `[warmup] GET /api/health returned ${health.status()}. The FastAPI backend ` +
          `must be up on :8000 and reachable via the next.config.js rewrite.`,
      )
    }
    // eslint-disable-next-line no-console
    console.log('[warmup] all routes compiled, assets 200, /api/health ok')
  } finally {
    await ctx.dispose()
  }
}

export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL =
    (config.projects[0]?.use?.baseURL as string | undefined) ?? 'http://localhost:3000'
  await warm(baseURL)
}
