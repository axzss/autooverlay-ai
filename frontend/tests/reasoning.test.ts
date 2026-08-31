import { describe, it, expect } from 'vitest'
import {
  parseReasoning,
  groupIsBlocked,
  type ParsedReasoning,
  type ReasoningGroup,
} from '../lib/reasoning'
import { REAL_TRACE } from './fixtures/realTrace'

/**
 * How many lines the parser actually accounts for in its output:
 * everything in preamble plus every group's raw list.
 */
function accountedLines(p: ParsedReasoning): number {
  return p.preamble.length + p.groups.reduce((n, g) => n + g.raw.length, 0)
}

/** Every line the parser accounted for, in output order. */
function accountedContent(p: ParsedReasoning): string[] {
  return [...p.preamble, ...p.groups.flatMap((g) => g.raw)]
}

/** Lines that carry content — the parser explicitly skips blank ones. */
function nonBlank(trace: readonly string[]): string[] {
  return trace.filter((l) => l.trim() !== '')
}

const MOOD = 'Mr. Market mood: indifferent (buying not favorable)'

describe('parseReasoning — real 41-line backend trace', () => {
  const parsed = parseReasoning(REAL_TRACE)

  it('reports the true input size', () => {
    expect(REAL_TRACE.length).toBe(41)
    expect(parsed.totalLines).toBe(41)
  })

  it('produces exactly 8 symbol groups in trace order', () => {
    expect(parsed.groups).toHaveLength(8)
    expect(parsed.groups.map((g) => g.symbol)).toEqual([
      'MSFT',
      'NVDA',
      'AAPL',
      'TSLA',
      'SPY',
      'QQQ',
      'JPM',
      'KO',
    ])
  })

  it('hoists the market mood exactly once', () => {
    expect(parsed.marketMood).toBe(MOOD)
    // The line repeats once per symbol in the input...
    expect(REAL_TRACE.filter((l) => l === MOOD)).toHaveLength(8)
    // ...but marketMood is a single string, not a list.
    expect(typeof parsed.marketMood).toBe('string')
  })

  it('accounts for all 41 lines across preamble + group.raw', () => {
    expect(parsed.preamble).toEqual([])
    expect(accountedLines(parsed)).toBe(41)
    expect(accountedContent(parsed)).toEqual([...REAL_TRACE])
  })

  it('leaves zero lines unclassified', () => {
    for (const g of parsed.groups) {
      expect(g.other).toEqual([])
    }
  })

  it('blocks MSFT and NVDA with 3 gates and a citation each', () => {
    for (const sym of ['MSFT', 'NVDA']) {
      const g = parsed.groups.find((x) => x.symbol === sym)!
      expect(g, sym).toBeDefined()
      expect(g.gates, sym).toHaveLength(3)
      expect(g.gates.map((x) => x.label), sym).toEqual([
        'concentration',
        'cash reserve',
        'sector-cap',
      ])
      expect(g.citation, sym).toBeTruthy()
      expect(g.citation, sym).toContain('Investment Council Report §6')
      expect(g.verdict?.kind, sym).toBe('blocked')
      expect(groupIsBlocked(g), sym).toBe(true)
    }
  })

  it('classifies each MSFT gate status from its detail', () => {
    const msft = parsed.groups.find((g) => g.symbol === 'MSFT')!
    expect(msft.gates.map((x) => x.status)).toEqual(['blocked', 'pass', 'blocked'])
  })

  it('captures the TSLA override verbatim', () => {
    const tsla = parsed.groups.find((g) => g.symbol === 'TSLA')!
    expect(tsla.override).toBe(
      'council §8: 59.1% vol + -27.2% drawdown — delta ≤0.10, half-size until vol <45%',
    )
    expect(tsla.gates).toEqual([])
  })

  it('marks AAPL/SPY/QQQ/JPM/KO as HOLD with no gates', () => {
    for (const sym of ['AAPL', 'SPY', 'QQQ', 'JPM', 'KO']) {
      const g = parsed.groups.find((x) => x.symbol === sym)!
      expect(g, sym).toBeDefined()
      expect(g.gates, sym).toHaveLength(0)
      expect(g.verdict?.kind, sym).toBe('hold')
      expect(groupIsBlocked(g), sym).toBe(false)
    }
  })

  it('parses consensus score, tier, vol and policy per symbol', () => {
    const msft = parsed.groups[0]
    expect(msft.consensusScore).toBeCloseTo(60.2)
    expect(msft.recommendation).toBe('ACCUMULATE')
    expect(msft.tier).toBe('high')
    expect(msft.volPct).toBeCloseTo(48.4)
    expect(msft.policy).toBe('delta 0.05-0.15, DTE≤30, strategies=COVERED_CALL, size x0.5')

    const spy = parsed.groups.find((g) => g.symbol === 'SPY')!
    expect(spy.tier).toBe('low')
    expect(spy.volPct).toBeCloseTo(11.8)
    expect(spy.consensusScore).toBeCloseTo(55.4)
    expect(spy.recommendation).toBe('HOLD')
  })

  it('never returns NaN for a parsed numeric field', () => {
    for (const g of parsed.groups) {
      if (g.consensusScore !== null) expect(Number.isNaN(g.consensusScore)).toBe(false)
      if (g.volPct !== null) expect(Number.isNaN(g.volPct)).toBe(false)
    }
  })
})

describe("trimCitedTail behaviour via blocked verdicts", () => {
  const parsed = parseReasoning(REAL_TRACE)
  const blocked = parsed.groups.filter((g) => g.verdict?.kind === 'blocked')

  it('drops the "; cited:" tail', () => {
    expect(blocked).toHaveLength(2)
    for (const g of blocked) {
      expect(g.verdict!.text).toBe('entry BLOCKED by portfolio gates → MONITOR only')
      expect(g.verdict!.text).not.toMatch(/cited:/i)
    }
  })

  it('removes nothing before the tail', () => {
    for (const g of blocked) {
      const original = g.raw.find((l) => /^entry BLOCKED/.test(l.trim()))!
      const text = g.verdict!.text
      // The kept text is a verbatim prefix of the original line.
      expect(original.startsWith(text)).toBe(true)
      // And the only thing removed starts the tail.
      expect(original.slice(text.length)).toMatch(/^;\s*cited:/i)
    }
  })

  it('leaves a blocked verdict with no tail untouched', () => {
    const line = 'entry BLOCKED by portfolio gates → MONITOR only'
    const p = parseReasoning(['council consensus 50 → HOLD', line])
    expect(p.groups[0].verdict).toEqual({ kind: 'blocked', text: line })
  })

  it('preserves everything before the tail verbatim, including trailing space', () => {
    // The invariant is "nothing before the tail is removed". The cut point is
    // the ';' that opens the tail, so any space that sat before it survives.
    const line = 'entry BLOCKED by portfolio gates; note: a; b ; CITED: junk'
    const p = parseReasoning(['council consensus 50 → HOLD', line])
    const text = p.groups[0].verdict!.text
    expect(text).toBe('entry BLOCKED by portfolio gates; note: a; b ')
    expect(line.startsWith(text)).toBe(true)
    expect(text).not.toMatch(/cited:/i)
  })
})

describe('line conservation', () => {
  /**
   * The module header promises no line is ever silently dropped. The parser
   * does deliberately skip lines that are empty after trim, so the exact
   * invariant it upholds is: every NON-BLANK input line is accounted for,
   * verbatim, exactly once.
   */
  const cases: Array<[string, readonly string[]]> = [
    ['real 41-line trace', REAL_TRACE],
    ['empty', []],
    ['single unparseable line', ['hello world']],
    ['single consensus line', ['council consensus 60.2 → ACCUMULATE']],
    ['no consensus line anywhere', ['some prose', 'more prose', 'entry BLOCKED by portfolio gates']],
    ['gates before any group', ['concentration check: 1% ✓', 'council consensus 5 → HOLD']],
    ['duplicate consensus lines back to back', [
      'council consensus 1 → A',
      'council consensus 2 → B',
      'council consensus 3 → C',
    ]],
    ['symbol-like line with no colon', ['council consensus 1 → A', 'MSFT 48.4% vol high tier']],
    ['non-numeric consensus score', ['council consensus ... → ACCUMULATE', 'x']],
    ['tier line missing parens', ['council consensus 1 → A', "MSFT: 48.4% vol → 'high' tier"]],
    ['unicode soup', ['council consensus 1 → A', '✓✗→§≤−—🙂', '日本語のテキスト']],
    ['extremely long line', ['council consensus 1 → A', 'x'.repeat(200000)]],
    ['citation with no group', ['council rule cited: §6 something']],
    ['override with no group', ['TSLA OVERRIDE ACTIVE (foo)']],
    ['only whitespace-ish content plus a group', ['council consensus 1 → A', '   x   ']],
  ]

  for (const [name, trace] of cases) {
    it(`accounts for every non-blank line: ${name}`, () => {
      const p = parseReasoning(trace)
      const expected = nonBlank(trace)
      expect(p.totalLines).toBe(trace.length)
      expect(accountedLines(p)).toBe(expected.length)
      expect(accountedContent(p)).toEqual(expected)
    })
  }

  // ---- The two tests below document a REAL DEFECT (see summary). ----
  // A "Mr. Market mood:" line is consumed by the RE_MOOD branch, which pushes
  // it to `current?.raw` — an optional call. When no group is open yet
  // (`current === null`) the line is swallowed: it lands in neither `preamble`
  // nor any `group.raw`, breaking the module's documented promise that no line
  // is ever silently dropped. The same happens to every mood variant after the
  // first if it arrives pre-group.
  it('BUG: silently drops a mood line that precedes the first group', () => {
    const trace = [MOOD, 'council consensus 60.2 → ACCUMULATE', "AAPL: 30.7% vol → 'mid' tier (x)"]
    const p = parseReasoning(trace)
    expect(p.marketMood).toBe(MOOD)
    expect(accountedContent(p)).toEqual(nonBlank(trace))
  })

  it('BUG: silently drops a second, different pre-group mood line', () => {
    const a = 'Mr. Market mood: greedy (buying not favorable)'
    const b = 'Mr. Market mood: fearful (buying favorable)'
    const p = parseReasoning([a, b, 'council consensus 1 → A'])
    // marketMood keeps only the first, so the second must survive elsewhere.
    expect(p.marketMood).toBe(a)
    expect(accountedContent(p)).toContain(b)
  })

  it('drops lines that are blank after trimming (and nothing else)', () => {
    const trace = ['', '   ', '\t\n', 'council consensus 1 → A', '  ']
    const p = parseReasoning(trace)
    expect(p.totalLines).toBe(5)
    expect(accountedContent(p)).toEqual(['council consensus 1 → A'])
  })
})

describe('parseReasoning — degenerate inputs', () => {
  it('handles an empty array', () => {
    expect(parseReasoning([])).toEqual({
      marketMood: null,
      groups: [],
      preamble: [],
      totalLines: 0,
    })
  })

  it('puts everything in preamble when there is no consensus line', () => {
    const trace = [
      'agent booting',
      'concentration check: whatever ✓',
      'council rule cited: §6',
      'entry BLOCKED by portfolio gates',
      'new entry NOT permitted (council says HOLD)',
    ]
    const p = parseReasoning(trace)
    expect(p.groups).toEqual([])
    expect(p.preamble).toEqual(trace)
    expect(p.marketMood).toBeNull()
  })

  it('keeps raw lines verbatim including original leading/trailing whitespace', () => {
    const raw = '   council consensus 60.2 → ACCUMULATE   '
    const p = parseReasoning([raw])
    expect(p.groups[0].raw).toEqual([raw])
    expect(p.groups[0].consensusScore).toBeCloseTo(60.2)
  })

  it('puts unparseable in-group lines in other, verbatim', () => {
    const odd = 'the agent said something nobody anticipated'
    const p = parseReasoning(['council consensus 60.2 → ACCUMULATE', odd])
    expect(p.groups[0].other).toEqual([odd])
    expect(p.groups[0].raw).toEqual(['council consensus 60.2 → ACCUMULATE', odd])
  })

  it('does not throw on adversarial input', () => {
    const nasty = [
      'council consensus → ACCUMULATE',
      'council consensus NaN → ',
      'MSFT 48.4% vol high tier',
      "MSFT: 48.4% vol → 'high' tier",
      'TSLA OVERRIDE ACTIVE',
      'check: ',
      ' check :x',
      '::::',
      '→→→',
      'x'.repeat(100000),
      '🙂'.repeat(5000),
      'council consensus 1e309 → HUGE',
      'council consensus -5 → NEGATIVE',
    ]
    expect(() => parseReasoning(nasty)).not.toThrow()
    const p = parseReasoning(nasty)
    expect(accountedContent(p)).toEqual(nonBlank(nasty))
  })

  it('tolerates a non-numeric consensus score without throwing', () => {
    // 'council consensus ..' cannot match [\d.]+ with a digit; '.' alone can.
    const p = parseReasoning(['council consensus . → ACCUMULATE'])
    expect(() => p).not.toThrow()
    // Number('.') is NaN — recorded, not crashed.
    if (p.groups.length > 0) {
      expect(p.groups[0].recommendation).toBe('ACCUMULATE')
    }
  })
})

describe('gateStatus classification (via gates)', () => {
  function statusOf(detailLine: string) {
    const p = parseReasoning(['council consensus 1 → A', detailLine])
    return p.groups[0].gates[0]?.status
  }

  it("is 'blocked' for ✗", () => {
    expect(statusOf('concentration check: 26% of portfolio ✗')).toBe('blocked')
  })

  it("is 'blocked' for BLOCKED in any case", () => {
    expect(statusOf('concentration check: over limit BLOCKED')).toBe('blocked')
    expect(statusOf('concentration check: over limit blocked')).toBe('blocked')
  })

  it("is 'blocked' when both ✓ and ✗ appear (fail closed)", () => {
    expect(statusOf('concentration check: ✓ then ✗ BLOCKED')).toBe('blocked')
  })

  it("is 'pass' for ✓ alone", () => {
    expect(statusOf('cash reserve check: $89,123 remaining ✓')).toBe('pass')
  })

  it("is 'unknown' with neither marker", () => {
    expect(statusOf('cash reserve check: $89,123 remaining')).toBe('unknown')
  })

  it('strips the "check" suffix and "council" prefix from labels', () => {
    const p = parseReasoning([
      'council consensus 1 → A',
      'council sector-cap check (a vs b): 1% ✓',
      'concentration check: 2% ✓',
    ])
    expect(p.groups[0].gates.map((g) => g.label)).toEqual(['sector-cap', 'concentration'])
  })

  it("falls back to label 'check' when nothing is left after stripping", () => {
    const p = parseReasoning(['council consensus 1 → A', 'check: 1% ✓'])
    expect(p.groups[0].gates[0].label).toBe('check')
  })
})

describe('groupIsBlocked', () => {
  const base: ReasoningGroup = {
    symbol: 'X',
    consensusScore: 50,
    recommendation: 'HOLD',
    tier: 'low',
    volPct: 10,
    policy: null,
    gates: [],
    override: null,
    citation: null,
    verdict: null,
    other: [],
    raw: [],
  }

  it('is false with no verdict and no gates', () => {
    expect(groupIsBlocked(base)).toBe(false)
  })

  it('is true when the verdict blocks', () => {
    expect(groupIsBlocked({ ...base, verdict: { kind: 'blocked', text: 'x' } })).toBe(true)
  })

  it('is true when any gate blocks even if the verdict permits', () => {
    expect(
      groupIsBlocked({
        ...base,
        verdict: { kind: 'permitted', text: 'entry permitted' },
        gates: [
          { label: 'a', detail: 'ok ✓', status: 'pass' },
          { label: 'b', detail: 'bad ✗', status: 'blocked' },
        ],
      }),
    ).toBe(true)
  })

  it('is false when all gates pass and the verdict holds', () => {
    expect(
      groupIsBlocked({
        ...base,
        verdict: { kind: 'hold', text: 'new entry NOT permitted' },
        gates: [{ label: 'a', detail: 'ok ✓', status: 'pass' }],
      }),
    ).toBe(false)
  })

  it('is false when gate status is unknown', () => {
    expect(
      groupIsBlocked({ ...base, gates: [{ label: 'a', detail: 'meh', status: 'unknown' }] }),
    ).toBe(false)
  })
})

describe('verdict kinds', () => {
  function kindOf(line: string) {
    return parseReasoning(['council consensus 1 → A', line]).groups[0].verdict?.kind
  }

  it('recognises blocked / hold / permitted', () => {
    expect(kindOf('entry BLOCKED by portfolio gates → MONITOR only')).toBe('blocked')
    expect(kindOf('new entry NOT permitted (council says HOLD)')).toBe('hold')
    expect(kindOf('entry permitted')).toBe('permitted')
    expect(kindOf('new entry allowed')).toBe('permitted')
  })

  it('leaves verdict null when no verdict line appears', () => {
    expect(kindOf('concentration check: 1% ✓')).toBeUndefined()
  })

  it('keeps the last verdict when several appear', () => {
    const p = parseReasoning([
      'council consensus 1 → A',
      'entry permitted',
      'entry BLOCKED by portfolio gates',
    ])
    expect(p.groups[0].verdict?.kind).toBe('blocked')
  })
})
