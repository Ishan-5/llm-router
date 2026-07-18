import { useEffect, useState } from 'react'
import { fetchPricing } from '../api'
import TopModels from './TopModels'

const PROVIDER_ORDER = ['groq', 'openai', 'anthropic', 'gemini', 'deepseek', 'mistral', 'perplexity', 'xai', 'ollama']
const PROVIDER_LABELS = {
  groq: 'Groq', openai: 'OpenAI', anthropic: 'Anthropic', gemini: 'Google Gemini',
  deepseek: 'DeepSeek', mistral: 'Mistral', perplexity: 'Perplexity', xai: 'xAI', ollama: 'Ollama (local)',
}

export default function PricingTable({ onBack }) {
  const [pricing, setPricing] = useState([])
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('')
  const [activeProvider, setActiveProvider] = useState('all')

  useEffect(() => {
    fetchPricing().then(setPricing).catch((e) => setError(e.message))
  }, [])

  const providers = PROVIDER_ORDER.filter((p) => pricing.some((r) => r.provider === p))

  const filtered = pricing.filter((r) => {
    const matchProvider = activeProvider === 'all' || r.provider === activeProvider
    const matchSearch = !filter || r.model_id.toLowerCase().includes(filter.toLowerCase()) || r.display_name.toLowerCase().includes(filter.toLowerCase())
    return matchProvider && matchSearch
  })

  const grouped = {}
  filtered.forEach((r) => {
    if (!grouped[r.provider]) grouped[r.provider] = []
    grouped[r.provider].push(r)
  })

  return (
    <section id="pricing" className="max-w-6xl mx-auto px-6 py-20 border-t border-line">
      <div className="flex items-center gap-4 mb-3">
        <button onClick={onBack} className="font-mono text-xs text-muted hover:text-primary transition-colors flex items-center gap-1">
          ← Back
        </button>
        <p className="font-mono text-xs text-signal tracking-wide uppercase">Models & Pricing</p>
      </div>
      <h2 className="font-display text-2xl font-semibold mb-2">Top picks & full pricing</h2>
      <p className="text-sm text-muted mb-10">
        Curated recommendations for every use case, plus complete pricing for all supported models.
      </p>

      {/* Top Models recommendations */}
      <TopModels />

      {/* Full pricing table */}
      <div className="border-t border-line pt-10">
        <h3 className="font-display text-xl font-semibold mb-2">All models & prices</h3>
        <p className="text-sm text-muted mb-8">
          Prices in USD per million tokens. Updated manually — verify with provider before billing.
        </p>

        {error && (
          <p className="font-mono text-xs text-danger mb-6">
            Couldn't load pricing — make sure the backend is running. ({error})
          </p>
        )}

        {/* filters */}
        <div className="flex flex-wrap gap-3 mb-8">
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search models..."
            className="bg-panel border border-line rounded-lg px-3 py-2 font-mono text-xs placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50 w-48"
          />
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setActiveProvider('all')}
              className={`font-mono text-xs px-3 py-1.5 rounded-full border transition-colors ${
                activeProvider === 'all' ? 'border-signal bg-signal/10 text-signal' : 'border-line text-muted hover:border-signal hover:text-signal'
              }`}
            >
              All
            </button>
            {providers.map((p) => (
              <button
                key={p}
                onClick={() => setActiveProvider(p)}
                className={`font-mono text-xs px-3 py-1.5 rounded-full border transition-colors ${
                  activeProvider === p ? 'border-signal bg-signal/10 text-signal' : 'border-line text-muted hover:border-signal hover:text-signal'
                }`}
              >
                {PROVIDER_LABELS[p] || p}
              </button>
            ))}
          </div>
        </div>

        {/* tables grouped by provider */}
        <div className="flex flex-col gap-10">
          {(activeProvider === 'all' ? providers : [activeProvider])
            .filter((p) => grouped[p]?.length > 0)
            .map((provider) => (
              <div key={provider}>
                <h3 className="font-display font-semibold text-base mb-3">{PROVIDER_LABELS[provider] || provider}</h3>
                <div className="overflow-x-auto rounded-lg border border-line">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr className="border-b border-line bg-panel2/50">
                        <th className="text-left px-4 py-3 text-muted font-medium text-[11px] uppercase tracking-wide">Model</th>
                        <th className="text-right px-4 py-3 text-muted font-medium text-[11px] uppercase tracking-wide">Input / 1M</th>
                        <th className="text-right px-4 py-3 text-muted font-medium text-[11px] uppercase tracking-wide">Output / 1M</th>
                        <th className="text-left px-4 py-3 text-muted font-medium text-[11px] uppercase tracking-wide hidden md:table-cell">Notes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {grouped[provider].map((row, i) => (
                        <tr key={row.model_id} className={`border-b border-line last:border-0 hover:bg-panel2/30 transition-colors ${i % 2 === 0 ? '' : 'bg-panel/50'}`}>
                          <td className="px-4 py-3 text-primary">{row.display_name}</td>
                          <td className="px-4 py-3 text-right text-cool">
                            {row.price_per_m_input === 0 ? 'free' : `$${row.price_per_m_input.toFixed(2)}`}
                          </td>
                          <td className="px-4 py-3 text-right text-signal">
                            {row.price_per_m_output === 0 ? 'free' : `$${row.price_per_m_output.toFixed(2)}`}
                          </td>
                          <td className="px-4 py-3 text-muted hidden md:table-cell">{row.notes || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
        </div>

        {filtered.length === 0 && !error && (
          <p className="font-mono text-xs text-muted text-center py-12">No models match your search.</p>
        )}
      </div>
    </section>
  )
}
