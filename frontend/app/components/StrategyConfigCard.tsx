'use client'

import { useCallback, useEffect, useState } from 'react'
import { Save, SlidersHorizontal, AlertCircle, CheckCircle2 } from 'lucide-react'

type StrategyParams = {
  take_profit_pct: number
  stop_loss_mult: number
  roll_delta: number
  roll_min_dte: number
  delta_min: number
  delta_max: number
  dte_min: number
  dte_max: number
  max_concentration_pct: number
  min_cash_reserve_pct: number
}

const DEFAULTS: StrategyParams = {
  take_profit_pct: 0.6,
  stop_loss_mult: 2.0,
  roll_delta: 0.4,
  roll_min_dte: 7,
  delta_min: 0.15,
  delta_max: 0.35,
  dte_min: 7,
  dte_max: 45,
  max_concentration_pct: 25.0,
  min_cash_reserve_pct: 10.0,
}

export default function StrategyConfigCard() {
  const [params, setParams] = useState<StrategyParams>(DEFAULTS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch('/api/strategy/config')
        if (!res.ok) throw new Error(`GET failed (${res.status})`)
        const data = await res.json()
        if (!cancelled) setParams({ ...DEFAULTS, ...data.config })
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load config')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  const set = (key: keyof StrategyParams) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const num = parseFloat(e.target.value)
      setSaved(false)
      setParams((p) => ({ ...p, [key]: Number.isNaN(num) ? p[key] : num }))
    }

  const handleSave = useCallback(async () => {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const res = await fetch('/api/strategy/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      })
      if (!res.ok) {
        let detail = `Save failed (${res.status})`
        try {
          const body = await res.json()
          if (body?.detail?.errors) detail = body.detail.errors.join('; ')
        } catch { /* keep generic message */ }
        throw new Error(detail)
      }
      const data = await res.json()
      setParams({ ...DEFAULTS, ...data.config })
      setSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save config')
    } finally {
      setSaving(false)
    }
  }, [params])

  const pct = (v: number) => `${Math.round(v * 100)}%`

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-3">
        <div className="flex h-8 w-8 items-center justify-center rounded border border-[#1e293b] bg-[#0f172a]">
          <SlidersHorizontal className="h-4 w-4 text-[#22c55e]" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">Overlay Strategy Parameters</h3>
          <p className="text-xs text-[#94a3b8]">Exit rules, entry bands and portfolio guards for the overlay engine.</p>
        </div>
      </div>

      {loading ? (
        <p className="text-xs text-[#94a3b8]">Loading current configuration…</p>
      ) : (
        <div className="space-y-4">
          <Slider label="TAKE PROFIT (% PREMIUM CAPTURED)" value={params.take_profit_pct} min={0.1} max={1} step={0.05}
            display={pct(params.take_profit_pct)} onChange={set('take_profit_pct')} />
          <Slider label="STOP LOSS (× INITIAL PREMIUM)" value={params.stop_loss_mult} min={1} max={5} step={0.25}
            display={`${params.stop_loss_mult.toFixed(2)}x`} onChange={set('stop_loss_mult')} />
          <Slider label={`ROLL DELTA TRIGGER (> ${params.roll_delta.toFixed(2)})`} value={params.roll_delta} min={0.1} max={0.8} step={0.05}
            display={params.roll_delta.toFixed(2)} onChange={set('roll_delta')} />
          <div className="grid grid-cols-2 gap-3">
            <NumberField label="DELTA BAND MIN" value={params.delta_min} min={0.01} max={1} step={0.01} onChange={set('delta_min')} />
            <NumberField label="DELTA BAND MAX" value={params.delta_max} min={0.01} max={1} step={0.01} onChange={set('delta_max')} />
            <NumberField label="DTE BAND MIN" value={params.dte_min} min={1} max={180} step={1} onChange={set('dte_min')} />
            <NumberField label="DTE BAND MAX" value={params.dte_max} min={1} max={365} step={1} onChange={set('dte_max')} />
          </div>
          <Slider label="MAX CONCENTRATION PER TICKER" value={params.max_concentration_pct} min={5} max={100} step={5}
            display={`${params.max_concentration_pct}%`} onChange={set('max_concentration_pct')} />
          <Slider label="MIN CASH RESERVE" value={params.min_cash_reserve_pct} min={0} max={50} step={1}
            display={`${params.min_cash_reserve_pct}%`} onChange={set('min_cash_reserve_pct')} />

          {error && (
            <div className="flex items-center gap-2 rounded border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {saved && !error && (
            <div className="flex items-center gap-2 rounded border border-green-900/60 bg-green-950/40 px-3 py-2 text-xs text-green-300">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>Strategy configuration saved.</span>
            </div>
          )}

          <button
            onClick={handleSave}
            disabled={saving}
            className="btn-primary inline-flex items-center gap-2 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {saving ? 'Saving…' : 'Save Strategy Parameters'}
          </button>
        </div>
      )}
    </div>
  )
}

function Slider(props: {
  label: string; value: number; min: number; max: number; step: number;
  display: string; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <label className="text-xs text-[#94a3b8]">{props.label}</label>
        <span className="font-mono text-xs text-[#22c55e]">{props.display}</span>
      </div>
      <input type="range" className="w-full accent-[#22c55e]" min={props.min}
        max={props.max} step={props.step} value={props.value} onChange={props.onChange} />
    </div>
  )
}

function NumberField(props: {
  label: string; value: number; min: number; max: number; step: number;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
}) {
  return (
    <div>
      <label className="block text-xs text-[#94a3b8] mb-1">{props.label}</label>
      <input type="number" className="input w-full font-mono" min={props.min}
        max={props.max} step={props.step} value={props.value} onChange={props.onChange} />
    </div>
  )
}
