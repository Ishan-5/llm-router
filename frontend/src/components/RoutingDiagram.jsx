import { useState, useEffect, useRef } from 'react'
import {
  fetchStats, fetchConfig, fetchSettings, fetchChaosStatus,
  setSharedThreshold, getSharedThreshold,
  fetchRoutePolicies, getSharedModelId, setSharedModelId,
} from '../api'
import TierCircuit from './TierCircuit'
import ThresholdSlider from './ThresholdSlider'
import ModelPicker from './ModelPicker'
import { getModel, policyBandsFor, DEFAULT_MODEL_ID } from '../models'
import QueryForm from './QueryForm'
import { UserBubble, AssistantBubble, TypingIndicator } from './ResponseCard'

const TIER_DEFAULTS = {
  cheap: { label: 'Cheap', sub: 'deepseek/deepseek-v4-flash · openrouter (default)', y: 60 },
  mid: { label: 'Mid', sub: 'openai/gpt-oss-20b · groq', y: 160 },
  frontier: { label: 'Frontier', sub: 'openai/gpt-oss-120b · groq', y: 260 },
}


function MobileRoutingDiagram({ tiers, activeTier, score, cacheHit, loading, chaosActive, crossProviderFallback }) {
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

  const isScanning = loading && scanIndex >= 0 && !activeTier
  const scanTier = isScanning ? tiers[scanIndex]?.key : null
  const isWeb = !loading && activeTier === 'web'
  const isGemini = !loading && (activeTier === 'gemini' || crossProviderFallback)

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
            className={`absolute inset-y-0 left-0 rounded-full bg-signal transition-all duration-700 ${score == null ? 'opacity-40' : ''}`}
            style={{ width: score != null ? `${Math.max(2, (score / 10) * 100)}%` : '12%' }}
          />
        </span>
        <span className="shrink-0 text-signal font-semibold">
          {score != null ? score.toFixed(1) : '—'}
        </span>
      </div>

      <div className="flex items-center gap-1.5">
        {tiers.map((t) => {
          const active = activeTier === t.key
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
        <span
          className={`font-mono text-[11px] px-2 py-1.5 rounded-lg border transition-all shrink-0 ${
            isGemini ? 'text-danger border-danger/30 bg-danger/10' : 'text-muted border-line'
          }`}
        >
          gemini
        </span>
        {chaosActive && (
          <span className="font-mono text-[10px] text-danger border border-danger/30 bg-danger/10 px-2 py-1 rounded-lg shrink-0 animate-pulse">
            ⚠ outage
          </span>
        )}
      </div>
    </div>
  )
}

export default function RoutingDiagram({ configVersion = 0, backendOnline = true }) {  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [regeneratingIndex, setRegeneratingIndex] = useState(null)
  const [error, setError] = useState(null)
  const [ticker, setTicker] = useState(null)
  const [activeConfig, setActiveConfig] = useState({})
  const [threshold, setThreshold] = useState(() => getSharedThreshold() ?? 1.0)
  const [modelId, setModelId] = useState(() => getSharedModelId() ?? DEFAULT_MODEL_ID)
  // Start with every model visible. Only a successful backend response saying a
  // policy is unavailable should hide it — a failed policies fetch must not
  // silently remove Lisa and Kate.
  const [availableModes, setAvailableModes] = useState(['generic', '3tier', '2tier'])
  // The chat does not exist until the user picks a model. Selecting a card from
  // the picker flips this on and opens the chat for that model.
  const [started, setStarted] = useState(false)
  const [chaosActive, setChaosActive] = useState(false)
  const abortRef = useRef(null)
  const scrollRef = useRef(null)
  const latestResult = messages.filter((m) => m.role === 'assistant').slice(-1)[0]?.result || null
  const streamingAssistant = messages.filter((m) => m.role === 'assistant').slice(-1)[0]
  const showTyping = loading && !streamingAssistant?.result?.response

  useEffect(() => {
    if (!backendOnline) return
    fetchStats().then(setTicker).catch(() => setTicker(null))
    fetchConfig().then(setActiveConfig).catch(() => {})
    fetchSettings().then((s) => { const v = s.router_threshold ?? 1.0; setThreshold(v); setSharedThreshold(v) }).catch(() => {})
    fetchChaosStatus().then((s) => setChaosActive(s?.active ?? false)).catch(() => {})
    fetchRoutePolicies().then((p) => {
      // Only narrow the list when the backend explicitly reports modes. If it
      // returns nothing usable, keep showing everything.
      if (!p) return
      const modes = p.available_modes?.length ? p.available_modes : null
      if (!modes) return
      setAvailableModes(modes)
      // If the saved model's policy is not servable here, fall back to the
      // default rather than rendering a model the backend cannot score.
      setModelId((cur) => {
        const m = getModel(cur)
        if (m.supportMode === 'generic' || modes.includes(m.supportMode)) return cur
        setSharedModelId(DEFAULT_MODEL_ID)
        return DEFAULT_MODEL_ID
      })
    }).catch(() => {})
    return () => abortRef.current?.abort()
  }, [configVersion, backendOnline])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, loading])

  function handleSelectModel(id) {
    setModelId(id)
    setSharedModelId(id)
  }

  function handleStartModel(id) {
    setModelId(id)
    setSharedModelId(id)
    setStarted(true)
  }

  // Clicking an example question on a model starts that model's chat and sends
  // the example immediately, so the demo shows itself working.
  function handleStartWithExample(id, example) {
    handleStartModel(id)
    handleSubmit(example, 'auto', false)
  }

  const model = getModel(modelId)
  const supportMode = model.supportMode

  // Tier list follows the selected model, and defers to the backend's
  // available_tiers for the last response, so the diagram can never show a
  // tier the router did not actually use.
  const lastTierKeys = latestResult?.available_tiers || null
  const tierKeys = lastTierKeys?.length ? lastTierKeys : model.tiers

  const TIERS = tierKeys.map((key) => {
    const defaults = TIER_DEFAULTS[key] || { label: key, sub: '', y: 60 }
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
    const startTime = Date.now()

    // seed an assistant bubble immediately so tokens render as they arrive
    if (replaceIndex != null) {
      setMessages((prev) => prev.map((m, i) => (i === replaceIndex ? { role: 'assistant', result: { response: '' } } : m)))
    } else {
      setMessages((prev) => [...prev, { role: 'assistant', result: { response: '' } }])
    }

    const patchResult = (patchFn) =>
      setMessages((prev) => prev.map((m, i) =>
        i === (replaceIndex != null ? replaceIndex : prev.length - 1) && m.role === 'assistant'
          ? { ...m, result: patchFn(m.result || {}) }
          : m
      ))

    try {
      const { routeQueryStream } = await import('../api')
      await routeQueryStream(
        query,
        override === 'auto' ? null : override,
        bypassCache,
        (text) => patchResult((r) => ({ ...r, response: r.response + text })),
        (meta) => { const { type, ...rest } = meta; patchResult((r) => ({ ...r, ...rest })) },
        (done) => {
          patchResult((r) => ({
            ...r,
            ...done,
            latency_ms: done.latency_ms ?? r.latency_ms ?? (Date.now() - startTime),
            cost_usd: done.cost_usd ?? r.cost_usd ?? 0,
            routed_to: done.routed_to ?? r.routed_to,
          }))
          if (abortRef.current === controller) setLoading(false)
        },
        (detail) => {
          setError(detail)
          patchResult((r) => ({ ...r, response: r.response || `Error: ${detail}`, routed_to: 'error', cost_usd: 0, latency_ms: Date.now() - startTime }))
          if (abortRef.current === controller) setLoading(false)
        },
        controller.signal,
        threshold,
        conversationMessages,
        supportMode,
      )
      fetchStats().then(setTicker).catch(() => {})
      fetchConfig().then(setActiveConfig).catch(() => {})
    } catch (err) {
      if (!(err.name === 'AbortError' && controller.signal.aborted)) {
        setError(err.message)
        patchResult((r) => ({ ...r, response: r.response || `Error: ${err.message}`, routed_to: 'error', cost_usd: 0, latency_ms: Date.now() - startTime }))
      }
    } finally {
      if (abortRef.current === controller) {
        setLoading(false)
        setRegeneratingIndex(null)
      }
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
    setStarted(false)
    setLoading(false)
    setError(null)
  }

  const activeTier = latestResult?.routed_to
  const score = latestResult?.difficulty_score
  const streaming = loading && activeTier != null

  // Emma has economy/balanced/quality, so her cuts move with the threshold
  // slider. Lisa and Kate ship fixed cuts, so their bands come from the policy
  // itself. Showing the generic bands for a fixed-cut model would be a lie.
  const t = threshold - 1
  const emmaCheapCeil = +(4.5 - t * 0.75).toFixed(3)
  const emmaFrontierFloor = +(6.0 - t * 0.75).toFixed(3)
  // Live response values win. Before the first response, fall back to whatever
  // the selected model actually uses.
  const policyBands = policyBandsFor(modelId)
  const cheapCeil = latestResult?.cheap_ceil ?? (model.adjustable ? emmaCheapCeil : policyBands.cheap)
  const frontierFloor = latestResult?.frontier_floor ?? (model.adjustable ? emmaFrontierFloor : policyBands.frontier)

  const savedPct = ticker && ticker.total_hypothetical_cost > 0
    ? Math.round((1 - ticker.total_actual_cost / ticker.total_hypothetical_cost) * 100)
    : null

  const isEmpty = !started && messages.length === 0 && !loading

  const queryCount = messages.filter((m) => m.role === 'user').length

  const lastAssistantIndex = messages.map((m, i) => m.role === 'assistant' ? i : -1).filter((i) => i >= 0).slice(-1)[0] ?? -1

  return (
    <section className="relative overflow-hidden border-b border-line bg-panel">

      {/* site hero theme — same background layers as the landing page */}
      <div aria-hidden className="pointer-events-none absolute -top-40 -right-32 w-[36rem] h-[36rem] rounded-full opacity-[0.15] dark:opacity-[0.18]"
        style={{ background: 'radial-gradient(circle, var(--color-signal) 0%, transparent 65%)' }} />
      <div aria-hidden className="pointer-events-none absolute -bottom-48 -left-32 w-[32rem] h-[32rem] rounded-full opacity-[0.10] dark:opacity-[0.14]"
        style={{ background: 'radial-gradient(circle, var(--color-cool) 0%, transparent 65%)' }} />
      <div aria-hidden className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(ellipse at center, transparent 55%, var(--color-base) 100%)' }} />
      <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-[40%] overflow-hidden [mask-image:radial-gradient(ellipse_at_center,black_10%,transparent_70%)]"
        style={{ backgroundImage: 'radial-gradient(var(--color-muted) 0.6px, transparent 0.6px)', backgroundSize: '22px 22px', opacity: 0.18 }} />

      {chaosActive && (
        <div className="relative max-w-6xl mx-auto px-6 pt-8 sm:pt-10">
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-danger opacity-60" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-danger" />
            </span>
            <p className="font-mono text-xs text-danger">
              <span className="font-semibold">SIMULATED OUTAGE</span> — cheap · mid · frontier are down. Send a query and watch failover land on the{' '}
              <span className="font-semibold">Gemini last resort</span>.{' '}
              <span className="text-danger/70">(managed from the Admin outage simulator)</span>.
            </p>
          </div>
        </div>
      )}

      <div className="max-w-6xl mx-auto px-6 lg:pl-16 pt-10 sm:pt-14 pb-10 sm:pb-14 grid grid-cols-1 lg:grid-cols-[1.05fr_0.95fr] gap-12 items-start">
        {/* left column */}
        <div className="flex flex-col min-h-0">
          {/* landing state: hero + model picker */}
          {isEmpty && (
            <>
              <p className="font-mono text-xs text-signal tracking-wide uppercase mb-5 flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-signal opacity-60" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-signal" />
                </span>
                Difficulty-scored request routing
              </p>
              <h1 className="font-display text-4xl sm:text-5xl md:text-6xl font-semibold leading-[1.03] tracking-tight mb-8">
                Most queries don't need your{' '}
                <span className="bg-gradient-to-r from-[var(--color-signal)] to-[var(--color-cool)] bg-clip-text text-transparent">
                  most expensive
                </span>{' '}
                model.
              </h1>

              <ModelPicker
                value={modelId}
                onSelect={handleSelectModel}
                onStart={handleStartModel}
                onExample={handleStartWithExample}
                availableModes={availableModes}
              />

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
            </>
          )}

          {/* chat state: header + welcome/messages */}
          {!isEmpty && (
            <>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <h2 className="font-display text-xl font-semibold">Chat with {model.name}</h2>
                  <span className="font-mono text-[10px] text-muted px-2 py-0.5 rounded-full bg-base border border-line num-tabular">
                    {queryCount} {queryCount === 1 ? 'query' : 'queries'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="hidden md:flex items-center gap-1.5 font-mono text-[10px] text-muted">
                    <span className={`h-1.5 w-1.5 rounded-full ${model.accent === 'danger' ? 'bg-danger' : model.accent === 'signal' ? 'bg-signal' : 'bg-cool'}`} />
                    <span className="text-primary">{model.name}</span> · {model.tagline}
                  </span>
                  <button
                    type="button"
                    onClick={handleExitChat}
                    title={model.description}
                    className="flex items-center gap-1.5 font-mono text-[11px] text-muted border border-line rounded-full px-3 py-1.5 hover:text-primary hover:border-signal/50 hover:shadow-card transition-all"
                  >
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                      <line x1="1" y1="1" x2="9" y2="9" />
                      <line x1="9" y1="1" x2="1" y2="9" />
                    </svg>
                    Change model
                  </button>
                </div>
              </div>

              {messages.length === 0 && (
                <div className="mb-4 rounded-2xl border border-line bg-panel p-5">
                  <div className="flex items-center gap-3 mb-2">
                    <span
                      style={{
                        backgroundColor: `color-mix(in srgb, ${model.accent === 'danger' ? 'var(--color-danger)' : model.accent === 'signal' ? 'var(--color-signal)' : 'var(--color-cool)'} 10%, transparent)`,
                        borderColor: model.accent === 'danger' ? 'var(--color-danger)' : model.accent === 'signal' ? 'var(--color-signal)' : 'var(--color-cool)',
                        color: model.accent === 'danger' ? 'var(--color-danger)' : model.accent === 'signal' ? 'var(--color-signal)' : 'var(--color-cool)',
                      }}
                      className={`h-9 w-9 rounded-xl grid place-items-center font-display text-base font-semibold border`}
                    >
                      {model.name[0]}
                    </span>
                    <div>
                      <p style={{ color: 'var(--color-primary)' }} className="font-display text-base font-semibold leading-none">{model.name}</p>
                      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted mt-1">{model.tagline}</p>
                    </div>
                  </div>
                  <p className="text-xs leading-relaxed font-medium mb-4" style={{ color: 'var(--color-primary)' }}>
                    {model.description}
                  </p>
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted mb-2">
                    What you can ask
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {model.examples.map((ex) => (
                      <button
                        key={ex}
                        type="button"
                        onClick={() => handleSubmit(ex, 'auto', false)}
                        className="font-mono text-[11px] rounded-full px-3.5 py-1.5 border transition-all hover:border-signal"
                        style={{ color: 'var(--color-primary)', borderColor: 'var(--color-line)', backgroundColor: 'var(--color-base)' }}
                      >
                        {ex}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.length > 0 && (
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
                            streaming={loading && i === lastAssistantIndex}
                          />
                        )
                  )}
                  {showTyping && <TypingIndicator />}
                </div>
              )}

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
                streaming={streaming}
                chaosActive={chaosActive}
                crossProviderFallback={latestResult?.cross_provider_fallback}
              />
            </div>
          )}

          {/* input — only after a model is chosen */}
          {!isEmpty && (
            <>
              <QueryForm
                onSubmit={handleSubmit}
                loading={loading}
                tiers={TIERS}
                activeConfig={activeConfig}
              />
              {/* Emma is the only model with economy/balanced/quality. Lisa and Kate
                  ship fixed cuts, so a threshold slider would be a control that does
                  nothing. Show their actual bands instead. */}
              {model.adjustable ? (
                <div className="mt-2 px-1">
                  <ThresholdSlider value={threshold} onChange={(v) => { setThreshold(v); setSharedThreshold(v) }} compact />
                </div>
              ) : (
                <div className="mt-2 px-1 font-mono text-[10px] text-muted flex items-center gap-2 flex-wrap">
                  <span className="text-primary">{model.name} routing</span>
                  <span aria-hidden>·</span>
                  {model.tiers.includes('mid') ? (
                    <span>cut at {model.cuts.cheap} and {model.cuts.frontier}</span>
                  ) : (
                    <span>cut at {model.cuts.cheap}</span>
                  )}
                  <span aria-hidden>·</span>
                  <span>fixed, tuned on 17,600 support labels</span>
                </div>
              )}
            </>
          )}
        </div>

        {/* right column: SVG diagram — always visible */}
        <div className="hidden sm:block lg:sticky lg:top-24">
          <TierCircuit
            tiers={TIERS}
            activeTier={activeTier}
            score={score}
            cacheHit={latestResult?.cache_hit}
            loading={loading}
            streaming={streaming}
            cheapCeil={cheapCeil}
            frontierFloor={frontierFloor}
            chaosActive={chaosActive}
            crossProviderFallback={latestResult?.cross_provider_fallback}
            intendedTier={latestResult?.intended_tier}
          />
        </div>
      </div>
    </section>
  )
}
