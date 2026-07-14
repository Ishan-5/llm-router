import { useEffect, useState } from 'react'
import { PieChart, Pie, Cell, BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid, LabelList } from 'recharts'
import { fetchStats } from '../api'

const TIER_ORDER = ['cheap', 'mid', 'frontier']

export default function MetricsDashboard({ isDark, backendOnline = true }) {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)

  function loadStats() {
    return fetchStats().then((s) => { setStats(s); setLastUpdated(new Date()) }).catch((e) => setError(e.message))
  }

  async function handleRefresh() {
    setRefreshing(true)
    await loadStats()
    setRefreshing(false)
  }

  useEffect(() => {
    if (!backendOnline) return
    loadStats()
    const id = setInterval(loadStats, 30_000)
    return () => clearInterval(id)
  }, [backendOnline])

  const palette = isDark
    ? { line: '#232D3B', muted: '#7C8B9A', panel: '#121821', signal: '#FF9F1C', cheap: '#3FB8AF', mid: '#FF9F1C', frontier: '#E85D5D' }
    : { line: '#E2E2DD', muted: '#6B7078', panel: '#FFFFFF', signal: '#C2570C', cheap: '#0F766E', mid: '#C2570C', frontier: '#B91C1C' }

  if (error) {
    return (
      <section id="metrics" className="max-w-6xl mx-auto px-6 py-16 border-t border-line">
        <p className="font-mono text-xs text-danger">
          Couldn't load /stats — make sure the backend is running. ({error})
        </p>
      </section>
    )
  }

  if (!stats) {
    return (
      <section id="metrics" className="max-w-6xl mx-auto px-6 py-16 border-t border-line">
        <p className="font-mono text-xs text-muted">Loading metrics…</p>
      </section>
    )
  }

  const tierCostData = TIER_ORDER
    .filter((t) => stats.tier_costs?.[t] != null)
    .map((t) => ({ name: t, value: stats.tier_costs[t] }))

  const pieData = TIER_ORDER
    .filter((t) => stats.tier_counts?.[t])
    .map((t) => ({ name: t, value: stats.tier_counts[t] }))

  const savedPct = stats.total_hypothetical_cost > 0
    ? Math.round((1 - stats.total_actual_cost / stats.total_hypothetical_cost) * 100)
    : 0

  const costData = [
    { name: 'Actual', value: stats.total_actual_cost },
    { name: 'If all → frontier', value: stats.total_hypothetical_cost },
  ]

  const latencyData = TIER_ORDER
    .filter((t) => stats.avg_latency_by_tier?.[t] != null)
    .map((t) => ({ name: t, value: Math.round(stats.avg_latency_by_tier[t]) }))

  const uniqueDays = new Set((stats.daily_costs || []).map((d) => d.date)).size
  const timeSeriesData = (stats.daily_costs || []).map((d) => ({
    date: d.date,
    Actual: d.actual_cost,
    'If all → frontier': d.hypothetical_cost,
  }))

  return (
    <section id="metrics" className="max-w-6xl mx-auto px-6 py-20 border-t border-line">
      <div className="flex items-center justify-between mb-2">
        <h2 className="font-display text-2xl font-semibold">Real usage, real savings</h2>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="font-mono text-[10px] text-muted">
              updated {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="font-mono text-[10px] px-3 py-1.5 rounded border border-line text-muted hover:text-primary hover:border-signal/50 transition disabled:opacity-50"
          >
            {refreshing ? 'refreshing…' : '↻ refresh'}
          </button>
        </div>
      <p className="text-sm text-muted mb-12">Computed from every request this router has actually logged.</p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-16">
        <Stat label="Total requests" value={stats.total_requests} />
        <Stat label="Cache hit rate" value={`${Math.round((stats.cache_hit_rate || 0) * 100)}%`} tone="cool" />
        <Stat label="Fallback events" value={stats.fallback_count} tone={stats.fallback_count > 0 ? 'danger' : undefined} />
        <Stat label="Cost saved" value={`${savedPct}%`} tone="signal" big />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-12 mb-16">
        <div>
          <h3 className="font-mono text-xs text-muted uppercase tracking-wide mb-4">Tier distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={3}>
                {pieData.map((entry) => (
                  <Cell key={entry.name} fill={palette[entry.name] || palette.muted} stroke="none" />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: palette.panel, border: `1px solid ${palette.line}`, borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 12 }} />
              <Legend
                iconType="circle"
                iconSize={8}
                wrapperStyle={{ fontFamily: 'JetBrains Mono', fontSize: 11, paddingTop: 8 }}
                formatter={(value) => <span style={{ color: palette.muted }}>{value}</span>}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div>
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-mono text-xs text-muted uppercase tracking-wide">Actual vs. hypothetical cost</h3>
            {savedPct > 0 && (
              <span className="font-mono text-xs font-semibold text-signal">−{savedPct}%</span>
            )}
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={costData} margin={{ top: 20, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={palette.line} vertical={false} />
              <XAxis dataKey="name" tick={{ fill: palette.muted, fontSize: 11, fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: palette.line }} />
              <YAxis tick={{ fill: palette.muted, fontSize: 11, fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: palette.line }} />
              <Tooltip contentStyle={{ background: palette.panel, border: `1px solid ${palette.line}`, borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 12 }} />
              <Bar dataKey="value" fill={palette.signal} radius={[4, 4, 0, 0]}>
                <LabelList
                  dataKey="value"
                  position="top"
                  formatter={(v) => `$${v.toFixed(4)}`}
                  style={{ fontFamily: 'JetBrains Mono', fontSize: 11, fill: palette.muted }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-12 mb-16">
        <div>
          <h3 className="font-mono text-xs text-muted uppercase tracking-wide mb-4">Cost by tier</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={tierCostData} margin={{ top: 20, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={palette.line} vertical={false} />
              <XAxis dataKey="name" tick={{ fill: palette.muted, fontSize: 11, fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: palette.line }} />
              <YAxis tick={{ fill: palette.muted, fontSize: 11, fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: palette.line }} />
              <Tooltip
                contentStyle={{ background: palette.panel, border: `1px solid ${palette.line}`, borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 12 }}
                formatter={(v) => [`$${v.toFixed(6)}`, 'cost']}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {tierCostData.map((entry) => (
                  <Cell key={entry.name} fill={palette[entry.name] || palette.muted} />
                ))}
                <LabelList
                  dataKey="value"
                  position="top"
                  formatter={(v) => `$${v.toFixed(4)}`}
                  style={{ fontFamily: 'JetBrains Mono', fontSize: 11, fill: palette.muted }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="mb-16">
        <h3 className="font-mono text-xs text-muted uppercase tracking-wide mb-4">Cost over time</h3>
        {uniqueDays >= 2 ? (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={timeSeriesData}>
              <CartesianGrid stroke={palette.line} vertical={false} />
              <XAxis dataKey="date" tick={{ fill: palette.muted, fontSize: 11, fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: palette.line }} />
              <YAxis tick={{ fill: palette.muted, fontSize: 11, fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: palette.line }} />
              <Tooltip contentStyle={{ background: palette.panel, border: `1px solid ${palette.line}`, borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 12 }} />
              <Legend wrapperStyle={{ fontFamily: 'JetBrains Mono', fontSize: 11 }} />
              <Line type="monotone" dataKey="Actual" stroke={palette.cheap} strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="If all → frontier" stroke={palette.frontier} strokeWidth={2} strokeDasharray="4 3" dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="border border-dashed border-line rounded-lg py-10 text-center">
            <p className="font-mono text-xs text-muted">
              Only one day of data so far — this trend fills in as the router gets used across multiple days.
            </p>
          </div>
        )}
      </div>

      <div>
        <h3 className="font-mono text-xs text-muted uppercase tracking-wide mb-4">Avg latency by tier</h3>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={latencyData} layout="vertical" margin={{ left: 10 }}>
            <CartesianGrid stroke={palette.line} horizontal={false} />
            <XAxis type="number" tick={{ fill: palette.muted, fontSize: 11, fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: palette.line }} unit="ms" />
            <YAxis type="category" dataKey="name" tick={{ fill: palette.muted, fontSize: 11, fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: palette.line }} width={70} />
            <Tooltip contentStyle={{ background: palette.panel, border: `1px solid ${palette.line}`, borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 12 }} />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {latencyData.map((entry) => (
                <Cell key={entry.name} fill={palette[entry.name] || palette.muted} />
              ))}
              <LabelList dataKey="value" position="right" formatter={(v) => `${v}ms`} style={{ fontFamily: 'JetBrains Mono', fontSize: 11, fill: palette.muted }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}

function Stat({ label, value, tone, big }) {
  const color = tone === 'cool' ? 'text-cool' : tone === 'signal' ? 'text-signal' : tone === 'danger' ? 'text-danger' : 'text-primary'
  const border = tone === 'cool' ? 'border-cool' : tone === 'signal' ? 'border-signal' : tone === 'danger' ? 'border-danger' : 'border-line'
  return (
    <div className={`border-l-2 ${border} pl-4`}>
      <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-1.5">{label}</p>
      <p className={`font-display font-semibold ${big ? 'text-4xl' : 'text-3xl'} ${color}`}>{value}</p>
    </div>
  )
}
