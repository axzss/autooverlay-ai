# SPEC · F1 — Live data layer (`frontend/lib/live/`)

Implementation spec for workstream **F1** of `docs/BRIEF-FRONTEND-V2.md` (§ "F1 ·
Live data layer", lines 69–134). Written so a frontend engineer can code the whole
workstream without asking a question. Where the brief says "sane defaults", this
document gives the number.

**Scope boundary.** F1 touches only: `frontend/lib/live/**` (new),
`frontend/lib/api.ts` (add two endpoints + a re-export shim),
`frontend/app/components/Providers.tsx` (mount one `QueryClientProvider`),
the five existing page/component call sites listed in §3, `frontend/tests/**`
(extend), and `docs/FRONTEND.md:40` (one-line factual correction). F1 does **not**
create new routes, does **not** touch `backend/**` or `agent/**`, and does **not**
add a dependency.

## 0 · Verified starting state

| Fact | Evidence |
|---|---|
| `@tanstack/react-query@^5.32.1` is a dependency and is **unused** | `frontend/package.json`; zero `QueryClient`/`useQuery`/`useMutation` hits under `app/` or `lib/` |
| The whole typed client is 472 lines in one file | `frontend/lib/api.ts` |
| Timeout split is 30 s for `/agent/run`, `/council/cycle`, `/council/assess`, `/strategy/screen`; 8 s for everything else | `lib/api.ts:118–119` |
| `ApiError` distinguishes `timed out` from `unreachable` | `lib/api.ts:133–143` |
| `usePortfolio()` falls back to bundled `mock_portfolio.json` and flags it with `usingFallback` | `lib/api.ts:422–472` |
| `app/components/Providers.tsx` holds only `MobileNavContext` — no query provider | `app/components/Providers.tsx:19–27` |
| `AgentRunProvider` already de-duplicates `POST /api/agent/run` behind a context | `app/components/AgentRunProvider.tsx:29–53` |
| Four dead per-route `Providers.tsx` stubs exist and are imported nowhere | `app/{assets,dashboard,settings,terminal}/Providers.tsx`; only `app/layout.tsx:2` imports the real one |
| `GET /api/strategy/config` is absent from the `api` object; `StrategyConfigCard` calls raw `fetch()` twice | `lib/api.ts:257–298`; `app/components/StrategyConfigCard.tsx:43`, `:69` |
| Backend exposes `GET` **and** `PUT` `/strategy/config`; `PUT` 422s with `{detail:{errors:[…]}}` | `backend/app/routes/strategy.py:53–68` |
| `/api/agent/stream` does **not** exist | no route in `backend/app/routes/`; brief §9 requests it |
| Vitest already configured: `environment: 'node'`, `include: ['tests/**/*.test.ts']`, alias `@ → ./app` | `frontend/vitest.config.ts` |

**Tailwind palette — the only colours this workstream may emit.** `background
#020617`, `surface #0f172a`, `surface-container #131c2e`, `primary #22c55e`,
`secondary #fbbf24`, `error #ef4444`, `on-surface #f8fafc`, `on-surface-variant
#94a3b8`, `outline #334155`. Arbitrary-value form (`bg-[#0f172a]`) matches the
existing codebase and is what the snippets below use.

## 1 · File tree and exports

```
frontend/lib/live/
├── queryClient.ts   makeQueryClient(), getQueryClient(), QUERY_DEFAULTS
├── keys.ts          queryKeys, POLICY, PolicyName, policyFor()
├── hooks.ts         usePortfolioQuery, useHealthQuery, useScreenQuery,
│                    useCouncilQuery, useStrategyConfigQuery,
│                    useAgentRunMutation, useCycleMutation,
│                    useStrategyConfigMutation, useVisibilityPause
├── stream.ts        useAgentStream(), AgentStreamEvent, AgentStreamState
└── freshness.ts     freshnessOf(), FreshnessInput, Freshness, FreshnessDot
```

Nothing else goes in this directory. Presentation stays in `app/components/**`;
`FreshnessDot` is the single exception because every panel needs it and it is
four `<span>`s (see §6).

### 1.1 `queryClient.ts`

```ts
import { QueryClient, type DefaultOptions } from '@tanstack/react-query'

/** Client-wide defaults. Per-query overrides live in keys.ts POLICY. */
export const QUERY_DEFAULTS: DefaultOptions

/** Fresh client. Call once per browser session (and once per test). */
export function makeQueryClient(): QueryClient

/**
 * Browser singleton. Next's App Router re-renders the layout on navigation;
 * a client constructed in render would throw the cache away each time.
 * On the server this returns a NEW client per call so no cache is shared
 * across requests (a shared server cache leaks one user's portfolio to the next).
 */
export function getQueryClient(): QueryClient
```

Reference implementation (copy-pasteable):

```ts
import { QueryClient, type DefaultOptions } from '@tanstack/react-query'

export const QUERY_DEFAULTS: DefaultOptions = {
  queries: {
    // Every interval-driven query opts in explicitly via POLICY; the default
    // is "no polling" so a new hook cannot start hammering Alpaca by accident.
    refetchInterval: false,
    // HARD RULE for this workstream: a hidden tab costs the same Alpaca quota
    // as a visible one and buys nothing.
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
    staleTime: 15_000,
    gcTime: 5 * 60_000,
    retry: 1,
    retryDelay: (attempt: number) => Math.min(1_000 * 2 ** attempt, 8_000),
    // lib/api.ts already throws ApiError with a human-readable message.
    throwOnError: false,
  },
  mutations: {
    // Mutations are never retried: POST /api/agent/run and PUT
    // /api/strategy/config are not idempotent in a way we can prove.
    retry: 0,
  },
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: QUERY_DEFAULTS })
}

let browserClient: QueryClient | undefined

export function getQueryClient(): QueryClient {
  if (typeof window === 'undefined') return makeQueryClient()
  if (!browserClient) browserClient = makeQueryClient()
  return browserClient
}
```

### 1.2 `keys.ts`

```ts
export type QueryKey = readonly unknown[]

export const queryKeys: {
  readonly portfolio: () => readonly ['portfolio']
  readonly health: () => readonly ['health']
  readonly screen: () => readonly ['screen']
  readonly council: (symbols?: readonly string[]) => readonly ['council', string]
  readonly strategyConfig: () => readonly ['strategyConfig']
  readonly agentRun: () => readonly ['agentRun']
}

export type PolicyName =
  | 'portfolio'
  | 'health'
  | 'screen'
  | 'council'
  | 'strategyConfig'
  | 'agentRun'

export interface QueryPolicy {
  /** ms between automatic refetches, or false for on-demand only. */
  readonly refetchInterval: number | false
  /** ms before cached data is considered stale. */
  readonly staleTime: number
  /** failed-attempt retries (react-query semantics: 1 = two total attempts). */
  readonly retry: number
  /** Never true for a mutation. Enforced by policyFor(). */
  readonly refetchIntervalInBackground: false
  /** Why this number and not a smaller one. Rendered in dev tooling and docs. */
  readonly cost: string
}

export const POLICY: Readonly<Record<PolicyName, QueryPolicy>>

/** Typed accessor; throws at module load if a mutation policy ever polls. */
export function policyFor(name: PolicyName): QueryPolicy
```

### 1.3 `hooks.ts`

```ts
import type {
  UseMutationResult,
  UseQueryResult,
} from '@tanstack/react-query'
import type {
  AgentRunResponse,
  CouncilAssessResponse,
  CycleResponse,
  HealthResponse,
  PortfolioSnapshot,
  StrategyConfigPayload,
  StrategyParams,
} from '../api'
import type { AgentRecommendation, PortfolioContext } from '../api'

/** Screen result after normalizeScreenings(), so no page re-normalises. */
export interface ScreenResult {
  entries: AgentRecommendation[]
  portfolioContext: PortfolioContext | null
  mode: string | null
  liveError: string | null
}

/**
 * GET /api/portfolio on the 'portfolio' policy.
 * `usingFallback` is true when the request failed and bundled mock data is
 * being shown instead — same contract as the legacy usePortfolio().
 */
export function usePortfolioQuery(): UseQueryResult<PortfolioSnapshot, Error> & {
  usingFallback: boolean
}

/** GET /api/health on the 'health' policy. */
export function useHealthQuery(): UseQueryResult<HealthResponse, Error>

/**
 * GET /api/strategy/screen on the 'screen' policy, pre-normalised.
 * `enabled: false` keeps it on-demand for pages that only want the button.
 */
export function useScreenQuery(options?: { enabled?: boolean }): UseQueryResult<
  ScreenResult,
  Error
>

/** GET or POST /api/council/assess on the 'council' policy. */
export function useCouncilQuery(
  symbols?: readonly string[],
): UseQueryResult<CouncilAssessResponse, Error>

/** GET /api/strategy/config on the 'strategyConfig' policy. */
export function useStrategyConfigQuery(): UseQueryResult<StrategyConfigPayload, Error>

/**
 * POST /api/agent/run. A MUTATION — it must never be a query and never poll.
 * On success invalidates queryKeys.portfolio() and queryKeys.screen().
 */
export function useAgentRunMutation(): UseMutationResult<
  AgentRunResponse,
  Error,
  { candidates?: string[]; cash_override?: number } | undefined
>

/** POST /api/council/cycle. Mutation; invalidates council + portfolio. */
export function useCycleMutation(): UseMutationResult<
  CycleResponse,
  Error,
  { candidates?: string[]; cash_override?: number } | undefined
>

/** PUT /api/strategy/config. Mutation; writes the response into the cache. */
export function useStrategyConfigMutation(): UseMutationResult<
  StrategyConfigPayload,
  Error,
  StrategyParams
>

/**
 * Belt-and-braces companion to refetchIntervalInBackground:false.
 * Returns true while document.visibilityState === 'visible'. Feed it into
 * a query's `enabled` when the interval is short, so the timer is torn down
 * on hide rather than merely skipped.
 */
export function useVisibilityPause(): boolean
```

`useVisibilityPause` implementation is fixed, not a suggestion — the SSR guard
matters because `document` does not exist during prerender:

```ts
import { useEffect, useState } from 'react'

export function useVisibilityPause(): boolean {
  const [visible, setVisible] = useState<boolean>(true)
  useEffect(() => {
    if (typeof document === 'undefined') return
    const sync = () => setVisible(document.visibilityState === 'visible')
    sync()
    document.addEventListener('visibilitychange', sync)
    return () => document.removeEventListener('visibilitychange', sync)
  }, [])
  return visible
}
```

### 1.4 `freshness.ts` (signatures; semantics in §6)

```ts
import type { ReactElement } from 'react'

export type Freshness = 'live' | 'stale' | 'offline'

export interface FreshnessInput {
  /** react-query dataUpdatedAt: ms epoch of the last SUCCESSFUL fetch, 0 if none. */
  dataUpdatedAt: number
  /** react-query errorUpdatedAt: ms epoch of the last FAILED fetch, 0 if none. */
  errorUpdatedAt: number
  /** react-query isFetching. */
  isFetching: boolean
  /** The policy's refetchInterval; false for on-demand queries. */
  interval: number | false
  /** Injected clock for deterministic tests. Defaults to Date.now(). */
  now?: number
}

export function freshnessOf(input: FreshnessInput): Freshness

export function freshnessLabel(state: Freshness): string

export function FreshnessDot(props: {
  state: Freshness
  isFetching?: boolean
  /** Extra context appended to the tooltip, e.g. 'mock data'. */
  detail?: string
}): ReactElement
```

### 1.5 `stream.ts` (signatures; semantics in §7)

```ts
export type AgentStreamStatus = 'idle' | 'connecting' | 'open' | 'polling' | 'error'

export interface AgentStreamEvent {
  /** Server event name; 'message' when the server omits one. */
  type: string
  /** ms epoch assigned on receipt by the client — never invented ahead of time. */
  receivedAt: number
  /** Parsed JSON payload, or the raw string when it is not JSON. */
  data: unknown
  /** EventSource lastEventId, when the server sends one. */
  id: string | null
}

export interface AgentStreamState {
  status: AgentStreamStatus
  events: AgentStreamEvent[]
  /** Human-readable reason for a non-open status. Rendered, never swallowed. */
  reason: string | null
  /** True once the endpoint 404'd: the UI MUST say "polling, stream unavailable". */
  degradedToPolling: boolean
  reconnectAttempts: number
}

export function useAgentStream(options?: {
  /** Defaults to '/api/agent/stream'. */
  path?: string
  /** Ring-buffer size; oldest events dropped. Defaults to 200. */
  maxEvents?: number
  /** Set false to keep the socket closed (e.g. route not mounted). */
  enabled?: boolean
}): AgentStreamState
```

## 2 · Polling policy — one table, no magic numbers

This is the literal contents of `frontend/lib/live/keys.ts`. Every interval in the
app comes from here; a `refetchInterval` literal anywhere else is a review
rejection.

```ts
export type QueryKey = readonly unknown[]

export const queryKeys = {
  portfolio: () => ['portfolio'] as const,
  health: () => ['health'] as const,
  screen: () => ['screen'] as const,
  // The symbol list is part of the identity: assessing [AAPL] is not the same
  // request as assessing the default universe. Sorted + joined so key order
  // never causes a spurious cache miss.
  council: (symbols?: readonly string[]) =>
    ['council', symbols && symbols.length > 0 ? [...symbols].sort().join(',') : 'default'] as const,
  strategyConfig: () => ['strategyConfig'] as const,
  agentRun: () => ['agentRun'] as const,
} as const

export type PolicyName =
  | 'portfolio'
  | 'health'
  | 'screen'
  | 'council'
  | 'strategyConfig'
  | 'agentRun'

export interface QueryPolicy {
  readonly refetchInterval: number | false
  readonly staleTime: number
  readonly retry: number
  readonly refetchIntervalInBackground: false
  readonly cost: string
}

export const POLICY: Readonly<Record<PolicyName, QueryPolicy>> = {
  portfolio: {
    refetchInterval: 20_000,
    staleTime: 10_000,
    retry: 1,
    refetchIntervalInBackground: false,
    cost:
      'GET /api/portfolio = 1 Alpaca account call + 1 positions call + 1 orders call. ' +
      '3 calls / 20 s = 9 req/min against a 200 req/min plan — ~4.5% of budget for ' +
      'the one panel the user actually watches. Faster than 20 s buys nothing: ' +
      'equity moves are not decision-relevant at 5 s granularity, and 5 s would be ' +
      '36 req/min before any other page is open.',
  },
  health: {
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: 1,
    refetchIntervalInBackground: false,
    cost:
      'GET /api/health touches no vendor API — it reports process state and ' +
      'alpaca_configured. Cost is one local FastAPI hop, so the interval is set by ' +
      'how fast a dead backend must become visible (30 s), not by quota.',
  },
  screen: {
    refetchInterval: 300_000,
    staleTime: 120_000,
    retry: 0,
    refetchIntervalInBackground: false,
    cost:
      'GET /api/strategy/screen FANS OUT PER SYMBOL: option-chain snapshot + ' +
      'underlying quote for every held/candidate underlying, then runs the ' +
      'DecisionEngine. ~2 s wall clock locally and it is the reason lib/api.ts ' +
      'gives it the 30 s timeout bucket. At 10 symbols that is 20+ vendor calls per ' +
      'refetch. 5 min keeps it under ~4 vendor calls/min; retry 0 because a retry ' +
      'doubles the most expensive request in the app and a 2 s-plus failure is ' +
      'almost never transient. Refresh is primarily USER-DRIVEN (the Run button).',
  },
  council: {
    refetchInterval: false,
    staleTime: 60_000,
    retry: 0,
    refetchIntervalInBackground: false,
    cost:
      'GET/POST /api/council/assess runs 6–7 persona evaluations per symbol on top ' +
      'of the same market data as screen. Strictly on demand: it is a deliberation, ' +
      'not a ticker, and a poll would re-derive an unchanged verdict at full price. ' +
      'The board refreshes on mount, on the Run button, and after a cycle mutation ' +
      'invalidates the key.',
  },
  strategyConfig: {
    refetchInterval: false,
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
    refetchIntervalInBackground: false,
    cost:
      'GET /api/strategy/config reads an in-process singleton (see ' +
      'backend/app/routes/strategy.py) — it costs nothing, but it also cannot change ' +
      'without this client PUTting it. Polling it would fight the user mid-edit and ' +
      'overwrite a half-typed form. Never polls; the mutation writes the response ' +
      'straight into the cache with setQueryData.',
  },
  agentRun: {
    // NOT NEGOTIABLE. POST /api/agent/run runs the whole council + screen
    // pipeline and prepares order intents. Polling it would repeatedly execute
    // trade-adjacent logic without a human asking. useMutation only.
    refetchInterval: false,
    staleTime: 0,
    retry: 0,
    refetchIntervalInBackground: false,
    cost:
      'MUTATION — never polled, never retried. POST /api/agent/run is the most ' +
      'expensive endpoint in the system (full cycle + intent preparation) and is ' +
      'trade-adjacent. An automatic refetch is an unrequested agent invocation.',
  },
} as const

export function policyFor(name: PolicyName): QueryPolicy {
  const p = POLICY[name]
  if (name === 'agentRun' && p.refetchInterval !== false) {
    throw new Error('agentRun is a mutation and must never poll')
  }
  return p
}
```

### 2.1 How a hook consumes the policy

```ts
import { useQuery } from '@tanstack/react-query'
import { api, normalizeScreenings } from '../api'
import { POLICY, queryKeys } from './keys'
import { useVisibilityPause } from './hooks'

export function useScreenQuery(options?: { enabled?: boolean }) {
  const visible = useVisibilityPause()
  const policy = POLICY.screen
  return useQuery({
    queryKey: queryKeys.screen(),
    queryFn: async () => normalizeScreenings(await api.screenStrategies()),
    refetchInterval: policy.refetchInterval,
    refetchIntervalInBackground: policy.refetchIntervalInBackground,
    staleTime: policy.staleTime,
    retry: policy.retry,
    enabled: (options?.enabled ?? true) && visible,
  })
}
```

Two independent guards, deliberately:

1. `refetchIntervalInBackground: false` — react-query's own suppression. Stops the
   timer firing while `document.hidden`.
2. `enabled: visible` from `useVisibilityPause()` — tears the query down entirely,
   which also stops a *pending* refetch that was scheduled just before the hide and
   prevents `refetchOnWindowFocus` from stacking a second burst on return.

The brief's acceptance criterion is explicit: "A demo laptop left on the council
page for an hour must not have hammered Alpaca ten thousand times." With this table
an hour on the council page costs 180 portfolio calls, 120 health calls, 12 screen
calls and zero council calls.

## 3 · Migration order

Prerequisite commit (**M0**), landed before any page changes:

1. `app/components/Providers.tsx` wraps its existing `MobileNavContext.Provider`
   in a single `QueryClientProvider`. This is the only place a `QueryClient` is
   mounted in the app.

```tsx
'use client'

import { createContext, useContext, useState, type ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { getQueryClient } from '../../lib/live/queryClient'

interface MobileNavContextValue {
  mobileOpen: boolean
  setMobileOpen: (open: boolean) => void
}

const MobileNavContext = createContext<MobileNavContextValue>({
  mobileOpen: false,
  setMobileOpen: () => {},
})

export function useMobileNav() {
  return useContext(MobileNavContext)
}

export default function Providers({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  // useState so the client survives re-render but is not module-global in a
  // way that leaks between server requests.
  const [queryClient] = useState(getQueryClient)

  return (
    <QueryClientProvider client={queryClient}>
      <MobileNavContext.Provider value={{ mobileOpen, setMobileOpen }}>
        {children}
      </MobileNavContext.Provider>
    </QueryClientProvider>
  )
}
```

2. Delete the four dead stubs: `app/assets/Providers.tsx`,
   `app/dashboard/Providers.tsx`, `app/settings/Providers.tsx`,
   `app/terminal/Providers.tsx`. Each returns `children` unchanged and is imported
   nowhere (`app/layout.tsx:2` imports only `app/components/Providers`). Verify with
   `grep -rn "from './Providers'" app/` returning nothing before deleting.
3. Add `getStrategyConfig` / `updateStrategyConfig` to `lib/api.ts` (§5). Doing this
   in M0 means the settings migration is a pure component change.

**M0 must not change:** `MobileNavContext`'s shape or the fact that
`useMobileNav()` keeps working — the sidebar depends on it. `AgentRunProvider`
stays mounted where it is (see M3).

### M1 — `app/dashboard/page.tsx`

| Current | Replacement |
|---|---|
| `page.tsx:55` — `const { data, error, loading, usingFallback } = usePortfolio()` | `const portfolio = usePortfolioQuery()`; read `portfolio.data`, `portfolio.error?.message`, `portfolio.isLoading`, `portfolio.usingFallback` |
| `page.tsx:56` — `useState<PortfolioContext \| null>(null)` | deleted; context comes from the query cache |
| `page.tsx:58–71` — `useEffect` calling `api.screenStrategies().then(res => setPortfolioContext(normalizeScreenings(res).portfolioContext)).catch(noop)` | `const screen = useScreenQuery(); const portfolioContext = screen.data?.portfolioContext ?? null` |
| `page.tsx:3` — `import { useEffect, useState } from 'react'` | drop `useEffect`; keep `useState` only if another local state remains |

Add a `FreshnessDot` to the portfolio stat strip fed by
`freshnessOf({ dataUpdatedAt: portfolio.dataUpdatedAt, errorUpdatedAt:
portfolio.errorUpdatedAt, isFetching: portfolio.isFetching, interval:
POLICY.portfolio.refetchInterval })`, with `detail="mock data"` when
`portfolio.usingFallback`.

**Must NOT change:** the swallow-on-failure semantics of the screen call. Today the
`.catch()` is intentionally silent — portfolio context is optional decoration and a
screen failure must never blank the dashboard. After migration, a `screen.isError`
still renders the dashboard with `portfolioContext === null`; do **not** surface a
screen error as a dashboard-level error banner. Also unchanged: the `dailyPnl` /
`lastEquity` derivation below line 73, and the mock fallback appearing whenever the
backend is down.

### M2 — `app/assets/page.tsx`

| Current | Replacement |
|---|---|
| `page.tsx:9` — `import { usePortfolio } from '../../lib/api'` | `import { usePortfolioQuery } from '../../lib/live/hooks'` |
| `page.tsx:53` — `const { data, error, usingFallback } = usePortfolio()` | `const { data, error, usingFallback, dataUpdatedAt, errorUpdatedAt, isFetching } = usePortfolioQuery()` |

There is no `useEffect` on this page — it is the cheapest migration and exists to
prove the hook is a drop-in before the harder pages.

**Must NOT change:** `FALLBACK_ACCOUNT` / `FALLBACK_POSITIONS` (lines ~20–50) and
the `data?.account_info ?? FALLBACK_ACCOUNT` pattern at lines 55–57. Those are a
*second, page-local* fallback layer independent of `usePortfolio`'s mock JSON, and
the orders-to-history mapping at lines 58–66 (`.slice(0, 10)`, the `Sell to Open`
label, the `text-[#94a3b8]` neutral P&L colour) stays byte-identical.

### M3 — `app/terminal/page.tsx` + `app/components/terminal/TerminalClient.tsx`

`app/terminal/page.tsx` (19 lines) is a shell that renders `<TerminalClient />`.
**It does not change at all.** All work is in the client component.

| Current (`TerminalClient.tsx`) | Replacement |
|---|---|
| `:3` `import { useCallback, useEffect, useState } from 'react'` | drop `useEffect`; `useCallback`/`useState` remain for UI-only state |
| `:68–88` `runCycle` useCallback wrapping `api.screenStrategies()` + `normalizeScreenings` + `setEntries/setMode/setLiveError/setPortfolioContext/setLastRun/setError` | `const screen = useScreenQuery()`. Derive: `entries = (screen.data?.entries ?? []).map(toFeedEntry)`, `mode = screen.data?.mode ?? null`, `liveError = screen.data?.liveError ?? null`, `portfolioContext = screen.data?.portfolioContext ?? null`, `error = screen.error?.message ?? null`. Manual refresh = `screen.refetch()`. `lastRun` = `new Date(screen.dataUpdatedAt).toLocaleTimeString()` when `dataUpdatedAt > 0` |
| `:90–103` `runDailyCycle` useCallback wrapping `api.runDailyCycle()` | `useCycleMutation()`: `directives = cycle.data?.directives ?? []`, `halted = cycle.data?.halted ?? false`, `cycleError = cycle.error?.message ?? null`, `cycleRunning = cycle.isPending`, `lastCycleRun` from `cycle.submittedAt` |
| `:115–127` `runAgent` useCallback wrapping `api.runAgent()` | `useAgentRunMutation()`: `agentRun = run.data ?? null`, `agentRunning = run.isPending`, `agentError = run.error?.message ?? null` |
| `:129–131` `useEffect(() => { runCycle(true) }, [runCycle])` | **deleted** — `useScreenQuery` fetches on mount by itself. This is the `useEffect(() => { api.… })` the acceptance criterion names |
| state vars `entries, mode, liveError, portfolioContext, loading, running, error, lastRun, directives, halted, cycleRunning, cycleError, lastCycleRun, agentRun, agentRunning, agentError` | all deleted; each is now derived from a query/mutation |

Keep `expandedDirectives` (`:61`) and `toggleDirective` (`:105–113`) exactly as they
are: that is view state, not server state.

Prefer `useAgentRun()` from `app/components/AgentRunProvider.tsx` if the terminal is
ever mounted alongside the dashboard agent card; otherwise call
`useAgentRunMutation()` directly. **In M3, refactor `AgentRunProvider` to wrap
`useAgentRunMutation()` internally** so its public contract
(`{ run, running, error, runAgent }`) is unchanged and consumers keep compiling.

**Must NOT change:** the `loading`-vs-`running` distinction in the UI (first load
shows a skeleton, a manual re-run shows an inline spinner — map to
`screen.isLoading` and `screen.isFetching && !screen.isLoading` respectively); the
`yieldBars` filter at `:134+` that drops candidates with a non-numeric
`premiumYieldPct` (a 0% bar would read as "no premium" rather than "not reported");
and the `toFeedEntry` shaping, which stays in `lib/api.ts` untouched.

### M4 — `app/council/page.tsx` + `app/components/council/CouncilBoard.tsx`

`app/council/page.tsx` (19 lines) is a shell. **No change.**

| Current (`CouncilBoard.tsx`) | Replacement |
|---|---|
| `:52–55` `useState<CouncilResponse \| null>(null)`, `loading`, `error` | `const council = useCouncilQuery()` |
| `:57–69` `runSession` useCallback: `api.assessCouncil()`, `setData`, and on failure `setData(MOCK_SNAPSHOT)` | `const data = council.data ?? (council.isError ? MOCK_SNAPSHOT : null)`; `error = council.error?.message ?? null`; `loading = council.isPending` |
| `:71–73` `useEffect(() => { runSession() }, [runSession])` | **deleted** — mount fetch is the query's job |
| the Run/refresh button's `onClick={runSession}` | `onClick={() => council.refetch()}` |
| `:3` `import { useCallback, useEffect, useState } from 'react'` | keep `useState` for `expanded` only |

Keep `expanded` (`:55`) — accordion state.

**Must NOT change:** the `MOCK_SNAPSHOT`-on-error behaviour. The council board is
the demo centrepiece; it must render six verdicts even with the backend down. It
must, however, still show the error string next to the freshness dot in `offline`
state — degraded, and labelled degraded. Also unchanged: `useReducedMotion()` at
`:51` and every `cn(...)` class expression.

### M5 — `app/settings/page.tsx` + `app/components/StrategyConfigCard.tsx`

`app/settings/page.tsx` (42 lines) has no data access. **No change**, including the
comment block explaining why `AgentConfiguration` was removed.

| Current (`StrategyConfigCard.tsx`) | Replacement |
|---|---|
| `:39–55` `useEffect` + `fetch('/api/strategy/config')` raw GET | `useStrategyConfigQuery()` |
| `:64–90` `handleSave` with raw `fetch(..., { method: 'PUT' })` | `useStrategyConfigMutation()` |
| `:34–37` `loading`, `saving`, `error`, `saved` | `query.isPending`, `mutation.isPending`, `query.error ?? mutation.error`, `mutation.isSuccess` |
| `:33` `useState<StrategyParams>(DEFAULTS)` | **stays** — this is a controlled form; see below |

The form state stays local and is seeded from the query, not replaced by it:

```ts
const query = useStrategyConfigQuery()
const mutation = useStrategyConfigMutation()
const [params, setParams] = useState<StrategyParams>(DEFAULTS)
const [seededFrom, setSeededFrom] = useState<number>(0)

// Seed once per successful fetch. Without the guard, a refetch mid-edit would
// overwrite the user's half-typed values.
if (query.data && query.dataUpdatedAt !== seededFrom) {
  setSeededFrom(query.dataUpdatedAt)
  setParams({ ...DEFAULTS, ...query.data.config })
}
```

**Must NOT change:** `DEFAULTS` (`:19–30`) and the `{ ...DEFAULTS, ...data.config }`
merge — the backend may omit a key and the slider must not become `NaN`; the 422
error extraction (`body?.detail?.errors` joined with `'; '`) which is the only way a
user sees *why* a config was rejected; the `Slider` / `NumberField` subcomponents and
every Tailwind class in them.

## 4 · The re-export shim

Five files import helpers from `lib/api.ts` today. Nothing in F1 requires moving
those helpers, so the shim exists purely to let hook *consumers* migrate one commit
at a time without a rename storm.

Appended to `lib/api.ts`, at the very bottom, under this exact banner:

```ts
// ---------------------------------------------------------------------------
// MIGRATION SHIM — F1 live data layer.
//
// These symbols are imported from 'lib/api' by five files:
//   usePortfolio         app/dashboard/page.tsx:21, app/assets/page.tsx:9
//   normalizeScreenings  app/dashboard/page.tsx, app/components/terminal/TerminalClient.tsx:7
//   toFeedEntry          app/components/terminal/TerminalClient.tsx:8
//   riskBadgeClasses     app/components/terminal/TerminalClient.tsx,
//                        app/components/council/CouncilBoard.tsx
//   actionLabel          app/components/terminal/TerminalClient.tsx
//
// usePortfolio is DEPRECATED as of commit M0 and is deleted in commit M6.
// The pure helpers (normalizeScreenings/toFeedEntry/riskBadgeClasses/actionLabel)
// are NOT deprecated: they stay defined in this module permanently, because
// tests/api.test.ts asserts them from here and lib/live/hooks.ts imports them.
//
// REMOVAL: commit M6 "F1: drop usePortfolio shim". Do not extend this block.
// ---------------------------------------------------------------------------

/**
 * @deprecated Use usePortfolioQuery() from lib/live/hooks. Removed in M6.
 * Kept verbatim (mock fallback included) so M1/M2 can land independently.
 */
export { usePortfolio as usePortfolioLegacy }
```

Rules:

- `usePortfolio` keeps its original name **and** gains the
  `usePortfolioLegacy` alias, so a half-migrated tree compiles either way. The
  `@deprecated` tag is what makes the ESLint/editor surface nag.
- `normalizeScreenings`, `toFeedEntry`, `riskBadgeClasses`, `actionLabel`,
  `ApiError`, `API_BASE_URL` and every exported type stay exported from
  `lib/api.ts` **after** M6. They are pure functions with existing test coverage
  (`tests/api.test.ts` imports them from `'../lib/api'`); moving them would churn
  the suite for no gain. `lib/live/hooks.ts` imports them from `lib/api`, never the
  reverse.
- `lib/live/**` must not be imported by `lib/api.ts`. One-way dependency:
  `app/** → lib/live/** → lib/api.ts`. A cycle here breaks the vitest `node`
  environment, which has no React runtime for `lib/api`'s hook import.

**Removal commit — M6, "F1: drop usePortfolio shim".** Preconditions, all
verified by command:

```
grep -rn "usePortfolio\b"      frontend/app frontend/lib   # only lib/api.ts
grep -rn "usePortfolioLegacy"  frontend/app frontend/lib    # nothing
grep -rn "useEffect(() *=> *{[^}]*api\." frontend/app       # nothing
npx tsc --noEmit && npm run test
```

M6 deletes `usePortfolio`, `ApiState`, the `FALLBACK` const's *sole* legacy
consumer, and the shim banner. The mock-fallback behaviour itself does **not**
disappear — by M6 it lives in `usePortfolioQuery` (§8.3).

## 5 · The StrategyConfigCard fix

### 5.1 Why this is the worst defect in F1

`app/components/StrategyConfigCard.tsx:69` is a raw `fetch()` with `method: 'PUT'`
and **no `AbortController`**. It writes live strategy parameters — delta bands, DTE
bands, take-profit, stop-loss multiple, concentration cap, cash reserve — into the
backend singleton that `DecisionEngine` reads on the next cycle.

Three properties combine into the worst-case:

1. **It is a write.** Every other unguarded path in the app is a read; a hung read
   shows stale numbers. A hung write leaves the user unable to tell whether the
   config was applied. They are now guessing about the risk limits of a system that
   places orders.
2. **It has no timeout.** Browser default is ~90–300 s depending on platform. The
   button sits at "Saving…" the whole time (`saving` never clears until the promise
   settles). Users conclude it worked, or click again — and a second PUT can land
   after the first, so the last writer wins nondeterministically.
3. **It bypasses `ApiError`.** A dead backend and a slow backend both surface as an
   opaque `TypeError: Failed to fetch`, so the "timed out vs unreachable"
   distinction that the rest of the app spent effort earning (`lib/api.ts:133–143`)
   does not exist on the one screen where knowing the difference matters.

`FRONTEND.md:40` asserts `lib/api.ts` is "the only place `fetch()` appears", so a
reviewer auditing network behaviour never looks at this file. The false claim is part
of the defect, not a separate cosmetic issue.

### 5.2 Types and client methods (added to `lib/api.ts` in M0)

```ts
/** Mirrors StrategyConfigModel in backend/app/routes/strategy.py. */
export interface StrategyParams {
  take_profit_pct: number
  stop_loss_mult: number
  roll_delta: number
  roll_min_dte: number
  delta_min: number
  delta_max: number
  dte_min: number
  dte_max: number
  max_concentration_pct: number
  min_cash_reserve_pct: number
}

/** GET returns {config, valid}; PUT returns {status, config}. Union of both. */
export interface StrategyConfigPayload {
  config: StrategyParams
  /** GET only: false when the active config fails its own validate(). */
  valid?: boolean
  /** PUT only: 'ok'. */
  status?: string
  [key: string]: unknown
}
```

Added inside the existing `api` object (after `placeTrade`):

```ts
  getStrategyConfig: () => request<StrategyConfigPayload>('/api/strategy/config'),
  updateStrategyConfig: (body: StrategyParams) =>
    request<StrategyConfigPayload>('/api/strategy/config', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
```

Both land in the 8 s read bucket, because `/strategy/config` does not match the slow
regex at `lib/api.ts:118` and touches no vendor API — an in-process singleton read/
write that takes longer than 8 s is a dead backend, and saying so in 8 s is correct.
**Do not widen the regex to include it.**

### 5.3 Preserving the 422 error detail

`request()` currently throws an `ApiError` whose message is
`API <path> responded <status>` and discards the response body, so the backend's `{detail: {errors: [...]}}` (422 from
`put_strategy_config`) would be lost — a regression against the raw fetch, which
extracts it at `StrategyConfigCard.tsx:75–81`. Fix additively; **the message string
must not change**, because `tests/api.test.ts:217` asserts it.

```ts
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly cause?: unknown,
    /** HTTP status when the response arrived; undefined on timeout/unreachable. */
    public readonly status?: number,
    /** Parsed error body, when the server sent JSON. FastAPI puts it under `detail`. */
    public readonly detail?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}
```

and in `request()`, replacing only the `!res.ok` branch:

```ts
    if (!res.ok) {
      // Read the body before throwing so validation errors survive. A body that
      // is not JSON (HTML error page, empty 502) must not mask the status.
      let detail: unknown
      try {
        detail = await res.json()
      } catch {
        detail = undefined
      }
      throw new ApiError(`API ${path} responded ${res.status}`, undefined, res.status, detail)
    }
```

Helper used by the card, exported from `lib/api.ts`:

```ts
/** Extracts FastAPI's {detail:{errors:[...]}} into one line, else the message. */
export function apiErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const detail = (err.detail as { detail?: { errors?: unknown } } | undefined)?.detail
    const errors = detail?.errors
    if (Array.isArray(errors) && errors.length > 0) return errors.map(String).join('; ')
    return err.message
  }
  return err instanceof Error ? err.message : 'Request failed'
}
```

`StrategyConfigCard` renders `apiErrorMessage(mutation.error ?? query.error)` in the
existing error block (`:127–132`), unchanged classes.

### 5.4 The `FRONTEND.md` correction

`docs/FRONTEND.md:40` currently reads:

```
├── lib/api.ts                  typed client — the only place fetch() appears
```

Replace with:

```
├── lib/api.ts                  typed client — the ONLY place fetch() appears.
│                               Enforced: every network call goes through
│                               request(), which owns the AbortController
│                               timeout split (30s agent/council/screen, 8s
│                               reads) and the ApiError timed-out-vs-unreachable
│                               distinction. lib/live/** wraps this client in
│                               react-query and never calls fetch() itself.
├── lib/live/                   react-query layer: queryClient, keys+POLICY,
│                               hooks, freshness, stream (see SPEC-F1-LIVE-DATA.md)
```

The claim only becomes true once M5 lands, so **the doc edit ships in the M5
commit, not earlier.** Shipping it in M0 would replace a stale falsehood with a
fresh one.

Also add to `docs/KNOWN-ISSUES.md` under the entry that tracked the dead
`Providers.tsx` stubs (#13): resolved in F1/M0.

## 6 · `freshness.ts`

### 6.1 State machine

Three states, no fourth. `loading` is not a freshness state — a query that has never
resolved has no freshness; it renders a skeleton, and `FreshnessDot` is not mounted
until `dataUpdatedAt > 0 || errorUpdatedAt > 0`.

Inputs are exactly the four react-query fields plus an injectable clock:

| Input | Source | Meaning |
|---|---|---|
| `dataUpdatedAt` | `UseQueryResult.dataUpdatedAt` | ms epoch of last **success**; `0` = never |
| `errorUpdatedAt` | `UseQueryResult.errorUpdatedAt` | ms epoch of last **failure**; `0` = never |
| `isFetching` | `UseQueryResult.isFetching` | a request is in flight right now |
| `interval` | `POLICY[name].refetchInterval` | `number` ms, or `false` for on-demand |
| `now` | optional, defaults `Date.now()` | injected in tests |

Derived quantities:

- `age = now - dataUpdatedAt`
- `staleAfter = interval === false ? ON_DEMAND_STALE_MS : interval * STALE_FACTOR`
- `ON_DEMAND_STALE_MS = 600_000` (10 min) — an on-demand query still goes amber
  eventually, because a council verdict from before lunch is not "live".
- `STALE_FACTOR = 1.5` — one missed tick is jitter (a slow response, a tab that
  just regained focus); two is a problem. A factor of exactly 1.0 makes the dot
  flicker amber on every normal cycle.

### 6.2 Transition table

Evaluated top to bottom; first match wins.

| # | Condition | Result | Rationale |
|---|---|---|---|
| 1 | `errorUpdatedAt > dataUpdatedAt` and `!isFetching` | `offline` | The most recent attempt failed and we are not retrying. Red. |
| 2 | `errorUpdatedAt > dataUpdatedAt` and `isFetching` | `stale` | Failed, but a retry is in flight — amber, not red; red would flicker on every transient blip. |
| 3 | `dataUpdatedAt === 0` and `errorUpdatedAt > 0` | `offline` | Never succeeded; only failures. |
| 4 | `dataUpdatedAt === 0` and `errorUpdatedAt === 0` | `stale` | Nothing has happened yet. Defensive only — callers gate on `> 0`. |
| 5 | `isFetching` | `live` | A successful history plus an in-flight refresh is the healthiest state there is. |
| 6 | `age <= staleAfter` | `live` | Inside the tolerance window. |
| 7 | otherwise | `stale` | Older than 1.5 intervals with no error and no fetch: the timer is paused (hidden tab) or the interval is `false`. |

```ts
export const STALE_FACTOR = 1.5
export const ON_DEMAND_STALE_MS = 600_000

export function freshnessOf(input: FreshnessInput): Freshness {
  const { dataUpdatedAt, errorUpdatedAt, isFetching, interval } = input
  const now = input.now ?? Date.now()
  if (errorUpdatedAt > dataUpdatedAt) return isFetching ? 'stale' : 'offline'
  if (dataUpdatedAt === 0) return errorUpdatedAt > 0 ? 'offline' : 'stale'
  if (isFetching) return 'live'
  const staleAfter = interval === false ? ON_DEMAND_STALE_MS : interval * STALE_FACTOR
  return now - dataUpdatedAt <= staleAfter ? 'live' : 'stale'
}

export function freshnessLabel(state: Freshness): string {
  if (state === 'live') return 'Live'
  if (state === 'stale') return 'Stale'
  return 'Offline'
}
```

### 6.3 `FreshnessDot`

The file is `freshness.ts`, not `.tsx`, so the component is written with
`createElement` — no JSX. This keeps `freshnessOf` importable from the
`environment: 'node'` vitest suite without adding a JSX transform to
`vitest.config.ts`.

Only palette tokens are used: `primary #22c55e` (live), `secondary #fbbf24`
(stale), `error #ef4444` (offline), `on-surface-variant #94a3b8` (label),
`surface-container #131c2e` (chip background), `outline #334155` (chip border).

```ts
import { createElement, type ReactElement } from 'react'

const DOT_CLASS: Readonly<Record<Freshness, string>> = {
  live: 'h-2 w-2 rounded-full bg-[#22c55e]',
  stale: 'h-2 w-2 rounded-full bg-[#fbbf24]',
  offline: 'h-2 w-2 rounded-full bg-[#ef4444]',
}

const CHIP_CLASS =
  'inline-flex items-center gap-1.5 rounded border border-[#334155] ' +
  'bg-[#131c2e] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[#94a3b8]'

export function FreshnessDot(props: {
  state: Freshness
  isFetching?: boolean
  detail?: string
}): ReactElement {
  const { state, isFetching = false, detail } = props
  const label = freshnessLabel(state)
  const title = detail ? `${label} — ${detail}` : label
  // animate-pulse only while a request is genuinely in flight. A dot that
  // always pulses is decoration; a dot that pulses on fetch is information.
  const dotClass = isFetching ? `${DOT_CLASS[state]} animate-pulse` : DOT_CLASS[state]
  return createElement(
    'span',
    { className: CHIP_CLASS, title, role: 'status', 'aria-label': title },
    createElement('span', { className: dotClass, key: 'dot' }),
    createElement('span', { key: 'label' }, label),
  )
}
```

Accessibility: colour alone never carries the meaning — the text label is always
rendered, and `role="status"` + `aria-label` give screen readers the same
information. This mirrors the brief's F2 rule ("Colour alone fails accessibility and
fails a projector").

Every data panel mounts one. `usePortfolioQuery().usingFallback === true` passes
`detail="mock data"`, which is how the brief's "must keep working and must be
visibly labelled" requirement is satisfied without touching the existing fallback
banner.

## 7 · `stream.ts`

`GET /api/agent/stream` **does not exist today.** It is requested in the brief's §9
backend-ask table (line 432). `stream.ts` therefore ships in a state where its
primary path fails, and the way it fails is the whole point of this section.

### 7.1 Absolute prohibition

> `stream.ts` must **NEVER** emit synthetic events on a timer.

No `setInterval` that pushes a fabricated "agent thinking…" event. No random
progress lines. No replaying the last real event with a fresh timestamp. If the
stream endpoint is absent, the correct behaviour is: **zero events**, `status:
'polling'`, `degradedToPolling: true`, and a visible indicator that says the stream
is unavailable. A fake event stream is the exact failure mode the brief's opening
rule names — "every placeholder is a lie that survives into the demo" — and it is
worse here than elsewhere, because the events describe an agent that trades.

`AgentStreamEvent.receivedAt` is stamped from the browser clock **at receipt**,
inside the `EventSource` handler. There is no code path that constructs an
`AgentStreamEvent` outside that handler.

### 7.2 Lifecycle

1. **SSR guard.** `EventSource` is a browser global; it is `undefined` in Node
   during prerender and in the vitest `node` environment. The hook must return
   `{ status: 'idle', events: [], reason: null, degradedToPolling: false,
   reconnectAttempts: 0 }` and open nothing when `typeof window === 'undefined' ||
   typeof EventSource === 'undefined'`. All construction happens inside `useEffect`,
   which never runs on the server.
2. **Connect.** `new EventSource(path)` — same-origin, so it goes through the
   `next.config.js` rewrite. `withCredentials` is not set (no cookies in play).
   `status: 'connecting'` until `onopen`, then `'open'`.
3. **Probe for 404 first.** `EventSource` reports a 404 as a generic `onerror` with
   `readyState === CLOSED`, indistinguishable from a network drop, and it will retry
   forever on its own. So before opening the socket, `fetch(path, { method: 'GET',
   headers: { Accept: 'text/event-stream' } })` and inspect the status. A 404 (or
   405) means the endpoint is absent: set `degradedToPolling: true`, `status:
   'polling'`, `reason: 'Agent stream not implemented (404) — falling back to
   polling'`, and **never construct an EventSource**. Any other outcome proceeds to
   step 2.
4. **Exponential backoff on a real error.** Only for a socket that opened at least
   once, or a probe that failed for a non-404 reason. Delay `1000 * 2 ** attempt`
   capped at `30_000`, i.e. 1 s, 2 s, 4 s, 8 s, 16 s, 30 s, 30 s… After
   `MAX_ATTEMPTS = 6` consecutive failures, stop and settle on `status: 'polling'`,
   `degradedToPolling: true`, `reason: 'Stream unavailable after 6 attempts —
   polling'`. Reset `reconnectAttempts` to 0 on a successful `onopen`.
5. **Cleanup on unmount.** The effect's teardown calls `es.close()`, clears the
   pending `setTimeout`, and sets a `cancelled` flag so a late probe response cannot
   `setState` on an unmounted component. Non-negotiable: an un-closed `EventSource`
   survives client-side navigation and reconnects forever in the background.

### 7.3 Reference implementation

```ts
import { useEffect, useRef, useState } from 'react'

const MAX_ATTEMPTS = 6
const MAX_BACKOFF_MS = 30_000

const IDLE: AgentStreamState = {
  status: 'idle',
  events: [],
  reason: null,
  degradedToPolling: false,
  reconnectAttempts: 0,
}

export function useAgentStream(options?: {
  path?: string
  maxEvents?: number
  enabled?: boolean
}): AgentStreamState {
  const path = options?.path ?? '/api/agent/stream'
  const maxEvents = options?.maxEvents ?? 200
  const enabled = options?.enabled ?? true
  const [state, setState] = useState<AgentStreamState>(IDLE)
  const attempts = useRef(0)

  useEffect(() => {
    if (!enabled) return
    // SSR / non-browser guard: EventSource does not exist in Node.
    if (typeof window === 'undefined' || typeof EventSource === 'undefined') return

    let cancelled = false
    let es: EventSource | null = null
    let timer: ReturnType<typeof setTimeout> | null = null

    const degrade = (reason: string) => {
      if (cancelled) return
      setState((s) => ({
        ...s,
        status: 'polling',
        degradedToPolling: true,
        reason,
      }))
    }

    const push = (type: string, raw: string, id: string | null) => {
      if (cancelled) return
      let data: unknown = raw
      try {
        data = JSON.parse(raw)
      } catch {
        /* keep the raw string; the server may send plain text */
      }
      // receivedAt is stamped HERE, on a real message. Nowhere else.
      const event: AgentStreamEvent = { type, receivedAt: Date.now(), data, id }
      setState((s) => ({ ...s, events: [...s.events, event].slice(-maxEvents) }))
    }

    const open = () => {
      if (cancelled) return
      setState((s) => ({ ...s, status: 'connecting', reason: null }))
      es = new EventSource(path)
      es.onopen = () => {
        if (cancelled) return
        attempts.current = 0
        setState((s) => ({ ...s, status: 'open', reason: null, reconnectAttempts: 0 }))
      }
      es.onmessage = (ev: MessageEvent<string>) => push('message', ev.data, ev.lastEventId || null)
      es.onerror = () => {
        es?.close()
        es = null
        attempts.current += 1
        if (cancelled) return
        if (attempts.current >= MAX_ATTEMPTS) {
          degrade(`Stream unavailable after ${MAX_ATTEMPTS} attempts — polling`)
          return
        }
        const delay = Math.min(1_000 * 2 ** (attempts.current - 1), MAX_BACKOFF_MS)
        setState((s) => ({
          ...s,
          status: 'error',
          reason: `Stream dropped — retrying in ${Math.round(delay / 1000)}s`,
          reconnectAttempts: attempts.current,
        }))
        timer = setTimeout(open, delay)
      }
    }

    // Probe before opening: EventSource cannot report a 404 distinguishably.
    fetch(path, { method: 'GET', headers: { Accept: 'text/event-stream' } })
      .then((res) => {
        if (cancelled) return
        if (res.status === 404 || res.status === 405) {
          degrade(`Agent stream not implemented (${res.status}) — falling back to polling`)
          return
        }
        open()
      })
      .catch(() => {
        if (cancelled) return
        degrade('Agent stream unreachable — falling back to polling')
      })

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
      es?.close()
    }
  }, [path, maxEvents, enabled])

  return state
}
```

### 7.4 Mandatory visible degradation

Wherever the stream is consumed, the indicator is rendered from
`AgentStreamState`, and the `polling` case is never silent:

| `status` | Rendered | Classes |
|---|---|---|
| `open` | `● Stream live` | `bg-[#22c55e]` dot, `text-[#94a3b8]` label |
| `connecting` | `● Connecting…` | `bg-[#fbbf24] animate-pulse` |
| `error` | `● {reason}` (includes the retry countdown) | `bg-[#fbbf24]` |
| `polling` | `● Polling — stream unavailable` plus `reason` as `title` | `bg-[#fbbf24]` |
| `idle` | nothing (stream disabled or not a browser) | — |

`polling` is **amber, not green**. A green indicator over a polling fallback is a
claim the app cannot back. The polling itself is already happening: it is the F1
`POLICY` intervals, which are the fallback — `stream.ts` starts no timers of its own.

## 8 · Preserved-behaviour checklist

Three behaviours in `lib/api.ts` were paid for with real debugging. They are not
refactor targets. Each is a regression test, not a comment.

### 8.1 The 30 s / 8 s timeout split (`lib/api.ts:114–119`)

```ts
const slow = /\/(agent\/run|council\/(cycle|assess)|strategy\/screen)/.test(path)
const timeout = setTimeout(() => controller.abort(), slow ? 30000 : 8000)
```

- **Bug it fixed.** A flat 5 s budget aborted `/council/cycle`, `/agent/run` and
  `/strategy/screen` mid-flight. Those endpoints fan out to Alpaca and Yahoo *per
  symbol* and take ~2 s locally, more over a tunnel. Every abort surfaced as
  `API … unreachable`, which reads as a dead backend.
- **Regressing it re-opens.** A working backend that reports itself dead on every
  agent action. Worse under react-query, which would then retry — turning one
  false negative into two full fan-outs.
- **How F1 preserves it.** `lib/live/**` never calls `fetch`. Every `queryFn` and
  `mutationFn` calls an `api.*` method, so the split applies unchanged. The regex is
  not touched; `/strategy/config` deliberately stays in the 8 s bucket (§5.2).
- **Guarded by.** `tests/api.test.ts:131–149` (mirrored predicate + "keeps the
  mirrored regex identical to the source"), extended by T27/T28 in §9.

### 8.2 `AbortError` vs unreachable (`lib/api.ts:133–143`)

```ts
if (err instanceof DOMException && err.name === 'AbortError') {
  throw new ApiError(`API ${path} timed out`, err)
}
throw new ApiError(`API ${path} unreachable`, err)
```

- **Bug it fixed.** Both conditions previously produced one indistinguishable
  message. "Timed out" and "unreachable" have different causes and different fixes:
  the first means the backend is alive and slow (wait, or widen the budget); the
  second means wrong host, wrong port, or a dead process. Merging them sent
  debugging down the wrong path repeatedly — including the
  `API_BASE_URL = 'http://localhost:8000'` incident, where every request was
  "unreachable" for anyone not at the dev box.
- **Regressing it re-opens.** Undiagnosable network failures, and the false-host
  class of bug becomes invisible again.
- **How F1 preserves it.** The `!res.ok` branch gains `status` and `detail` (§5.3),
  additively. The two `catch`-branch messages are byte-identical, and the
  `DOMException`/`AbortError` check is untouched. react-query surfaces the thrown
  `ApiError` as `query.error`, so the message reaches the UI verbatim.
- **Guarded by.** `tests/api.test.ts:226` and `:236`, extended by T32/T33 in §9.

### 8.3 The mock-portfolio fallback (`lib/api.ts:422–468`)

- **Bug it fixed.** With the backend down, the dashboard and assets pages rendered
  `$0.00` equity and an empty positions table — indistinguishable from a real empty
  account. `mock_portfolio.json` plus the `usingFallback` flag makes "we could not
  reach the backend" visually distinct from "you hold nothing".
- **Regressing it re-opens.** A zeroed dashboard read as a real flat account —
  precisely the brief's opening rule ("Zero is a claim of flatness").
- **How F1 preserves it.** `usePortfolioQuery` reproduces it exactly, including
  the `usingFallback` flag, and now labels it via `FreshnessDot detail="mock data"`:

```ts
import { useQuery } from '@tanstack/react-query'
import { api, type PortfolioSnapshot } from '../api'
import mockPortfolio from '../../app/data/mock_portfolio.json'
import { POLICY, queryKeys } from './keys'
import { useVisibilityPause } from './hooks'

const FALLBACK = mockPortfolio as unknown as PortfolioSnapshot

export function usePortfolioQuery() {
  const visible = useVisibilityPause()
  const policy = POLICY.portfolio
  const query = useQuery<PortfolioSnapshot, Error>({
    queryKey: queryKeys.portfolio(),
    queryFn: () => api.getPortfolio(),
    refetchInterval: policy.refetchInterval,
    refetchIntervalInBackground: policy.refetchIntervalInBackground,
    staleTime: policy.staleTime,
    retry: policy.retry,
    enabled: visible,
  })
  // Fallback ONLY when there is no successful data at all. A transient failure
  // after a good fetch keeps the last real snapshot (amber dot), because
  // replacing live numbers with mock numbers on a blip would be a lie.
  const usingFallback = query.isError && query.data === undefined
  return {
    ...query,
    data: usingFallback ? FALLBACK : query.data,
    usingFallback,
  }
}
```

- **Guarded by.** T35/T36 in §9.

Additional invariants that must survive, restated so nobody "cleans them up":

| Invariant | Location | Why |
|---|---|---|
| `API_BASE_URL` defaults to `''` | `lib/api.ts:23` | A hardcoded host resolves to the *visitor's* machine |
| `getHealth()` requests `/api/health`, never `/health` | `lib/api.ts:263` | Only `/api/*` is proxied by `next.config.js`; bare `/health` 404s at the Next origin |
| `assessCouncil()` GETs with no symbols, POSTs with symbols | `lib/api.ts:286–292` | Backend exposes both; the GET path is the demo default |
| `normalizeScreenings` never throws on a malformed shape | `lib/api.ts:308–337` | Screen responses have four documented shapes plus junk |
| `toFeedEntry`'s 1.5 fraction/percent boundary | `lib/api.ts:392–397` | Backend yields are fractional; some paths pre-multiply |

## 9 · Tests

Extend the **existing** suite. `frontend/vitest.config.ts` is already correct
(`environment: 'node'`, `include: ['tests/**/*.test.ts']`, alias `@ → ./app`) and
`npm run test` already runs `vitest run`. **Do not add a runner, a config file, or a
DOM environment.** `environment: 'node'` is why `freshness.ts` uses `createElement`
instead of JSX and why hook tests assert pure functions rather than rendering.

New file `frontend/tests/live.test.ts`:

| # | Test | Assertion |
|---|---|---|
| T01 | `POLICY.agentRun.refetchInterval` is `false` | the mutation can never be scheduled |
| T02 | every `POLICY` entry has `refetchIntervalInBackground === false` | hidden-tab suppression is universal, not per-hook |
| T03 | every `POLICY` entry has a non-empty `cost` string | no interval lands without a justification |
| T04 | `POLICY.screen.refetchInterval >= 300_000` and `POLICY.screen.retry === 0` | the per-symbol fan-out is never polled fast and never doubled by a retry |
| T05 | `POLICY.portfolio.refetchInterval <= POLICY.screen.refetchInterval` | cheap reads poll faster than expensive ones |
| T06 | `policyFor('agentRun')` throws if the fixture's interval is mutated to a number | the guard is live, not decorative |
| T07 | `queryKeys.council(['B','A'])` equals `queryKeys.council(['A','B'])` | symbol order never causes a cache miss |
| T08 | `queryKeys.council()` differs from `queryKeys.council(['AAPL'])` | the default universe is a distinct request |
| T09 | every `queryKeys` factory returns a stable, frozen-shaped tuple across calls | keys are structurally equal, so react-query dedupes |
| T10 | `QUERY_DEFAULTS.queries.refetchIntervalInBackground === false` and `.refetchInterval === false` | a new hook cannot poll by omission |
| T11 | `QUERY_DEFAULTS.mutations.retry === 0` | `/agent/run` and the config PUT are never auto-retried |
| T12 | `makeQueryClient()` returns a distinct instance on each call | no cache shared across server requests |
| T13 | `freshnessOf` → `'live'` when `dataUpdatedAt = now` and `interval = 20_000` | fresh data inside the window is green |
| T14 | `freshnessOf` → `'live'` at `age = 30_000` with `interval = 20_000` | 1.5× tolerance absorbs one jittery tick |
| T15 | `freshnessOf` → `'stale'` at `age = 30_001` with `interval = 20_000` | the boundary is inclusive at exactly 1.5× |
| T16 | `freshnessOf` → `'offline'` when `errorUpdatedAt > dataUpdatedAt` and `!isFetching` | last attempt failed, no retry pending |
| T17 | `freshnessOf` → `'stale'` when `errorUpdatedAt > dataUpdatedAt` and `isFetching` | a retry in flight is amber, never red |
| T18 | `freshnessOf` → `'offline'` when `dataUpdatedAt === 0 && errorUpdatedAt > 0` | never succeeded once |
| T19 | `freshnessOf` → `'live'` when `isFetching` and `dataUpdatedAt` is ancient | an in-flight refresh over prior success is healthy |
| T20 | `freshnessOf` with `interval: false` → `'live'` at 9 min, `'stale'` at 11 min | on-demand queries still age out at `ON_DEMAND_STALE_MS` |
| T21 | `freshnessOf` is pure: identical inputs with an injected `now` give identical output | no hidden `Date.now()` read |
| T22 | `freshnessLabel` covers all three states with non-empty distinct strings | colour is never the only signal |
| T23 | `FreshnessDot` class strings only reference `#22c55e`, `#fbbf24`, `#ef4444`, `#94a3b8`, `#131c2e`, `#334155` | palette lock — assert by regex over the exported class maps |
| T24 | `FreshnessDot` includes `animate-pulse` only when `isFetching` | the pulse means "fetching", not "decorative" |

Additions to the existing `frontend/tests/api.test.ts` (same file, same style):

| # | Test | Assertion |
|---|---|---|
| T25 | `api.getStrategyConfig()` requests `/api/strategy/config` with no `method` override | the GET goes through `request()` |
| T26 | `api.updateStrategyConfig(params)` requests `/api/strategy/config` with `method: 'PUT'`, `Content-Type: application/json`, and the serialised body | the mutating write goes through `request()` |
| T27 | `/api/strategy/config` classifies as **fast** (8 s) under the mirrored slow-path regex | the config endpoint is deliberately not in the 30 s bucket |
| T28 | `/api/strategy/screen`, `/api/agent/run`, `/api/council/cycle`, `/api/council/assess` all classify as slow (30 s); `/api/portfolio`, `/api/health`, `/api/trade` do not | the split is unchanged after F1's edits |
| T29 | a 422 from `updateStrategyConfig` throws `ApiError` with `message` `API /api/strategy/config responded 422`, `status === 422`, and `detail.detail.errors` preserved | the validation reason survives `request()` |
| T30 | `apiErrorMessage` joins `detail.detail.errors` with `'; '` | matches the raw-fetch behaviour it replaces |
| T31 | `apiErrorMessage` falls back to `err.message` when there is no `errors` array, and to `'Request failed'` for a non-Error | no `undefined` in the UI |
| T32 | an aborted `updateStrategyConfig` throws `API /api/strategy/config timed out`, not `unreachable` | the PUT now has a timeout at all — the §5.1 defect, as a test |
| T33 | a network rejection from `getStrategyConfig` throws `… unreachable` | the two failure modes stay distinguishable on the config path |
| T34 | `ApiError` with no `status`/`detail` still constructs and keeps `name === 'ApiError'` | the added constructor params are optional |
| T35 | `usePortfolioQuery`'s fallback selector (extracted as a pure `pickPortfolio(isError, data, fallback)`) returns the mock only when `data === undefined` | a blip after a good fetch keeps real numbers |
| T36 | the same selector reports `usingFallback === true` exactly when the mock is returned | the flag and the data never disagree |

New file `frontend/tests/stream.test.ts` (node environment; `EventSource` is
absent, which is the point):

| # | Test | Assertion |
|---|---|---|
| T37 | with `globalThis.EventSource` undefined, the stream module imports and its `IDLE` state is `{status:'idle', events:[], degradedToPolling:false}` | the SSR guard holds; importing never touches a browser global |
| T38 | `grep`-style source assertion: `lib/live/stream.ts` contains no `setInterval` | the "never fake events on a timer" rule is machine-checked |
| T39 | the backoff schedule helper returns `[1000, 2000, 4000, 8000, 16000, 30000, 30000]` for attempts 1..7 | exponential with a 30 s cap |
| T40 | the 404/405 branch produces `status: 'polling'`, `degradedToPolling: true`, and a `reason` containing `'polling'` | degradation is visible and never silent |

Extract the backoff into an exported pure `streamBackoffMs(attempt: number): number`
and the degradation reason into an exported pure
`degradedReason(status: number): string` so T39/T40 assert real code rather than a
transcription of it.

### Acceptance gate for F1

```
cd frontend
npx tsc --noEmit                                     # clean
npm run test                                         # existing suite + T01–T40 green
grep -rn "useEffect(() *=> *{[^}]*api\." app/        # no hits
grep -rn "fetch(" app/                               # no hits
grep -rn "refetchInterval:" app/ lib/ | grep -v lib/live/keys.ts   # no hits
grep -rln "Providers" app/*/Providers.tsx            # no such files
```

Plus the brief's own criteria: all five pages migrated, a freshness dot on every data
panel, and the stream indicator reading "Polling — stream unavailable" until §9's
`GET /api/agent/stream` exists.

