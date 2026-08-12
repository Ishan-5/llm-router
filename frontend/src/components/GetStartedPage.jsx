import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { supabase } from '../supabase'
import { API_BASE } from '../config'
import Confetti from './Confetti'

async function authHeaders() {
  const { data: { session } } = await supabase.auth.getSession()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session?.access_token}`,
  }
}

const STEPS = [
  {
    n: '01',
    title: 'Copy your API key',
    desc: 'It lives above. Store it server-side — never ship it in client code.',
  },
  {
    n: '02',
    title: 'Make your first request',
    desc: 'One header, one query. routewise scores it, picks the tier, and returns the response + cost.',
  },
  {
    n: '03',
    title: 'Explore the dashboard',
    desc: 'Watch live traffic split across cheap, mid, and frontier — and what it costs.',
  },
]

export default function GetStartedPage() {
  const navigate = useNavigate()
  const [apiKey, setApiKey] = useState(null)
  const [copied, setCopied] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [firstName, setFirstName] = useState('')
  const [celebrate, setCelebrate] = useState(true)
  const [lang, setLang] = useState('curl')

  useEffect(() => {
    const t = setTimeout(() => setCelebrate(false), 2200)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    async function run() {
      try {
        const headers = await authHeaders()
        if (!headers.Authorization || headers.Authorization === 'Bearer null') {
          navigate('/auth', { replace: true })
          return
        }

        const { data: { user } } = await supabase.auth.getUser()
        const meta = user?.user_metadata || {}
        setFirstName((meta.full_name || user?.email?.split('@')[0] || '').split(' ')[0])

        const res = await fetch(`${API_BASE}/keys`, { headers })
        if (!res.ok) throw new Error('Failed to load keys')
        const keys = await res.json()

        if (keys.length > 0) {
          setApiKey(keys[0].key)
        } else {
          const createRes = await fetch(`${API_BASE}/keys`, {
            method: 'POST',
            headers,
            body: JSON.stringify({ name: 'My first key' }),
          })
          if (!createRes.ok) throw new Error('Failed to create key')
          const data = await createRes.json()
          setApiKey(data.key)
        }
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    run()
  }, [navigate])

  function handleCopy() {
    if (!apiKey) return
    navigator.clipboard.writeText(apiKey).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  if (loading) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center px-6">
        <div className="w-full max-w-md flex flex-col items-center gap-4">
          <div className="w-5 h-5 rounded-full bg-signal/30 animate-pulse" />
          <p className="font-mono text-xs text-muted">Setting up your API key...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center px-6">
        <div className="w-full max-w-md text-center">
          <p className="font-mono text-xs text-danger mb-4">{error}</p>
          <Link to="/dashboard" className="font-mono text-xs text-signal hover:underline">
            Go to dashboard →
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-6 py-16">
      <div className="w-full max-w-xl relative">
        <Confetti active={celebrate} />

        {/* Header */}
        <div className="text-center mb-10">
          <div className="w-14 h-14 rounded-full bg-cool/10 border border-cool/30 flex items-center justify-center mx-auto auth-pulse">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--color-cool)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <h1 className="font-display text-3xl font-semibold mt-5">
            {firstName ? `Welcome to routewise, ${firstName}` : "You're all set"}
          </h1>
          <p className="text-sm text-muted mt-2 max-w-md mx-auto">
            Your API key is ready — one header and every query goes to the right model, automatically.
          </p>
        </div>

        {/* API Key Card */}
        <div className="border border-signal/30 bg-signal/5 rounded-xl p-5 mb-8">
          <div className="flex items-center gap-2 mb-3">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-signal">
              <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
            </svg>
            <p className="font-mono text-[10px] text-signal uppercase tracking-wide">Your API key</p>
          </div>
          <div className="flex items-center gap-3">
            <code className="font-mono text-sm text-primary break-all flex-1 bg-base border border-line rounded-lg px-4 py-3">
              {apiKey}
            </code>
            <button
              onClick={handleCopy}
              className="shrink-0 font-mono text-xs px-4 py-3 rounded-lg border border-signal text-signal hover:bg-signal/10 transition font-medium"
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <p className="font-mono text-[10px] text-muted mt-3">
            Pass this in the <code className="bg-line px-1 py-0.5 rounded">Authorization: Bearer &lt;key&gt;</code> header.
          </p>
        </div>

        {/* Next steps */}
        <div className="grid sm:grid-cols-3 gap-4 mb-8">
          {STEPS.map((step) => (
            <div key={step.n} className="border border-line rounded-xl p-4 bg-panel/60">
              <span className="font-mono text-[10px] text-signal font-semibold">{step.n}</span>
              <p className="text-sm font-medium text-primary mt-2">{step.title}</p>
              <p className="text-xs text-muted mt-1 leading-relaxed">{step.desc}</p>
            </div>
          ))}
        </div>

        {/* Code snippet with tabs */}
        <div className="border border-line rounded-xl overflow-hidden mb-8">
          <div className="flex items-center justify-between px-4 py-2.5 bg-panel border-b border-line">
            <p className="font-mono text-[10px] text-muted uppercase tracking-wide">Quick start</p>
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
  -H "Authorization: Bearer ${apiKey?.slice(0, 12)}..." \\
  -d '{"query": "What is 2+2?"}'`}</pre>
            ) : (
              <pre className="font-mono text-xs text-primary leading-relaxed whitespace-pre">{`from routewise import RouteWiseClient

client = RouteWiseClient(api_key="${apiKey?.slice(0, 12)}...")
result = client.route("What is 2+2?")

print(result["tier"])        # cheap, mid, or frontier
print(result["response"])   # model response
print(result["cost_usd"])   # actual cost`}</pre>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-col sm:flex-row items-center gap-3">
          <Link
            to="/dashboard"
            className="w-full sm:w-auto text-center bg-signal text-white font-semibold text-sm px-6 py-3 rounded-lg hover:brightness-110 transition"
          >
            Go to Dashboard
          </Link>
          <Link
            to="/playground"
            className="w-full sm:w-auto text-center font-mono text-sm text-muted border border-line px-6 py-3 rounded-lg hover:text-primary hover:border-signal/50 transition"
          >
            Try the Playground
          </Link>
        </div>
      </div>
    </div>
  )
}
