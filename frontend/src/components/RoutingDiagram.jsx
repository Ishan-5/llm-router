import { useState, useEffect } from 'react'
import { routeQuery, fetchStats, fetchConfig } from '../api'

const TIER_DEFAULTS = {
  cheap:    { label: 'Cheap',    sub: 'llama3.2:3b · local',      y: 60  },
  mid:      { label: 'Mid',      sub: 'qwen3-32b · Groq',          y: 160 },
  frontier: { label: 'Frontier', sub: 'llama-3.3-70b · Groq',       y: 260 },
}

export default function RoutingDiagram({ configVersion = 0 }) {
  const [query, setQuery] = useState('')
  const [override, setOverride] = useState('auto')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [ticker, setTicker] = useState(null)
  const [activeConfig, setActiveConfig] = useState({})

  useEffect(() => {
    fetchStats().then(setTicker).catch(() => setTicker(null))
    fetchConfig().then(setActiveConfig).catch(() => {})
  }, [configVersion])  // re-fetch whenever settings are saved

  // build TIERS dynamically from active config so diagram reflects custom models
  const TIERS = ['cheap', 'mid', 'frontier'].map((key) => {
    const defaults = TIER_DEFAULTS[key]
    const cfg = activeConfig[key]
    const sub = cfg ? `${cfg.model_id} · ${cfg.provider}` : defaults.sub
    return { key, label: defaults.label, sub, y: defaults.y }
  })

  async function handleSubmit(e) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await routeQuery(query, override === 'auto' ? null : override)
      setResult(data)
      fetchStats().then(setTicker).catch(() => {})
      fetchConfig().then(setActiveConfig).catch(() => {})
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const activeTier = result?.routed_to
  const score = result?.difficulty_score
  const savedPct = ticker && ticker.total_hypothetical_cost > 0
    ? Math.round((1 - ticker.total_actual_cost / ticker.total_hypothetical_cost) * 100)
    : null

  return (
    <section className="relative overflow-hidden border-b border-line">
      {/* decorative dotted grid, corner accent */}
      <div className="absolute top-8 right-8 grid grid-cols-6 gap-1.5 opacity-40 pointer-events-none hidden lg:grid">
        {Array.from({ length: 24 }).map((_, i) => (
          <span key={i} className="w-1 h-1 rounded-full bg-muted" />
        ))}
      </div>

      {/* rotated vertical label, echoing a "scroll down" style accent */}
      <div className="hidden lg:block absolute left-6 top-1/2 -translate-y-1/2 -rotate-90 origin-left">
        <span className="font-mono text-[10px] tracking-[0.3em] text-muted whitespace-nowrap">
          LIVE · AUTO-ROUTED · REAL COST
        </span>
      </div>

      <div className="max-w-6xl mx-auto px-6 lg:pl-16 pt-16 pb-20 grid grid-cols-1 lg:grid-cols-[1.05fr_0.95fr] gap-12 items-start">

        {/* LEFT: copy + form */}
        <div>
          <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4">
            Difficulty-scored request routing
          </p>
          <h1 className="font-display text-[2.75rem] md:text-6xl font-semibold leading-[1.05] tracking-tight mb-6">
            Most queries<br />don't need your<br /><span className="text-signal">most expensive</span> model.
          </h1>
          <p className="text-muted text-base leading-relaxed max-w-md mb-8">
            A regression model trained on 6,500 labeled queries predicts how hard each
            request actually is, then routes it to the cheapest tier that can handle it.
          </p>

          {savedPct !== null && (
            <div className="flex items-baseline gap-3 mb-8 font-mono border-l-2 border-signal pl-4">
              <span className="text-3xl font-semibold text-signal">{savedPct}%</span>
              <span className="text-xs text-muted leading-snug">
                cheaper than routing all {ticker.total_requests} logged requests to frontier —
                ${ticker.total_actual_cost.toFixed(4)} spent vs ${ticker.total_hypothetical_cost.toFixed(4)}
              </span>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="flex flex-col gap-3">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask anything — trivial or hard"
                className="bg-panel border border-line rounded-lg px-4 py-3 font-body text-sm
                           placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50 focus:border-signal"
              />
              <div className="flex gap-3">
                <select
                  value={override}
                  onChange={(e) => setOverride(e.target.value)}
                  className="bg-panel border border-line rounded-lg px-3 py-3 font-mono text-xs text-muted flex-1
                             focus:outline-none focus:ring-2 focus:ring-signal/50"
                  title="Force a specific tier instead of using the model's prediction"
                >
                  <option value="auto">Auto-route</option>
                  {TIERS.map((t) => (
                    <option key={t.key} value={t.key}>Force: {t.label} ({activeConfig[t.key]?.model_id || t.sub})</option>
                  ))}
                </select>
                <button
                  type="submit"
                  disabled={loading}
                  className="bg-signal text-white font-semibold text-sm px-6 py-3 rounded-lg
                             hover:brightness-110 transition disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                >
                  {loading ? 'Routing…' : 'Route it'}
                </button>
              </div>
            </div>
            {error && <p className="mt-2 text-xs font-mono text-danger">{error}</p>}
          </form>

          {result && (
            <div className="mt-6 rounded-lg border border-line bg-panel p-5">
              <div className="flex flex-wrap gap-4 mb-3 font-mono text-xs">
                <span className="text-cool">${result.cost_usd.toFixed(6)}</span>
                <span className="text-muted">{result.latency_ms.toFixed(0)}ms</span>
                <span className={result.cache_hit ? 'text-cool' : 'text-muted'}>
                  {result.cache_hit ? 'CACHE HIT' : 'CACHE MISS'}
                </span>
                {result.fallback_used && <span className="text-danger">FALLBACK</span>}
              </div>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{result.response}</p>
            </div>
          )}
        </div>

        {/* RIGHT: large decorative-but-functional circuit graphic */}
        <div className="relative hidden lg:block">
          <svg viewBox="0 0 380 300" className="w-full h-auto -mr-8">
            {/* incoming query node -- score lives here, not floating separately */}
            <circle cx="190" cy="30" r="8" fill="none" stroke="var(--color-muted)" strokeWidth="2" />
            <text x="205" y="27" className="font-mono" fontSize="11" fill="var(--color-muted)">query</text>
            {score != null && (
              <text x="205" y="44" className="font-mono font-semibold" fontSize="13" fill="var(--color-signal)">
                difficulty {score.toFixed(1)}
              </text>
            )}

            {TIERS.map((t) => {
              const isActive = activeTier === t.key
              return (
                <g key={t.key}>
                  <line x1="190" y1="30" x2="90" y2={t.y} stroke={isActive ? 'var(--color-signal)' : 'var(--color-line)'} strokeWidth={isActive ? 2.5 : 1.5} />
                  <circle cx="90" cy={t.y} r={isActive ? 12 : 9} fill={isActive ? 'var(--color-signal)' : 'none'} stroke={isActive ? 'var(--color-signal)' : 'var(--color-line)'} strokeWidth="2" className="transition-all duration-500" />
                  <text x="112" y={t.y - 8} className="font-display font-semibold" fontSize="15" fill={isActive ? 'var(--color-signal)' : 'var(--color-primary)'}>{t.label}</text>
                  <text x="112" y={t.y + 10} className="font-mono" fontSize="10" fill="var(--color-muted)">{t.sub}</text>
                </g>
              )
            })}
          </svg>
        </div>
      </div>
    </section>
  )
}
