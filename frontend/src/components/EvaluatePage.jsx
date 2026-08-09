import { useState, useRef, useEffect } from 'react'
import { evaluateQueries } from '../api'

const SAMPLE_QUERIES = [
  // Cheap tier (score <= 3)
  'What is the capital of France?',
  'What is 2+2?',
  'Translate hello to Spanish',
  'Tell me a joke',
  'What year did World War II end?',
  // Mid tier (score 3-7)
  'Write a Python function to sort a list of dictionaries by a nested key',
  'Create a docker-compose.yml for a Node.js app with PostgreSQL',
  'Explain the difference between TCP and UDP with examples',
  'Write a regex to validate email addresses and explain each part',
  'Summarize the causes of the French Revolution in 3 paragraphs',
  // Frontier tier (score >= 7) - these change with slider
  'Design a distributed rate limiter that works across 50 microservices with sub-millisecond overhead',
  'Implement a lock-free concurrent skip list in C++ with memory ordering guarantees',
  'Architect a CQRS event-sourcing system for a financial ledger handling 100k transactions per second',
  'Prove that P does not equal NP or explain the strongest current complexity-theoretic barriers',
  'Design a Byzantine fault-tolerant consensus protocol for a permissioned blockchain with 200 nodes',
]

const TIER_COLORS = {
  cheap: 'text-cool bg-cool/10 border-cool/30',
  mid: 'text-signal bg-signal/10 border-signal/30',
  frontier: 'text-danger bg-danger/10 border-danger/30',
}

const MARGINS = [
  { key: 'tier_economy', label: 'Economy', desc: 'slider left', color: 'cool' },
  { key: 'tier_balanced', label: 'Balanced', desc: 'slider center', color: 'signal' },
  { key: 'tier_quality', label: 'Quality', desc: 'slider right', color: 'danger' },
]

export default function EvaluatePage() {
  const [queries, setQueries] = useState(SAMPLE_QUERIES.join('\n'))
  const [results, setResults] = useState(null)
  const [thresholds, setThresholds] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const resultsRef = useRef(null)

  useEffect(() => {
    if (results && resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [results])

  async function handleRun() {
    setLoading(true)
    setError(null)
    setResults(null)
    setThresholds(null)
    const list = queries.split('\n').map((q) => q.trim()).filter(Boolean)
    if (list.length === 0) { setError('Enter at least one query'); setLoading(false); return }
    try {
      const data = await evaluateQueries(list)
      setResults(data.results)
      setThresholds(data.thresholds || null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function countTiers(results, marginKey) {
    const counts = { cheap: 0, mid: 0, frontier: 0 }
    results.forEach((r) => { counts[r[marginKey]] = (counts[r[marginKey]] || 0) + 1 })
    return counts
  }

  const total = results ? results.length : 0
  const counts = results ? {
    economy: countTiers(results, 'tier_economy'),
    balanced: countTiers(results, 'tier_balanced'),
    quality: countTiers(results, 'tier_quality'),
  } : null

  function tierChanges(r) {
    return !(r.tier_economy === r.tier_balanced && r.tier_balanced === r.tier_quality)
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-20">
      <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4">Test Router</p>
      <h1 className="font-display text-3xl font-semibold mb-2">Evaluate your router</h1>
      <p className="text-muted text-sm mb-2">
        Paste queries to see which tier each would be routed to at different slider positions.
      </p>

      {/* Threshold explanation */}
      <div className="bg-surface border border-line rounded-xl p-4 mb-6">
        <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-2">How routing works</p>
        <div className="grid grid-cols-3 gap-3 font-mono text-[10px]">
          <div className="text-center">
            <span className="text-cool font-semibold">Score ≤ 3</span>
            <span className="text-muted"> → Cheap</span>
          </div>
          <div className="text-center">
            <span className="text-signal font-semibold">Score 3–threshold</span>
            <span className="text-muted"> → Mid</span>
          </div>
          <div className="text-center">
            <span className="text-danger font-semibold">Score ≥ threshold</span>
            <span className="text-muted"> → Frontier</span>
          </div>
        </div>
        <div className="flex justify-between mt-2 font-mono text-[9px] text-muted">
          <span>Economy: frontier ≥ 6.3</span>
          <span>Balanced: frontier ≥ 6.0</span>
          <span>Quality: frontier ≥ 5.7</span>
        </div>
        <p className="font-mono text-[9px] text-muted/60 mt-2">
          The slider shifts the frontier threshold. Scores ≤ 4.0 always route to Cheap.
          Scores 4.0–5.7 always route to Mid. Scores ≥ 5.7 change tier with the slider.
        </p>
      </div>

      <div className="bg-panel border border-line rounded-xl overflow-hidden mb-6">
        <textarea
          value={queries}
          onChange={(e) => setQueries(e.target.value)}
          rows={8}
          className="w-full bg-transparent px-5 py-4 font-mono text-xs text-primary placeholder:text-muted resize-y focus:outline-none leading-relaxed"
        />
        <div className="flex items-center justify-between px-5 py-3 border-t border-line bg-surface">
          <span className="font-mono text-[10px] text-muted">
            {queries.split('\n').filter(Boolean).length} queries — one per line
          </span>
          <button
            onClick={handleRun}
            disabled={loading}
            className="h-8 px-4 flex items-center gap-1.5 rounded-lg bg-signal text-white text-xs font-semibold disabled:opacity-30 disabled:cursor-not-allowed hover:brightness-110 transition"
          >
            {loading ? 'Classifying...' : 'Run evaluation'}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-danger/5 border border-danger/30 rounded-xl px-4 py-3 mb-6">
          <p className="font-mono text-xs text-danger">{error}</p>
          {error.includes('fetch') && (
            <p className="font-mono text-[10px] text-muted mt-1">
              Make sure the backend is running and accessible.
            </p>
          )}
        </div>
      )}

      {results && (
        <div ref={resultsRef} className="space-y-6 animate-[slide-in_0.2s_ease-out]">
          {/* Summary cards */}
          <div className="grid grid-cols-3 gap-3">
            {MARGINS.map((m) => {
              const c = counts[m.key.replace('tier_', '')]
              return (
                <div key={m.key} className={`bg-panel border rounded-xl p-4 ${
                  m.color === 'cool' ? 'border-cool/20' : m.color === 'signal' ? 'border-signal/20' : 'border-danger/20'
                }`}>
                  <div className={`font-mono text-[10px] font-semibold ${
                    m.color === 'cool' ? 'text-cool' : m.color === 'signal' ? 'text-signal' : 'text-danger'
                  }`}>{m.label} <span className="text-muted font-normal">({m.desc})</span></div>
                  <div className="flex gap-3 mt-2">
                    {['cheap', 'mid', 'frontier'].map((t) => (
                      <div key={t} className="text-center">
                        <div className={`font-display text-lg font-bold ${
                          t === 'cheap' ? 'text-cool' : t === 'mid' ? 'text-signal' : 'text-danger'
                        }`}>{c[t] || 0}</div>
                        <div className="font-mono text-[8px] text-muted capitalize">{t}</div>
                      </div>
                    ))}
                  </div>
                  <div className="font-mono text-[9px] text-muted mt-1">
                    {total > 0 ? `${Math.round((c.frontier || 0) / total * 100)}% frontier` : '—'}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Results table */}
          <div className="bg-panel border border-line rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-line flex items-center justify-between">
              <span className="font-mono text-[10px] text-muted uppercase tracking-wide">Results ({total} queries)</span>
              <span className="font-mono text-[9px] text-muted">
                {results.filter(tierChanges).length} change tier across slider positions
              </span>
            </div>
            <div className="divide-y divide-line">
              {results.map((r, i) => {
                const changes = tierChanges(r)
                return (
                  <div key={i} className={`px-5 py-3 flex items-start gap-3 transition-colors ${
                    changes ? 'bg-signal/5 hover:bg-signal/10' : 'hover:bg-surface/50'
                  }`}>
                    <span className="font-mono text-[10px] text-muted w-6 shrink-0 pt-0.5">{i + 1}.</span>
                    <div className="flex-1 min-w-0">
                      <p className="font-mono text-xs text-primary truncate">{r.query}</p>
                      <span className={`font-mono text-[9px] ${changes ? 'text-signal' : 'text-muted'}`}>
                        score: {r.difficulty_score.toFixed(2)}
                        {r.difficulty_score <= 4.0 && ' (always cheap)'}
                        {r.difficulty_score > 4.0 && r.difficulty_score < 5.7 && ' (always mid)'}
                        {r.difficulty_score >= 5.7 && r.difficulty_score < 6.3 && ' (changes with slider)'}
                        {r.difficulty_score >= 6.3 && ' (always frontier)'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {MARGINS.map((m) => {
                        const tier = r[m.key]
                        return (
                          <span key={m.key} className={`font-mono text-[9px] px-1.5 py-0.5 rounded border w-16 text-center ${TIER_COLORS[tier] || 'text-muted border-line'}`}>
                            {tier}
                          </span>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
