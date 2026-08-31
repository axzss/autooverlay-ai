'use client'

import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import {
  api,
  riskBlockFrom,
  type AgentRunResponse,
  type OrderIntent,
  type RiskDecision,
} from '../../lib/api'
import { intentToTradeRequest, mintClientOrderId } from '../../lib/orderMapping'

/** Outcome of one approval attempt, in the shape the UI actually needs to render. */
export interface ApprovalOutcome {
  status?: string
  error?: string
  /**
   * The gate's verdict. Present on a 409 block AND on an accepted order, since
   * `POST /api/trade` returns `risk` either way. Rendering `hard_failures` as a
   * list is the whole reason the backend answers 409 with structure instead of
   * a string.
   */
  risk?: RiskDecision | null
  /** True when the idempotency store recognised the payload and did NOT resubmit. */
  duplicate?: boolean
  /** True when the backend validated but did not submit (no Alpaca credentials). */
  simulated?: boolean
}

/**
 * Shares one agent run across the dashboard so the control card and the
 * reasoning panel show the SAME run instead of each firing its own request.
 */
interface AgentRunContextValue {
  run: AgentRunResponse | null
  running: boolean
  error: string | null
  /** Fires POST /api/agent/run. Recommendation-only — never submits an order. */
  runAgent: () => Promise<void>
  /** Submit one approved order intent to the backend trade endpoint. */
  approveOrder: (intent: OrderIntent) => Promise<void>
  /** Track last approval result/error for UI feedback. */
  lastApproval: ApprovalOutcome | null
  /** True while an approval is in flight — callers must disable their submit control. */
  approving: boolean
}

const AgentRunContext = createContext<AgentRunContextValue>({
  run: null,
  running: false,
  error: null,
  runAgent: async () => {},
  approveOrder: async () => {},
  lastApproval: null,
  approving: false,
})

export function useAgentRun() {
  return useContext(AgentRunContext)
}

export default function AgentRunProvider({ children }: { children: ReactNode }) {
  const [run, setRun] = useState<AgentRunResponse | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastApproval, setLastApproval] = useState<ApprovalOutcome | null>(null)
  const [approving, setApproving] = useState(false)

  const runAgent = useCallback(async () => {
    setRunning(true)
    setError(null)
    setLastApproval(null)
    try {
      const res = await api.runAgent()
      setRun(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Agent run failed')
      setRun(null)
    } finally {
      setRunning(false)
    }
  }, [])

  const approveOrder = useCallback(async (intent: OrderIntent) => {
    setLastApproval(null)
    // The request is built by lib/orderMapping, which refuses to substitute the
    // underlying ticker when no option contract is resolved. This used to send
    // `symbol: intent.symbol`, so approving a covered call submitted a sell of
    // the underlying SHARES — the wrong instrument, and the collateral the
    // position depended on.
    //
    // Provenance travels with the order: trade.py records run_id and
    // directive_ref on every intent, and without them a ledger row cannot be
    // traced back to the run that proposed it.
    const { request, blocked } = intentToTradeRequest(intent, {
      runId: run?.run_id,
      directiveRef: intent.option_symbol ?? intent.symbol,
      clientOrderId: mintClientOrderId(),
    })
    if (!request) {
      setLastApproval({ error: blocked ?? 'Order intent could not be mapped to a trade request.' })
      return
    }
    setApproving(true)
    try {
      const res = await api.placeTrade(request)
      setLastApproval({
        status: res.status || (res.submitted === false ? 'validated' : 'submitted'),
        risk: res.risk ?? null,
        // A recognised duplicate is a SUCCESS of the idempotency store, not a
        // silent no-op: the operator must see that nothing was resubmitted.
        duplicate: res.duplicate === true,
        simulated: res.submitted === false,
      })
    } catch (err) {
      // A 409 is the risk gate refusing, and it carries every check it decided
      // on. Surfacing it as a truncated JSON string wasted the one explanation
      // the operator actually needs.
      const risk = riskBlockFrom(err)
      setLastApproval({
        error: risk
          ? 'Blocked by the pre-trade risk gate'
          : err instanceof Error
            ? err.message
            : 'Approval failed',
        risk,
      })
    } finally {
      setApproving(false)
    }
  }, [run?.run_id])

  return (
    <AgentRunContext.Provider
      value={{ run, running, error, runAgent, approveOrder, lastApproval, approving }}
    >
      {children}
    </AgentRunContext.Provider>
  )
}
