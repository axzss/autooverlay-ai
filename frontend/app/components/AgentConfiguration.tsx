'use client'

import { useState } from 'react'
import { Save, Cpu, Sliders, Clock } from 'lucide-react'

export default function AgentConfiguration() {
  const [config, setConfig] = useState({
    targetAsset: 'SPY (S&P 500)',
    moneyness: 'Conservative (3-5% OTM)',
    dte: '30 Days',
    cron: '0 10 * * 1-5',
  })

  const handleSave = () => {
    alert('Configuration saved successfully.')
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 pt-6 pb-2">
        <h1 className="text-lg font-semibold text-[#22c55e]">Agent Configuration</h1>
        <p className="text-sm text-[#94a3b8]">Adjust the parameters for the autonomous overlay engine.</p>
      </div>
      <div className="px-6 pb-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="card">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex h-8 w-8 items-center justify-center rounded border border-[#1e293b] bg-[#0f172a]">
                <Cpu className="h-4 w-4 text-[#22c55e]" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Target Asset</h3>
                <p className="text-xs text-[#94a3b8]">Select the underlying instrument for overlay generation.</p>
              </div>
            </div>
            <label className="block text-xs text-[#94a3b8] mb-1">PRIMARY ETF TARGET</label>
            <select
              className="input w-full"
              value={config.targetAsset}
              onChange={(e) => setConfig({ ...config, targetAsset: e.target.value })}
            >
              <option>SPY (S&P 500)</option>
              <option>QQQ (Nasdaq-100)</option>
              <option>IWM (Russell 2000)</option>
            </select>
          </div>

          <div className="card">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex h-8 w-8 items-center justify-center rounded border border-[#1e293b] bg-[#0f172a]">
                <Sliders className="h-4 w-4 text-[#22c55e]" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Strategy Parameters</h3>
                <p className="text-xs text-[#94a3b8]">Define risk tolerance and operational horizons.</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-[#94a3b8] mb-1">TARGET MONEYNESS (RISK TOLERANCE)</label>
                <select
                  className="input w-full"
                  value={config.moneyness}
                  onChange={(e) => setConfig({ ...config, moneyness: e.target.value })}
                >
                  <option>Conservative (3-5% OTM)</option>
                  <option>Moderate (1-3% OTM)</option>
                  <option>Aggressive (0-1% OTM)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-[#94a3b8] mb-1">DAYS TO EXPIRATION (DTE)</label>
                <select
                  className="input w-full"
                  value={config.dte}
                  onChange={(e) => setConfig({ ...config, dte: e.target.value })}
                >
                  <option>7 Days</option>
                  <option>14 Days</option>
                  <option>30 Days</option>
                  <option>45 Days</option>
                </select>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex h-8 w-8 items-center justify-center rounded border border-[#1e293b] bg-[#0f172a]">
                <Clock className="h-4 w-4 text-[#22c55e]" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Automation Schedule</h3>
                <p className="text-xs text-[#94a3b8]">Configure cron execution for autonomous logic.</p>
              </div>
            </div>
            <label className="block text-xs text-[#94a3b8] mb-1">CRON SCHEDULE</label>
            <input
              type="text"
              className="input w-full font-mono"
              value={config.cron}
              onChange={(e) => setConfig({ ...config, cron: e.target.value })}
            />
            <div className="mt-2 flex items-center gap-2 text-xs text-[#94a3b8]">
              <span>Runs Monday to Friday at 10:00 AM</span>
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <button onClick={handleSave} className="btn-primary inline-flex items-center gap-2">
            <Save className="h-4 w-4" />
            Save Configuration
          </button>
        </div>
      </div>
    </div>
  )
}
