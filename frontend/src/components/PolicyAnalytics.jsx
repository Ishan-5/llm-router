import { useState, useEffect } from 'react'
import {
  BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, LabelList,
} from 'recharts'
import { fetchPolicyAnalytics } from '../api'
import { MODEL_LIST } from '../models'

const TIER_COLORS = { cheap: '#3FB8AF', mid: '#FF9F1C', frontier: '#E85D5D' }
const TIER_TEXT = { cheap: 'text-cool', mid: 'text-signal', frontier: 'text-danger' }
const TIER_ORDER = ['cheap', 'mid', 'frontier']
const ACCENT_HEX = { cool: '#3FB8AF', signal: '#FF9F1C', danger: '#E85D5D' }

function money(v) {
  if (v == null) return '—'
  return `$${v.toFixed(4)}`
}

function TrafficBar({ traffic }) {
  return (
    <div>
      <div className="h-2.5 rounded-full bg-panel2 border border-line overflow-hidden flex">
        {TIER_ORDER.filter((t) => (traffic[t] || 0) > 0).map((t) => (
          <div
            key={t}
            title={`${t} ${(traffic[t] * 100).toFixed(1)}%`}
            style={{ width: `${traffic[t] * 100}%`, background: TIER_COLORS[t] }}
          />
        ))}
      </div>
      <div className="flex gap-4 mt-2 flex-wrap">
        {TIER_ORDER.map((t) => (
          <span key={t} className="font-mono text-[10px] text-muted flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-sm" style={{ background: TIER_COLORS[t] }} />
            <span className={TIER_TEXT[t]}>{t}</span>
            {(traffic[t] || 0) > 0 ? `${(traffic[t] * 100).toFixed(1)}%` : '—'}
          </span>
        ))}
      </div>
    </div>
  )
}

function ModelCard({ model, isDark }) {
  const m = MODEL_LIST.find((x) => x.id === model.id) || MODEL_LIST[0]
  const hex = ACCENT_HEX[m.accent]
  const p = isDark
    ? { line: '#232D3B', muted: '#7C8B9A', panel: '#121821', surface: '#0B0F14' }
    : { line: '#E2E2DD', muted: '#6B7078', panel: '#F6F6F4', surface: '#FFFFFF' }
  const tickStyle = { fill: p.muted, fontSize: 10, fontFamily: 'JetBrains Mono' }

  if (!model.available) {
    return (
      <div className="bg-panel border border-line rounded-xl p-5">
        <h3 className="font-display text-lg font-semibold text-muted mb-2">{m.name}</h3>
        <p className="font-mono text-xs text-muted">Policy unavailable — artifact not loaded on this deployment.</p>
      </div>
    )
  }

  const ev = model.eval || {}
  const escape = ev.frontier_escape_pct
  const recall = ev.recall_frontier_pct

  return (
    <div className="bg-panel border rounded-xl p-5 flex flex-col" style={{ borderColor: hex }}>
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-display text-lg font-semibold text-primary">{m.name}</h3>
        <span className="font-mono text-[10px] px-2 py-0.5 rounded-md border" style={{ color: hex, borderColor: hex }}>
          {model.support_mode}
        </span>
      </div>
      <p className="font-mono text-[10px] text-muted mb-4">
        {model.tiers.join(' → ')}
        {'  ·  '}
        {model.cuts ? `cut ≤${model.cuts.cheap} / ≥${model.cuts.frontier}` : 'adjustable'}
      </p>

      <div className="bg-surface border border-line rounded-lg p-3 mb-3">
        <p className="font-mono text-[9px] text-muted uppercase tracking-wide mb-2">Traffic mix (your logs)</p>
        <TrafficBar traffic={model.traffic || {}} />
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="bg-surface border border-line rounded-lg px-3 py-2">
          <p className="font-mono text-[9px] text-muted uppercase tracking-wide">Avg cost / req</p>
          <p className="font-mono text-sm font-semibold text-primary">{money(model.cost_per_request)}</p>
        </div>
        <div className="bg-surface border border-line rounded-lg px-3 py-2">
          <p className="font-mono text-[9px] text-muted uppercase tracking-wide">Saved vs frontier</p>
          <p className="font-mono text-sm font-semibold text-cool">{model.savings_pct}%</p>
        </div>
      </div>

      <div className="bg-surface border border-line rounded-lg p-3 mb-3">
        <p className="font-mono text-[9px] text-muted uppercase tracking-wide mb-1">
          Offline eval · {escape != null ? `${escape}% frontier escape` : `${recall}% frontier recall`}
        </p>
        <p className="font-mono text-[10px] text-muted leading-relaxed">
          MAE {ev.mae != null ? ev.mae.toFixed(3) : '—'}
          {'  ·  '}
          Spearman {ev.spearman != null ? ev.spearman.toFixed(3) : '—'}
        </p>
        {ev.source && <p className="font-mono text-[9px] text-muted/70 mt-1.5 leading-relaxed">{ev.source}</p>}
      </div>

      <div className="mt-auto h-[100px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={[model]} margin={{ top: 18, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={p.line} vertical={false} />
            <XAxis dataKey="label" tick={tickStyle} axisLine={{ stroke: p.line }} tickLine={false} />
            <YAxis hide />
            <Tooltip
              contentStyle={{ background: p.panel, border: `1px solid ${p.line}`, borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 11 }}
              formatter={(v) => [money(v), 'cost']}
            />
            <Bar dataKey="cost_usd" name="policy cost" fill={hex} radius={[4, 4, 0, 0]} barSize={38} label={false}>
              <LabelList
                dataKey="cost_usd"
                position="top"
                formatter={(v) => money(v)}
                style={{ ...tickStyle, fill: p.muted, fontSize: 9 }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export default function PolicyAnalytics({ isDark }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [updated, setUpdated] = useState(null)

  useEffect(() => {
    let cancelled = false
    function load() {
      fetchPolicyAnalytics()
        .then((d) => {
          if (cancelled) return
          setData(d)
          setError(null)
          setUpdated(new Date())
        })
        .catch((e) => { if (!cancelled) setError(e.message) })
        .finally(() => { if (!cancelled) setLoading(false) })
    }
    load()
    const id = setInterval(load, 60_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const models = (data && data.models) || []
  const available = models.filter((m) => m.available)

  // Same scale for all three bars so the cost gap is readable, not implied.
  const chartMax = available.reduce((max, m) => Math.max(max, m.cost_usd), 0)
  const chartData = available.map((m) => {
    const meta = MODEL_LIST.find((x) => x.id === m.id) || {}
    return { label: meta.name || m.id, cost_usd: m.cost_usd, id: m.id }
  })

  const p = isDark
    ? { line: '#232D3B', muted: '#7C8B9A', panel: '#121821', surface: '#0B0F14' }
    : { line: '#E2E2DD', muted: '#6B7078', panel: '#F6F6F4', surface: '#FFFFFF' }
  const tickStyle = { fill: p.muted, fontSize: 10, fontFamily: 'JetBrains Mono' }

  return (
    <div className="max-w-6xl mx-auto px-6 py-20">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
        <div>
          <p className="font-mono text-xs text-signal tracking-wide uppercase mb-3">Analytics</p>
          <h1 className="font-display text-3xl font-semibold mb-2">ema · lisa · kate, side by side</h1>
          <p className="text-muted text-sm max-w-xl">
            What your real traffic looks like under each difficulty model — traffic mix, cost per request,
            and what each policy would let slip to a cheaper tier.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {updated && (
            <span className="font-mono text-[10px] text-muted">
              updated {updated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button
            onClick={() => { setLoading(true); fetchPolicyAnalytics().then(setData).catch((e) => setError(e.message)).finally(() => setLoading(false)) }}
            className="font-mono text-[10px] px-3 py-1.5 rounded border border-line text-muted hover:text-primary hover:border-signal/50 transition"
          >
            ↻ refresh
          </button>
        </div>
      </div>

      {error && <p className="font-mono text-xs text-danger mb-6">{error}</p>}

      {loading && !data && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-80 bg-line/40 rounded-xl animate-pulse" />
          ))}
        </div>
      )}

      {data && data.analyzed_requests === 0 && (
        <div className="border border-dashed border-line rounded-xl p-10 text-center">
          <p className="text-sm text-primary mb-2">No routed requests yet</p>
          <p className="font-mono text-[10px] text-muted">
            {data.message || 'Send a few queries through the router and this fills in automatically.'}
          </p>
        </div>
      )}

      {available.length > 0 && (
        <>
          <p className="font-mono text-[10px] text-muted mb-4 leading-relaxed">
            {data.caveat}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            {models.map((m) => (
              <ModelCard key={m.id} model={m} isDark={isDark} />
            ))}
          </div>

          <div className="bg-panel border border-line rounded-xl p-5">
            <h3 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-1">
              Total cost over your {data.analyzed_requests} requests
            </h3>
            <p className="font-mono text-[10px] text-muted mb-4">
              Same requests, three policies. Frontier baseline = {money(data.frontier_baseline_cost_usd)}.
            </p>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} margin={{ top: 22, right: 0, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={p.line} vertical={false} />
                <XAxis dataKey="label" tick={tickStyle} axisLine={{ stroke: p.line }} />
                <YAxis
                  tick={tickStyle}
                  axisLine={{ stroke: p.line }}
                  tickFormatter={(v) => `$${v.toFixed(3)}`}
                  domain={[0, chartMax * 1.15]}
                />
                <Tooltip
                  contentStyle={{ background: p.panel, border: `1px solid ${p.line}`, borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 11 }}
                  formatter={(v, name) => [money(v), name]}
                />
                <Bar dataKey="cost_usd" name="policy cost" radius={[4, 4, 0, 0]} barSize={60} fill={isDark ? '#3FB8AF' : '#0F766E'}>
                  {chartData.map((entry) => (
                    <Cell key={entry.id} fill={ACCENT_HEX[MODEL_LIST.find((x) => x.id === entry.id)?.accent || 'cool']} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <p className="font-mono text-[10px] text-muted/70 mt-6 leading-relaxed max-w-3xl">
            Offline evals are measured on each policy's own holdout — emma on general Claude-gold rows,
            lisa and kate on 17,600 support tickets — so compare them as directional signals, not a
            single leaderboard. Frontier escape is the share of genuinely-hard queries a policy would
            have downgraded; lower is safer, higher is cheaper.
          </p>
        </>
      )}
    </div>
  )
}