'use client'

import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { api, type AgentRunResponse, type OrderIntent } from '../../lib/api'

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
    try {
      const res = await api.placeTrade({
        symbol: intent.symbol,
        qty: intent.contracts,
        side: intent.side === 'sell' ? 'sell' : 'buy',
        type: intent.type === 'limit' ? 'limit' : 'market',
        time_in_force: intent.time_in_force || 'day',
        limit_price: intent.limit_price ?? null,
      })
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
