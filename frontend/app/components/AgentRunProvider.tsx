'use client'

import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { api, type AgentRunResponse } from '../../lib/api'

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
}

const AgentRunContext = createContext<AgentRunContextValue>({
  run: null,
  running: false,
  error: null,
  runAgent: async () => {},
})

export function useAgentRun() {
  return useContext(AgentRunContext)
}

export default function AgentRunProvider({ children }: { children: ReactNode }) {
  const [run, setRun] = useState<AgentRunResponse | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const runAgent = useCallback(async () => {
    setRunning(true)
    setError(null)
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

  return (
    <AgentRunContext.Provider value={{ run, running, error, runAgent }}>
      {children}
    </AgentRunContext.Provider>
  )
}
