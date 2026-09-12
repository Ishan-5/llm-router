import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchStats } from '../api'
import AnimatedCounter from './AnimatedCounter'

const TIER_STYLES = {
  cheap: 'text-cool bg-cool/10 border-cool/30',
  mid: 'text-signal bg-signal/10 border-signal/30',
  frontier: 'text-danger bg-danger/10 border-danger/30',
}

function Stat({ label, value, color = 'text-primary', sub }) {
  return (
    <div className="bg-base border border-line rounded-xl p-4 min-w-0 shadow-card hover:shadow-card-hover hover:-translate-y-px transition-all">
      <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-1 truncate">{label}</p>
      <div className={`font-display text-2xl font-bold num-tabular ${color}`}>{value}</div>
      {sub && <p className="font-mono text-[10px] text-muted mt-0.5 truncate">{sub}</p>}
    </div>
  )
}

export default function MetricsBand() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchStats().then(setStats).catch((e) => setError(e.message))
  }, [])

  const savedPct = stats && stats.total_hypothetical_cost > 0
    ? Math.round((1 - stats.total_actual_cost / stats.total_hypothetical_cost) * 100)
    : 0

  const avgValues = Object.values(stats?.avg_latency_by_tier || {})
  const avgMs = avgValues.length > 0 ? Math.round(avgValues.reduce((a, b) => a + b, 0) / avgValues.length) : null

  const quality = stats?.judged_quality_avg != null && stats.judged_quality_avg > 0
    ? `${(stats.judged_quality_avg * 100).toFixed(0)}%`
    : null

  const labeling = stats?.labeling

  return (
    <section id="metrics" className="border-t border-line bg-panel">
      <div className="max-w-6xl mx-auto px-6 py-20">
        <div className="flex items-end justify-between gap-4 mb-2">
          <div>
            <p className="font-mono text-xs text-signal tracking-wide uppercase mb-1 flex items-center gap-2">
              <span className="w-1 h-4 rounded-full bg-signal" />
              Production metrics
            </p>
            <h2 className="font-display text-2xl md:text-3xl font-semibold text-primary">Real savings, real data</h2>
          </div>
          <Link
            to="/metrics"
            className="font-mono text-[11px] text-muted hover:text-signal transition-colors flex items-center gap-1 whitespace-nowrap shrink-0"
          >
            Full dashboard
            <svg width="10" height="10" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <line x1="2" y1="7" x2="12" y2="7" />
              <polyline points="7,2 12,7 7,12" />
            </svg>
          </Link>
        </div>
        <p className="text-sm text-muted mb-8">Every number comes from actual production traffic routed through this system.</p>

        {error ? (
          <p className="font-mono text-xs text-danger">Couldn't load metrics — {error}</p>
        ) : !stats ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => <div key={i} className="h-24 bg-line rounded-xl animate-pulse" />)}
          </div>
        ) : (
          <>
            {/* Hero stat */}
            <div className="relative bg-base border border-line rounded-2xl p-6 md:p-8 mb-6 shadow-card overflow-hidden">
              <div aria-hidden className="pointer-events-none absolute -top-24 -right-16 w-72 h-72 rounded-full opacity-15 dark:opacity-20"
                style={{ background: 'radial-gradient(circle, var(--color-signal) 0%, transparent 65%)' }} />
              <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-5 relative">
                <div>
                  <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-2">Total saved vs. all-frontier</p>
                  <div className="flex items-baseline gap-3">
                    <span className="font-display text-4xl md:text-5xl font-bold text-signal num-tabular">
                      <AnimatedCounter value={Math.round((stats.total_savings_usd || 0) * 100)} prefix="$" duration={800} />
                      <span className="text-2xl md:text-3xl">.{String((stats.total_savings_usd || 0).toFixed(2)).split('.')[1] || '00'}</span>
                    </span>
                    {savedPct > 0 && (
                      <span className="font-mono text-sm font-semibold text-signal bg-signal/10 border border-signal/20 rounded-full px-3 py-1">
                        {savedPct}% saved
                      </span>
                    )}
                    {quality && (
                      <span className="font-mono text-sm font-semibold text-cool bg-cool/10 border border-cool/20 rounded-full px-3 py-1">
                        {quality} quality
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

            {/* Stat overview */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <Stat label="Requests routed" value={<AnimatedCounter value={stats.total_requests || 0} />} />
              <Stat label="Cache hit rate" value={`${Math.round((stats.cache_hit_rate || 0) * 100)}%`} color="text-cool"
                sub={stats.total_requests > 0 ? `${Math.round((stats.cache_hit_rate || 0) * stats.total_requests)} served instantly` : null} />
              <Stat label="Avg latency" value={avgMs != null ? `${avgMs}ms` : '—'} color="text-signal" sub="across all tiers" />
              <Stat label="Judge quality" value={quality || '—'} color="text-cool"
                sub={stats.quality_judged_count > 0 ? `${stats.quality_judged_count} responses scored` : 'will appear after first response'} />
            </div>

            {/* Labeling agreement — differentiator */}
            {labeling && labeling.labeled_count > 0 && (
              <div className="bg-base border border-line rounded-xl px-5 py-4 mb-6 shadow-card">
                <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                  <p className="font-mono text-[10px] text-muted uppercase tracking-wide shrink-0">
                    Router vs LLM-judged difficulty
                  </p>
                  <div className="flex-1 h-2 rounded-full bg-surface border border-line overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-700"
                      style={{ width: `${Math.min(100, labeling.agreement_pct ?? 0)}%`, background: 'var(--color-cool)' }} />
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="font-display text-2xl font-bold text-cool num-tabular">{labeling.agreement_pct ?? '—'}%</span>
                    <span className="font-mono text-[10px] text-muted">
                      match on {labeling.labeled_count} queries
                      {labeling.over_routed > 0 && ` · ${labeling.over_routed} over-routed`}
                      {labeling.under_routed > 0 && ` · ${labeling.under_routed} under-routed`}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Tier split */}
            {Object.keys(stats.tier_counts || {}).length > 0 && (
              <div className="bg-base border border-line rounded-xl px-5 py-4 mb-8 shadow-card">
                <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-3">Where queries went</p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {Object.entries(stats.tier_counts).map(([tier, count]) => (
                    <div key={tier} className="flex items-center gap-3">
                      <span className={`font-mono text-[11px] px-2 py-1 rounded-lg border w-20 text-center ${TIER_STYLES[tier] || 'text-muted bg-panel border-line'}`}>
                        {tier}
                      </span>
                      <div className="flex-1 h-2 rounded-full bg-surface border border-line overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${(count / stats.total_requests) * 100}%`, background: tier === 'cheap' ? 'var(--color-cool)' : tier === 'mid' ? 'var(--color-signal)' : tier === 'frontier' ? 'var(--color-danger)' : 'var(--color-muted)' }} />
                      </div>
                      <span className="font-mono text-xs text-primary w-8 text-right num-tabular">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        <div className="text-center mt-10">
          <Link
            to="/metrics"
            className="inline-flex items-center gap-2 bg-signal text-white font-semibold text-sm px-6 py-3 rounded-full hover:brightness-110 hover:shadow-card-hover shadow-card transition-all"
          >
            Explore the full dashboard
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="2" y1="7" x2="12" y2="7" />
              <polyline points="7,2 12,7 7,12" />
            </svg>
          </Link>
        </div>
      </div>
    </section>
  )
}