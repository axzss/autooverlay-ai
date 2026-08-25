'use client'

import { Bot, Play } from 'lucide-react'

export default function AgentControl() {
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e293b] flex items-center gap-2">
        <Bot className="h-4 w-4 text-[#22c55e]" />
        <h3 className="text-sm font-semibold text-white uppercase tracking-wider">AI Agent Control</h3>
      </div>
      <div className="p-4 space-y-4">
        <p className="text-sm text-[#94a3b8]">Manual override to trigger execution logic analysis immediately.</p>
        <button className="btn-primary w-full flex items-center justify-center gap-2">
          <Play className="h-4 w-4" />
          Run Agent Now
        </button>
      </div>
    </div>
  )
}
