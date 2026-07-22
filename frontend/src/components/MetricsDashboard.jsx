import { useEffect, useState } from 'react'
import { PieChart, Pie, Cell, BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid, LabelList } from 'recharts'
import { fetchStats, fetchCompare } from '../api'
import AnimatedCounter from './AnimatedCounter'

const TIER_ORDER = ['cheap', 'mid', 'frontier', 'web']

const TIER_LABELS = { cheap: 'Cheap', mid: 'Mid', frontier: 'Frontier', web: 'Web' }

export default function MetricsDashboard({ isDark, backendOnline = true }) {
  const [stats, setStats] = useState(null)
  const [compareData, setCompareData] = useState(null)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)

  function loadStats() {
    return fetchStats().then((s) => { setStats(s); setLastUpdated(new Date()) }).catch((e) => setError(e.message))
  }

  function loadCompare() {
    return fetchCompare().then(setCompareData).catch(() => {})
  }

  async function handleRefresh() {
    setRefreshing(true)
    await loadStats()
    await loadCompare()
    setRefreshing(false)
  }

  useEffect(() => {
    if (!backendOnline) return
    loadStats()
    loadCompare()
    const id = setInterval(loadStats, 30_000)
    return () => clearInterval(id)
  }, [backendOnline])

  const p = isDark
    ? { line: '#232D3B', muted: '#7C8B9A', panel: '#121821', surface: '#0B0F14', signal: '#FF9F1C', cool: '#3FB8AF', danger: '#E85D5D', primary: '#E6EDF3', cheap: '#3FB8AF', mid: '#FF9F1C', frontier: '#E85D5D', web: '#818CF8' }
    : { line: '#E2E2DD', muted: '#6B7078', panel: '#F6F6F4', surface: '#FFFFFF', signal: '#C2570C', cool: '#0F766E', danger: '#B91C1C', primary: '#16181C', cheap: '#0F766E', mid: '#C2570C', frontier: '#B91C1C', web: '#4F46E5' }

  const tooltipStyle = { background: p.panel, border: `1px solid ${p.line}`, borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 11 }
  const tickStyle = { fill: p.muted, fontSize: 11, fontFamily: 'JetBrains Mono' }

  if (error) {
    return (
      <section id="metrics" className="max-w-6xl mx-auto px-6 py-16">
        <p className="font-mono text-xs text-danger">Couldn't load metrics — {error}</p>
      </section>
    )
  }

  if (!stats) {
    return (
      <section id="metrics" className="max-w-6xl mx-auto px-6 py-20">
        <div className="h-7 w-48 bg-line rounded animate-pulse mb-2" />
        <div className="h-4 w-72 bg-line rounded animate-pulse mb-12" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-12">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-24 bg-line rounded-lg animate-pulse" />)}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="h-64 bg-line rounded-lg animate-pulse" />
          <div className="h-64 bg-line rounded-lg animate-pulse" />
        </div>
      </section>
    )
  }

  const savedPct = stats.total_hypothetical_cost > 0
    ? Math.round((1 - stats.total_actual_cost / stats.total_hypothetical_cost) * 100)
    : 0

  const successRate = stats.total_requests > 0
    ? Math.round(((stats.total_requests - (stats.fallback_count || 0)) / stats.total_requests) * 100)
    : 100

  const avgLatency = stats.avg_latency_by_tier && Object.keys(stats.avg_latency_by_tier).length > 0
    ? Math.round(Object.values(stats.avg_latency_by_tier).reduce((a, b) => a + b, 0) / Object.values(stats.avg_latency_by_tier).length)
    : 0

  const pieData = TIER_ORDER
    .filter((t) => stats.tier_counts?.[t])
    .map((t) => ({ name: TIER_LABELS[t] || t, value: stats.tier_counts[t], color: p[t] }))

  const costCompare = [
    { name: 'You paid', value: stats.total_actual_cost, fill: p.cool },
    { name: 'Without routing', value: stats.total_hypothetical_cost, fill: p.frontier },
  ]

  const timeSeriesData = (stats.daily_costs || []).map((d) => ({
    date: d.date.slice(5),
    'You paid': d.actual_cost,
    'Without routing': d.hypothetical_cost,
  }))
  const uniqueDays = new Set((stats.daily_costs || []).map((d) => d.date)).size

  return (
    <section id="metrics" className="max-w-6xl mx-auto px-6 py-20">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div>
          <p className="font-mono text-[10px] text-signal tracking-wide uppercase mb-1">Live metrics</p>
          <h2 className="font-display text-2xl font-semibold text-primary">Real savings, real data</h2>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="font-mono text-[10px] text-muted hidden sm:block">
              updated {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="font-mono text-[10px] px-3 py-1.5 rounded border border-line text-muted hover:text-primary hover:border-signal/50 transition disabled:opacity-50"
          >
            {refreshing ? '...' : '↻ refresh'}
          </button>
        </div>
      </div>
      <p className="text-sm text-muted mb-10">Every number comes from actual production traffic routed through this system.</p>

      {/* Hero stat — savings + quality */}
      <div className="bg-panel border border-line rounded-xl p-6 md:p-8 mb-6">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-2">Total saved vs. all-frontier</p>
            <div className="flex items-baseline gap-3">
              <span className="font-display text-4xl md:text-5xl font-bold text-signal">
                <AnimatedCounter value={Math.round((stats.total_savings_usd || 0) * 100)} prefix="$" suffix="" duration={800} />
                <span className="text-2xl md:text-3xl">.{String((stats.total_savings_usd || 0).toFixed(2)).split('.')[1] || '00'}</span>
              </span>
              {savedPct > 0 && (
                <span className="font-mono text-sm font-semibold text-signal bg-signal/10 border border-signal/20 rounded-full px-3 py-1">
                  {savedPct}% saved
                </span>
              )}
              {stats.average_quality != null && stats.average_quality > 0 && (
                <span className="font-mono text-sm font-semibold text-cool bg-cool/10 border border-cool/20 rounded-full px-3 py-1">
                  {(stats.average_quality * 100).toFixed(0)}% quality
                </span>
              )}
            </div>
            <p className="font-mono text-xs text-muted mt-2">
              ${stats.total_actual_cost?.toFixed(4)} actual vs. ${stats.total_hypothetical_cost?.toFixed(4)} if all frontier
            </p>
          </div>
          <div className="flex gap-6 md:gap-8">
            <div className="text-right">
              <p className="font-mono text-[10px] text-muted uppercase">Cache saved</p>
              <p className="font-display text-lg font-semibold text-cool">${(stats.cache_savings_usd || 0).toFixed(4)}</p>
            </div>
            <div className="text-right">
              <p className="font-mono text-[10px] text-muted uppercase">Routing saved</p>
              <p className="font-display text-lg font-semibold text-signal">${(stats.routing_savings_usd || 0).toFixed(4)}</p>
            </div>
          </div>
        </div>
      </div>

      {/* stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-10">
        <StatBox
          label="Requests routed"
          value={stats.total_requests}
          icon={<PathIcon />}
          color="primary"
        />
        <StatBox
          label="Cache hit rate"
          value={`${Math.round((stats.cache_hit_rate || 0) * 100)}%`}
          icon={<CacheIcon />}
          color="cool"
          sub={stats.total_requests > 0 ? `${Math.round((stats.cache_hit_rate || 0) * stats.total_requests)} served instantly` : null}
        />
        <StatBox
          label="Avg latency"
          value={`${avgLatency}ms`}
          icon={<SpeedIcon />}
          color="signal"
          sub="across all tiers"
        />
        <StatBox
          label="Success rate"
          value={`${successRate}%`}
          icon={<ShieldIcon />}
          color={successRate >= 99 ? 'cool' : successRate >= 95 ? 'signal' : 'danger'}
          sub={`${stats.fallback_count || 0} fallbacks triggered`}
        />
        <StatBox
          label="Quality retained"
          value={stats.average_quality != null && stats.average_quality > 0 ? `${(stats.average_quality * 100).toFixed(0)}%` : '—'}
          icon={<StarIcon />}
          color={stats.average_quality >= 0.97 ? 'cool' : stats.average_quality >= 0.90 ? 'signal' : 'danger'}
          sub={stats.average_quality > 0 ? 'avg across all requests' : 'will appear after first request'}
        />
      </div>

      {/* Charts row 1: Cost comparison + Tier pie */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
        {/* Cost comparison */}
        <div className="bg-panel border border-line rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-mono text-[10px] text-muted uppercase tracking-wide">Cost comparison</h3>
            {savedPct > 0 && <span className="font-mono text-xs font-semibold text-signal">{savedPct}% saved</span>}
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={costCompare} margin={{ top: 25, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={p.line} vertical={false} />
              <XAxis dataKey="name" tick={tickStyle} axisLine={{ stroke: p.line }} />
              <YAxis tick={tickStyle} axisLine={{ stroke: p.line }} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v) => [`$${v.toFixed(4)}`, 'cost']} />
              <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={48}>
                {costCompare.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                <LabelList dataKey="value" position="top" formatter={(v) => `$${v.toFixed(4)}`} style={{ ...tickStyle, fontSize: 10 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Tier distribution */}
        <div className="bg-panel border border-line rounded-xl p-5">
          <h3 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-4">Tier distribution</h3>
          {pieData.length > 0 ? (
            <div className="flex items-center gap-6">
              <ResponsiveContainer width="50%" height={180}>
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={72} paddingAngle={3} strokeWidth={0}>
                    {pieData.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-3">
                {pieData.map((d) => (
                  <div key={d.name} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ background: d.color }} />
                      <span className="font-mono text-xs text-muted">{d.name}</span>
                    </div>
                    <span className="font-mono text-xs text-primary font-medium">{d.value}</span>
                  </div>
                ))}
                <div className="pt-2 border-t border-line">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] text-muted">Total</span>
                    <span className="font-mono text-xs text-primary font-semibold">{stats.total_requests}</span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-[180px] flex items-center justify-center">
              <p className="font-mono text-xs text-muted">No data yet</p>
            </div>
          )}
        </div>
      </div>

      {/* Charts row 2: Cost over time + Latency */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
        {/* Cost over time */}
        <div className="bg-panel border border-line rounded-xl p-5">
          <h3 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-4">Cost over time</h3>
          {uniqueDays >= 2 ? (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={timeSeriesData}>
                <CartesianGrid stroke={p.line} vertical={false} />
                <XAxis dataKey="date" tick={tickStyle} axisLine={{ stroke: p.line }} />
                <YAxis tick={tickStyle} axisLine={{ stroke: p.line }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ fontFamily: 'JetBrains Mono', fontSize: 10, paddingTop: 4 }} />
                <Line type="monotone" dataKey="You paid" stroke={p.cool} strokeWidth={2} dot={{ r: 3, fill: p.cool }} />
                <Line type="monotone" dataKey="Without routing" stroke={p.frontier} strokeWidth={2} strokeDasharray="4 3" dot={{ r: 3, fill: p.frontier }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[200px] border border-dashed border-line rounded-lg flex items-center justify-center">
              <p className="font-mono text-xs text-muted">Trend fills in over multiple days</p>
            </div>
          )}
        </div>

        {/* Latency by tier */}
        <div className="bg-panel border border-line rounded-xl p-5">
          <h3 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-4">Avg latency by tier</h3>
          {Object.keys(stats.avg_latency_by_tier || {}).length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart
                data={TIER_ORDER.filter((t) => stats.avg_latency_by_tier?.[t] != null).map((t) => ({ name: TIER_LABELS[t] || t, value: Math.round(stats.avg_latency_by_tier[t]), color: p[t] }))}
                layout="vertical" margin={{ left: 0 }}
              >
                <CartesianGrid stroke={p.line} horizontal={false} />
                <XAxis type="number" tick={tickStyle} axisLine={{ stroke: p.line }} />
                <YAxis type="category" dataKey="name" tick={tickStyle} axisLine={{ stroke: p.line }} width={65} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => [`${v}ms`, 'latency']} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={20}>
                  {TIER_ORDER.filter((t) => stats.avg_latency_by_tier?.[t] != null).map((t) => (
                    <Cell key={t} fill={p[t]} />
                  ))}
                  <LabelList dataKey="value" position="right" formatter={(v) => `${v}ms`} style={{ ...tickStyle, fontSize: 10 }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[200px] flex items-center justify-center">
              <p className="font-mono text-xs text-muted">No latency data yet</p>
            </div>
          )}
        </div>
      </div>

      {/* Multi-router comparison */}
      {compareData && compareData.modes && compareData.modes.length > 0 && (
        <div className="bg-panel border border-line rounded-xl p-5 mb-6">
          <h3 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-3">Mode comparison</h3>
          <p className="font-mono text-[10px] text-muted mb-4">
            What {compareData.analyzed_requests} recent requests would cost with different thresholds:
          </p>
          <div className="grid grid-cols-3 gap-3">
            {compareData.modes.map((m) => {
              const isEconomy = m.mode === 'economy'
              const isBalanced = m.mode === 'balanced'
              const isQuality = m.mode === 'quality'
              const borderClass = isEconomy ? 'border-cool/20' : isBalanced ? 'border-signal/20' : 'border-danger/20'
              const textClass = isEconomy ? 'text-cool' : isBalanced ? 'text-signal' : 'text-danger'
              return (
                <div key={m.mode} className={`bg-surface border ${borderClass} rounded-lg p-3`}>
                  <div className={`font-mono text-[10px] font-semibold ${textClass} capitalize mb-1`}>{m.mode}</div>
                  <div className="font-display text-lg font-semibold text-primary">${m.estimated_cost.toFixed(4)}</div>
                  <div className="font-mono text-[10px] text-muted mt-1">Save {m.savings_pct}% vs frontier</div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Trust badges */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <TrustBadge
          icon={<ShieldCheckIcon />}
          title="Zero dropped requests"
          desc="Auto-fallback steps in before any tier fails."
          color="cool"
        />
        <TrustBadge
          icon={<CacheIcon />}
          title={`${Math.round((stats.cache_hit_rate || 0) * 100)}% cache hit rate`}
          desc="Near-duplicate queries served instantly, zero cost."
          color="signal"
        />
        <TrustBadge
          icon={<BoltIcon />}
          title={`${stats.total_requests} requests routed`}
          desc="Every query scored, routed, and logged in real time."
          color="primary"
        />
      </div>
    </section>
  )
}

function StatBox({ label, value, icon, color, sub }) {
  const colors = {
    primary: 'text-primary border-primary/20',
    cool: 'text-cool border-cool/20',
    signal: 'text-signal border-signal/20',
    danger: 'text-danger border-danger/20',
  }
  return (
    <div className="bg-panel border border-line rounded-xl p-4 hover:border-signal/20 transition-colors">
      <div className="flex items-center gap-2 mb-3">
        <div className={`w-7 h-7 rounded-md bg-surface border border-line flex items-center justify-center ${colors[color]?.split(' ')[0] || 'text-muted'}`}>
          {icon}
        </div>
        <p className="font-mono text-[10px] text-muted uppercase tracking-wide">{label}</p>
      </div>
      <p className={`font-display text-2xl font-bold ${colors[color]?.split(' ')[0] || 'text-primary'}`}>{value}</p>
      {sub && <p className="font-mono text-[10px] text-muted mt-1">{sub}</p>}
    </div>
  )
}

function TrustBadge({ icon, title, desc, color }) {
  const borderColor = color === 'cool' ? 'border-cool/20' : color === 'signal' ? 'border-signal/20' : 'border-line'
  const iconColor = color === 'cool' ? 'text-cool' : color === 'signal' ? 'text-signal' : 'text-primary'
  return (
    <div className={`border ${borderColor} rounded-xl p-4 bg-panel`}>
      <div className={`w-8 h-8 rounded-lg bg-surface border border-line flex items-center justify-center mb-3 ${iconColor}`}>
        {icon}
      </div>
      <p className="text-sm font-semibold text-primary mb-0.5">{title}</p>
      <p className="font-mono text-[11px] text-muted leading-relaxed">{desc}</p>
    </div>
  )
}

function PathIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}

function CacheIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  )
}

function SpeedIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  )
}

function ShieldIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

function ShieldCheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <polyline points="9 12 11 14 15 10" />
    </svg>
  )
}

function BoltIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  )
}

function StarIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  )
}
