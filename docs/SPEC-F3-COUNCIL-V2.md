# SPEC · F3 · Council v2 surface — debate, red team, calibration

**Status:** implementation-ready · **Owner:** frontend · **Brief:** `docs/BRIEF-FRONTEND-V2.md` §F3
**Consumes:** `docs/BRIEF-AGENT-V2.md` §W5 (5a INCONCLUSIVE half-fail, 5b two-round
debate, 5c red-team persona, 5d calibration record)
**Touches:** `frontend/app/council/`, `frontend/app/components/council/`,
`frontend/lib/api.ts` (types only), `frontend/tests/`

---

## 0 · Scope and the one rule that governs everything

W5 is not shipped. The backend today (`backend/app/routes/council.py::_assessment_to_dict`)
returns exactly this per assessment: `symbol`, `tier`, `tier_policy_summary`,
`tier_policy`, `consensus_score`, `recommendation`, `majority_stance`, `is_split`,
`verdicts[]`, `dissent[]`. Six personas, one round, no revisions, no challenges,
no calibration ledger.

F3 therefore ships against a payload that does not yet contain the data F3 exists
to display. That is the constraint, not a problem to be designed around:

> **Every field introduced by this spec is optional. Every component built by this
> spec must render correctly, with no thrown error and no empty hole in the layout,
> when the field is `undefined`.** The council page must look finished today and
> gain detail later, never the reverse.

Concretely: when the agent ships W5b, `DebateTimeline` starts rendering; until
then the verdict list renders exactly as it does now and the timeline is absent —
not blank, not a spinner, not a "coming soon" placeholder. Absence of a section is
the correct rendering of absent data. Absence of a *value inside a rendered
section* is not, and §2 turns that rule into a hard requirement.

### Allowed dependencies

`frontend/package.json` only. In practice: `react`, `next`, `framer-motion`,
`lucide-react`, `recharts`, `clsx`/`tailwind-merge` (via `lib/utils.cn`),
`@tanstack/react-query` (F1), `vitest` + `playwright` for tests. **No new
packages.** In particular there is no `@testing-library/react` in the repo, which
shapes §8 — do not add it as part of F3.

### Allowed colour tokens

`background #020617`, `surface #0f172a`, `surface-container #131c2e`,
`surface-container-high #1a2332`, `primary #22c55e`, `secondary #fbbf24`,
`error #ef4444`, `tertiary #f472b6`, `on-surface #f8fafc`,
`on-surface-variant #94a3b8`, `outline #334155`.

Existing hex classes already used inside `CouncilBoard.tsx` (`#052e16`, `#451a03`,
`#450a0a`, `#f87171`, `#1e293b`, `#f59e0b`, `#e2e8f0`) are the established chip
fills for the stance/tier badges and stay as they are — this spec does not
re-theme what already works. New surfaces use the token list above.

Semantic assignment for the new surfaces:

| Meaning | Token |
|---|---|
| Held position under dissent (positive) | `primary #22c55e` |
| Revised position (neutral-notable) | `secondary #fbbf24` |
| Capitulation / `BLOCK` / breached threshold | `error #ef4444` |
| Red-team voice, `NOTE` severity | `tertiary #f472b6` |
| Panel body | `surface #0f172a` |
| Nested row inside a panel | `surface-container #131c2e` |
| Hovered/selected nested row | `surface-container-high #1a2332` |
| Rules, dividers, reference lines | `outline #334155` |

`#f472b6` (tertiary) is currently unused in the council surface. It is reserved
here for the red team specifically, so that "the adversary spoke" is
recognisable at a glance without reading a word — the red team is neither an
error state nor a warning, it is a distinct voice.

---

## 1 · Types — extended council payload

All of the following go into `frontend/lib/api.ts`, appended to the existing
council block. Nothing existing is edited except the two marked `// EXTENDED`
interfaces, which gain optional members only.

```ts
/* ------------------------------------------------------------------ *
 * Council v2 — W5. Every field below is optional. The backend at the
 * time of writing (routes/council.py::_assessment_to_dict) emits none
 * of them. See COMPAT-1..COMPAT-7 for what that obligates.
 * ------------------------------------------------------------------ */

/** W5b round index. 1 = independent verdict, 2 = post-dissent revision. */
export type DebateRound = 1 | 2

/** W5c severity ladder. BLOCK removes the directive, DOWNGRADE halves size. */
export type RedTeamSeverity = 'BLOCK' | 'DOWNGRADE' | 'NOTE'

/**
 * One persona's round-1 verdict. Structurally identical to CouncilVerdict —
 * declared as its own alias so DebateTimeline props read as intended and so a
 * future round-1-only field does not have to widen CouncilVerdict.
 */
export type CouncilRoundOneVerdict = CouncilVerdict

/**
 * One persona's round-2 output from council/debate.py. A persona that was shown
 * the dissent and declined to move still emits a record here with
 * `revised: false` — that is a signal and §2 requires it to be rendered as one.
 */
export interface CouncilRevision {
  persona: string
  /** Score after round 2. Equals round-1 score when `revised` is false. */
  score?: number
  /** Stance after round 2. Equals round-1 stance when `revised` is false. */
  stance?: string
  /** False = held position under dissent. Absent = round 2 did not run. */
  revised?: boolean
  /** Free text from the persona. Only meaningful when `revised` is true. */
  revision_reason?: string
  /** Bullets the persona added or rewrote in round 2. */
  bullets?: string[]
  [key: string]: unknown
}

/** W5b ledger figure: fraction of debates in which this persona revised. */
export interface CouncilRevisionRate {
  persona: string
  /** 0..1. Above CAPITULATION_THRESHOLD the persona is broken, not agreeable. */
  revision_rate?: number
  /** Debates counted. Without it the rate is unreadable — render "n = ?". */
  sample_size?: number
  /** Revisions counted, when the ledger exposes the numerator directly. */
  revisions?: number
  [key: string]: unknown
}

/** W5c red-team output. `directive_id` joins to DailyDirective provenance. */
export interface RedTeamChallenge {
  directive_id: string
  severity: RedTeamSeverity
  attack: string
  evidence: string[]
  /** Present on DOWNGRADE: contracts before the halving. */
  size_before?: number
  /** Present on DOWNGRADE: contracts after the halving. */
  size_after?: number
  /** Convenience denormalisation; do not rely on it for the join. */
  symbol?: string
  [key: string]: unknown
}

/** W5d calibration ledger rollup. Sample will be tiny; say so — see §5. */
export interface CouncilCalibration {
  /** Assessments with a stamped forward outcome. May legitimately be 0. */
  sample_size?: number
  /** 0..1 over the resolved sample. Meaningless at small n; still shown. */
  hit_rate?: number
  /** Mean (consensus_score - realised outcome score). Sign is meaningful. */
  mean_error?: number
  /** Optional per-persona breakdown, same honesty rules as the rollup. */
  by_persona?: Array<{
    persona: string
    sample_size?: number
    hit_rate?: number
    mean_error?: number
  }>
  /** First/last ledger timestamps, ISO-8601, for the "6 days" statement. */
  window_start?: string
  window_end?: string
  [key: string]: unknown
}
```

### 1.1 · The two extended interfaces

```ts
/** EXTENDED — v1 fields unchanged, v2 fields all optional. */
export interface CouncilAssessment {
  symbol: string
  tier: string
  tier_policy_summary: string
  tier_policy: CouncilTierPolicy
  consensus_score: number
  recommendation: string
  majority_stance: string
  is_split: boolean
  /** v1 + W5b: round-1 verdicts. Still the only guaranteed persona list. */
  verdicts: CouncilVerdict[]
  dissent: CouncilDissent[]

  /** W5b: round-2 output, one entry per persona that participated. */
  revisions?: CouncilRevision[]
  /** W5b: consensus after round 2. Absent when round 2 did not run. */
  consensus_score_round2?: number
  /** W5b: recommendation after round 2, if it moved. */
  recommendation_round2?: string
  /** W5b: how many rounds actually ran. Absent means 1. */
  rounds?: number
  /** W5c: challenges raised against directives derived from this symbol. */
  red_team?: RedTeamChallenge[]
}

/** EXTENDED — v1 fields unchanged, v2 fields all optional. */
export interface CouncilAssessResponse {
  mode: string
  count: number
  assessments: CouncilAssessment[]
  /** W5b: per-persona revision rates across the run, from the ledger. */
  revision_rates?: CouncilRevisionRate[]
  /** W5d: calibration rollup. */
  calibration?: CouncilCalibration
  /** W5c: run-level challenge list, when the backend does not nest them. */
  red_team?: RedTeamChallenge[]
}
```

`CouncilVerdict` is **not** modified. Round-2 data lives in `CouncilRevision`,
joined to the verdict by `persona`, for one reason: a mutated `CouncilVerdict`
makes "which round is this score from?" ambiguous at every call site, and the
score delta in §2 is the whole point of the timeline.

### 1.2 · Constants

```ts
/** W5b: above this a persona is broken, not agreeable. */
export const CAPITULATION_THRESHOLD = 0.7
/** W5d: below this n, the calibration caveat is mandatory. */
export const CALIBRATION_MIN_SAMPLE = 30
```

### 1.3 · Type guards and derivations

The single decision "is debate data available?" is made in exactly one place and
nowhere else. Components receive already-resolved props; they never re-sniff the
payload.

```ts
/**
 * True when round-2 debate data is present AND usable for this assessment.
 * `rounds` alone is not enough — a backend that reports rounds: 2 but emits an
 * empty revisions array must be treated as "no debate data", because the
 * alternative is a rendered timeline with nothing in it.
 */
export function hasDebateData(a: CouncilAssessment): boolean {
  if (!Array.isArray(a.revisions) || a.revisions.length === 0) return false
  return a.revisions.some(
    (r) => typeof r.revised === 'boolean' || typeof r.score === 'number',
  )
}

/** True when at least one persona-level revision rate is a usable number. */
export function hasRevisionRates(res: CouncilAssessResponse): boolean {
  return (res.revision_rates ?? []).some(
    (r) => typeof r.revision_rate === 'number' && Number.isFinite(r.revision_rate),
  )
}

/**
 * True when a calibration record exists at all — INCLUDING n = 0. An empty
 * ledger is a state worth rendering ("no resolved assessments yet"), so the
 * guard tests for the object, not for a non-zero sample.
 */
export function hasCalibration(res: CouncilAssessResponse): boolean {
  return res.calibration != null
}

/** Challenges for one assessment, run-level list included. */
export function challengesFor(
  res: CouncilAssessResponse,
  a: CouncilAssessment,
): RedTeamChallenge[] {
  const nested = a.red_team ?? []
  const runLevel = (res.red_team ?? []).filter((c) => c.symbol === a.symbol)
  const seen = new Set(nested.map((c) => c.directive_id))
  return [...nested, ...runLevel.filter((c) => !seen.has(c.directive_id))]
}

/** Round-2 record for a persona, or undefined. Case-insensitive by name. */
export function revisionFor(
  a: CouncilAssessment,
  persona: string,
): CouncilRevision | undefined {
  const key = persona.trim().toLowerCase()
  return (a.revisions ?? []).find((r) => r.persona.trim().toLowerCase() === key)
}
```

### 1.4 · Compatibility requirements (normative)

These are acceptance criteria, not guidance. Each is testable and §8 names the
test that covers it.

**COMPAT-1 — Today's payload renders unchanged.** Given a `CouncilAssessResponse`
containing only the v1 fields (`mode`, `count`, `assessments[]` with `symbol`,
`tier`, `tier_policy_summary`, `tier_policy`, `consensus_score`,
`recommendation`, `majority_stance`, `is_split`, `verdicts[]` of six personas,
`dissent[]`) and **none** of `revisions`, `consensus_score_round2`,
`recommendation_round2`, `rounds`, `red_team`, `revision_rates`, `calibration`:
`CouncilBoard` renders every assessment card, every stance chip, every dissent
row and all six expandable persona verdicts, with no thrown error, no React key
warning, and no visual gap where a v2 panel would be. This is the primary
regression guard on F3 and it never gets relaxed.

**COMPAT-2 — Optional means optional in the type system.** Every field added by
§1 is declared with `?`. Adding F3's types to `lib/api.ts` must leave
`npx tsc --noEmit` clean without editing a single existing call site, and without
any non-null assertion (`!`) or `as` cast in `CouncilBoard.tsx` or its children.

**COMPAT-3 — Absent section, not empty section.** A v2 panel whose guard
(`hasDebateData`, `hasRevisionRates`, `hasCalibration`, non-empty
`challengesFor`) returns false renders `null`. It does not render a heading with
an empty body, a zero-height bordered box, a skeleton, or a "not available yet"
placeholder. Rationale: a heading with nothing under it reads as a bug; a section
that is simply not there reads as a feature that has not been reached.

**COMPAT-4 — Round 1 is the only guaranteed persona list.** Persona iteration is
always driven by `assessment.verdicts`. `revisions` is looked up per persona via
`revisionFor()`. A persona present in `revisions` but missing from `verdicts` is
ignored; a persona in `verdicts` with no revision record renders round-1 only.
This makes a partial round 2 (debate crashed after three personas) degrade to a
readable mixed view instead of an exception.

**COMPAT-5 — Round-2 numbers never silently overwrite round-1 numbers.** The
consensus gauge on the card shows `consensus_score` (round 1) unless
`consensus_score_round2` is a finite number, in which case both are shown with
the round-1 value labelled. There is no code path in which a displayed score
cannot be attributed to a round.

**COMPAT-6 — Non-finite and out-of-range numbers are treated as absent.**
`revision_rate` outside `[0, 1]`, and any `NaN`/`Infinity` in a score, delta,
`size_before`/`size_after`, `hit_rate` or `mean_error`, is handled as if the
field were `undefined`. No component renders the string `NaN`, `Infinity`, or
`undefined`. `sample_size === 0` is a real value and is rendered as `0`, never
coerced to absent (see §5).

**COMPAT-7 — Unknown enum values degrade, never crash.** A `severity` outside
`BLOCK | DOWNGRADE | NOTE` renders with the `NOTE` treatment and the raw string
as its label. A stance outside the known set already falls through to the bearish
chip in `stanceChip()`; that behaviour is preserved. Backend vocabulary drift
must never blank the panel.

---

## 2 · DebateTimeline

**File:** `app/components/council/DebateTimeline.tsx`
**Rendered:** inside the expanded region of an assessment card, above the
existing round-1 verdict list, only when `hasDebateData(assessment)` is true.

```ts
export interface DebateTimelineProps {
  /** Round-1 verdicts — drives iteration order (COMPAT-4). */
  verdicts: CouncilRoundOneVerdict[]
  /** Round-2 records, joined by persona name. May be shorter than verdicts. */
  revisions: CouncilRevision[]
  /** Round-1 consensus, for the "vs consensus" reference. */
  consensusRound1: number
  /** Round-2 consensus when present (COMPAT-5). */
  consensusRound2?: number
}
```

### 2.1 · Row anatomy

One row per persona in `verdicts` order. Each row is a three-part grid:
persona identity · round-1 → round-2 score pair · outcome marker + reason.

Rows sit on `surface-container #131c2e` with a `1px` left border that carries the
row's state colour, `outline #334155` when the row has no round-2 record at all.
Hover raises the row to `surface-container-high #1a2332`. The left border is the
scanning cue: a judge should be able to count green versus amber down the left
edge of the timeline without reading a single label.

### 2.2 · Revised versus unrevised — the visual contract

| | Revised | Held (`revised === false`) |
|---|---|---|
| Left border | `secondary #fbbf24`, 2px | `primary #22c55e`, 2px |
| Icon (`lucide-react`) | `RefreshCw`, 14px, `#fbbf24` | `ShieldCheck`, 14px, `#22c55e` |
| Marker label | `REVISED` | `HELD` |
| Label chip | `border-[#fbbf24]/40 bg-[#451a03] text-[#fbbf24]` | `border-[#22c55e]/40 bg-[#052e16] text-[#22c55e]` |
| Score pair | `68.0 → 67.6` with delta | `68.0 → 68.0` rendered as `68.0 · unchanged` |
| Third column | `revision_reason` in `on-surface-variant #94a3b8` | held copy, see §2.4 |

A row whose revision record exists but has `revised === undefined` and no
numeric `score` is treated as no record: `outline` border, no marker chip,
round-1 score only, and the third column reads `Round 2 did not report on this
persona.` in `#94a3b8`. This is the partial-round-2 case from COMPAT-4 and it
must be visibly distinguishable from `HELD` — "we do not know" and "she held" are
different facts and collapsing them would be a lie in the direction that
flatters the system.

### 2.3 · Score delta rendering

One helper, used nowhere else, no inline duplication:

```ts
export interface ScoreDelta {
  before: string   // '68.0'
  after: string    // '67.6'
  delta: string    // '-0.4' — always signed, '0.0' when unchanged
  direction: 'up' | 'down' | 'flat'
}

/** One decimal place, always signed delta. Returns null when unusable. */
export function formatScoreDelta(before?: number, after?: number): ScoreDelta | null {
  if (!Number.isFinite(before) || !Number.isFinite(after)) return null
  const b = before as number
  const a = after as number
  const d = a - b
  const direction = Math.abs(d) < 0.05 ? 'flat' : d > 0 ? 'up' : 'down'
  const sign = direction === 'flat' ? '' : d > 0 ? '+' : '-'
  return {
    before: b.toFixed(1),
    after: a.toFixed(1),
    delta: `${sign}${Math.abs(d).toFixed(1)}`,
    direction,
  }
}
```

Rendered form, exactly:

```
68.0  →  67.6   -0.4
```

- Both scores in `font-mono`, one decimal place, always. `68` renders as `68.0`;
  a bare integer next to a decimal makes a −0.4 move look like a rounding
  artefact.
- The arrow is the literal character `→` (U+2192) in `on-surface-variant #94a3b8`,
  never a `lucide-react` icon. It must survive copy-paste out of a screenshot and
  it must never carry colour, because the colour belongs to the delta.
- The delta is `font-mono`, **always signed**: `-0.4`, `+1.2`. `error #ef4444`
  when the direction is `down`, `primary #22c55e` when `up`, and
  `on-surface-variant #94a3b8` for `flat`. An unsigned delta is forbidden — the
  sign is the information.
- `direction: 'flat'` renders `68.0 · unchanged` in `#94a3b8` and suppresses both
  the arrow and the numeric delta. A `→` between two identical numbers invites
  the reader to hunt for a difference that is not there.
- The arrow has `aria-hidden="true"`. The row carries an `aria-label` of the form
  `Cathie Wood, round one 68.0, round two 67.6, down 0.4, revised` (or
  `…, unchanged, held position under dissent`) so the screen-reader rendering
  states the same fact as the visual one.
- `formatScoreDelta` returning `null` (COMPAT-6) falls back to the round-1 score
  alone with no arrow and no delta.

Delta arithmetic is always `round2 - round1`. It is never inferred from
`consensus`, never from a stance change, and never recomputed inside a component.

### 2.4 · Not revising is a positive signal — normative

This is the requirement most likely to be lost in implementation, so it is stated
as a rule rather than as a description.

> **A persona with `revised === false` MUST render a filled, affirmative cell. It
> is forbidden to render an empty string, a blank table cell, a dash, an em-dash,
> `null`, `n/a`, `—`, a greyed-out row, a reduced-opacity row, or any other
> treatment that reads as missing data.**

The exact copy in the third column:

```
Held position under dissent.
```

When the persona also appears in `dissent[]` for this symbol — that is, it held a
position that was *against* the consensus and was argued at directly — the copy
extends to:

```
Held position under dissent. Saw the counter-argument and did not move.
```

The `HELD` chip and the `ShieldCheck` icon in `primary #22c55e` are mandatory on
these rows. Green is deliberate: in this panel the desirable outcome is
independence, and holding under pressure is the strongest evidence of it the
system can produce.

Rationale, for whoever is tempted to simplify this later: a blank cell against
"did not revise" tells the reader the system failed to collect something. The
opposite is true — the system collected the most valuable observation available.
`REVISED` rows are the ones that owe the reader an explanation, and they pay it
with `revision_reason`. `HELD` rows owe nothing and must not look like they are
withholding.

### 2.5 · Header and consensus movement

The timeline is introduced by a single header line, `text-xs`, in
`on-surface-variant #94a3b8`:

```
Round 1 → Round 2 · 4 held · 2 revised
```

Counts come from the rendered rows, and personas with no round-2 record are
excluded from both counts and appended as `· 1 unreported` when non-zero.

When `consensusRound2` is a finite number and differs from `consensusRound1`, the
header gains a second line using the same `formatScoreDelta` output:

```
Consensus 68.0 → 67.6  -0.4
```

When they are equal it reads `Consensus 68.0 · unchanged after debate`, which is
itself a result worth stating.

### 2.6 · Motion

Rows mount through the existing `RevealGroup`/`RevealItem` primitives from
`app/components/motion/primitives.tsx` with the same `stagger={0.045}` already
used by `CouncilBoard`. `useReducedMotion` is respected exactly as in the current
file — `{ duration: 0 }` transitions when reduced. No new animation primitives,
no `layoutId`, and nothing that animates the score number itself: a counting
animation on a −0.4 delta obscures the only figure on the row that matters.

---

## 3 · RevisionRateMeter

**File:** `app/components/council/RevisionRateMeter.tsx`
**Rendered:** once per run, in a run-level panel above the assessment grid, only
when `hasRevisionRates(response)` is true. It is a property of the *council*, not
of a symbol, and must not be duplicated inside each card.

```ts
export interface RevisionRateMeterProps {
  /** Per-persona rates from the ledger. Rows with unusable rates are dropped. */
  rates: CouncilRevisionRate[]
  /** Defaults to CAPITULATION_THRESHOLD (0.7). Injectable for tests. */
  threshold?: number
}
```

### 3.1 · Bar geometry

One horizontal bar per persona, sorted descending by `revision_rate` so any
breach is the first thing on screen. Each row is a fixed-height (`h-6`) track:

- Track: `surface-container #131c2e`, `rounded-sm`, full width of the column.
- Fill: width `revision_rate * 100%`. `primary #22c55e` at or below threshold,
  `error #ef4444` above it. No gradient, no amber middle band — this is a
  pass/fail line and an intermediate colour would imply a tolerance band that
  does not exist.
- Value label: `font-mono text-xs` to the right of the track, two decimal places,
  e.g. `0.83`. Sample size follows in `on-surface-variant #94a3b8` as
  `n = 12`, or `n = ?` when `sample_size` is absent.
- Persona name: left column, fixed width, `text-xs` `on-surface #f8fafc`,
  truncated with `title` on overflow.

### 3.2 · The 0.7 reference line — drawn, not implied

The threshold is a **drawn element**, not a colour change:

- A `2px` vertical rule at exactly `70%` of track width, `outline #334155`,
  spanning the full height of the track and extending 4px above the topmost track
  and 4px below the bottommost so it reads as one continuous line across all
  personas rather than six separate ticks.
- Rendered **above** the fill (`z-index` order: track, fill, line) so a breaching
  red bar is visibly crossing it. A line hidden under the fill defeats the point.
- Labelled once, under the last row, aligned to 70%: `0.70 capitulation line`,
  `text-[10px]` `on-surface-variant #94a3b8`.
- The line is positioned from the `threshold` prop, never hard-coded to `70%` in
  a class string, so the constant and the drawing cannot drift apart.

Implementation note: a plain `div` with `absolute left-[70%]` inside a `relative`
track container. `recharts` is available but is the wrong tool here — six
single-value horizontal bars with one reference line is less code and more
controllable as raw markup, and it keeps the meter dependency-free.

### 3.3 · Breach copy — exact

When `revision_rate > threshold` the row gains a chip immediately after the value
label, and no other visual change:

```
capitulating — not independent
```

Chip styling: `border-[#ef4444]/50 bg-[#450a0a] text-[#ef4444]`,
`text-[10px] font-semibold uppercase tracking-wider`, `AlertTriangle` icon 12px.
The em-dash and the lower case are part of the copy and are not to be
title-cased.

When one or more personas breach, the panel header gains a second line in
`error #ef4444`:

```
1 of 6 personas above the 0.7 revision line — the committee is losing independence.
```

The count is live. With zero breaches the line is absent (COMPAT-3) and the
header reads only:

```
Revision rate by persona · 0.7 = capitulation line
```

Comparison is strictly `>`, not `>=`. A persona sitting exactly at `0.70` is at
the line, not over it, and the brief says *above* 0.7.

### 3.4 · Why a high revision rate means broken, not agreeable

The panel carries this as body copy, `text-xs`, `on-surface-variant #94a3b8`,
directly beneath the bars — permanently, not behind a tooltip or an info icon:

> A persona that revises toward consensus in most debates has stopped being an
> independent estimator. Its round-1 verdict is no longer evidence, because it
> will be withdrawn as soon as it is contradicted; and its round-2 verdict is not
> evidence either, because it merely restates what the others already said. Six
> such members do not produce a six-member consensus — they produce one opinion
> counted six times, with the appearance of agreement standing in for the fact of
> it. Cathie Wood exists to disagree. If debate silences her, the committee has
> become one voice with six names, and a high revision rate is how that failure
> announces itself before anyone notices the votes are all the same.

That paragraph is the argument for the whole feature and it stays in the UI. A
judge reading a red bar needs to know within one sentence why red is bad here,
given that "the committee reached agreement" sounds like success.

---

## 4 · RedTeamPanel

**File:** `app/components/council/RedTeamPanel.tsx`
**Rendered:** wherever a directive is rendered — `/council` assessment cards and
`/terminal` directive rows — gated on a non-empty challenge list for that
directive.

```ts
export interface RedTeamPanelProps {
  /** Challenges already filtered to one directive. Never the whole run. */
  challenges: RedTeamChallenge[]
  /** The directive under attack, for the DOWNGRADE size fallback. */
  directive?: DailyDirective
  /** 'card' inside a council card, 'row' inside a terminal directive row. */
  density?: 'card' | 'row'
}
```

### 4.1 · Severity treatments

| Severity | Border / fill | Icon | Chip label |
|---|---|---|---|
| `BLOCK` | `border-[#ef4444]/50 bg-[#450a0a] text-[#ef4444]` | `Ban` | `BLOCKED` |
| `DOWNGRADE` | `border-[#fbbf24]/50 bg-[#451a03] text-[#fbbf24]` | `TrendingDown` | `DOWNGRADED` |
| `NOTE` | `border-[#f472b6]/40 bg-[#131c2e] text-[#f472b6]` | `MessageSquareWarning` | `NOTE` |
| unknown | `NOTE` treatment, raw string as label (COMPAT-7) | `MessageSquareWarning` | raw value |

Ordering within a directive: `BLOCK`, then `DOWNGRADE`, then `NOTE`, then
unknown; ties keep payload order. The most consequential attack is always first.

Every challenge renders `attack` as its body text (`text-xs`, `on-surface
#f8fafc`) and `evidence[]` as a bulleted list beneath (`text-xs`,
`on-surface-variant #94a3b8`, `list-disc pl-4`). In `density='row'` the evidence
list is capped at two items with `+N more` as a plain-text suffix — never a
truncation that hides the last item silently.

### 4.2 · BLOCK — the vetoed directive stays on screen

> **A directive with a `BLOCK` challenge is NEVER removed from the UI, never
> filtered out of a list, and never hidden behind a "show blocked" toggle.**

The backend removes it from execution. The interface keeps it visible, because the
fact that a trade was proposed and then killed by an adversarial reviewer is the
single most persuasive artefact this product can show. A clean list of surviving
directives proves nothing — it looks identical to a system with no red team at
all.

Rendering of a blocked directive:

- The directive's action, symbol and size render with `line-through` and
  `opacity-60`. Struck through, still legible; `opacity-60` is the floor, and text
  must never be faded to the point of being unreadable.
- A `BLOCKED BY RED TEAM` chip sits on the directive header line, in the `BLOCK`
  colours, `text-[10px] font-bold uppercase tracking-wider`, with the `Ban` icon.
  The chip is **not** struck through.
- Directly beneath, not collapsed, the killing attack:

```
Vetoed: {attack}
```

  `Vetoed:` in `error #ef4444` `font-semibold`, the attack text in
  `on-surface #f8fafc` at full opacity. The attack is the reason the strike-through
  is meaningful and must be the most readable thing in the block.
- `evidence[]` renders as a list beneath the attack, `on-surface-variant #94a3b8`,
  full opacity, never struck through.
- The directive's own `reasoning_trace` remains available at whatever disclosure
  level it had before. Both cases stay on the record: why it was proposed, and why
  it was killed.
- The row keeps its position in the list. It is not sorted to the bottom, which
  would read as a soft form of hiding.
- `aria-label` on the container: `Blocked directive: {action} {symbol}, vetoed by
  red team`. Screen-reader users must not be told a struck-through row is merely
  decorative.

The empty-list guard from COMPAT-3 does **not** apply to a directive list that
becomes empty because everything in it was blocked. In that case the list renders
all of its blocked rows plus the header
`All 3 proposed directives were vetoed by the red team.` A directive list that
renders "no directives today" while three vetoed proposals exist is a factual
misstatement.

### 4.3 · DOWNGRADE — size before and after

A `DOWNGRADE` renders the halving explicitly, with the same arrow convention as
§2.3:

```
Size 4 → 2 contracts   (halved by red team)
```

- Values come from `size_before` / `size_after` when present.
- When only `size_before` is present, `size_after` is computed as
  `Math.floor(size_before / 2)` and the line is annotated `(derived)` in
  `on-surface-variant #94a3b8`. Floor, not round: a halving that rounds up
  overstates the reduction the risk layer actually applied.
- When neither is present, fall back to the directive's own contract count from
  `directive.params` and apply the same derivation, still annotated `(derived)`.
- When no size can be established at all, the line reads
  `Size halved by red team — original size not reported.` The halving is stated
  even when the numbers are missing; silence would imply the size was untouched.
- `size_after > size_before` (a nonsensical payload) renders both values verbatim
  with the annotation `(reported, not a halving)`. Do not silently swap them.
- Both numbers `font-mono`. The arrow is the same U+2192 as §2.3, `aria-hidden`,
  with the sentence available to assistive tech through the container label.

The directive is **not** struck through on `DOWNGRADE` — it is still live, at half
size, and striking it would misrepresent it as vetoed.

### 4.4 · Attaching challenges to directives — `/council` and `/terminal`

`RedTeamChallenge.directive_id` is the join key. The link back is
`DailyDirective.provenance`, which already exists in `lib/api.ts` as
`Array<{ source: string; detail?: string }>` — W5c requires `BLOCK` and
`DOWNGRADE` to be written into it so the audit trail carries the challenge.

One resolver, in `lib/api.ts`, used by both routes:

```ts
/** Provenance sources that carry a red-team directive id. */
const RED_TEAM_SOURCES = ['red_team', 'red-team', 'redteam'] as const

/** Directive ids named in a directive's provenance, plus its own id field. */
export function directiveIds(d: DailyDirective): string[] {
  const ids: string[] = []
  const own = d.directive_id
  if (typeof own === 'string' && own) ids.push(own)
  for (const p of d.provenance ?? []) {
    const src = (p.source ?? '').toLowerCase()
    if (!RED_TEAM_SOURCES.some((s) => src.includes(s))) continue
    const detail = p.detail ?? ''
    const m = detail.match(/[A-Za-z0-9_.:-]{6,}/)
    if (m) ids.push(m[0])
  }
  return ids
}

/** Challenges belonging to one directive. Empty array = render nothing. */
export function challengesForDirective(
  d: DailyDirective,
  challenges: RedTeamChallenge[],
): RedTeamChallenge[] {
  const ids = new Set(directiveIds(d))
  if (ids.size === 0) return []
  return challenges.filter((c) => ids.has(c.directive_id))
}
```

Rules that apply identically on both routes:

1. **The join is by id, never by symbol.** Two directives on the same symbol
   (`INITIATE` and `ROLL`) must not inherit each other's veto. `symbol` on
   `RedTeamChallenge` is a display convenience only, used solely by
   `challengesFor()` in §1.3 for the run-level fallback list.
2. **The panel is nested inside the directive it attacks.** Never a sibling list,
   never a separate "red team" tab. Physical adjacency is what makes
   proposed-then-vetoed legible at a glance.
3. **A challenge whose `directive_id` matches nothing** is rendered in a run-level
   `Unmatched red-team challenges` group at the bottom of the panel that owns the
   list, with the raw `directive_id` shown. It is never dropped — a swallowed veto
   is the worst possible failure for this feature.
4. **`/council`:** challenges come from `challengesFor(response, assessment)` and
   render inside the assessment card, beneath the recommendation chip row and
   above the dissent list. Where the card shows no per-directive rows, the panel
   attaches to the recommendation itself, which is the directive-in-waiting.
5. **`/terminal`:** each directive row renders
   `challengesForDirective(directive, challenges)` in `density='row'`, inline
   under the row, with the strike-through applied to the row's own action/symbol
   cells rather than to a nested copy of them.
6. **Both routes read from the same resolver.** No route-local matching logic; a
   veto visible on `/council` and invisible on `/terminal` is a bug in exactly one
   place, and this rule is what keeps it that way.

---

## 5 · CalibrationScoreboard

**File:** `app/components/council/CalibrationScoreboard.tsx`
**Rendered:** run-level, beneath `RevisionRateMeter`, whenever
`hasCalibration(response)` is true — **including when `sample_size` is 0**.

```ts
export interface CalibrationScoreboardProps {
  calibration: CouncilCalibration
  /** Defaults to CALIBRATION_MIN_SAMPLE (30). */
  minSample?: number
}
```

### 5.1 · Header — sample size first

The sample size is part of the header, not a footnote, and it precedes every
metric on screen:

```
Calibration · n = 12 assessments — far below significance
```

- `Calibration` in `on-surface #f8fafc` `font-semibold text-sm`.
- `n = 12 assessments` in `font-mono`, `secondary #fbbf24` when
  `sample_size < minSample`, `on-surface-variant #94a3b8` at or above it.
- The trailing clause `— far below significance` is rendered only while
  `sample_size < minSample`, in `secondary #fbbf24`.
- `sample_size === 0` renders `n = 0 assessments — no resolved outcomes yet` and
  the metric row is replaced by
  `Nothing has resolved yet. The instrument is built; the readings are not in.`
  in `on-surface-variant #94a3b8`. The panel still renders — a scoreboard showing
  honestly that it has nothing to show is worth more than a hidden panel.
- `sample_size` absent (not zero) renders `n = unreported`, and the caveat block
  below is shown, because an unknown n cannot be assumed adequate.
- When `window_start`/`window_end` are present, a second header line reads
  `Window: {window_start:date} → {window_end:date}` using `toLocaleDateString()`.
  Formatting is done with the platform `Intl` API — no date library is in
  `package.json` and none is to be added.

### 5.2 · Metrics

Three figures, `font-mono`, on `surface-container #131c2e` tiles:

| Figure | Format | Colour |
|---|---|---|
| Hit rate | `58.3%` — one decimal, from `hit_rate * 100` | `on-surface #f8fafc` |
| Mean error | `+3.2` / `-1.7` — always signed, one decimal | `#22c55e` if `abs < 5`, else `#fbbf24`, else `#ef4444` above 15 |
| Resolved | `12 / 20` when the denominator is derivable, else `12` | `on-surface-variant #94a3b8` |

Any figure that is absent or non-finite renders as `—` **with the label still
present**, so the reader sees which instrument has no reading rather than a
shorter list of instruments. This is the one place a dash is correct: the metric
genuinely has no value, unlike the `HELD` cell in §2.4 which has the most
important value on the row.

`by_persona`, when present, renders as a compact table beneath the tiles with the
same per-row caveat rule: any persona whose own `sample_size < minSample` shows
its n in `secondary #fbbf24`.

### 5.3 · The caveat — exact copy, never dismissible

While `sample_size < minSample` (including 0, including unreported), the panel
renders this block directly under the header, above the metrics:

```
n = 12 assessments over 6 days. This sample is far below statistical
significance; treat every figure below as directional at best. A hit rate
computed on 12 observations can move more than 10 points on one outcome.
The instrument is here so the number can be checked later — it is not yet
evidence that the council is calibrated.
```

Styling: `text-xs`, `secondary #fbbf24`, on `bg-[#451a03]` with
`border border-[#fbbf24]/50`, `rounded`, `px-3 py-2`, `Info` icon 14px. Substitute
the real `n` and, when `window_start`/`window_end` allow, the real day count;
when the window is unknown the second clause of the first sentence is omitted and
the rest of the copy is unchanged.

Normative constraints on this block:

1. **Never dismissible.** No close button, no `×`, no `localStorage`
   "acknowledged" flag, no session-scoped suppression. There is no state in which
   the app has rendered the caveat once and may now stop.
2. **Never collapsed behind a toggle.** No `<details>`, no accordion, no "show
   caveat" link, no tooltip, no `title` attribute as the delivery mechanism, no
   hover-only reveal. It is always expanded text in the normal flow.
3. **Never below the fold of its own panel.** It sits above the metrics it
   qualifies. A reader who sees `58.3%` has already seen why `58.3%` cannot be
   trusted.
4. **Not `aria-hidden`, not visually hidden, and it survives print/screenshot.**
   The caveat exists precisely for the case where someone screenshots the panel.
5. **Removed only by the data.** It disappears when and only when
   `sample_size >= minSample`. There is no prop, flag, or environment variable
   that turns it off.

Rationale: a judge who finds the caveat themselves stops trusting every other
number on the screen. A judge who is handed the caveat by the interface starts
trusting the interface. The asymmetry is large and entirely in favour of saying it
first.

---

## 6 · Refactor plan for `CouncilBoard.tsx`

Current file: 265 lines, one default export, one `useState` for `expanded`, one
`useCallback` fetch, and a single deeply nested JSX tree containing the header,
the mode badge, the error strip, the skeleton, the card grid, the dissent list and
the animated verdict disclosure. F3 adds four panels; left alone the file lands
around 520 lines and every new panel deepens the same nesting.

### 6.1 · Target structure

```
app/components/council/
├── CouncilBoard.tsx          orchestration + layout only  (~110 lines)
├── CouncilBoardHeader.tsx    title, mode badge, freshness dot, run button
├── AssessmentCard.tsx        one symbol: identity, gauge, chips, disclosure
├── PersonaVerdictList.tsx    round-1 verdict list (moved verbatim)
├── DissentList.tsx           flat dissent rows (moved verbatim)
├── DebateTimeline.tsx        §2
├── RevisionRateMeter.tsx     §3
├── RedTeamPanel.tsx          §4
├── CalibrationScoreboard.tsx §5
└── councilFormat.ts          tierStyle, scoreColor, stanceChip, formatScoreDelta
```

### 6.2 · Props boundaries

```ts
// CouncilBoardHeader — presentational, no data fetching.
interface CouncilBoardHeaderProps {
  mode?: string
  loading: boolean
  onRun: () => void
  freshness?: 'live' | 'stale' | 'offline'   // F1 freshness.ts
}

// AssessmentCard — owns its own expanded state; the board no longer tracks it.
interface AssessmentCardProps {
  assessment: CouncilAssessment
  challenges: RedTeamChallenge[]            // pre-filtered by the board
}

interface PersonaVerdictListProps {
  verdicts: CouncilVerdict[]
}

interface DissentListProps {
  dissent: CouncilDissent[]
  /** Rows past this are summarised as "+N more"; undefined = show all. */
  maxRows?: number
}
```

`DebateTimelineProps`, `RevisionRateMeterProps`, `RedTeamPanelProps` and
`CalibrationScoreboardProps` are as declared in §§2–5.

Boundary rules:

- **No child fetches, and no child calls `api.*`.** All data enters through
  `CouncilBoard` (F1 `useCouncilQuery`) and flows down as props. This is what makes
  every child testable with a literal object.
- **No child reads a type guard.** The board evaluates `hasDebateData`,
  `hasRevisionRates`, `hasCalibration` and `challengesFor` and either renders the
  child or does not (COMPAT-3). Children assume their data is present and usable.
- **`expanded` moves into `AssessmentCard`.** The current board-level
  `expanded: string | null` exists only because the JSX is one tree; per-card local
  state removes a re-render of the whole grid on every toggle.
- **`councilFormat.ts` is pure.** No JSX, no React import, so `vitest` can
  exercise `formatScoreDelta` and the class-name mappers directly without a DOM.

### 6.3 · What stays in `CouncilBoard.tsx`

- The F1 query hook and the mock-fallback behaviour on error, unchanged in
  substance from the current `runSession` (the fallback is explicitly protected by
  the F1 brief; do not regress it).
- The `RevealGroup` grid wrapper and `stagger={0.045}`.
- The three-state branch (skeleton / empty / error) it shares with the page, §7.
- Evaluation of the four v2 guards and the `challengesFor` fan-out.
- Composition order: `CouncilBoardHeader`, error strip, `RevisionRateMeter`,
  `CalibrationScoreboard`, then the `AssessmentCard` grid. Run-level truth first,
  per-symbol detail second: the revision meter and calibration caveat frame how
  every card below them should be read.

### 6.4 · Order of extraction — the file is never broken mid-refactor

Each step is a standalone commit that compiles (`npx tsc --noEmit`) and passes
`npm test`. No step depends on a later step. Steps 1–5 are pure moves with **zero
behavioural change**; the v2 panels only arrive at step 6, so any visual
regression can be bisected to a move rather than to new code.

| # | Step | Why here |
|---|---|---|
| 1 | Extract `councilFormat.ts`: move `TIER_STYLES`, `tierStyle`, `scoreColor`, `stanceChip` out verbatim; import them back into `CouncilBoard`. Add `formatScoreDelta` in the same commit — unused so far, but unit-testable immediately. | Pure functions, no JSX, no props to design. Lowest-risk possible first move and it gives §8's first tests something to run against. |
| 2 | Extract `PersonaVerdictList.tsx`: lift the `AnimatePresence` verdict block, props `{ verdicts }`. `expanded` stays in the board and the child stays uncontrolled. | The deepest nesting in the file. Removing it makes every later step readable. Behaviour-identical, so a diff of the rendered card is expected to be empty. |
| 3 | Extract `DissentList.tsx`, props `{ dissent }`. | Same shape as step 2, half the size. Card body drops to header + chips + two children. |
| 4 | Extract `CouncilBoardHeader.tsx`, props `{ mode, loading, onRun }`; `freshness` is added as an optional prop but not yet passed. | Isolates the F1 seam. When F1 lands, only this file and the board's hook call change. |
| 5 | Extract `AssessmentCard.tsx`, props `{ assessment }`; move `expanded` into it as a local boolean. The board's `expanded` state and its `setExpanded` disappear in this commit. | Last structural move. After it the board is orchestration only and is around 110 lines — room for four panels without growing past the original 265. |
| 6 | Add `DebateTimeline.tsx` behind `hasDebateData`, rendered from `AssessmentCard` above `PersonaVerdictList`. | First v2 panel. Guarded, so on today's payload the rendered output is byte-identical to step 5 and the COMPAT-1 test proves it. |
| 7 | Add `RevisionRateMeter.tsx` behind `hasRevisionRates`, rendered from the board. | Run-level, no card changes, independent of step 6. |
| 8 | Add `CalibrationScoreboard.tsx` behind `hasCalibration`, rendered from the board. | Run-level, independent of 6 and 7. |
| 9 | Add `RedTeamPanel.tsx` plus `directiveIds` / `challengesForDirective` in `lib/api.ts`; wire into `AssessmentCard` and the `/terminal` directive row. | Last because it is the only step touching a second route. The resolver ships with tests in the same commit. |
| 10 | Add `challenges` to `AssessmentCardProps` and hoist the `challengesFor` fan-out into the board. | Separated from step 9 so the prop-boundary change is reviewable on its own. |

Invariants across all ten steps:

- After every step the council page renders against today's live payload with no
  visual diff except where the step's own row explicitly says otherwise (only step
  9 does).
- No step deletes a file another step still imports. Steps 1–5 leave the moved
  symbol imported from its new home in the same commit that removes it.
- No step introduces a `TODO`, a commented-out block, or an unused import. A
  half-migrated file with dead code in it is exactly the state this ordering
  exists to avoid.

---

## 7 · Three-state audit for `app/council/page.tsx`

Today's page is 19 lines: `Sidebar`, `Header`, `<CouncilBoard />`. It has no
loading, empty, or error handling of its own and inherits whatever `CouncilBoard`
does — which is a four-tile pulse skeleton, an amber error strip, and, for an
empty `assessments` array, nothing at all. That last case is the real defect:
`MOCK_SNAPSHOT` is `{ mode: 'mock', count: 0, assessments: [] }`, so a failed
fetch currently renders an error strip above a completely blank grid.

### 7.1 · Where F1 plugs in

The page becomes a client component that owns the query and passes state down;
`CouncilBoard` keeps rendering the data but stops fetching it.

```tsx
'use client'
// F1: lib/live/hooks.ts
const { data, isLoading, isError, error, refetch, isFetching } = useCouncilQuery()
// F1: lib/live/freshness.ts
const freshness = useFreshness(keys.council())
```

- `useCouncilQuery` (F1 `lib/live/hooks.ts`) replaces the `useEffect` +
  `useCallback` + three `useState`s currently in `CouncilBoard`.
- The query key comes from F1 `lib/live/keys.ts`; the council interval is defined
  in the one interval table there, never inline.
- `QueryClientProvider` is mounted once in `app/components/Providers.tsx` (F1) —
  the page does not mount its own.
- `refetch` is passed to `CouncilBoardHeader` as `onRun`; `isFetching` becomes
  `loading` for the spinner. The 30s `AbortController` timeout for
  `/api/council/assess` carries over from `lib/api.ts` verbatim.
- `freshness` feeds the header's dot. `mode === 'mock'` keeps its existing amber
  `MOCK DATA` badge — that labelling already exists and F1 forbids regressing it.

### 7.2 · Loading

Condition: `isLoading && !data`.

Structure mirrors the final layout so nothing jumps on resolve: one full-width bar
for the header, one full-width block for the run-level panels, then four
`h-44` tiles in `md:grid-cols-2` — matching today's skeleton count exactly.

- Tiles: `animate-pulse rounded-lg border border-[#334155] bg-[#0f172a]`.
- One line of copy above the grid, `text-xs` `on-surface-variant #94a3b8`:

```
Convening the council — six personas scoring the overlay universe…
```

- The skeleton is `aria-busy="true"` with `aria-live="polite"` on the copy line.
- No spinner in the page body. The only spinner is the `RefreshCw` in the header
  button, which already spins on `loading`.

### 7.3 · Empty

Condition: `!isLoading && !isError && (data?.assessments?.length ?? 0) === 0`.

A bordered panel on `surface #0f172a` with `border-[#334155]`, a `Users` icon in
`on-surface-variant #94a3b8`, and:

```
No assessments in this session.

The council ran but returned no symbols to score. That usually means the
overlay universe is empty or every candidate was filtered before scoring.
```

Plus a `Run council session` button wired to `refetch()`.

Distinguish the two empty shapes:

- `data.mode === 'mock'` with `count === 0` — the bundled fallback. Second
  paragraph is replaced by
  `Showing the bundled fallback snapshot: the backend returned no live data.`
- A genuine live empty (`mode === 'live'`, `count === 0`) keeps the copy above.

An empty result is never rendered as an error, and never as a bare blank area,
which is today's behaviour and the specific defect this section closes.

### 7.4 · Error

Condition: `isError`.

The existing amber strip in `CouncilBoard` is preserved for the
degraded-but-usable case (fetch failed, fallback snapshot shown) and moves into
the page in the same colours: `border-[#fbbf24]/50 bg-[#451a03] text-[#fbbf24]`,
`AlertCircle` icon.

```
{message} — showing bundled fallback.
```

When there is no fallback to show (`data == null`), escalate to a full error panel
in `error #ef4444` on `bg-[#450a0a]` with `border-[#ef4444]/50`:

```
Council unavailable.

{message}

Nothing is being shown for this session — this is a fetch failure, not an
empty council.
```

With a `Retry` button calling `refetch()`. The final sentence is required: an
error state that could be mistaken for "the council found nothing" is worse than
no error state, because it invents a result.

`message` uses the existing `ApiError` distinction from `lib/api.ts` — "timed out"
and "unreachable" are different sentences and F1 requires that distinction be
carried over intact.

### 7.5 · Ordering

The three states are mutually exclusive and evaluated in this order: **error →
loading → empty → data.** Error outranks loading so a failed refetch of stale data
is never masked by a spinner. `data` renders alongside a non-fatal error strip
when a fallback exists, which is the one overlap and it is deliberate.

---

## 8 · Tests

The suite at `frontend/tests/` is `vitest` with three files (`api.test.ts`,
`reasoning.test.ts`, `utils.test.ts`) and one fixture (`fixtures/realTrace.ts`).
There is **no** `@testing-library/react` and no `jsdom` environment configured, and
F3 does not add either. Consequently:

- Pure logic — type guards, resolvers, formatters, severity ordering, threshold
  comparisons, caveat decisions — is tested directly in `vitest`. This is where the
  bulk of the risk actually lives.
- Rendered-output requirements (strike-through present, caveat visible, HELD cell
  non-empty) are asserted through **pure predicate functions that the components
  consume**, so the rule is testable without a DOM. Where a rule cannot be reduced
  to a predicate, it is covered by a Playwright assertion in
  `frontend/tests/e2e/` (`@playwright/test` is already a devDependency).

New fixture: `frontend/tests/fixtures/councilPayloads.ts` exporting
`V1_PAYLOAD` (today's shape, six personas, no v2 fields), `V2_PAYLOAD` (two
rounds, one held, one revised, one persona at 0.83, a BLOCK, a DOWNGRADE,
calibration n = 12), `EMPTY_PAYLOAD` and `CALIBRATION_ZERO`.

### 8.1 · `tests/councilTypes.test.ts` — guards and compatibility

1. `hasDebateData` returns false for every assessment in `V1_PAYLOAD` — no field, no debate.
2. `hasDebateData` returns false when `revisions` is present but an empty array.
3. `hasDebateData` returns false when `rounds === 2` but `revisions` is empty — reported rounds alone never enable the timeline.
4. `hasDebateData` returns true when at least one revision carries a boolean `revised`.
5. `hasDebateData` returns true when a revision carries a numeric `score` but no `revised` flag.
6. `hasRevisionRates` returns false for `V1_PAYLOAD` and for a `revision_rates` array whose every rate is `undefined`.
7. `hasRevisionRates` returns false when the only rate is `NaN` — COMPAT-6 treats non-finite as absent.
8. `hasCalibration` returns true for `CALIBRATION_ZERO` (`sample_size: 0`) — an empty ledger is a renderable state, not an absent one.
9. `hasCalibration` returns false when `calibration` is absent from the response.
10. `revisionFor` matches persona names case-insensitively and with surrounding whitespace trimmed.
11. `revisionFor` returns `undefined` for a persona present in `verdicts` but absent from `revisions` — the COMPAT-4 partial-round-2 path.
12. `challengesFor` merges nested `assessment.red_team` with symbol-matched run-level challenges and de-duplicates by `directive_id`.
13. **COMPAT-1:** every F3 guard evaluated over `V1_PAYLOAD` returns false or an empty array, and no guard throws — the single assertion that today's payload drives the UI into its pre-v2 rendering with no error.

### 8.2 · `tests/councilFormat.test.ts` — score delta and formatting

14. `formatScoreDelta(68, 67.6)` returns `{ before: '68.0', after: '67.6', delta: '-0.4', direction: 'down' }` — the exact case named in the brief.
15. `formatScoreDelta` renders an integer input with one decimal place (`68` → `'68.0'`), never as a bare integer.
16. `formatScoreDelta` always signs the delta: an upward move yields a leading `+`.
17. `formatScoreDelta` reports `direction: 'flat'` and an unsigned `'0.0'` when the two scores are equal.
18. `formatScoreDelta` treats a sub-0.05 difference as `flat` rather than emitting a `-0.0` delta.
19. `formatScoreDelta` returns `null` for `NaN`, `Infinity` and `undefined` inputs — COMPAT-6, so no component can render the string `NaN`.
20. `tierStyle` and `stanceChip` still return their pre-refactor class strings for `LOW`/`MID`/`HIGH` and for every known stance — the step-1 extraction is a pure move.
21. `stanceChip` falls through to the bearish chip for an unrecognised stance rather than returning `undefined` (COMPAT-7).

### 8.3 · `tests/debateTimeline.test.ts` — held is a signal

22. A persona with `revised === false` yields a non-empty held label, and the returned string is neither `''`, `'—'`, `'-'`, `'n/a'` nor `null` — the §2.4 prohibition, asserted as a value rather than as a style.
23. A persona with `revised === false` that also appears in `dissent[]` yields the extended copy `Held position under dissent. Saw the counter-argument and did not move.`
24. A persona with `revised === true` yields its `revision_reason` as the row explanation, and an empty `revision_reason` falls back to `Revised after seeing the dissent.` rather than to an empty cell.
25. A persona with a revision record but neither `revised` nor a numeric `score` is classified `unreported`, distinct from both `held` and `revised`.
26. The row-state classifier returns `held` for `revised: false` and `revised` for `revised: true`, and the two states never collapse to a shared value.
27. Header counts over `V2_PAYLOAD` report the correct held / revised / unreported tallies and sum to `verdicts.length`.
28. Persona iteration order follows `verdicts`, and a persona present only in `revisions` is excluded (COMPAT-4).

### 8.4 · `tests/revisionRate.test.ts` — the 0.7 line

29. A persona at `revision_rate: 0.83` is classified as breaching and carries the exact copy `capitulating — not independent`.
30. A persona at exactly `0.70` is **not** breaching — the comparison is strictly `>` because the brief says *above* 0.7.
31. A persona at `0.69` is not breaching and its bar fill resolves to `primary #22c55e`.
32. A breaching persona's bar fill resolves to `error #ef4444`, and no intermediate amber band exists between the two states.
33. The reference-line offset is derived from the threshold (`0.7 → '70%'`), not hard-coded, so `threshold: 0.5` moves the line to `'50%'`.
34. Rates are sorted descending, so a breaching persona is the first row rendered.
35. Rows whose `revision_rate` is absent, `NaN` or outside `[0, 1]` are dropped from the list rather than rendered at 0% (COMPAT-6).
36. The breach summary line pluralises and counts correctly: one breach of six reports `1 of 6 personas above the 0.7 revision line`.

### 8.5 · `tests/redTeam.test.ts` — BLOCK, DOWNGRADE, attachment

37. **BLOCK:** a directive with a `BLOCK` challenge is retained by the render-list selector — the selector returns the same length as its input, proving vetoed directives are never filtered out.
38. **BLOCK:** the blocked directive's display state carries `struckThrough: true` and a non-empty `vetoReason` sourced from `attack`; the veto reason is not itself struck through.
39. **BLOCK:** a list in which every directive is blocked returns all rows plus the header `All 3 proposed directives were vetoed by the red team.` and never the empty-state copy.
40. **DOWNGRADE:** `size_before: 4, size_after: 2` renders `4 → 2` with `derived: false`.
41. **DOWNGRADE:** `size_before: 5` alone derives `size_after: 2` by flooring, and flags `derived: true` — never rounds up to 3.
42. **DOWNGRADE:** with no sizes anywhere the panel still states the halving, returning the `original size not reported` copy rather than omitting the line.
43. **DOWNGRADE:** `size_after > size_before` returns both values verbatim with the `(reported, not a halving)` annotation and does not swap them.
44. **DOWNGRADE** never sets `struckThrough` — a halved directive is still live.
45. `directiveIds` extracts the id from a `provenance` entry whose `source` is `red_team`, and ignores entries from other sources.
46. `challengesForDirective` joins strictly on `directive_id`: two directives on the same symbol do not inherit each other's challenge.
47. `challengesForDirective` returns an empty array for a directive with no ids, and the panel guard therefore renders nothing (COMPAT-3).
48. A challenge whose `directive_id` matches no directive is reported by the unmatched selector — no veto is ever silently dropped.
49. Severity ordering places `BLOCK` before `DOWNGRADE` before `NOTE`, with unknown severities last and payload order preserved within a tie.
50. An unknown severity string resolves to the `NOTE` treatment and keeps its raw label (COMPAT-7).

### 8.6 · `tests/calibration.test.ts` — honest small numbers

51. **n = 0:** `CALIBRATION_ZERO` renders the panel, reports `n = 0 assessments — no resolved outcomes yet`, and shows the caveat.
52. **n = 0:** the metric tiles are replaced by `Nothing has resolved yet. The instrument is built; the readings are not in.` and no hit rate is fabricated from a zero denominator.
53. `sample_size: 12` produces the header `Calibration · n = 12 assessments — far below significance`.
54. `sample_size: 29` still shows the caveat; `sample_size: 30` does not — the boundary is `>= CALIBRATION_MIN_SAMPLE`.
55. `sample_size: undefined` renders `n = unreported` and shows the caveat — an unknown n is never assumed adequate.
56. The caveat descriptor exposes no `dismissible`, `collapsed` or `defaultOpen` affordance; the caveat model has exactly one input, the sample size.
57. The caveat text interpolates the real `n` and the real day count when `window_start`/`window_end` are present, and omits the day clause when they are not.
58. A `hit_rate` of `NaN` renders `—` while its label remains present — the reader sees which instrument has no reading.
59. `mean_error` is always signed, and `+0.0` / `-0.0` never appear as unsigned `0`.

### 8.7 · `tests/councilPage.test.ts` — three states

60. The state selector returns `error` when `isError` is true even while `isLoading` is also true — error outranks loading (§7.5).
61. It returns `loading` for `isLoading && !data`, and the loading copy is `Convening the council — six personas scoring the overlay universe…`.
62. It returns `empty` for a resolved response with `assessments: []`, never `error`.
63. The empty state distinguishes `mode: 'mock'` from `mode: 'live'` and returns the fallback-specific second paragraph for the former.
64. `data == null` with an error returns the fatal panel including `this is a fetch failure, not an empty council`; a non-null fallback returns the amber strip instead.
65. The `ApiError` "timed out" and "unreachable" messages produce different strings — the F1 distinction survives the migration.

### 8.8 · Playwright — `tests/e2e/council.spec.ts`

66. Against the live dev server on today's payload, `/council` renders six persona verdicts with no console error and no element matching the v2 panel headings — COMPAT-1 and COMPAT-3 verified end to end.
67. With a routed mock of `V2_PAYLOAD`, a blocked directive is visible with `text-decoration: line-through` computed on its action cell while its veto reason computes to no line-through.
68. With the same mock, the calibration caveat is visible in the DOM, has no `[aria-expanded]` ancestor, and no clickable control dismisses it.

### 8.9 · Coverage of the brief's acceptance clause

The F3 acceptance line requires "a persona that revised, one that did not, one
above the 0.7 revision line, a `BLOCK`, a `DOWNGRADE`, and an empty-calibration
state all render correctly." Mapping: revised → 24, did not → 22/23/26, above 0.7
→ 29, `BLOCK` → 37/38/39/67, `DOWNGRADE` → 40/41/44, empty calibration → 51/52.
COMPAT-1 is 13 and 66.

---

## 9 · Definition of done

1. `npx tsc --noEmit` clean.
2. `npm test` green, including the pre-existing three test files unmodified.
3. `V1_PAYLOAD` renders the council page with no v2 panel and no console error.
4. `V2_PAYLOAD` renders all four v2 surfaces with the exact copy specified in
   §§2.4, 3.3, 4.2, 4.3 and 5.3.
5. `CouncilBoard.tsx` is under 130 lines and fetches nothing.
6. `app/council/page.tsx` has all three states with the copy in §7.
7. No new entry in `frontend/package.json`.
8. No colour outside the token list in §0 and the pre-existing chip fills.

