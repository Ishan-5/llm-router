const FEATURES = [
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-signal">
        <line x1="12" y1="1" x2="12" y2="23" />
        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
      </svg>
    ),
    title: 'Cost savings',
    body: 'Routes trivial queries to cheap models, complex ones to frontier. Most requests never touch an expensive API.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-cool">
        <path d="M12 2a10 10 0 1 0 10 10" />
        <path d="M12 2a10 10 0 0 1 10 10" />
        <polyline points="12 6 12 12 16 14" />
      </svg>
    ),
    title: 'Semantic cache',
    body: 'Near-duplicate queries are served from cache instantly. Zero latency, zero cost for repeated questions.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-signal">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
      </svg>
    ),
    title: 'Auto-fallback',
    body: 'If a tier fails or rate-limits, the router steps down to the next tier automatically. No dropped requests.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-cool">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
    title: 'Security screening',
    body: 'PII detection and prompt-injection blocking. Bad input is rejected before it ever reaches a model.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-signal">
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
        <line x1="8" y1="21" x2="16" y2="21" />
        <line x1="12" y1="17" x2="12" y2="21" />
      </svg>
    ),
    title: 'Bring your own models',
    body: 'Plug in any OpenAI-compatible endpoint — Ollama, vLLM, custom providers. Switch between built-in and BYOM in one click.',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-cool">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    ),
    title: 'Multi-user ready',
    body: 'Per-user API keys with scoped logs, usage analytics, and budget controls. Admin dashboard for full visibility.',
  },
]

export default function Features() {
  return (
    <section className="max-w-6xl mx-auto px-6 py-16">
      <div className="mb-10">
        <p className="font-mono text-xs text-signal tracking-wide uppercase mb-2">What we offer</p>
        <h2 className="font-display text-2xl font-semibold text-primary mb-2">Built for production</h2>
        <p className="text-sm text-muted max-w-lg">Everything you need to route LLM traffic intelligently — from cost optimization to security.</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {FEATURES.map((f) => (
          <div key={f.title} className="border border-line rounded-lg p-5 bg-panel hover:border-signal/30 transition-colors group">
            <div className="w-9 h-9 rounded-md bg-surface border border-line flex items-center justify-center mb-4 group-hover:border-signal/30 transition-colors">
              {f.icon}
            </div>
            <h3 className="text-sm font-semibold text-primary mb-1.5">{f.title}</h3>
            <p className="text-xs text-muted leading-relaxed">{f.body}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
