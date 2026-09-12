import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchStats } from '../api'
import AnimatedCounter from './AnimatedCounter'

function Money({ value, size = 'lg' }) {
  const [int, dec] = (value ?? 0).toFixed(4).split('.')
  const cls = size === 'sm' ? 'text-xl' : 'text-2xl'
  return (
    <span className={`font-display font-bold num-tabular ${cls}`}>
      <AnimatedCounter value={Math.round(Number(int))} prefix="$" />
      .{dec}
    </span>
  )
}

function Cell({ label, node, sub, color = 'text-primary' }) {
  return (
    <div className="border border-line rounded-xl bg-base px-4 py-3.5 hover:border-signal/40 hover:shadow-card-hover hover:-translate-y-px transition-all shadow-card min-w-0 group">
      <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-1 truncate group-hover:text-primary transition-colors">{label}</p>
      <div className={`font-display font-bold text-2xl num-tabular ${color}`}>{node}</div>
      {sub && <p className="font-mono text-[10px] text-muted mt-0.5 truncate">{sub}</p>}
    </div>
  )
}

const Skel = () => <div className="w-16 h-6 bg-line rounded animate-pulse" />

export default function LiveStatsStrip() {
  const [stats, setStats] = useState(null)

  function load() {
    fetchStats().then(setStats).catch(() => setStats(null))
  }
  useEffect(() => {
    load()
    const id = setInterval(load, 15_000)
    return () => clearInterval(id)
  }, [])

  const savedPct = stats && stats.total_hypothetical_cost > 0
    ? Math.round((1 - stats.total_actual_cost / stats.total_hypothetical_cost) * 100)
    : 0

  const avgValues = Object.values(stats?.avg_latency_by_tier || {})
  const avgMs = avgValues.length > 0 ? Math.round(avgValues.reduce((a, b) => a + b, 0) / avgValues.length) : null

  const cacheRate = stats ? Math.round((stats.cache_hit_rate || 0) * 100) : null

  return (
    <section className="border-b border-line bg-panel">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between gap-4 mb-5">
          <div className="flex items-center gap-2.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-signal opacity-60" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-signal" />
            </span>
            <p className="font-mono text-xs text-primary tracking-wide uppercase">Live across all routed traffic</p>
          </div>
          <Link
            to="/metrics"
            className="font-mono text-[11px] text-muted hover:text-signal hover:gap-1.5 transition-all flex items-center gap-1 whitespace-nowrap"
          >
            View full metrics
            <svg width="10" height="10" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <line x1="2" y1="7" x2="12" y2="7" />
              <polyline points="7,2 12,7 7,12" />
            </svg>
          </Link>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3.5">
          <Cell
            label="Requests routed"
            node={stats == null ? <Skel /> : <AnimatedCounter value={stats.total_requests || 0} />}
            sub={stats ? `${Object.keys(stats.tier_counts || {}).length} tiers live` : null}
          />
          <Cell
            label="Total saved"
            node={stats == null ? <Skel /> : <Money value={stats.total_savings_usd || 0} />}
            sub={savedPct > 0 ? `${savedPct}% vs frontier` : 'vs all-frontier'}
            color="text-signal"
          />
          <Cell
            label="Cache hit rate"
            node={stats == null ? <Skel /> : cacheRate != null ? <AnimatedCounter value={cacheRate} suffix="%" /> : '—'}
            sub={stats && stats.total_requests > 0 ? `${Math.round((stats.cache_hit_rate || 0) * stats.total_requests)} served instantly` : null}
            color="text-cool"
          />
          <Cell
            label="Avg latency"
            node={stats == null ? <Skel /> : avgMs != null ? `${avgMs}ms` : '—'}
            sub={stats ? 'across all tiers' : null}
          />
          <Cell
            label="Judge quality"
            node={stats == null ? <Skel /> : stats.judged_quality_avg != null && stats.judged_quality_avg > 0 ? `${(stats.judged_quality_avg * 100).toFixed(0)}%` : '—'}
            sub={stats?.quality_judged_count > 0 ? `${stats.quality_judged_count} responses scored` : null}
            color="text-cool"
          />
        </div>
      </div>
    </section>
  )
}