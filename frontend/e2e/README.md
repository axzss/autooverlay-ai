# Frontend E2E regression suite

`npm run test:e2e` — Playwright, Chromium, 46 tests, ~20 min serial.

## Why this exists

Three bugs shipped past `tsc --noEmit` and `next build` and were caught only when
a human opened the app in a browser. Every page returned HTTP 200 throughout.

| # | Bug | Fixed in | What made it invisible |
|---|-----|----------|------------------------|
| 1 | `API_BASE_URL` defaulted to `http://localhost:8000`, so browser `fetch()` hit the **visitor's** machine | `ab6b2de` | HTML was fine; only the data calls failed, and only for non-dev-box users |
| 2 | `getHealth()` requested bare `/health`, which is not a Next page → 404 | `69cdf8c` | The backend was healthy; the frontend just asked the wrong origin path |
| 3 | framer-motion serialised `initial="hidden"` into server HTML → `/dashboard` shipped at `opacity:0` | `b869874` | Text was present in the DOM, so a `toHaveText` assertion would also have passed |

Common thread: **HTTP 200 and DOM presence are not evidence a page works.** So this
suite asserts on what the browser actually does — origins contacted, computed
visibility, raw server HTML, console errors.

## Files

| File | Tests | Covers |
|------|-------|--------|
| `bug1-api-origin.spec.ts` | 11 | every request is same-origin; no `:8000`; no "unreachable" text |
| `bug2-health-endpoint.spec.ts` | 3 | `/api/health` 200, bare `/health` 404, status card reads OK |
| `bug3-cold-load-visibility.spec.ts` | 15 | cold-load visibility (A), computed opacity at DCL (B), raw SSR HTML (C) |
| `console-hygiene.spec.ts` | 10 | zero console/page errors; every `_next` asset delivers |
| `navigation.spec.ts` | 5 | sidebar routing + active marker, `/`→`/dashboard`, mobile drawer at 390×844 |
| `agent-run.spec.ts` | 2 | agent run populates grouped reasoning; no line over 300 chars |

## Mutation-verified

Each bug was reintroduced and the suite re-run, to prove the tests fail for the
right reason rather than passing by construction:

- **Bug 1** → 6 failures. `/settings` survived: `StrategyConfigCard` calls
  `fetch('/api/strategy/config')` directly, bypassing `lib/api.ts`.
- **Bug 2** → 1 failure (the card test). Both API-level tests still passed — the
  endpoints were never broken, only the path the client picked.
- **Bug 3** → 5 failures, all in layer C (raw HTML). Layers A and B passed: on a
  warm local dev server hydration finishes inside Playwright's auto-wait window,
  so the blank-page symptom needs the 257 kB cold load a real user hit. Layer C is
  the deterministic detector; A and B stay for slower machines and CSS-level
  regressions that never touch an inline style.

## Two real findings from building it

**Pre-hydration clicks are silently swallowed.** "Run Agent Now" is
server-rendered, so `toBeVisible()` and `toBeEnabled()` both pass while no
`onClick` is attached. Clicking then issues no request and shows no feedback —
measured: zero POSTs. `runAgentAndWaitForResponse()` in `helpers.ts` waits for
hydration evidence and confirms the POST reached the wire. A fast-clicking user
hits the same dead window.

**`next dev` serves 404s for its own chunks on a cold route.** During first
compile the HTML is served while `main-app.js`, `app-pages-internals.js`,
`app/<route>/page.js` and `css/app/layout.css` all 404. With no CSS the Tailwind
`hidden lg:flex` on the sidebar does nothing (so it is "visible" at 390 px); with
no JS nothing hydrates (so no `/api/*` call fires and no redirect happens). This
produced 25 spurious failures on the first run. `global-setup.ts` requests each
route and re-requests its assets until they all return 200 — the assertions stay
armed, they just no longer fire on an unfinished compile.

## Running it

Needs the dev server on `:3000` and FastAPI on `:8000`.
`webServer.reuseExistingServer` is true, so an already-running server is reused.

```bash
cd frontend && npm run test:e2e
npx playwright test e2e/bug1-api-origin.spec.ts   # one file
npx playwright show-trace test-results/<dir>/trace.zip
```

**Never run `next build` while `next dev` is serving the same folder.** It
overwrites `.next` and the dev server then 404s every chunk; `global-setup.ts`
fails with an explicit message when that happens. Recovery: stop dev, `rm -rf
.next`, restart.

## Conventions

- Nothing is allow-listed. If a legitimate third-party origin or console error is
  ever introduced, add it here by name with a reason — never widen a regex to make
  a test green.
- Failure messages state which bug class regressed and what to look at.
- Tests that could pass vacuously assert their own preconditions: the same-origin
  test requires at least one `/api/*` call, and the line-length test requires the
  backend to still emit an over-long line.
