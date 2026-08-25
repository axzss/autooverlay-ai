'use client'

import { Bot, Play, Zap } from 'lucide-react'

const logs = [
  { time: '10:00:00', tag: 'SYSTEM', text: 'Trigger received. Waking up AutoOverlay Agent...', color: 'text-[#fbbf24]' },
  { time: '10:00:02', tag: 'MCP', text: 'Connecting to Alpaca Server... Connected.', color: 'text-[#2dd4bf]' },
  { time: '10:00:03', tag: 'MCP', text: 'Fetching portfolio data... 100 shares of SPY found.', color: 'text-[#2dd4bf]' },
  { time: '10:00:05', tag: 'API', text: 'Requesting SPY option chain data...', color: 'text-[#94a3b8]' },
  { time: '10:00:08', tag: 'LLM', text: 'Analyzing volatility... IV Rank is at 45%. Market trend is slightly bullish.', color: 'text-[#22c55e]' },
  { time: '10:00:12', tag: 'LLM', text: 'Decision Engine: Selecting Strike $565 (2.7% OTM) to avoid early assignment.', color: 'text-[#22c55e]' },
  { time: '10:00:14', tag: 'MCP', text: 'Executing SELL to OPEN 1 Contract SPY 565C 09/04.', color: 'text-[#2dd4bf]' },
  { time: '10:00:16', tag: 'SYSTEM', text: 'Order Confirmed. Yield harvested: $120.00. Returning to sleep.', color: 'text-[#fbbf24]' },
]

export default function AgentTerminal() {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[#1e293b]">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-white">AI Agent Terminal</h1>
          <span className="inline-flex items-center rounded border border-[#334155] bg-[#0f172a] px-2 py-0.5 text-xs text-[#94a3b8]">
            Agent: Sleeping (Awaiting Schedule)
          </span>
        </div>
        <button className="inline-flex items-center gap-2 rounded border border-[#22c55e]/50 bg-[#0f172a] px-3 py-1.5 text-xs font-medium text-[#22c55e] hover:bg-[#22c55e]/10 transition-colors">
          <Zap className="h-4 w-4" />
          FORCE RUN AGENT
        </button>
      </div>
      <div className="flex-1 bg-[#060e20] m-4 rounded border border-[#1e293b] overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2 border-b border-[#1e293b]">
          <div className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-full bg-[#ef4444]" />
            <span className="h-3 w-3 rounded-full bg-[#fbbf24]" />
            <span className="h-3 w-3 rounded-full bg-[#22c55e]" />
          </div>
          <span className="text-[10px] text-[#64748b] uppercase tracking-wider">AUTO_OVERLAY_KERNEL_V2.4</span>
        </div>
        <div className="p-4 font-mono text-sm leading-relaxed">
          <div className="space-y-1">
            {logs.map((log, idx) => (
              <div key={idx} className="flex gap-2">
                <span className="text-[#64748b]">[{log.time}]</span>
                <span className={log.color}>[{log.tag}]</span>
                <span className="text-[#e2e8f0]">{log.text}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-2 text-[#22c55e]">
            <span>{'>'}</span>
            <span className="inline-block h-4 w-2.5 bg-[#22c55e]" />
          </div>
        </div>
      </div>
    </div>
  )
}
