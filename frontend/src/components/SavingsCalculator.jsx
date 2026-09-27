import { useState, useMemo, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchCatalog, projectSavings } from '../api'

/**
 * Savings calculator.
 *
 * Two ways to supply the tier mix, because the honest answer to "how do I know
 * what share of my traffic is hard?" is that most people do not:
 *
 *   - paste real prompts, scored by the same classifier the router uses, so the
 *     mix is measured rather than guessed
 *   - assert a mix yourself, which is fine but is an assumption
 *
 * Both feed one /project call, so there is a single set of formulas. The
 * backend labels every result is_estimate; this page never implies otherwise.
 */

const MODES = [
  { key: 'economy', label: 'Economy', desc: 'Send more traffic to cheap models' },
  { key: 'balanced', label: 'Balanced', desc: 'Default routing behaviour' },
  { key: 'quality', label: 'Quality', desc: 'Promote more traffic to frontier' },
]

const PERSONAS = {
  'support-bot': {
    label: 'Customer support bot',
    blurb: 'Mostly short factual lookups, some long complaint threads.',
    queries: [
      'What are your opening hours?',
      'Can I return an item without a receipt?',
      'How long does standard shipping take?',
      'I ordered on the 3rd and it still has not arrived, what happens now?',
      'Summarise this conversation so far and list every open issue the customer raised.',
      'Compare the warranty terms for the standard and premium plans and explain which applies to an item bought 14 months ago.',
    ],
  },
  'code-assistant': {
    label: 'Coding assistant',
    blurb: 'Short edits alongside multi-file architectural questions.',
    queries: [
      'Rename this variable to snake_case across the file.',
      'Add a docstring to this function.',
      'Fix this TypeScript type error.',
      'Write a Python function to paginate a SQLAlchemy query with a cursor.',
      'Refactor this module to remove the circular dependency between the cache and the session layer.',
      'Design a migration strategy for a live database that cannot take downtime while splitting one 40-column table into four.',
    ],
  },
  'research': {
    label: 'Research / analysis',
    blurb: 'Long synthesis and reasoning. Honest answer here is often "not worth it".',
    queries: [
      'Summarise the abstract.',
      'List the main findings as bullet points.',
      'Compare the methodology in these two papers and explain where they disagree.',
      'Analyse the limitations of this study design and propose a study that would address them.',
      'Reconcile these three conflicting datasets into a single coherent account, and justify each place you had to discard data as unreliable.',
    ],
  },
}

const TIERS = ['cheap', 'mid', 'frontier']

const usd = (n) => {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  const abs = Math.abs(n)
  if (abs > 0 && abs < 0.01) return `$${n.toFixed(5)}`
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const TIER_STYLE = {
  cheap: { text: 'text-cool', bg: 'bg-cool/10', border: 'border-cool/30', label: 'Cheap' },
  mid: { text: 'text-signal', bg: 'bg-signal/10', border: 'border-signal/30', label: 'Mid' },
  frontier: { text: 'text-danger', bg: 'bg-danger/10', border: 'border-danger/30', label: 'Frontier' },
}

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="font-mono text-xs text-muted uppercase tracking-wide">{label}</span>
      {hint && <span className="block text-xs text-muted/70 mt-0.5 mb-2">{hint}</span>}
      {!hint && <span className="block mt-2" />}
      {children}
    </label>
  )
}

const inputCls =
  'w-full bg-base border border-line rounded-lg px-3 py-2 text-sm text-primary focus:outline-none focus:border-signal/60'
const btnPrimary =
  'inline-flex items-center justify-center gap-2 bg-signal text-white font-semibold text-sm px-5 py-2.5 rounded-full hover:brightness-110 shadow-card transition disabled:opacity-50 disabled:cursor-not-allowed'
const btnGhost =
  'inline-flex items-center justify-center gap-2 font-mono text-xs text-muted bg-base border border-line rounded-full px-4 py-2.5 hover:text-primary hover:border-signal/50 transition'

export default function SavingsCalculator() {
  const [params, setParams] = useSearchParams()

  const [catalog, setCatalog] = useState(null)
  const [catalogError, setCatalogError] = useState(null)

  const [mode, setMode] = useState('balanced')
  const [requestsPerDay, setRequestsPerDay] = useState(100)
  const [inputTokens, setInputTokens] = useState(500)
  const [outputTokens, setOutputTokens] = useState(500)
  const [frontierModel, setFrontierModel] = useState('')
  const [providerFilter, setProviderFilter] = useState('')
  const [tierModels, setTierModels] = useState({ cheap: '', mid: '', frontier: '' })

  const [path, setPath] = useState('prompts')
  const [persona, setPersona] = useState('support-bot')
  const [queries, setQueries] = useState(PERSONAS['support-bot'].queries.join('\n'))
  const [manualMix, setManualMix] = useState({ cheap: 50, mid: 30, frontier: 20 })

  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [linkCopied, setLinkCopied] = useState(false)

  useEffect(() => {
    let alive = true
    fetchCatalog()
      .then((d) => {
        if (!alive) return
        setCatalog(d)
        const astra = d.models.find((m) => m.id === 'gpt-6-astra')
        if (astra) setFrontierModel((cur) => cur || astra.id)
      })
      .catch((e) => alive && setCatalogError(e.message))
    return () => { alive = false }
  }, [])

  useEffect(() => {
    const q = params.get('q')
    const v = params.get('v')
    const tin = params.get('in')
    const tout = params.get('out')
    const fm = params.get('frontier')
    if (q) { setQueries(q); setPath('prompts') }
    if (v) setRequestsPerDay(Number(v))
    if (tin) setInputTokens(Number(tin))
    if (tout) setOutputTokens(Number(tout))
    if (fm) setFrontierModel(fm)
  }, [params])

  useEffect(() => {
    setQueries(PERSONAS[persona].queries.join('\n'))
  }, [persona])

  const run = useCallback(
    async (currentParams) => {
      setBusy(true)
      setError(null)
      setResult(null)
      try {
        const payload = {
          requests_per_month: Math.max(1, Math.round(requestsPerDay * 30)),
          input_tokens: Math.max(0, Number(inputTokens) || 0),
          output_tokens: Math.max(0, Number(outputTokens) || 0),
          mode,
        }
        if (frontierModel) payload.tier_models = { frontier: frontierModel }
        const tm = {}
        for (const t of TIERS) if (tierModels[t]) tm[t] = tierModels[t]
        if (Object.keys(tm).length) payload.tier_models = { ...(payload.tier_models || {}), ...tm }

        if (path === 'prompts') {
          const list = queries.split('\n').map((q) => q.trim()).filter(Boolean).slice(0, 50)
          if (!list.length) throw new Error('Paste at least one real prompt, or switch to the slider path.')
          payload.queries = list
        } else {
          payload.tier_mix = {
            cheap: manualMix.cheap / 100,
            mid: manualMix.mid / 100,
            frontier: manualMix.frontier / 100,
          }
        }

        setParams(
          {
            q: path === 'prompts' ? queries : undefined,
            v: requestsPerDay,
            in: inputTokens,
            out: outputTokens,
            frontier: frontierModel || undefined,
          },
          { replace: true }
        )
        setResult(await projectSavings(payload))
      } catch (e) {
        setError(e.message)
      } finally {
        setBusy(false)
      }
    },
    [requestsPerDay, inputTokens, outputTokens, mode, path, queries, manualMix, frontierModel, tierModels, setParams]
  )

  const mixTotal = manualMix.cheap + manualMix.mid + manualMix.frontier
  const breaksEven = result ? result.savings_pct <= 0 : false
  const groupSavings = result?.tiers || {}

  const shareLink = useCallback(async () => {
    const u = new URL(window.location.href)
    u.searchParams.set('v', requestsPerDay)
    u.searchParams.set('in', inputTokens)
    u.searchParams.set('out', outputTokens)
    if (frontierModel) u.searchParams.set('frontier', frontierModel)
    if (path === 'prompts') u.searchParams.set('q', queries)
    try {
      await navigator.clipboard.writeText(u.toString())
      setLinkCopied(true)
      setTimeout(() => setLinkCopied(false), 2000)
    } catch {
      window.prompt('Copy this link:', u.toString())
    }
  }, [requestsPerDay, inputTokens, outputTokens, frontierModel, path, queries])

  const frontierPrice = useMemo(
    () => catalog?.models.find((m) => m.id === frontierModel),
    [catalog, frontierModel]
  )

  // The catalog runs to ~70 models across ~15 providers. A single flat <select>
  // is unusable at that size, so the provider is chosen first and the model
  // list narrows to it. Sorted by provider so the narrowing is predictable.
  const providers = useMemo(() => {
    const byName = new Map()
    for (const m of catalog?.models ?? []) {
      byName.set(m.provider, (byName.get(m.provider) ?? 0) + 1)
    }
    return [...byName.entries()]
      .map(([name, count]) => ({ name, count, label: name.replace(/-/g, ' ') }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
  }, [catalog])

  const visibleModels = useMemo(() => {
    const list = catalog?.models ?? []
    return providerFilter ? list.filter((m) => m.provider === providerFilter) : list
  }, [catalog, providerFilter])

  // Keep the two dropdowns consistent: if the filter changes underneath a
  // selected model (share link, or a provider with no match), fall back to the
  // default rather than leaving a stale id that the projection cannot price.
  useEffect(() => {
    if (!frontierModel || !catalog) return
    if (!visibleModels.some((m) => m.id === frontierModel)) setFrontierModel('')
  }, [visibleModels, frontierModel, catalog])

  return (
    <div className="max-w-6xl mx-auto px-6 py-16">
      <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4">Savings calculator</p>
      <h1 className="font-display text-3xl md:text-4xl font-semibold mb-3">
        What would routing your traffic actually save you?
      </h1>
      <p className="text-muted text-sm max-w-2xl mb-10">
        Enter your own volume and token counts. The baseline is the model you already use for
        everything. This projects your bill &mdash; it does not read the public dashboard, and it
        will happily tell you the answer is zero.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
        {/* ---------------- inputs ---------------- */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-panel border border-line rounded-xl p-5 space-y-5">
            <Field label="Requests per day">
              <div className="flex items-center gap-3">
                <input
                  type="range" min="1" max="100000" step="1"
                  value={requestsPerDay}
                  onChange={(e) => setRequestsPerDay(Number(e.target.value))}
                  className="flex-1 accent-[var(--color-signal)]"
                />
                <input
                  type="number" min="1" value={requestsPerDay}
                  onChange={(e) => setRequestsPerDay(Math.max(1, Number(e.target.value) || 1))}
                  className={`${inputCls} w-28`}
                />
              </div>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Input tokens">
                <input type="number" min="0" value={inputTokens}
                  onChange={(e) => setInputTokens(Math.max(0, Number(e.target.value) || 0))}
                  className={inputCls} />
              </Field>
              <Field label="Output tokens">
                <input type="number" min="0" value={outputTokens}
                  onChange={(e) => setOutputTokens(Math.max(0, Number(e.target.value) || 0))}
                  className={inputCls} />
              </Field>
            </div>
            <p className="text-xs text-muted/70 -mt-2">
              Most chat traffic lands near 500/500. Long-context or code work is much higher and
              scales both figures linearly.
            </p>
          </div>

          <div className="bg-panel border border-line rounded-xl p-5 space-y-4">
            <Field label="Frontier model" hint="What you send everything to today. This is the baseline you are compared against.">
              <select
                value={providerFilter}
                onChange={(e) => {
                  const p = e.target.value
                  setProviderFilter(p)
                  // Jump straight to that provider's first model so the second
                  // dropdown is never empty and the choice stays obvious.
                  const first = catalog?.models.find((m) => m.provider === p)
                  if (first) setFrontierModel(first.id)
                }}
                className={inputCls}
              >
                <option value="">All providers ({catalog?.models.length ?? 0} models)</option>
                {providers.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.label} ({p.count})
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Model" hint={providerFilter ? `Showing ${providerFilter} only.` : 'Every routable text model, cheapest first.'}>
              <select value={frontierModel} onChange={(e) => setFrontierModel(e.target.value)} className={inputCls}>
                <option value="">Routewise default tiers</option>
                {visibleModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} &mdash; ${m.input_per_m}/${m.output_per_m} per M
                  </option>
                ))}
              </select>
            </Field>
            {catalogError && (
              <p className="text-xs text-danger">Price list unavailable ({catalogError}). Using configured tier rates.</p>
            )}
            {frontierPrice && (
              <p className="text-xs text-muted/70">
                {frontierPrice.provider} &middot; ${frontierPrice.input_per_m} in / ${frontierPrice.output_per_m} out per 1M
                {frontierPrice.source_url && (
                  <> &middot; <a href={frontierPrice.source_url} target="_blank" rel="noreferrer" className="text-cool hover:underline">source</a></>
                )}
              </p>
            )}

            <div className="pt-2 border-t border-line">
              <p className="font-mono text-xs text-muted uppercase tracking-wide mb-3">Routing mode</p>
              <div className="space-y-2">
                {MODES.map((m) => (
                  <button
                    key={m.key}
                    onClick={() => setMode(m.key)}
                    className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition ${
                      mode === m.key ? 'border-signal/50 bg-signal/10 text-primary' : 'border-line text-muted hover:border-signal/30'
                    }`}
                  >
                    <span className="font-medium">{m.label}</span>
                    <span className="block text-xs text-muted/70">{m.desc}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ---------------- tier mix + result ---------------- */}
        <div className="lg:col-span-3 space-y-6">
          <div className="bg-panel border border-line rounded-xl p-5">
            <div className="flex gap-2 mb-4">
              <button onClick={() => setPath('prompts')}
                className={`px-3 py-1.5 rounded-full text-xs font-mono border transition ${path === 'prompts' ? 'bg-signal/10 border-signal/40 text-signal' : 'border-line text-muted hover:border-signal/30'}`}>
                From real prompts
              </button>
              <button onClick={() => setPath('sliders')}
                className={`px-3 py-1.5 rounded-full text-xs font-mono border transition ${path === 'sliders' ? 'bg-signal/10 border-signal/40 text-signal' : 'border-line text-muted hover:border-signal/30'}`}>
                I'll estimate
              </button>
            </div>

            {path === 'prompts' ? (
              <div className="space-y-3">
                <p className="text-xs text-muted">
                  Paste up to 50 prompts you actually send. The same classifier the router uses
                  scores them, so the tier split is measured rather than guessed.
                </p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(PERSONAS).map(([k, p]) => (
                    <button key={k} onClick={() => setPersona(k)}
                      title={p.blurb}
                      className={`px-2.5 py-1 rounded-full text-xs font-mono border transition ${persona === k ? 'bg-cool/10 border-cool/40 text-cool' : 'border-line text-muted hover:border-cool/30'}`}>
                      {p.label}
                    </button>
                  ))}
                </div>
                <textarea
                  value={queries}
                  onChange={(e) => setQueries(e.target.value)}
                  rows={8}
                  placeholder="One prompt per line"
                  className={`${inputCls} font-mono text-xs resize-y`}
                />
                <p className="text-xs text-muted/70">
                  {queries.split('\n').filter((q) => q.trim()).length} prompts
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-xs text-muted">
                  Your call, but this is the assumption the whole number rests on. It is a guess
                  until it is measured.
                </p>
                {TIERS.map((t) => (
                  <Field key={t} label={`${TIER_STYLE[t].label} share`}>
                    <div className="flex items-center gap-3">
                      <input type="range" min="0" max="100" value={manualMix[t]}
                        onChange={(e) => setManualMix({ ...manualMix, [t]: Number(e.target.value) })}
                        className="flex-1 accent-[var(--color-signal)]" />
                      <span className="font-mono text-xs text-primary w-12 text-right">{manualMix[t]}%</span>
                    </div>
                  </Field>
                ))}
                {mixTotal !== 100 && (
                  <p className="text-xs text-signal">
                    Shares total {mixTotal}% &mdash; they will be normalised to 100%.
                  </p>
                )}
              </div>
            )}

            <div className="flex flex-wrap gap-3 mt-5">
              <button onClick={() => run(params)} disabled={busy} className={btnPrimary}>
                {busy ? 'Scoring\u2026' : 'Calculate my savings'}
              </button>
              {result && (
                <button onClick={shareLink} className={btnGhost}>
                  {linkCopied ? 'Link copied' : 'Copy shareable link'}
                </button>
              )}
            </div>
            {error && <p className="text-xs text-danger mt-3">{error}</p>}
          </div>

          {/* ---------------- result ---------------- */}
          {result && (
            <div className="space-y-5">
              <div className={`border rounded-xl p-6 ${breaksEven ? 'border-line bg-panel' : 'border-signal/30 bg-signal/5'}`}>
                <p className="font-mono text-xs text-muted uppercase tracking-wide mb-2">
                  {breaksEven ? 'Projected change' : 'Projected saving'}
                </p>
                {breaksEven ? (
                  <>
                    <p className="font-display text-4xl font-semibold text-muted">
                      {result.savings_pct < 0 ? `+${usd(-result.monthly_saved)}/mo` : 'No change'}
                    </p>
                    <p className="text-sm text-muted mt-3 max-w-xl">
                      On this workload, routing does not reduce your bill &mdash; the down-routed
                      tiers cost more per token than the frontier model you picked as the baseline.
                      That is a real answer, and it usually means either the tier prices are
                      misconfigured or this traffic is genuinely all-hard.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="font-display text-4xl font-semibold text-signal">
                      {usd(result.monthly_saved)}<span className="text-lg text-muted">/month</span>
                    </p>
                    <p className="text-sm text-muted mt-2">
                      {usd(result.daily_saved)} a day &middot; {usd(result.yearly_saved)} a year &middot;{' '}
                      <span className="text-primary font-medium">{result.savings_pct}%</span> off
                    </p>
                  </>
                )}

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-5 border-t border-line">
                  <div>
                    <p className="font-mono text-xs text-muted">All frontier</p>
                    <p className="text-lg text-muted mt-1">{usd(result.monthly_cost_baseline)}<span className="text-xs">/mo</span></p>
                  </div>
                  <div>
                    <p className="font-mono text-xs text-muted">Routed</p>
                    <p className="text-lg text-primary mt-1">{usd(result.monthly_cost_routed)}<span className="text-xs text-muted">/mo</span></p>
                  </div>
                  <div>
                    <p className="font-mono text-xs text-muted">Per request</p>
                    <p className="text-lg text-primary mt-1">{usd(result.cost_per_request_routed)}</p>
                  </div>
                  <div>
                    <p className="font-mono text-xs text-muted">Down-routed</p>
                    <p className="text-lg text-primary mt-1">
                      {100 - (result.tier_mix.frontier || 0)}%
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-panel border border-line rounded-xl p-5">
                <p className="font-mono text-xs text-muted uppercase tracking-wide mb-4">
                  Where each request goes
                </p>
                <div className="space-y-3">
                  {TIERS.filter((t) => groupSavings[t]).map((t) => {
                    const row = groupSavings[t]
                    const s = TIER_STYLE[t]
                    return (
                      <div key={t}>
                        <div className="flex items-center justify-between text-sm mb-1.5">
                          <span className={s.text}>
                            {s.label} &middot; <span className="text-primary font-mono text-xs">{row.name}</span>
                          </span>
                          <span className="font-mono text-xs text-muted">
                            {row.share_pct}% &middot; {usd(row.cost_per_request)}/req
                          </span>
                        </div>
                        <div className="h-2 bg-line/50 rounded-full overflow-hidden">
                          <div className={`h-full ${s.bg.replace('/10', '/60')}`} style={{ width: `${row.share_pct}%` }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
                <p className="text-xs text-muted/70 mt-4">
                  Tier mix from {result.mix_source === 'scored' ? `${result.scored_queries} scored prompts` : 'your stated split'}.
                  Baseline: <span className="text-primary font-mono">{result.baseline_name}</span>.
                </p>
                {result.unpriced_tiers_fell_back?.length > 0 && (
                  <p className="text-xs text-signal mt-2">
                    Could not price {result.unpriced_tiers_fell_back.join(', ')} from the live list;
                    used configured rates.
                  </p>
                )}
              </div>

              <div className="border border-line rounded-xl p-5 space-y-2">
                <p className="font-mono text-xs text-muted uppercase tracking-wide">What this is not</p>
                <p className="text-xs text-muted">{result.caveat}</p>
                <p className="text-xs text-muted">
                  Cheaper is only half the trade. {100 - (result.tier_mix.frontier || 0)}% of these
                  requests would be answered by a smaller model, so quality is the thing to watch
                  &mdash; run real traffic in shadow mode and compare before switching.
                </p>
                {catalog?.attribution && (
                  <p className="text-xs text-muted/60 pt-1">{catalog.attribution}</p>
                )}
              </div>
            </div>
          )}

          {!result && !busy && (
            <div className="border border-dashed border-line rounded-xl p-8 text-center">
              <p className="text-sm text-muted mb-1">No projection yet</p>
              <p className="text-xs text-muted/70">
                Set your volume above, then either paste real prompts or state your tier split.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
