'use client'

import { Terminal as TerminalIcon, Loader2 } from 'lucide-react'
import { useAgentRun } from './AgentRunProvider'

/**
 * Shows the reasoning trace from the most recent agent run.
 *
 * This component previously rendered a hardcoded log that claimed an order had
 * been executed and a $120 premium harvested. None of that ever happened, and
 * displaying it made a demo look like a live trade. It now renders only lines
 * the backend actually produced, or an empty state.
 */
export default function ThoughtProcess() {
  const { run, running, error } = useAgentRun()

  const trace = run?.reasoning_trace ?? []

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e293b] flex items-center gap-2">
        <TerminalIcon className="h-4 w-4 text-[#22c55e]" />
        <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
          Agent Reasoning
        </h3>
        {running && <Loader2 className="ml-auto h-3.5 w-3.5 animate-spin text-[#64748b]" />}
        {!running && run?.completed_at && (
          <span className="ml-auto text-[10px] text-[#64748b]">
            {new Date(run.completed_at).toLocaleTimeString()}
          </span>
        )}
      </div>

      <div className="bg-[#060e20] p-4 font-mono text-xs leading-relaxed">
        {error && <p className="text-[#f87171]">{error}</p>}

        {!error && trace.length === 0 && (
          <p className="text-[#64748b]">
            {running
              ? 'Running analysis…'
              : 'No reasoning trace yet. Run the agent to see every check it performs.'}
          </p>
        )}

        {trace.length > 0 && (
          <div className="space-y-1">
            {trace.map((line, idx) => (
              <div key={idx} className="flex gap-2">
                <span className="shrink-0 select-none text-[#334155] tabular-nums">
                  {String(idx + 1).padStart(2, '0')}
                </span>
                <span className="text-[#94a3b8] break-words">{line}</span>
              </div>
            ))}
          </div>
        )}

        {trace.length > 0 && (
          <p className="mt-3 border-t border-[#1e293b] pt-2 text-[10px] text-[#64748b]">
            {trace.length} step{trace.length === 1 ? '' : 's'} from run{' '}
            <span className="font-mono">{run?.run_id?.slice(0, 12)}</span>
          </p>
        )}
      </div>
    </div>
  )
}
