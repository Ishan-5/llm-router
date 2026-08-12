import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { supabase } from '../supabase'
import { API_BASE } from '../config'
import Confetti from './Confetti'

const EXAMPLES = [
  { label: 'Quick check', query: 'What is 2+2?' },
  { label: 'Creative', query: 'Write a haiku about distributed systems' },
  { label: 'Hard routing', query: 'Design a distributed rate limiter' },
]

const TIER_STYLES = {
  cheap: { color: '#10B981' },
  mid: { color: '#F59E0B' },
  frontier: { color: '#8B5CF6' },
  web: { color: '#3B82F6' },
  cache: { color: '#64748B' },
}

function StepIcon({ done, active, n }) {
  return (
    <div className={`flex items-center justify-center w-8 h-8 rounded-full font-mono text-xs font-semibold transition-all duration-300 ${
      done
        ? 'bg-signal text-white'
        : active
          ? 'bg-signal/15 text-signal ring-1 ring-signal'
          : 'bg-line text-muted'
    }`}>
      {done ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      ) : n}
    </div>
  )
}

const STEP_META = [
  { label: 'Welcome', title: 'Let’s get you routing', desc: 'Three quick steps and every query you send goes to the right model automatically.' },
  { label: 'API key', title: 'Create your API key', desc: 'Your key is what calls `/route`. Keep it server-side — never in client code.' },
  { label: 'First request', title: 'Make your first request', desc: 'Send a real query through the router and watch it pick the cheapest tier that works.' },
  { label: 'Done', title: 'You’re all set', desc: 'Your key is live. Go explore.' },
]

export default function OnboardingWizard() {
  const navigate = useNavigate()
  const [phase, setPhase] = useState('loading') // loading | signedout | ready
  const [step, setStep] = useState(0)
  const [apiKey, setApiKey] = useState('')
  const [firstName, setFirstName] = useState('')
  const [copied, setCopied] = useState(false)
  const [revealed, setRevealed] = useState(false)
  const [lang, setLang] = useState('curl')
  const [celebrate, setCelebrate] = useState(false)
  const [test, setTest] = useState({ running: false, error: null, result: null })
  const [query, setQuery] = useState('')
  const [loadingKey, setLoadingKey] = useState(false)

  useEffect(() => {
    async function setup() {
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (!session?.access_token) { setPhase('signedout'); return }

        const { data: { user } } = await supabase.auth.getUser()
        const meta = user?.user_metadata || {}
        setFirstName((meta.full_name || user?.email?.split('@')[0] || '').split(' ')[0])

        const savedKey = sessionStorage.getItem('rw_onboarding_key')
        if (savedKey) {
          setApiKey(savedKey)
          setStep(Math.min(3, Number(sessionStorage.getItem('rw_onboarding_step')) || 1))
          setPhase('ready')
          return
        }

        const headers = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${session.access_token}` }
        const res = await fetch(`${API_BASE}/keys`, { headers })
        if (!res.ok) throw new Error('Failed to load keys')
        const keys = await res.json()

        let key = keys[0]?.key
        if (!key) {
          const createRes = await fetch(`${API_BASE}/keys`, {
            method: 'POST',
            headers,
            body: JSON.stringify({ name: 'My first key' }),
          })
          if (!createRes.ok) throw new Error('Failed to create key')
          key = (await createRes.json()).key
        }
        sessionStorage.setItem('rw_onboarding_key', key)
        setApiKey(key)
        setPhase('ready')
      } catch (e) {
        setPhase('ready')
      }
    }
    setup()
  }, [])

  function goTo(next) {
    if (next > 3) return
    if (next === 3) setCelebrate(true)
    setStep(next)
    sessionStorage.setItem('rw_onboarding_step', String(next))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function handleCopy() {
    if (!apiKey) return
    navigator.clipboard.writeText(apiKey).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  async function runTest(q) {
    const queryText = (q ?? query ?? '').trim()
    if (!queryText || test.running) return
    setTest({ running: true, error: null, result: null })
    try {
      const res = await fetch(`${API_BASE}/route`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${apiKey}` },
        body: JSON.stringify({ query: queryText }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }))
        throw new Error(err.detail || 'Request failed')
      }
      setTest({ running: false, result: await res.json() })
    } catch (e) {
      setTest({ running: false, error: e.message })
    }
  }

  if (phase === 'loading') {
    return (
      <div className="min-h-[70vh] flex items-center justify-center px-6">
        <div className="flex flex-col items-center gap-4">
          <div className="w-5 h-5 rounded-full bg-signal/30 animate-pulse" />
          <p className="font-mono text-xs text-muted">Setting up your workspace...</p>
        </div>
      </div>
    )
  }

  if (phase === 'signedout') {
    return (
      <div className="min-h-[70vh] flex items-center justify-center px-6">
        <div className="w-full max-w-md text-center">
          <div className="w-14 h-14 rounded-full bg-cool/10 border border-cool/30 flex items-center justify-center mx-auto auth-pulse mb-5">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--color-cool)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </div>
          <h1 className="font-display text-2xl font-semibold mb-2">Sign in to get started</h1>
          <p className="text-sm text-muted mb-8">You need an account to create an API key and start routing.</p>
          <Link
            to="/auth"
            className="inline-block bg-signal text-white font-semibold text-sm px-6 py-3 rounded-lg hover:brightness-110 transition"
          >
            Sign in or create an account
          </Link>
        </div>
      </div>
    )
  }

  const meta = STEP_META[step]
  const tier = test.result?.routed_to || test.result?.tier
  const tierStyle = TIER_STYLES[tier === 'cache' ? 'cache' : tier] || TIER_STYLES.cheap

  return (
    <div className="min-h-[70vh] flex items-start justify-center px-6 py-16">
      <div className="w-full max-w-2xl relative">
        {step === 3 && <Confetti active={celebrate} />}

        {/* Progress */}
        <div className="mb-10">
          <div className="flex items-center gap-3 mb-3">
            {STEP_META.map((s, i) => (
              <div key={s.label} className="flex items-center gap-3 flex-1 last:flex-none">
                <StepIcon done={i < step} active={i === step} n={i + 1} />
                <span className={`font-mono text-[10px] tracking-wide uppercase hidden sm:block ${i === step ? 'text-signal' : i < step ? 'text-primary' : 'text-muted'}`}>
                  {s.label}
                </span>
                {i < STEP_META.length - 1 && <div className="flex-1 h-px bg-line" />}
              </div>
            ))}
          </div>
          <div className="h-1.5 w-full bg-line rounded-full overflow-hidden">
            <div
              className="h-full bg-signal rounded-full transition-all duration-500 ease-out"
              style={{ width: `${((step + 1) / STEP_META.length) * 100}%` }}
            />
          </div>
        </div>

        {/* Content */}
        <div key={step} className="animate-[page-fade-in_0.3s_ease-out]">
          <div className="text-center mb-8">
            <h1 className="font-display text-3xl font-semibold">
              {step === 0 ? `Welcome, ${firstName || 'there'} 👋` : meta.title}
            </h1>
            <p className="text-sm text-muted mt-2 max-w-md mx-auto">{meta.desc}</p>
          </div>

          {step === 0 && (
            <>
              <div className="grid sm:grid-cols-3 gap-4 mb-8">
                {[
                  { icon: '🔑', t: 'Get an API key', d: 'One header and the router knows who you are.' },
                  { icon: '⚡', t: 'Fire your first request', d: 'See it scored and routed in real time.' },
                  { icon: '📊', t: 'Explore the dashboard', d: 'Watch traffic, cost, and tier split.' },
                ].map((item) => (
                  <div key={item.t} className="border border-line rounded-xl p-5 bg-panel/60 text-center">
                    <div className="text-2xl mb-2">{item.icon}</div>
                    <p className="text-sm font-medium text-primary mb-1">{item.t}</p>
                    <p className="text-xs text-muted leading-relaxed">{item.d}</p>
                  </div>
                ))}
              </div>
              <div className="flex justify-center">
                <button
                  onClick={() => goTo(1)}
                  className="bg-signal text-white font-semibold text-sm px-8 py-3 rounded-lg hover:brightness-110 transition"
                >
                  Create my API key →
                </button>
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <div className="border border-signal/30 bg-signal/5 rounded-xl p-5 mb-6">
                <div className="flex items-center gap-2 mb-3">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-signal">
                    <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
                  </svg>
                  <p className="font-mono text-[10px] text-signal uppercase tracking-wide">Your API key</p>
                </div>
                <div className="flex items-center gap-3">
                  <code
                    className={`font-mono text-sm text-primary break-all flex-1 bg-base border border-line rounded-lg px-4 py-3 ${revealed ? '' : 'select-none blur-sm'}`}
                  >
                    {apiKey}
                  </code>
                  <button
                    onClick={() => setRevealed((v) => !v)}
                    className="shrink-0 font-mono text-xs px-3 py-3 rounded-lg border border-line text-muted hover:text-primary hover:border-signal/50 transition"
                    title={revealed ? 'Hide key' : 'Reveal key'}
                  >
                    {revealed ? 'Hide' : 'Reveal'}
                  </button>
                  <button
                    onClick={handleCopy}
                    className="shrink-0 font-mono text-xs px-4 py-3 rounded-lg border border-signal text-signal hover:bg-signal/10 transition font-medium"
                  >
                    {copied ? 'Copied' : 'Copy'}
                  </button>
                </div>
                <p className="font-mono text-[10px] text-muted mt-3">
                  Pass it in the <code className="bg-line px-1 py-0.5 rounded">Authorization: Bearer &lt;key&gt;</code> header. It’s revealed only on demand — keep it server-side.
                </p>
              </div>
              <div className="flex justify-center">
                <button
                  onClick={() => goTo(2)}
                  className="bg-signal text-white font-semibold text-sm px-8 py-3 rounded-lg hover:brightness-110 transition"
                >
                  Make your first request →
                </button>
              </div>
            </>
          )}

          {step === 2 && (
            <>
              {/* Test runner */}
              <div className="border border-line rounded-xl p-5 mb-4 bg-panel/60">
                <p className="font-mono text-[10px] text-signal uppercase tracking-wide mb-3">Try it live</p>
                <div className="flex flex-wrap gap-2 mb-3">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex.label}
                      onClick={() => { setQuery(ex.query); setTest({ running: false, error: null, result: null }) }}
                      className="font-mono text-[11px] px-3 py-1.5 rounded-full border border-line text-muted hover:text-signal hover:border-signal/50 transition"
                    >
                      {ex.label}
                    </button>
                  ))}
                </div>
                <div className="flex gap-3">
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') runTest() }}
                    placeholder="Type any query…"
                    className="flex-1 bg-base border border-line rounded-lg px-4 py-3 text-sm text-primary placeholder:text-muted focus:outline-none focus:border-signal transition"
                  />
                  <button
                    onClick={() => runTest()}
                    disabled={test.running || !query.trim()}
                    className="shrink-0 font-mono text-xs px-5 py-3 rounded-lg bg-signal text-white hover:brightness-110 transition disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {test.running ? 'Routing…' : 'Run test'}
                  </button>
                </div>
              </div>

              {/* Result */}
              {test.error && (
                <div className="border border-danger/30 bg-danger/5 rounded-xl px-4 py-3 mb-4">
                  <p className="font-mono text-xs text-danger">{test.error}</p>
                </div>
              )}
              {test.result && !test.error && (
                <div className="border border-line rounded-xl overflow-hidden mb-4 animate-[page-fade-in_0.3s_ease-out]">
                  <div className="flex items-center justify-between flex-wrap gap-2 px-4 py-2.5 bg-panel border-b border-line">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: tierStyle.color }} />
                      <span className="font-mono text-xs font-semibold" style={{ color: tierStyle.color }}>
                        {tier?.toUpperCase()}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 font-mono text-[11px] text-muted">
                      {test.result.difficulty_score != null && (
                        <span>score <span className="text-primary">{test.result.difficulty_score.toFixed(2)}</span></span>
                      )}
                      {test.result.model_id && <span>model <span className="text-primary">{test.result.model_id}</span></span>}
                      {test.result.latency_ms != null && <span><span className="text-primary">{test.result.latency_ms}ms</span></span>}
                      {test.result.cost_usd != null && <span>$<span className="text-primary">{test.result.cost_usd.toFixed(5)}</span></span>}
                    </div>
                  </div>
                  <div className="bg-base p-4">
                    <p className="text-sm text-primary leading-relaxed whitespace-pre-wrap">{test.result.response}</p>
                  </div>
                </div>
              )}

              {/* Code snippet */}
              <div className="border border-line rounded-xl overflow-hidden mb-6">
                <div className="flex items-center justify-between px-4 py-2.5 bg-panel border-b border-line">
                  <p className="font-mono text-[10px] text-muted uppercase tracking-wide">Do it with code</p>
                  <div className="flex gap-1 p-0.5 bg-base border border-line rounded-md">
                    {['curl', 'python'].map((key) => (
                      <button
                        key={key}
                        onClick={() => setLang(key)}
                        className={`font-mono text-[10px] px-2.5 py-1 rounded transition-colors ${
                          lang === key ? 'bg-signal text-white' : 'text-muted hover:text-primary'
                        }`}
                      >
                        {key}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="bg-base p-4 overflow-x-auto">
                  {lang === 'curl' ? (
                    <pre className="font-mono text-xs text-primary leading-relaxed whitespace-pre">{`curl -X POST ${API_BASE}/route \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${apiKey.slice(0, 12)}..." \\
  -d '{"query": "${query || 'What is 2+2?'}"}'`}</pre>
                  ) : (
                    <pre className="font-mono text-xs text-primary leading-relaxed whitespace-pre">{`from routewise import RouteWiseClient

client = RouteWiseClient(api_key="${apiKey.slice(0, 12)}...")
result = client.route("${query || 'What is 2+2?'}")

print(result["tier"])        # cheap, mid, or frontier
print(result["response"])    # model response
print(result["cost_usd"])    # actual cost`}</pre>
                  )}
                </div>
              </div>

              <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
                <button
                  onClick={() => goTo(3)}
                  className="w-full sm:w-auto text-center bg-signal text-white font-semibold text-sm px-8 py-3 rounded-lg hover:brightness-110 transition"
                >
                  Finish →
                </button>
                <button
                  onClick={() => navigate('/playground')}
                  className="w-full sm:w-auto text-center font-mono text-sm text-muted border border-line px-6 py-3 rounded-lg hover:text-primary hover:border-signal/50 transition"
                >
                  Open full playground
                </button>
              </div>
            </>
          )}

          {step === 3 && (
            <>
              <div className="text-center mb-8">
                <div className="w-16 h-16 rounded-full bg-signal/10 border border-signal/40 flex items-center justify-center mx-auto auth-pulse">
                  <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="var(--color-signal)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                </div>
                <h2 className="font-display text-2xl font-semibold mt-5">All set, {firstName || 'friend'} 🎉</h2>
                <p className="text-sm text-muted mt-2 max-w-md mx-auto">
                  Every query you send now gets scored, routed to the cheapest tier that can answer it, and logged.
                </p>
              </div>
              <div className="grid sm:grid-cols-3 gap-4 mb-8">
                {[
                  { to: '/dashboard', icon: '📊', t: 'Dashboard', d: 'Live traffic, cost, tier split' },
                  { to: '/playground', icon: '🧪', t: 'Playground', d: 'Streaming, tiers, code snippets' },
                  { to: '/guide', icon: '📖', t: 'Developer guide', d: 'SDK, MCP, alerts, BYOM' },
                ].map((item) => (
                  <Link
                    key={item.t}
                    to={item.to}
                    className="border border-line rounded-xl p-5 bg-panel/60 text-center hover:border-signal/40 transition group"
                  >
                    <div className="text-2xl mb-2">{item.icon}</div>
                    <p className="text-sm font-medium text-primary mb-1 group-hover:text-signal transition">{item.t}</p>
                    <p className="text-xs text-muted leading-relaxed">{item.d}</p>
                  </Link>
                ))}
              </div>
              <div className="text-center">
                <button
                  onClick={() => { sessionStorage.removeItem('rw_onboarding_key'); sessionStorage.removeItem('rw_onboarding_step'); window.location.reload() }}
                  className="font-mono text-xs text-muted hover:text-primary transition"
                >
                  Start over
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
