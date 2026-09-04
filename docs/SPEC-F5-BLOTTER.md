# SPEC-F5 · Order approval queue + blotter (`/blotter`)

**Workstream:** F5 of `docs/BRIEF-FRONTEND-V2.md`
**Closes:** `docs/KNOWN-ISSUES.md` #7 · **Designs around:** #2
**Transports (all EXIST today):**
`POST /api/agent/run` → `AgentRunResponse.order_intents` (`backend/app/routes/agent.py::_order_intents`)
`POST /api/trade` → `TradeResponse` (`backend/app/routes/trade.py:65`)
`GET /api/trade/orders?status=` → `{ mode, orders }` (`backend/app/routes/trade.py:114`) — **called by nothing in the frontend today**
**Governing rule:** `docs/FRONTEND.md` — never render a number the backend did not
produce. Corollary for this route: **never send a field the agent did not produce.**

Scope: new route `app/blotter/page.tsx`, new component dir
`app/components/blotter/`, new pure modules `lib/blotter/machine.ts`,
`lib/blotter/map.ts`, `lib/blotter/orders.ts`. Links added from `/dashboard`
and `/terminal` (link only — no logic moves).

Out of scope, do not touch: `backend/**`, `agent/**`. This spec asks the backend
for two things (§4, §5) and specifies what the UI does **until** they exist.

Dependency budget: only what `frontend/package.json` already has —
`@tanstack/react-query`, `framer-motion`, `lucide-react`, `zod`,
`@radix-ui/react-*`, `clsx`, `tailwind-merge`. No table library, no state
library, no uuid package (`crypto.randomUUID()` is in every target browser and
in Node 18+ for vitest).

Colour budget: `background #020617`, `surface #0f172a`,
`surface-container #131c2e`, `surface-container-high #1a2332`,
`primary #22c55e`, `secondary #fbbf24`, `error #ef4444`,
`on-surface #f8fafc`, `on-surface-variant #94a3b8`, `outline #334155`.

---

## 0 · Why this route exists

`POST /api/trade` places a **real Alpaca paper order** and, per
`docs/BRIEF-BACKEND-V2.md` **D4**, has *zero* coupling to the risk system: it
validates syntax (OCC format, NaN, magnitude, TIF) and nothing else — no
coverage, no collateral, no kill-switch, no concentration, no provenance. The
reproduced case in D4 is 500 short calls on a symbol the portfolio does not
hold, returning 200.

So the UI is currently the *only* thing between a click and a broker order.
That is not an acceptable architecture, and this spec does not pretend it is:
every guard below is a **UX affordance**, and §4 says so in the file the next
reader will open. The real gate is backend **B2** (pre-trade risk gate, HTTP 409)
plus **B3** (idempotency + order ledger). This spec is written so that when B2/B3
land, the UI needs *additive* changes only — a 409 renderer and a `duplicate: true`
badge — and no guard has to be removed.

---

## 1 · Types — `lib/blotter/types.ts`

Every field below exists in a payload verified against the current backend.
`OrderIntent`, `TradeRequest`, `TradeResponse` are imported from `lib/api.ts`
unchanged. `Order` is imported from `app/types/portfolio.ts` unchanged, then
widened, because Alpaca returns statuses that type does not list.

```ts
import type { OrderIntent, TradeRequest, TradeResponse } from '@/lib/api'

/** Stable identity for an intent across re-renders and reloads.
 *  Derived, not random: the same intent from the same run always hashes the
 *  same, so a reload can re-attach persisted decisions to re-fetched intents. */
export type IntentKey = string

export type ApprovalState =
  | 'intent'
  | 'pending_approval'
  | 'confirming'
  | 'submitting'
  | 'submitted'
  | 'filled'
  | 'partially_filled'
  | 'rejected'
  | 'blocked'
  | 'error'

/** Terminal — no transition leaves these except an explicit operator reset. */
export const TERMINAL_STATES: readonly ApprovalState[] = [
  'filled',
  'partially_filled',
  'rejected',
  'error',
] as const

export interface BlockReason {
  /** Which authority blocked it. Never invented by the UI. */
  source: 'kill_switch' | 'red_team' | 'contract_unresolved' | 'risk_gate'
  /** Verbatim from the payload where one exists. */
  detail: string
}

export interface IntentRecord {
  key: IntentKey
  /** Verbatim intent from POST /api/agent/run. Never mutated. */
  intent: OrderIntent
  /** run_id of the AgentRunResponse that produced it — provenance for B2 check 8. */
  runId: string
  state: ApprovalState
  /** Client-generated, persisted, reused on retry. See §3. */
  idempotencyKey: string
  /** Operator-entered limit override, or null if untouched. */
  limitOverride: number | null
  /** Non-empty only in 'blocked'. */
  blocks: BlockReason[]
  /** Operator reason, 'rejected' only. Local, never sent. */
  rejectReason: string | null
  /** Set once POST /api/trade resolves. */
  response: TradeResponse | null
  /** Broker order id once known — the join key to the blotter. */
  brokerOrderId: string | null
  /** ISO timestamps, for the audit column. */
  approvedAt: string | null
  /** Set synchronously immediately before fetch. Survives reload. See §4.2. */
  submitIntendedAt: string | null
  submittedAt: string | null
  /** True when reconciliation used the last-resort heuristic (§6.3). */
  matchedHeuristically?: boolean
}
```

### 1.1 · Identity: `IntentKey`

```ts
/** Deterministic. Two intents with the same economics in the same run collapse
 *  to one key — which is what we want, because submitting both would be the
 *  duplicate we are trying to prevent. */
export function intentKey(runId: string, intent: OrderIntent): IntentKey {
  return [
    runId,
    intent.symbol,
    intent.option_symbol ?? 'NOCONTRACT',
    intent.side,
    intent.type,
    String(intent.qty),
    intent.limit_price === null ? 'NOLIMIT' : intent.limit_price.toFixed(4),
  ].join('|')
}
```

No hashing library: the key is an opaque string, never displayed, and collision
resistance across a single `run_id` is not a security property.

---

## 2 · The approval state machine — `lib/blotter/machine.ts`

Pure. No React, no fetch, no `Date.now()` passed implicitly — the caller supplies
timestamps so tests are deterministic. This is the module vitest hammers (§7).

### 2.1 · States and exactly what the UI renders

| State | Meaning | Row chrome | Primary control | Detail shown |
|---|---|---|---|---|
| `intent` | Received from `/api/agent/run`, not yet triaged. Only possible when `requires_approval === false` — which the current backend never emits. | `border-outline`, text `on-surface-variant` | none | badge `INTENT` `outline` |
| `pending_approval` | The normal arrival state (`requires_approval: true`). | `border-outline`, `bg-surface-container` | **Approve** (`primary`), **Reject** (`outline`), **Modify limit** (`outline`) | badge `NEEDS APPROVAL` in `secondary` |
| `confirming` | Operator clicked Approve. Confirmation dialog open. **No request has been sent.** | row dimmed to 60%, dialog above | **Confirm & submit** (`primary`), **Cancel** (`outline`) | the §3.1 restatement block, verbatim |
| `submitting` | `POST /api/trade` in flight. | row `bg-surface-container-high`, spinner | all controls `disabled` | text `Submitting… do not reload` + the idempotency key, monospace, `on-surface-variant` |
| `submitted` | 2xx received, order accepted, not yet filled. | `border-primary/40` | **Cancel order** only if a cancel endpoint exists — **it does not today, so: none** | broker `id`, `status` verbatim, `mode` badge (`live`/`mock`) |
| `filled` | Blotter reconciliation saw `status === 'filled'`. | `border-primary`, `text-primary` | none | fill qty + `filled_avg_price` if present, else `—` |
| `partially_filled` | Blotter saw `partially_filled`. | `border-secondary` | none | `filled_qty / qty` |
| `rejected` | Operator declined. **Terminal. Nothing was sent.** | row at 45% opacity, `line-through` on symbol | **Undo** (returns to `pending_approval`, ≤10s window) | `Rejected — {reason}` in `on-surface-variant` |
| `blocked` | Kill-switch halted, red-team `BLOCK`, or unresolved contract. Approve is not offered. | `border-error/40`, `bg-surface-container` | **Approve disabled** with `title` = reason | every `BlockReason.detail`, inline, one per line, `error` |
| `error` | Request failed: network, timeout, non-2xx, or `submitted: false`. | `border-error` | **Retry** (reuses the same idempotency key) | `ApiError.message` verbatim + HTTP status when known |

Rendering rule inherited from `docs/FRONTEND.md` and KNOWN-ISSUES #2: an absent
`option_symbol` renders **`contract pending`**, an absent `limit_price` renders
**`no limit set`**. Never `—` in the confirmation dialog (an em dash reads as
"nothing to see"); `—` stays acceptable in dense table cells only.

### 2.2 · Transitions — every one, with its trigger

| # | From | To | Trigger | Side effect |
|---|---|---|---|---|
| T1 | *(none)* | `pending_approval` | intent arrives with `requires_approval === true` | record created, `idempotencyKey` minted once |
| T2 | *(none)* | `intent` | intent arrives with `requires_approval === false` | record created, no controls |
| T3 | *(none)* | `blocked` | intent arrives while `risk_summary.halted === true`, or its directive carries a red-team `BLOCK`, or `option_symbol === null` | `blocks[]` populated from the payload |
| T4 | `intent` | `pending_approval` | operator clicks **Queue for approval** | none |
| T5 | `pending_approval` | `confirming` | operator clicks **Approve** | dialog opens. **No network call.** |
| T6 | `confirming` | `pending_approval` | **Cancel**, `Esc`, or backdrop click | dialog closes, nothing sent |
| T7 | `confirming` | `submitting` | operator clicks **Confirm & submit** | `approvedAt` set, `inflight` set, `POST /api/trade` issued |
| T8 | `submitting` | `submitted` | 2xx **and** (`submitted === true` or `mode === 'mock'`) | `brokerOrderId` = `res.order?.id ?? res.id ?? null`; `submittedAt` set |
| T9 | `submitting` | `error` | non-2xx, `ApiError`, timeout, **or** 2xx with `submitted === false` and `mode !== 'mock'` | `response` stored, reason rendered verbatim |
| T10 | `submitting` | `blocked` | HTTP **409** once B2 exists (§4) | `blocks[]` from the `checks` array |
| T11 | `submitted` | `filled` | blotter poll returns a matching order with `status === 'filled'` | polling for this row stops |
| T12 | `submitted` | `partially_filled` | poll returns `partially_filled` | polling continues |
| T13 | `partially_filled` | `filled` | poll returns `filled` | polling stops |
| T14 | `submitted` \| `partially_filled` | `error` | poll returns `rejected`, `canceled`, `expired`, `suspended` | broker status rendered verbatim |
| T15 | `pending_approval` \| `intent` | `rejected` | operator clicks **Reject** and supplies a reason | reason stored locally. **Assert: zero requests.** |
| T16 | `rejected` | `pending_approval` | **Undo** within 10s | reason cleared |
| T17 | `error` | `submitting` | **Retry** | **same** `idempotencyKey` reused — never re-minted |
| T18 | `pending_approval` | `pending_approval` | **Modify limit** committed | `limitOverride` set; `type` becomes `'limit'` in the mapping (§3) |
| T19 | any non-terminal | `blocked` | a later `/api/agent/run` or kill-switch read reports `halted` | in-flight requests are **not** cancelled (see note) |

**Note on T19.** A request already sent cannot be unsent. If halt arrives while a
row is `submitting`, the row completes its transition (T8/T9/T10) and *then* the
banner explains that a halt was declared mid-submit. Pretending otherwise would
be the lie the whole route exists to avoid.

### 2.3 · Signature

```ts
export type ApprovalEvent =
  | { kind: 'queue' }
  | { kind: 'approve' }
  | { kind: 'cancel_confirm' }
  | { kind: 'confirm_submit'; at: string }
  | { kind: 'submit_ok'; at: string; response: TradeResponse }
  | { kind: 'submit_fail'; message: string; status?: number }
  | { kind: 'submit_blocked'; blocks: BlockReason[] }
  | { kind: 'reject'; reason: string }
  | { kind: 'undo_reject' }
  | { kind: 'retry' }
  | { kind: 'set_limit'; limit: number | null }
  | { kind: 'broker_status'; status: string }
  | { kind: 'halt'; blocks: BlockReason[] }

/** Total function: an illegal event returns the record unchanged.
 *  Throwing here would let one bad payload blank the page. */
export function reduceIntent(rec: IntentRecord, ev: ApprovalEvent): IntentRecord

export function isTerminal(s: ApprovalState): boolean
export function canApprove(rec: IntentRecord, halted: boolean): boolean
```

`canApprove` is the single source of truth for button `disabled`. It returns
`false` when `halted`, when `rec.blocks.length > 0`, when `rec.state !== 'pending_approval'`,
or when a submit for that key is in flight. One function, one test file, no
`disabled={...}` expressions duplicated across components.

### 2.4 · What a page reload lands in

There is **no server-side record of an approval** today (that is B3). So:

- `IntentRecord[]` is persisted to `sessionStorage` under
  `autooverlay.blotter.v1`, keyed by `IntentKey`, on every reducer step.
- On mount, records are rehydrated, then **`/api/agent/run` is NOT re-fired**.
  The blotter is a consumer of the run held in `AgentRunProvider`; if the
  provider has no run, the page shows *"No agent run in this session — run the
  agent from /dashboard or /terminal, then return here."*
- Reload lands each state as follows:

| Persisted state | State after reload | Why |
|---|---|---|
| `intent`, `pending_approval`, `blocked`, `rejected` | unchanged | no in-flight side effect |
| `confirming` | **`pending_approval`** | a dialog is not a commitment; re-arming Approve is safe, re-opening a modal on load is not |
| `submitting` | **`error`** with message *"Submit was interrupted by a page reload; outcome unknown. Check the blotter before retrying."* and Retry **disabled** until one blotter refresh completes | see §3.3 |
| `submitted`, `partially_filled` | unchanged, then reconciled by the first poll | broker is the authority |
| `filled`, `error` | unchanged | terminal |

---

## 3 · The submit guard

### 3.1 · The confirmation step

`app/components/blotter/ConfirmSubmit.tsx`. Reached only by T5. It restates the
order in operator language, from the record, with no derived numbers:

```
  You are about to place a REAL order on the Alpaca paper account.

  Symbol            AAPL
  Side              SELL  (sell to open)
  Contracts         2          (qty sent: 2)
  Option contract   contract pending — no OCC symbol resolved
  Order type        MARKET     ← no limit price was set
  Limit price       no limit set
  Time in force     day
  Run              run-9f2c…            Intent  AAPL|NOCONTRACT|sell|market|2|NOLIMIT

  [ Cancel ]                                    [ Confirm & submit ]
```

Hard requirements:

1. **Nothing is sent before Confirm.** T5 opens the dialog, T7 sends. A vitest
   test asserts `reduceIntent(rec, {kind:'approve'})` performs no I/O by
   construction (the reducer cannot reach `fetch` — it is a pure module).
2. `Confirm & submit` is **not** the default-focused element. Focus lands on
   `Cancel`; `Enter` therefore cancels, `Esc` cancels. A keyboard mis-press must
   not place an order.
3. The word **MARKET** appears in `error` colour with the trailing clause
   `← no limit price was set` whenever the effective type is market. This is
   non-negotiable per KNOWN-ISSUES #2: the normal case must be *loud*.
4. `Confirm & submit` requires a deliberate second gesture when the effective
   type is market: a checkbox `I accept an unpriced market order` must be ticked
   before the button enables. Limit orders need no checkbox.

### 3.2 · `OrderIntent` → `TradeRequest`, field by field

`lib/blotter/map.ts`. Verified against `TradeRequest` in `frontend/lib/api.ts`
**and** `backend/app/routes/trade.py::TradeRequest` (which aliases `type` and
rejects `limit_price` on market orders).

| `TradeRequest` field | Source | Transform | If source is absent |
|---|---|---|---|
| `symbol` | `intent.option_symbol ?? intent.symbol` | `.toUpperCase().trim()` (backend upper-cases too; doing it here keeps the confirmation text and the request identical) | never absent: `intent.symbol` is always present. When `option_symbol` is null the **underlying** ticker is sent — see §3.3 |
| `qty` | `intent.qty` | `Number(intent.qty)`; must be `> 0` and finite | if not `> 0` and finite → **do not send**, row → `error` with *"agent produced qty={value}; refusing to submit"* |
| `side` | `intent.side` | narrowed: `'buy' \| 'sell'` via `side === 'buy' ? 'buy' : side === 'sell' ? 'sell' : null` | `null` → **do not send**, row → `error`. No default. Defaulting a side is how you sell something you meant to buy |
| `type` | effective type = `limitToSend === null ? 'market' : 'limit'` | literal `'market' \| 'limit'` | never absent — always derived, never copied from `intent.type` |
| `limit_price` | `rec.limitOverride ?? intent.limit_price` | if `null` → **omit the key entirely**; else `Number(v)`, must be finite and `> 0` | omitted. **Never `0`, never `"0"`, never `null` on the wire.** See §3.3 |
| `time_in_force` | `intent.time_in_force` | lower-cased; if the effective symbol parses as OCC, force `'day'` (backend rejects anything else for options) | `'day'` |

Not sent, deliberately: `intent.action`, `intent.strategy`, `intent.contracts`,
`intent.requires_approval`, `intent.submitted`. The current backend `TradeRequest`
has no fields for them and Pydantic would either ignore or reject them. `contracts`
is displayed in the dialog and *not* sent — `qty` is the wire field, and the
dialog shows both so an operator can see if the agent disagreed with itself.

```ts
export type MapFailure = { ok: false; reason: string }
export type MapSuccess = { ok: true; request: TradeRequest; effectiveType: 'market' | 'limit' }

export function toTradeRequest(rec: IntentRecord): MapSuccess | MapFailure
```

A discriminated union, not a thrown error and not a partially-filled object:
the caller cannot accidentally submit a failed mapping.

### 3.3 · The two null cases — the normal case, per KNOWN-ISSUES #2

`_order_intents()` reads `params.get("option_symbol")` / `params.get("limit_price")`
from `INITIATE` directives that carry tier policy, not a resolved contract. Verified
result: `option_symbol` is always `null`, `limit_price` is always `null`, `type`
always falls back to `"market"`. Design for that as the default path.

(`agent.py` now attempts `_pick_option_contract()` before that fallback. When it
succeeds both fields are populated and the limit path below applies unchanged;
when it returns nothing the `params` fallback runs and #2 is reproduced exactly.
The UI must handle both without a code path that only works in one of them — which
is why every rule here is keyed on the *value* being null, never on issue #2 being
open or closed.)

**`option_symbol === null`.**

- The row enters `blocked` at T3 with
  `{ source: 'contract_unresolved', detail: 'No option contract resolved (KNOWN-ISSUES #2). The agent produced a directive, not a tradeable contract.' }`.
- Approve is **disabled**. Rationale: the intent's `action` is `SELL_TO_OPEN` and
  its `strategy` is an option strategy. Sending the *underlying ticker* would
  submit an equity order — selling 2 shares of AAPL instead of 2 covered calls.
  That is not a degraded version of the intended trade; it is a different trade.
- The row offers **Enter contract manually**: a text input validated client-side
  against the OCC shape `^[A-Z]{1,6}\d{6}[CP]\d{8}$` (the same shape
  `parse_occ_symbol` accepts). On a valid entry the row leaves `blocked` for
  `pending_approval`, and the confirmation dialog labels the contract
  `manually entered — not agent-resolved` in `secondary`. The record keeps
  `intent` untouched and stores the override separately, so provenance survives.
- If the intent's `strategy` is an equity strategy (no option semantics), the
  underlying ticker is the correct symbol and no block applies. Decided by
  strategy string, never by "the field was null so use the other one".

**`limit_price === null`.**

- The `limit_price` key is **omitted** from the JSON body. Not `0`, not `null`,
  not `""`. Sending `0` would be rejected by the backend (`gt=0`) — but the
  danger is a future backend that coerces it, so the frontend never constructs
  it. Sending `null` is also refused here because the backend's
  `order_type == "market" and limit_price is not None` check treats explicit
  `null` as absent today, and relying on that is relying on a `None` comparison
  we do not own.
- `type` becomes `'market'`, and §3.1 item 3 + item 4 make the operator *read
  and tick* that fact. A null limit never silently becomes a market order.
- **Modify limit** is the escape hatch: entering a price sets `limitOverride`,
  the effective type flips to `'limit'`, the market-order checkbox disappears,
  and the value is echoed in the confirmation dialog. Input validation:
  finite, `> 0`, and for OCC symbols within `0.01 … 10000` (mirrors the backend
  validator, so the operator sees the error before the round trip).

Invariant, tested in vitest (§7):

```ts
// for every OrderIntent fixture, with and without overrides:
const m = toTradeRequest(rec)
if (m.ok) {
  const body = JSON.parse(JSON.stringify(m.request))
  if (m.effectiveType === 'market') expect('limit_price' in body).toBe(false)
  else expect(body.limit_price).toBeGreaterThan(0)
  expect(body.limit_price).not.toBe(0)
  expect(body.limit_price).not.toBe('0')
}
```

---

## 4 · Idempotency and double-submit protection

`POST /api/trade` reaches Alpaca. Per D4 the backend performs no duplicate check
(that is B3, unbuilt). Two clicks today = two orders. Therefore:

### 4.1 · Client-side controls (all three, not one)

1. **Disabled while in flight.** A module-scope `Set<IntentKey>` of in-flight
   keys lives in `lib/blotter/inflight.ts`, not in React state. React state is
   asynchronous — two clicks inside one render batch both read the stale
   `false`. The set is checked and inserted **synchronously** in the click
   handler before `await`:

   ```ts
   const inflight = new Set<IntentKey>()
   export function claim(key: IntentKey): boolean {
     if (inflight.has(key)) return false
     inflight.add(key)
     return true
   }
   export function release(key: IntentKey): void { inflight.delete(key) }
   ```

   `claim()` returning `false` is a silent no-op — no second request, no error
   toast. `release()` runs in `finally`. This is what makes a double-click submit
   exactly once even when the button's `disabled` prop has not repainted yet.

2. **Client-generated idempotency key.** Minted once at T1 and persisted with the
   record:

   ```ts
   export function mintIdempotencyKey(): string {
     return `aoc-${crypto.randomUUID()}`
   }
   ```

   It is sent as `client_order_id` — the field `backend/app/routes/trade.py`
   **already accepts** (`Optional[str], max_length=128`) and already forwards to
   Alpaca. Alpaca itself rejects a duplicate `client_order_id`, so a retry with
   the same key converges instead of duplicating. This makes the guard real today,
   without any backend change. Adding it to `TradeRequest` in `lib/api.ts` is a
   one-field additive change:

   ```ts
   // lib/api.ts — additive, optional, matches the existing backend field
   client_order_id?: string
   ```

   T17 (Retry) reuses the key. Re-minting on retry would defeat the entire
   mechanism, so `reduceIntent` never writes `idempotencyKey` after T1.

3. **Confirmation step.** §3.1. Two gestures minimum, three for market orders.

### 4.2 · Reload mid-submit

The in-flight `Set` dies with the page; `sessionStorage` does not. So:

1. Before `fetch`, the record is written with `state: 'submitting'` **and** a
   `submitIntendedAt` ISO stamp. This write is synchronous and lands before the
   request leaves.
2. On reload, any record found in `submitting` is moved to `error` with the
   interrupted-submit message (§2.4) and **Retry disabled**.
3. The page immediately calls `GET /api/trade/orders?status=all` and matches on
   `client_order_id === rec.idempotencyKey`. That field is in the Alpaca order
   object and in `mock_portfolio.json`'s orders (verified). Outcomes:
   - **Match found** → the record is promoted to `submitted` / `filled` /
     `partially_filled` from the broker status. The duplicate is prevented not by
     hoping, but by looking.
   - **No match** and the reload was within 60s of `submitIntendedAt` → Retry
     stays disabled with *"Waiting for broker confirmation…"* and the poll repeats
     up to 5 times at 3s.
   - **No match** after that → Retry enables, still bound to the original
     idempotency key, so if the first request *did* land late, Alpaca rejects the
     second on duplicate `client_order_id` rather than doubling the position.

This is the concrete answer to "what prevents a duplicate order if the user
reloads mid-submit": a persisted client-generated key, a broker lookup keyed on
it, and a retry that cannot mint a new one.

### 4.3 · What we are asking the backend for

Formal request to backend, tracked against **B3** (`docs/BRIEF-BACKEND-V2.md`):

1. Accept an `Idempotency-Key` header **or** keep honouring `client_order_id`,
   and record it in the `order_intent` ledger table.
2. A repeat inside the window returns **the original response body with
   `duplicate: true`** and does **not** call the broker — exactly as B3 §246
   already specifies. Not a 409, not an error: a client that retries after a
   network timeout must converge.
3. `GET /api/trade/orders` (or a sibling) accepts a `client_order_id` filter so
   the reload path in §4.2 is one request instead of a full list scan.
4. Echo `client_order_id` in the `POST /api/trade` response `order` object. It is
   already returned by the live branch (`trade.py:99`) but **not** by the mock
   branch, which returns only `{...order_payload, status: "simulated"}` — that
   payload does include `client_order_id` when supplied, so this is a
   consistency confirmation rather than a new field.

**Until those exist,** the UI behaves exactly as §4.1–4.2 describe and renders,
once per session in the blotter header, a `secondary` note:

> Server-side idempotency is not implemented (backend B3). Duplicate protection
> here is client-side only: an in-flight lock, a persisted `client_order_id`, and
> a broker lookup after a reload. Do not rely on it as a guarantee.

When B3 lands, the additive change is: render `duplicate: true` as a
`secondary` badge `already submitted — no new order` and leave state at
`submitted`. No guard is removed.

---

## 5 · Blocking rules

### 5.1 · What blocks, and where the reason comes from

| Condition | Detected from | `BlockReason.source` | Inline text |
|---|---|---|---|
| Kill switch halted | `AgentRunResponse.risk_summary.halted === true` — or `risk_summary.kill_switch.halted === true` | `kill_switch` | each string in `risk_summary.kill_switch.reasons`, verbatim, one per line. If `reasons` is empty: *"Kill switch halted; no reason string supplied."* |
| Red team `BLOCK` | the directive for this symbol is absent from `recommendations` while a `BLOCK`-severity entry names it, or the payload carries an explicit block marker | `red_team` | the payload's own reason string, verbatim. Never paraphrased |
| Contract unresolved | `intent.option_symbol === null` on an option strategy | `contract_unresolved` | §3.3 text |
| Risk gate refusal | HTTP 409 from `POST /api/trade` once B2 exists | `risk_gate` | one line per failed check from the `checks` array |

When `halted` is true the **whole queue** is blocked, not just rows: a page-level
banner in `error` renders the halt reasons, every Approve is disabled, and a
`Run agent again` link is the only affordance. Individual rows still show their
own reasons so an operator can tell "halted" from "this specific trade".

`risk_summary.halted` is also the reason `order_intents` is usually `[]` while
halted (`agent.py:168` short-circuits). If the array is empty **and** halted, the
page says so explicitly rather than showing an empty table.

### 5.2 · The plain statement

**The frontend must never be the bypass path for a risk control the agent layer
enforced.** If the kill switch is halted or the red team returned `BLOCK`, there
is no "force submit", no query parameter, no dev-only toggle, and no keyboard
shortcut that sends the order anyway. A blocked row's Approve handler is not
merely `disabled` — `canApprove()` is re-checked inside the submit function, and
a blocked record returns before `fetch` is reached. Two independent checks,
because a `disabled` attribute is trivially removed in devtools.

**And a disabled button is a UX affordance, not a security control.** Anyone with
the tunnel URL can `curl POST /api/trade` and skip this route entirely — that is
D4, reproduced, `HTTP 200`, 500 naked short calls. Nothing in this spec changes
that. The real gate belongs in **backend B2** (pre-trade risk gate: kill-switch,
coverage, collateral, concentration, duplicate, contract sanity, price sanity,
provenance, Greeks — hard failure → **HTTP 409** with the full `checks` array,
fail-closed when portfolio state is unreadable) and **B3** (idempotency + audit
ledger). This route's job is to make the *honest* path safe and legible; it
cannot make the dishonest path impossible, and it must not be described as if it
could.

---

## 6 · The blotter — `GET /api/trade/orders`

### 6.1 · Transport and types

`trade.py:114` — `list_orders(status: str = "open")`. Two shapes:
`{ mode: 'mock', orders: [...] }` from `mock_orders()` (reads
`frontend/app/data/mock_portfolio.json`), or `{ mode: 'live', orders: [...] }`
from `AlpacaClient().list_orders(status=...)`. Errors surface as **502**.

Add to `lib/api.ts` (additive):

```ts
export interface OrdersResponse {
  mode?: string
  orders: BrokerOrder[]
}

/** Widened from app/types/portfolio.ts::Order. That type declares
 *  status: "new" | "partially_filled" | "filled" | "done" and non-null
 *  filled_at / filled_avg_price — Alpaca returns neither guarantee, so the
 *  blotter uses this shape and treats every field as possibly absent. */
export interface BrokerOrder {
  id: string
  client_order_id?: string | null
  symbol?: string
  qty?: string | number | null
  filled_qty?: string | number | null
  side?: string
  type?: string
  time_in_force?: string
  limit_price?: string | number | null
  status?: string
  submitted_at?: string | null
  filled_at?: string | null
  canceled_at?: string | null
  filled_avg_price?: string | number | null
  [key: string]: unknown
}

listOrders: (status: 'open' | 'closed' | 'all' = 'open') =>
  request<OrdersResponse>(`/api/trade/orders?status=${status}`),
```

`lib/blotter/orders.ts` holds the pure helpers: `isOpenStatus`,
`normalizeStatus`, `reconcile`, `num(v)` (`string | number | null → number | null`,
never `0` for absent — Alpaca returns numerics as strings).

### 6.2 · Terminal statuses that stop polling

```ts
export const OPEN_STATUSES = [
  'new', 'accepted', 'pending_new', 'accepted_for_bidding',
  'partially_filled', 'held', 'pending_replace', 'pending_cancel',
  'replaced', 'calculated', 'stopped', 'suspended',
] as const

export const CLOSED_STATUSES = [
  'filled', 'canceled', 'cancelled', 'expired', 'rejected', 'done_for_day',
  'pending_review', // treated closed: no further transition we act on
] as const

export function isOpenStatus(s: string | undefined | null): boolean {
  if (!s) return false                       // unknown status is NOT open —
  return (OPEN_STATUSES as readonly string[]).includes(s.toLowerCase())
}                                            // an unknown string must not
                                             // poll forever
```

Polling rule: **poll only while at least one row is open.**

- `refetchInterval` is a function, not a constant:
  `(query) => query.state.data?.orders.some(o => isOpenStatus(o.status)) ? 4000 : false`.
- `refetchOnWindowFocus: true`, `refetchIntervalInBackground: false` — a
  backgrounded tab must not hammer a route that fans out to Alpaca (D5: blocking
  I/O in `async def` serialises the process; a 4s poll from three open tabs is a
  self-inflicted outage).
- `staleTime: 2000`. Manual **Refresh** always available.
- With zero open orders the interval is `false`: no polling at all. Fills arrive
  on focus or on demand. This is the specified behaviour, not a limitation to
  work around.
- Query key: `['trade-orders', status]`. Uses the `@tanstack/react-query` already
  in `package.json`.

### 6.3 · Reconciling a submitted intent to a live order

`reconcile(records: IntentRecord[], orders: BrokerOrder[]): IntentRecord[]`, pure,
matching in strict priority order:

1. **`client_order_id === rec.idempotencyKey`** — exact, unambiguous, survives
   reload. This is why §4.1 sends the key.
2. **`order.id === rec.brokerOrderId`** — set at T8 from
   `res.order?.id ?? res.id ?? null`. `TradeResponse` carries `id` at the top
   level *and* inside `order`; the live branch of `trade.py` populates
   `order.id`, so read `order.id` first and fall back.
3. **Heuristic, last resort, badge required.** Same `symbol` + same `side` +
   `submitted_at >= rec.submittedAt`. Match is displayed with a `secondary`
   badge `matched heuristically` and never used to advance state past
   `submitted` — a guessed match may not fire T11/T13.

On match: `brokerOrderId` is filled if empty, then `{ kind: 'broker_status',
status }` is dispatched, driving T11–T14. Unmatched broker orders still render —
they are real orders someone placed, possibly by a previous session or by hand,
and hiding them would make the blotter a lie. They show source `external`.

### 6.4 · Columns at 1440px

Full table, `min-w-[1100px]`, header `label-caps` in `on-surface-variant`, rows
`border-b border-outline/60`, numerics `tabular-nums` right-aligned.

| # | Column | Source | Empty rendering |
|---|---|---|---|
| 1 | Status | `status` → badge: `filled` `primary`, `partially_filled` `secondary`, `new`/`accepted` `outline`, `rejected`/`canceled`/`expired` `error` | `unknown` in `outline` |
| 2 | Symbol | `symbol` | `—` |
| 3 | Contract | `symbol` when OCC-parseable, else blank | `equity` in `on-surface-variant` |
| 4 | Side | `side` upper-cased; `sell` in `secondary`, `buy` in `primary` | `—` |
| 5 | Qty | `num(qty)` | `—` |
| 6 | Filled | `num(filled_qty)` / `num(qty)` | `0 / n` only when `filled_qty` is literally `"0"`; `— / n` when absent |
| 7 | Type | `type` upper-cased | `—` |
| 8 | Limit | `num(limit_price)`, 2dp | `no limit set` |
| 9 | Avg fill | `num(filled_avg_price)`, 2dp | `—` |
| 10 | TIF | `time_in_force` | `—` |
| 11 | Submitted | `submitted_at`, `HH:mm:ss` local, full ISO in `title` | `—` |
| 12 | Filled at | `filled_at` same format | `—` |
| 13 | Source | `intent` (reconciled) / `external` (unmatched) / `manual` | — |
| 14 | Order id | `id` first 8 chars, monospace, full value in `title`, click-to-copy | `—` |

Two sections on the page, in this order: **Approval queue** (records not yet
`submitted`), then **Blotter** (broker orders + reconciled records). A `mode`
badge (`live`/`mock`) sits in each section header, read from the respective
response — never inferred.

### 6.5 · Columns at 390px

No horizontal scroll. The table is replaced by a card list (same data, same
source, different layout — one component, `layout` prop, not two implementations).

Each card:

```
┌────────────────────────────────────────┐
│ AAPL              [ PARTIALLY FILLED ] │   status badge right
│ SELL · 2 contracts · MARKET            │   line 2, on-surface-variant
│ filled 1 / 2 @ 3.15                    │   line 3, only if any fill
│ no limit set                           │   line 4, only if market
│ 09:31:15 · 98765432                    │   line 5, time · id prefix
└────────────────────────────────────────┘
```

- Dropped from the card: TIF, Filled-at, Contract, Source. All reachable via a
  tap that expands the card in place (`framer-motion` height animation, respects
  `useReducedMotion`).
- Approval queue cards keep **Approve / Reject** full-width stacked, min 44px
  tall, Approve on top. The confirmation dialog becomes a bottom sheet, `Cancel`
  focused, and the market-order checkbox is a full-width tap target.
- Blocked cards show the reason above the buttons, not in a tooltip: a `title`
  attribute is unreachable on touch.

---

## 7 · KNOWN-ISSUES #7 — resolved

### 7.1 · Division of responsibility

| Route | Component | Calls | Renders | Must NOT |
|---|---|---|---|---|
| `/dashboard` | `AgentControl` (`app/components/AgentControl.tsx`) | `POST /api/agent/run` via `AgentRunProvider` | **Compact trigger + summary only**: mode badge, directive count, intent count, blocked count, halt banner with reasons, and a `Review N intents →` link to `/blotter` | never call `/api/trade`; never render a per-intent table; never offer Approve |
| `/terminal` | `TerminalClient` | the **same** `AgentRunProvider` run — no second POST unless the operator explicitly re-runs | **Detailed read-only view**: full reasoning trace, directives, the existing `order_intents` table with `needs approval` badges, provenance | never call `/api/trade`; never offer Approve; the intents table stays read-only and links to `/blotter` |
| `/blotter` | `BlotterClient` (new) | `POST /api/trade` (only place in the app), `GET /api/trade/orders` | Approval queue with Approve / Reject / Modify limit, the confirmation guard, and the blotter | never re-run the agent; never render a directive it did not receive from the provider |

The two buttons stop diverging because they stop being two runs: both read
`AgentRunProvider`, which already exists and which `AgentControl` already uses.
`/terminal` gains a re-run affordance labelled explicitly `Re-run agent (replaces
current run)` so a divergence is a deliberate act with visible consequences.

**One endpoint, one writer.** `POST /api/trade` is called from exactly one module,
`lib/blotter/submit.ts`. A repo-wide grep for `placeTrade` returning more than one
call site is a review failure.

### 7.2 · The sentence for `FRONTEND.md`

Paste verbatim under the routing section:

> **Agent run vs. order submission.** `POST /api/agent/run` has exactly one
> caller — `AgentRunProvider` — which `/dashboard` (`AgentControl`: compact
> trigger plus summary) and `/terminal` (`TerminalClient`: detailed read-only
> view) both consume, so they can never show different runs; `POST /api/trade` has
> exactly one caller — `lib/blotter/submit.ts` on `/blotter` — so approval is a
> single, guarded, auditable path and neither of the other two routes can place an
> order.

That sentence closes #7: it names the routes, names the endpoints, states the
invariant, and is falsifiable by grep.

---

## 8 · Tests

Split rule: **vitest owns everything that is a function of data; playwright owns
everything that is a function of a user.** If a test needs a click, a reload, or a
network intercept, it is E2E. If it can be expressed as `f(input) === output`, it
is vitest — and it must be, because those run in milliseconds and gate every push.

### 8.1 · vitest — `frontend/tests/blotter.machine.test.ts`

Pure `lib/blotter/machine.ts`. Fixtures in `frontend/tests/fixtures/` alongside
the existing ones.

1. T1 creates `pending_approval` when `requires_approval: true`; T2 creates
   `intent` when `false`.
2. T3 creates `blocked` when `halted`, with `reasons` copied verbatim (assert
   string identity, not `toContain`).
3. T3 creates `blocked` when `option_symbol === null` on an option strategy.
4. `approve` → `confirming` and the record is otherwise byte-identical (deep equal
   minus `state`) — proves no side effect is smuggled into the reducer.
5. `cancel_confirm` returns to `pending_approval`.
6. **`reject` is terminal and mutates nothing but `state` + `rejectReason`.**
7. `undo_reject` restores `pending_approval` and clears the reason.
8. `retry` preserves `idempotencyKey` byte-for-byte. Table-driven over 3 retries.
9. `isTerminal` is exhaustive: every member of `ApprovalState` is classified, and
   the test fails if a new state is added without a decision (`satisfies Record<ApprovalState, boolean>`).
10. Illegal events are no-ops: for every state × every event not in §2.2, the
    returned record is reference-or-deep equal to the input.
11. `broker_status` mapping: `filled`→`filled`, `partially_filled`→`partially_filled`,
    `rejected`/`canceled`/`expired`→`error`, unknown string→unchanged.

### 8.2 · vitest — `frontend/tests/blotter.map.test.ts`

Pure `lib/blotter/map.ts`. **The highest-value file in this spec.**

1. **`limit_price: null` → the key is absent from `JSON.stringify` output.**
   Asserted three ways: `!('limit_price' in body)`, `not.toBe(0)`, `not.toBe('0')`.
2. `limit_price: null` → `type === 'market'` and `effectiveType === 'market'`.
3. `limit_price: 0` from the agent (defensive: should be impossible) → `ok: false`,
   reason mentions the value. **Never coerced to a market order silently.**
4. `limit_price: 3.15` → `type === 'limit'`, `limit_price === 3.15`.
5. `limitOverride` beats `intent.limit_price`; `limitOverride: null` falls back.
6. `option_symbol: null` → mapping refuses on option strategies (`ok: false`), and
   the underlying ticker is **not** substituted. Assert `request` is absent.
7. `option_symbol` present → `symbol` is the OCC string, upper-cased, and
   `time_in_force === 'day'` even if the intent said `gtc`.
8. `side` outside `{buy,sell}` → `ok: false`. No default.
9. `qty` of `0`, `-1`, `NaN`, `Infinity`, `'2'` → first four refuse; `'2'` maps to
   `2`.
10. Round-trip against the backend validator's rules as a documented table: for
    each fixture, the produced body satisfies every `TradeRequest.validate_order`
    precondition (OCC or ticker regex, TIF in set, no `limit_price` on market, no
    missing `limit_price` on limit).
11. `client_order_id` is always present and equals `rec.idempotencyKey`.

### 8.3 · vitest — `frontend/tests/blotter.orders.test.ts`

1. `isOpenStatus` over all `OPEN_STATUSES` (true), all `CLOSED_STATUSES` (false),
   `undefined`/`null`/`''`/`'WEIRD'` (false — **unknown must not poll forever**).
2. Case-insensitivity: `'FILLED'`, `'New'`.
3. `num()`: `'172.45'`→`172.45`, `null`→`null`, `undefined`→`null`, `''`→`null`,
   `'abc'`→`null`, `0`→`0`. **Absent never becomes `0`.**
4. `reconcile` priority: `client_order_id` wins over `id`; `id` wins over the
   heuristic; heuristic match sets the badge flag and does not advance state.
5. `reconcile` with zero orders is a no-op; unmatched orders come back as
   `external`.
6. Polling predicate: derives `4000` with one open order, `false` with none,
   `false` for a list of unknown statuses.

### 8.4 · vitest — `frontend/tests/blotter.inflight.test.ts`

1. `claim(k)` → `true`; immediate second `claim(k)` → `false`.
2. `claim` on a different key → `true`.
3. `release(k)` then `claim(k)` → `true`.
4. **Synchronous double-claim in one tick yields exactly one `true`** — the
   double-click invariant proved without a browser.

### 8.5 · playwright — `frontend/e2e/blotter-approval.spec.ts`

All specs use `page.route()` fixtures; none touch a live broker. Follows the
existing `frontend/e2e/helpers.ts` conventions.

1. **Reject sends no request.** Register a `page.route('**/api/trade', …)` handler
   that fails the test if called. Click Reject, enter a reason, assert the row is
   greyed and the handler never fired. Assert with a request-count spy, not a
   timeout.
2. **Halted disables approve.** Stub `/api/agent/run` with
   `risk_summary.halted: true` and two `kill_switch.reasons`. Assert Approve has
   `disabled`, both reason strings are visible in the DOM, and the `/api/trade`
   spy count is `0` after clicking the disabled button.
3. **Confirmation is required.** Approve opens the dialog; assert zero `/api/trade`
   calls while it is open; assert focus is on Cancel; press `Enter` and assert the
   dialog closed with still zero calls.
4. **Market-order acknowledgement.** With `limit_price: null`, assert the literal
   text `MARKET` is visible, `Confirm & submit` is `disabled`, tick the checkbox,
   assert enabled.
5. **Double-click submits once.** `page.route` delays the response 800ms.
   `dblclick` on Confirm. Assert exactly **one** request, and that its body has no
   `limit_price` key.
6. **Reload mid-submit does not duplicate.** Route `/api/trade` to hang, click
   Confirm, `page.reload()` while in flight. Assert: the row is `error` with the
   interrupted message, Retry is disabled, `/api/trade/orders` was called, and the
   total `/api/trade` request count across both page lifetimes is **1**. Then
   return the order with the matching `client_order_id` and assert the row becomes
   `submitted` without a second POST.
7. **Happy path to blotter.** Approve → confirm → `/api/trade` returns
   `{ mode:'live', submitted:true, order:{ id:'ord-1', client_order_id:<key>, status:'new' } }`.
   Assert the row shows `submitted` and `ord-1` appears in the blotter section.
   Then `/api/trade/orders` returns that order `filled` and assert the row becomes
   `filled` and polling stops (request count stable over 6s).
8. **Contract pending blocks approve.** `option_symbol: null` → Approve disabled,
   the KNOWN-ISSUES #2 reason visible, manual-entry input present; an invalid OCC
   string keeps Approve disabled.
9. **502 on the blotter is legible.** `/api/trade/orders` returns 502; the section
   shows the error and the approval queue still works.
10. **Responsive.** At `1440×900` the table has 14 headers; at `390×844` there is
    no horizontal overflow (`scrollWidth <= clientWidth`) and Approve/Reject are
    ≥44px tall.
11. **Console hygiene.** Extend the existing `console-hygiene.spec.ts` pattern to
    `/blotter`: zero errors, zero unhandled rejections through the full approve
    flow.
12. **Route isolation (closes #7).** On `/dashboard` and `/terminal`, run the agent
    with a `/api/trade` spy attached and assert the count is `0` after interacting
    with every control on the page.

### 8.6 · Not tested here, deliberately

- That a naked short call is refused. That is `test_risk_gate.py` under backend
  B2. Asserting it in the frontend would encode the false claim that the UI is the
  gate.
- Real Alpaca submission. No test in this suite may hold live credentials.

---

## 9 · Acceptance (from BRIEF-FRONTEND-V2 F5)

- [ ] Approve → confirm → order appears in the blotter with a real Alpaca paper
      order id (verified in `live` mode manually, in `mock` mode by test).
- [ ] Reject → row greyed, **no request sent** (spy-asserted).
- [ ] Halted → Approve disabled with reasons inline.
- [ ] `option_symbol: null` and `limit_price: null` — the normal case — render as
      `contract pending` / `no limit set`, and a market order cannot be submitted
      without the operator reading the word `MARKET` and ticking a box.
- [ ] Polling runs only while an order is open.
- [ ] `POST /api/trade` has exactly one call site; `POST /api/agent/run` has
      exactly one.
- [ ] §7.2 sentence is in `FRONTEND.md`.
- [ ] `npm test` and `npm run test:e2e` green; no new dependency in
      `package.json`; no colour outside the token list.

