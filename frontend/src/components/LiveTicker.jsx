import { useEffect, useState } from 'react'
import { fetchLogs } from '../api'

const TIER_STYLES = {
  cheap: 'text-cool bg-cool/10 border-cool/30',
  mid: 'text-signal bg-signal/10 border-signal/30',
  frontier: 'text-danger bg-danger/10 border-danger/30',
  web: 'text-cool bg-cool/10 border-cool/30',
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function LiveTicker({ limit = 6 }) {
  const [logs, setLogs] = useState([])

  useEffect(() => {
    let cancelled = false
    function load() {
      fetchLogs(limit)
        .then((rows) => { if (!cancelled) setLogs(rows) })
        .catch(() => {})
    }
    load()
    const id = setInterval(load, 12_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [limit])

  if (logs.length === 0) return null

  return (
    <section className="border-b border-line bg-panel">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex items-center gap-2.5 mb-5">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cool opacity-60" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cool" />
          </span>
          <p className="font-mono text-xs text-primary tracking-wide uppercase">Now routing — last {logs.length} requests</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
          {logs.map((r) => {
            const tier = r.tier || '—'
            const model = (r.model_id || '').split('/').pop() || '—'
            const tierClass = TIER_STYLES[tier] || 'text-muted bg-panel border-line'
            return (
              <div
                key={r.id}
                className="flex items-center gap-3 bg-base border border-line rounded-xl px-3 py-2.5 min-w-0 animate-slide-in shadow-card hover:shadow-card-hover hover:border-signal/30 transition-all"
              >
                <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded-md border shrink-0 ${tierClass}`}>
                  {tier}
                </span>
                <span className="text-primary text-xs font-mono truncate flex-1" title={r.query}>
                  {r.query}
                </span>
                {r.cache_hit && (
                  <span className="font-mono text-[10px] text-cool shrink-0 font-semibold">cache</span>
                )}
                <span className="text-muted font-mono text-[10px] shrink-0 hidden sm:inline">{model}</span>
                <span className="text-muted font-mono text-[10px] shrink-0 num-tabular">{r.latency_ms?.toFixed(0)}ms</span>
                <span className="font-mono text-[10px] text-primary shrink-0 num-tabular">${r.cost_usd?.toFixed(4)}</span>
              </div>
            )
          })}
        </div>
        <p className="font-mono text-[10px] text-muted mt-3">
          live · {logs.length ? formatTime(logs[0].created_at) : ''} latest
        </p>
      </div>
    </section>
  )
}