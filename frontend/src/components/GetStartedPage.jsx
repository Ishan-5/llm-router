import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { supabase } from '../supabase'
import { API_BASE } from '../config'

async function authHeaders() {
  const { data: { session } } = await supabase.auth.getSession()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session?.access_token}`,
  }
}

export default function GetStartedPage() {
  const navigate = useNavigate()
  const [apiKey, setApiKey] = useState(null)
  const [copied, setCopied] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    async function run() {
      try {
        const headers = await authHeaders()
        if (!headers.Authorization || headers.Authorization === 'Bearer null') {
          navigate('/auth', { replace: true })
          return
        }

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
      <div className="w-full max-w-lg">

        {/* Success checkmark */}
        <div className="flex items-center justify-center mb-8">
          <div className="w-12 h-12 rounded-full bg-cool/10 border border-cool/30 flex items-center justify-center">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--color-cool)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
        </div>

        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="font-display text-2xl font-semibold mb-2">You're all set</h1>
          <p className="text-sm text-muted">
            Here's your API key. Use it to route queries through any provider with automatic cost optimization.
          </p>
        </div>

        {/* API Key Card */}
        <div className="border border-signal/30 bg-signal/5 rounded-xl p-5 mb-6">
          <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-3">Your API key</p>
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

        {/* Code snippet */}
        <div className="border border-line rounded-xl overflow-hidden mb-8">
          <div className="flex items-center justify-between px-4 py-2.5 bg-panel border-b border-line">
            <p className="font-mono text-[10px] text-muted uppercase tracking-wide">Quick start</p>
            <span className="font-mono text-[10px] text-muted">cURL</span>
          </div>
          <div className="bg-base p-4 overflow-x-auto">
            <pre className="font-mono text-xs text-primary leading-relaxed whitespace-pre">{`curl -X POST ${API_BASE}/route \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${apiKey?.slice(0, 12)}..." \\
  -d '{"query": "What is 2+2?"}'`}</pre>
          </div>
        </div>

        {/* Python SDK option */}
        <div className="border border-line rounded-xl overflow-hidden mb-8">
          <div className="flex items-center justify-between px-4 py-2.5 bg-panel border-b border-line">
            <p className="font-mono text-[10px] text-muted uppercase tracking-wide">Or use the Python SDK</p>
            <span className="font-mono text-[10px] text-muted">pip install routewise</span>
          </div>
          <div className="bg-base p-4 overflow-x-auto">
            <pre className="font-mono text-xs text-primary leading-relaxed whitespace-pre">{`from routewise import RouteWiseClient

client = RouteWiseClient(api_key="${apiKey?.slice(0, 12)}...")
result = client.route("What is 2+2?")

print(result["tier"])        # cheap, mid, or frontier
print(result["response"])   # model response
print(result["cost_usd"])   # actual cost`}</pre>
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
