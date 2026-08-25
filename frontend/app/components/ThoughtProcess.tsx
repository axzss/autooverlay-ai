'use client'

export const logs = [
  { time: '10:00:00', tag: 'SYSTEM', text: 'Trigger received. Waking up AutoOverlay Agent...', color: 'text-[#fbbf24]' },
  { time: '10:00:02', tag: 'MCP', text: 'Connecting to Alpaca Server... Connected.', color: 'text-[#2dd4bf]' },
  { time: '10:00:03', tag: 'MCP', text: 'Fetching portfolio data... 100 shares of SPY found.', color: 'text-[#2dd4bf]' },
  { time: '10:00:05', tag: 'API', text: 'Requesting SPY option chain data...', color: 'text-[#94a3b8]' },
  { time: '10:00:08', tag: 'LLM', text: 'Analyzing volatility... IV Rank is at 45%. Market trend is slightly bullish.', color: 'text-[#22c55e]' },
  { time: '10:00:12', tag: 'LLM', text: 'Decision Engine: Selecting Strike $565 (2.7% OTM) to avoid early assignment.', color: 'text-[#22c55e]' },
  { time: '10:00:14', tag: 'MCP', text: 'Executing SELL to OPEN 1 Contract SPY 565C 09/04.', color: 'text-[#2dd4bf]' },
  { time: '10:00:16', tag: 'SYSTEM', text: 'Order Confirmed. Yield harvested: $120.00. Returning to sleep.', color: 'text-[#fbbf24]' },
]

export default function ThoughtProcess() {
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e293b] flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white uppercase tracking-wider">AI Thought Process</h3>
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ef4444]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#fbbf24]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#22c55e]" />
        </div>
      </div>
      <div className="bg-[#060e20] p-4 font-mono text-sm leading-relaxed">
        <div className="flex items-center justify-end mb-2">
          <span className="text-[10px] text-[#64748b] uppercase tracking-wider">AutoOverlay Kernel v2.4</span>
        </div>
        <div className="space-y-1">
          {logs.map((log, idx) => (
            <div key={idx} className="flex gap-2">
              <span className="text-[#64748b]">{log.time}</span>
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
  )
}
