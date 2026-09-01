'use client'

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import {
  api,
  riskBlockFrom,
  type AgentRunResponse,
  type OrderIntent,
  type RiskDecision,
} from '../../lib/api'
import { intentToTradeRequest, mintClientOrderId } from '../../lib/orderMapping'

export interface ApprovalOutcome {
  status?: string
  error?: string
  risk?: RiskDecision | null
  duplicate?: boolean
  simulated?: boolean
}

interface AgentRunContextValue {
  run: AgentRunResponse | null
  running: boolean
  error: string | null
  runAgent: () => Promise<void>
  approveOrder: (intent: OrderIntent) => Promise<void>
  lastApproval: ApprovalOutcome | null
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

  const restoreRun = useCallback(async (runId: string) => {
    try {
      const res = await api.getAgentRun(runId)
      if (res) setRun(res)
    } catch {
      // ignore restore failures; UI stays empty until next manual run
    }
  }, [])

  useEffect(() => {
    const saved = sessionStorage.getItem('last_agent_run_id')
    if (saved) restoreRun(saved)
  }, [restoreRun])

  const persistRun = useCallback((runId: string) => {
    sessionStorage.setItem('last_agent_run_id', runId)
  }, [])

  const runAgent = useCallback(async () => {
    setRunning(true)
    setError(null)
    setLastApproval(null)
    try {
      const res = await api.runAgent()
      setRun(res)
      persistRun(res.run_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Agent run failed')
      setRun(null)
    } finally {
      setRunning(false)
    }
  }, [persistRun])

  const approveOrder = useCallback(async (intent: OrderIntent) => {
    setLastApproval(null)
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
        duplicate: res.duplicate === true,
        simulated: res.submitted === false,
      })
    } catch (err) {
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
