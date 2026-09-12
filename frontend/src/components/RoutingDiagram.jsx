import { useState, useEffect, useRef } from 'react'
import { fetchStats, fetchConfig, fetchSettings, setSharedThreshold, getSharedThreshold } from '../api'
import TierCircuit from './TierCircuit'
import ThresholdSlider from './ThresholdSlider'
import QueryForm, { ChatSuggestions } from './QueryForm'
import { UserBubble, AssistantBubble, TypingIndicator } from './ResponseCard'


function MobileRoutingDiagram({ tiers, activeTier, score, cacheHit, loading }) {
  const [scanIndex, setScanIndex] = useState(-1)

  useEffect(() => {
    if (!loading) {
      setScanIndex(-1)
      return
    }
    setScanIndex(0)
    const id = setInterval(() => setScanIndex((i) => (i + 1) % tiers.length), 400)
    return () => clearInterval(id)
  }, [loading, tiers.length])

  const isScanning = loading && scanIndex >= 0
  const scanTier = isScanning ? tiers[scanIndex]?.key : null
  const isWeb = !loading && activeTier === 'web'

  return (
    <div className="bg-base border border-line rounded-xl px-4 py-3 space-y-3">
      <div className="flex items-center gap-3 font-mono text-[11px] text-muted">
        <span className="uppercase tracking-wide shrink-0">query</span>
        <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="shrink-0">
          <line x1="2" y1="7" x2="12" y2="7" />
          <polyline points="7,2 12,7 7,12" />
        </svg>
        <span className="flex-1 relative h-1.5 rounded-full bg-line overflow-hidden">
          <span
            className={`absolute inset-y-0 left-0 rounded-full bg-signal transition-all duration-700 ${score == null || loading ? 'opacity-40' : ''}`}
            style={{ width: score != null && !loading ? `${Math.max(2, (score / 10) * 100)}%` : '12%' }}
          />
        </span>
        <span className="shrink-0 text-signal font-semibold">
          {score != null && !loading ? score.toFixed(1) : '—'}
        </span>
      </div>

      <div className="flex items-center gap-1.5">
        {tiers.map((t) => {
          const active = !loading && activeTier === t.key
          const scanning = isScanning && scanTier === t.key
          const on = active || scanning
          const cl = active && cacheHit
            ? 'text-cool border-cool/30 bg-cool/10'
            : on
              ? 'text-signal border-signal/40 bg-signal/10'
              : 'text-muted border-line'
          return (
            <span
              key={t.key}
              className={`font-mono text-[11px] px-2 py-1.5 rounded-lg border transition-all flex-1 text-center truncate ${cl}`}
            >
              {t.label}
            </span>
          )
        })}
        <span
          className={`font-mono text-[11px] px-2 py-1.5 rounded-lg border transition-all w-12 text-center shrink-0 ${
            isWeb ? 'text-cool border-cool/30 bg-cool/10' : 'text-muted border-line'
          }`}
        >
          web
        </span>
      </div>
    </div>
  )
}

export default function RoutingDiagram({ configVersion = 0, backendOnline = true }) {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [regeneratingIndex, setRegeneratingIndex] = useState(null)
  const [error, setError] = useState(null)
  const [ticker, setTicker] = useState(null)
  const [activeConfig, setActiveConfig] = useState({})
  const [threshold, setThreshold] = useState(() => getSharedThreshold() ?? 1.0)
  const abortRef = useRef(null)
  const scrollRef = useRef(null)
  const latestResult = messages.filter((m) => m.role === 'assistant').slice(-1)[0]?.result || null

  useEffect(() => {
    if (!backendOnline) return
    fetchStats().then(setTicker).catch(() => setTicker(null))
    fetchConfig().then(setActiveConfig).catch(() => {})
    fetchSettings().then((s) => { const v = s.router_threshold ?? 1.0; setThreshold(v); setSharedThreshold(v) }).catch(() => {})
    return () => abortRef.current?.abort()
  }, [configVersion, backendOnline])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, loading])

  const TIERS = ['cheap', 'mid', 'frontier'].map((key) => {
    const defaults = {
      cheap: { label: 'Cheap', sub: 'deepseek/deepseek-v4-flash · openrouter (default)', y: 60 },
      mid: { label: 'Mid', sub: 'openai/gpt-oss-20b · groq', y: 160 },
      frontier: { label: 'Frontier', sub: 'openai/gpt-oss-120b · groq', y: 260 },
    }[key]
    const cfg = activeConfig[key]
    const sub = cfg ? `${cfg.model_id} · ${cfg.provider}` : defaults.sub
    return { key, label: defaults.label, sub, y: defaults.y }
  })

  async function sendQuery(query, override, bypassCache, historyBase, replaceIndex = null) {
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller

    // build conversation history for multi-turn
    const history = historyBase.flatMap((m) =>
      m.role === 'user'
        ? [{ role: 'user', content: m.text }]
        : m.result?.response ? [{ role: 'assistant', content: m.result.response }] : []
    )
    const conversationMessages = [...history, { role: 'user', content: query }]

    setLoading(true)
    setError(null)

    const applyResult = (result) => {
      if (replaceIndex != null) {
        setMessages((prev) => prev.map((m, i) => (i === replaceIndex ? { role: 'assistant', result } : m)))
      } else {
        setMessages((prev) => [...prev, { role: 'assistant', result }])
      }
    }

    try {
      const { routeQuery } = await import('../api')
      const data = await routeQuery(
        query,
        override === 'auto' ? null : override,
        bypassCache,
        controller.signal,
        threshold,
        conversationMessages,
      )
      applyResult(data)
      fetchStats().then(setTicker).catch(() => {})
      fetchConfig().then(setActiveConfig).catch(() => {})
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError(err.message)
        applyResult({ response: `Error: ${err.message}`, routed_to: 'error', cost_usd: 0, latency_ms: 0 })
      }
    } finally {
      setLoading(false)
      setRegeneratingIndex(null)
    }
  }

  async function handleSubmit(query, override, bypassCache) {
    // save to localStorage history
    try {
      const prev = JSON.parse(localStorage.getItem('rw_query_history') || '[]')
      const updated = [query, ...prev.filter((q) => q !== query)].slice(0, 50)
      localStorage.setItem('rw_query_history', JSON.stringify(updated))
    } catch {}

    setMessages((prev) => [...prev, { role: 'user', text: query }])
    sendQuery(query, override, bypassCache, [...messages, { role: 'user', text: query }])
  }

  function handleRegenerate(index) {
    let userIndex = -1
    for (let i = index - 1; i >= 0; i--) {
      if (messages[i].role === 'user') { userIndex = i; break }
    }
    if (userIndex === -1) return
    const query = messages[userIndex].text
    setRegeneratingIndex(index)
    sendQuery(query, 'auto', true, messages.slice(0, userIndex + 1), index)
  }

  function handleExitChat() {
    if (abortRef.current) abortRef.current.abort()
    setMessages([])
    setLoading(false)
    setError(null)
  }

  const activeTier = loading ? null : latestResult?.routed_to
  const score = loading ? null : latestResult?.difficulty_score

  const t = threshold - 1
  const defaultCheapCeil = +(4.5 - t * 0.75).toFixed(3)
  const defaultFrontierFloor = +(6.0 - t * 0.75).toFixed(3)
  const cheapCeil = loading ? null : (latestResult?.cheap_ceil ?? defaultCheapCeil)
  const frontierFloor = loading ? null : (latestResult?.frontier_floor ?? defaultFrontierFloor)

  const savedPct = ticker && ticker.total_hypothetical_cost > 0
    ? Math.round((1 - ticker.total_actual_cost / ticker.total_hypothetical_cost) * 100)
    : null

  const isEmpty = messages.length === 0 && !loading

  const queryCount = messages.filter((m) => m.role === 'user').length

  return (
    <section className="relative overflow-hidden border-b border-line bg-panel">

      {/* ambient glow */}
      <div aria-hidden className="pointer-events-none absolute -top-40 -right-32 w-[36rem] h-[36rem] rounded-full opacity-[0.15] dark:opacity-[0.18]"
        style={{ background: 'radial-gradient(circle, var(--color-signal) 0%, transparent 65%)' }} />
      <div aria-hidden className="pointer-events-none absolute -bottom-48 -left-32 w-[32rem] h-[32rem] rounded-full opacity-[0.10] dark:opacity-[0.14]"
        style={{ background: 'radial-gradient(circle, var(--color-cool) 0%, transparent 65%)' }} />
      <div aria-hidden className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(ellipse at center, transparent 55%, var(--color-base) 100%)' }} />

      {/* dot matrix pattern */}
      <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-[40%] overflow-hidden [mask-image:radial-gradient(ellipse_at_center,black_10%,transparent_70%)]"
        style={{ backgroundImage: 'radial-gradient(var(--color-muted) 0.6px, transparent 0.6px)', backgroundSize: '22px 22px', opacity: 0.18 }} />

      <div className="hidden lg:block absolute left-6 top-1/2 -translate-y-1/2 -rotate-90 origin-left">
        <span className="font-mono text-[10px] tracking-[0.3em] text-muted/70 whitespace-nowrap">
          LIVE · AUTO-ROUTED · REAL COST
        </span>
      </div>

      <div className="max-w-6xl mx-auto px-6 lg:pl-16 pt-10 sm:pt-12 pb-10 sm:pb-12 grid grid-cols-1 lg:grid-cols-[1.05fr_0.95fr] gap-12 items-start">
        {/* left column */}
        <div className="flex flex-col min-h-0">
          {/* empty state: hero text */}
          {isEmpty && (
            <>
              <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4 flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-signal opacity-60" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-signal" />
                </span>
                Difficulty-scored request routing
              </p>
              <h1 className="font-display text-4xl sm:text-5xl md:text-6xl font-semibold leading-[1.05] tracking-tight mb-6">
                Most queries<br />don't need your<br />{' '}
                <span className="bg-gradient-to-r from-[var(--color-signal)] to-[var(--color-cool)] bg-clip-text text-transparent">
                  most expensive
                </span>{' '}
                model.
              </h1>
              <p className="text-muted text-base leading-relaxed max-w-md mb-6">
                A regression model trained on 8,200 Claude-gold labels predicts how hard each
                request actually is, then routes it to the cheapest tier that can handle it.
              </p>
              {savedPct !== null && ticker && (
                <div className="flex items-stretch gap-px mb-8 rounded-xl border border-line bg-base shadow-card overflow-hidden max-w-md">
                  <div className="px-5 py-3.5 bg-base">
                    <div className="flex items-baseline gap-1.5">
                      <span className="font-display text-3xl font-bold text-signal num-tabular">{savedPct}%</span>
                      <span className="font-mono text-[10px] text-muted uppercase tracking-wide">saved</span>
                    </div>
                  </div>
                  <div className="px-5 py-3.5 bg-panel/50">
                    <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-1">vs all-frontier</p>
                    <p className="font-mono text-xs text-primary num-tabular">
                      ${ticker.total_savings_usd?.toFixed(4) || '0.0000'} on {ticker.total_requests} requests
                    </p>
                  </div>
                </div>
              )}
              <div className="mb-8">
                <ChatSuggestions onSelect={(q) => handleSubmit(q, 'auto', false)} />
              </div>
            </>
          )}

          {/* chat state: header + messages */}
          {!isEmpty && (
            <>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-signal opacity-40 animate-ping" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-signal" />
                  </span>
                  <h2 className="font-display text-lg font-semibold">Routing demo</h2>
                  <span className="font-mono text-[10px] text-muted px-2 py-0.5 rounded-full bg-base border border-line num-tabular">
                    {queryCount} {queryCount === 1 ? 'query' : 'queries'}
                  </span>
                </div>
                <button
                  onClick={handleExitChat}
                  className="flex items-center gap-1.5 font-mono text-[11px] text-muted border border-line rounded-full px-3 py-1.5 hover:text-primary hover:border-signal/50 hover:shadow-card transition-all"
                >
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                    <line x1="1" y1="1" x2="9" y2="9" />
                    <line x1="9" y1="1" x2="1" y2="9" />
                  </svg>
                  Exit chat
                </button>
              </div>

              <div
                ref={scrollRef}
                className="flex flex-col max-h-[46vh] lg:max-h-[42vh] overflow-y-auto mb-4 scroll-smooth chat-scroll"
              >
                {messages.map((msg, i) =>
                  msg.role === 'user'
                    ? <UserBubble key={i} text={msg.text} />
                    : (
                        <AssistantBubble
                          key={i}
                          result={msg.result}
                          logId={msg.result?.request_log_id}
                          onRegenerate={() => handleRegenerate(i)}
                          regenerating={regeneratingIndex === i}
                        />
                      )
                )}
                {loading && <TypingIndicator />}
              </div>

              {error && !loading && (
                <p className="font-mono text-xs text-danger mb-3 px-1">{error}</p>
              )}
            </>
          )}

          {/* compact diagram for small screens */}
          {!isEmpty && (
            <div className="mb-5 sm:hidden">
              <MobileRoutingDiagram
                tiers={TIERS}
                activeTier={activeTier}
                score={score}
                cacheHit={latestResult?.cache_hit}
                loading={loading}
                cheapCeil={cheapCeil}
                frontierFloor={frontierFloor}
              />
            </div>
          )}

          {/* input — always visible */}
          <QueryForm
            onSubmit={handleSubmit}
            loading={loading}
            tiers={TIERS}
            activeConfig={activeConfig}
          />
          <div className="mt-2 px-1">
            <ThresholdSlider value={threshold} onChange={(v) => { setThreshold(v); setSharedThreshold(v) }} compact />
          </div>
        </div>

        {/* right column: SVG diagram — always visible */}
        <div className="hidden sm:block lg:sticky lg:top-24">
          <TierCircuit
            tiers={TIERS}
            activeTier={activeTier}
            score={score}
            cacheHit={latestResult?.cache_hit}
            loading={loading}
            cheapCeil={cheapCeil}
            frontierFloor={frontierFloor}
          />
        </div>
      </div>
    </section>
  )
}
