'use client'

import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { api, type AgentRunResponse, type OrderIntent } from '../../lib/api'
import { intentToTradeRequest } from '../../lib/orderMapping'

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
  lastApproval: { status?: string; error?: string } | null
}

const AgentRunContext = createContext<AgentRunContextValue>({
  run: null,
  running: false,
  error: null,
  runAgent: async () => {},
  approveOrder: async () => {},
  lastApproval: null,
})

export function useAgentRun() {
  return useContext(AgentRunContext)
}

export default function AgentRunProvider({ children }: { children: ReactNode }) {
  const [run, setRun] = useState<AgentRunResponse | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastApproval, setLastApproval] = useState<{ status?: string; error?: string } | null>(null)

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
    const { request, blocked } = intentToTradeRequest(intent)
    if (!request) {
      setLastApproval({ error: blocked ?? 'Order intent could not be mapped to a trade request.' })
      return
    }
    try {
      const res = await api.placeTrade(request)
      setLastApproval({ status: res.status || 'submitted' })
    } catch (err) {
      setLastApproval({ error: err instanceof Error ? err.message : 'Approval failed' })
    }
  }, [])

  return (
    <AgentRunContext.Provider value={{ run, running, error, runAgent, approveOrder, lastApproval }}>
      {children}
    </AgentRunContext.Provider>
  )
}
