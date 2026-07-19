import { useState, useEffect } from 'react'
import { supabase } from '../supabase'
import { API_BASE } from '../config'
import { fetchLogs, fetchLogDetail, fetchAnalytics } from '../api'
import RequestLogs from './RequestLogs'
import CostAnalytics from './CostAnalytics'
import ApiPlayground from './ApiPlayground'

async function authHeaders() {
  const { data: { session } } = await supabase.auth.getSession()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session?.access_token}`,
  }
}

export default function DashboardPage() {
  const [keys, setKeys] = useState([])
  const [keyName, setKeyName] = useState('')
  const [newKey, setNewKey] = useState(null)
  const [loadingKeys, setLoadingKeys] = useState(true)
  const [creating, setCreating] = useState(false)
  const [revoking, setRevoking] = useState(null)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)
  const [activeTab, setActiveTab] = useState('keys')
  const [selectedKeyId, setSelectedKeyId] = useState(null)

  useEffect(() => { loadKeys() }, [])

  useEffect(() => {
    if (keys.length > 0 && !selectedKeyId) {
      setSelectedKeyId(keys[0].id)
    }
  }, [keys])

  async function loadKeys() {
    setLoadingKeys(true)
    const headers = await authHeaders()
    const res = await fetch(`${API_BASE}/keys`, { headers })
    if (res.ok) setKeys(await res.json())
    setLoadingKeys(false)
  }

  async function handleCreate(e) {
    e.preventDefault()
    if (!keyName.trim()) return
    setCreating(true)
    setError(null)
    setNewKey(null)
    const headers = await authHeaders()
    const res = await fetch(`${API_BASE}/keys`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ name: keyName.trim() }),
    })
    if (res.ok) {
      const data = await res.json()
      setNewKey(data.key)
      setKeyName('')
      loadKeys()
    } else {
      const err = await res.json().catch(() => ({}))
      setError(err.detail || 'Failed to create key')
    }
    setCreating(false)
  }

  async function handleRevoke(id) {
    const safeId = Math.floor(Number(id))
    if (!Number.isFinite(safeId) || safeId <= 0) return
    setRevoking(id)
    const headers = await authHeaders()
    await fetch(`${API_BASE}/keys/${safeId}`, { method: 'DELETE', headers })
    setKeys((prev) => prev.filter((k) => k.id !== id))
    if (selectedKeyId === id) setSelectedKeyId(keys.find((k) => k.id !== id)?.id || null)
    setRevoking(null)
  }

  function copyKey(key) {
    navigator.clipboard.writeText(key).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  function maskKey(key) {
    if (!key || key.length < 16) return key
    return key.slice(0, 8) + '...' + key.slice(-4)
  }

  const selectedKey = keys.find((k) => k.id === selectedKeyId)
  const hasKeys = keys.length > 0

  return (
    <div className="max-w-5xl mx-auto px-6 py-20">
      <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4">Dashboard</p>
      <h1 className="font-display text-3xl font-semibold mb-6">Dashboard</h1>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-line mb-8">
        {[
          { id: 'keys', label: 'API Keys' },
          ...(hasKeys ? [
            { id: 'playground', label: 'Playground' },
            { id: 'analytics', label: 'Analytics' },
            { id: 'logs', label: 'Request Logs' },
          ] : []),
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2.5 font-mono text-xs border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-signal text-primary'
                : 'border-transparent text-muted hover:text-primary'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'keys' && (
        <>
          <p className="text-muted text-sm mb-8">
            Use these keys in the <code className="font-mono text-xs bg-line px-1.5 py-0.5 rounded">Authorization: Bearer &lt;key&gt;</code> header when calling <code className="font-mono text-xs bg-line px-1.5 py-0.5 rounded">/route</code>.
          </p>

          {/* Create key */}
          <form onSubmit={handleCreate} className="flex gap-3 mb-8">
            <input
              type="text"
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              placeholder="Key name (e.g. my-app)"
              className="flex-1 bg-panel border border-line rounded-lg px-4 py-3 font-body text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50 focus:border-signal"
            />
            <button
              type="submit"
              disabled={creating}
              className="bg-signal text-white font-semibold text-sm px-5 py-3 rounded-lg hover:brightness-110 transition disabled:opacity-50 whitespace-nowrap"
            >
              {creating ? 'Creating…' : 'Generate key'}
            </button>
          </form>

          {error && <p className="font-mono text-xs text-danger mb-4">{error}</p>}

          {/* Newly created key — show once */}
          {newKey && (
            <div className="border border-signal/40 bg-signal/5 rounded-lg p-4 mb-8">
              <p className="font-mono text-[10px] text-signal uppercase tracking-wide mb-2">Copy your key — you can view it anytime from the keys list</p>
              <div className="flex items-center gap-3">
                <code className="font-mono text-xs text-primary break-all flex-1">{newKey}</code>
                <button
                  onClick={() => copyKey(newKey)}
                  className="font-mono text-[10px] px-3 py-1.5 rounded border border-line text-muted hover:text-primary hover:border-signal/50 transition shrink-0"
                >
                  {copied ? 'copied ✓' : 'copy'}
                </button>
              </div>
            </div>
          )}

          {/* Key list */}
          <div className="border-t border-line">
            {loadingKeys ? (
              <div className="py-8 flex flex-col gap-3">
                {[1, 2].map((i) => (
                  <div key={i} className="h-12 bg-line rounded-lg animate-pulse" />
                ))}
              </div>
            ) : keys.length === 0 ? (
              <p className="font-mono text-xs text-muted py-8">No keys yet — generate one above.</p>
            ) : (
              keys.map((k) => (
                <div key={k.id} className="flex items-center justify-between py-4 border-b border-line gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="font-body text-sm font-medium">{k.name}</p>
                    <p className="font-mono text-[10px] text-muted">{maskKey(k.key)}</p>
                    <p className="font-mono text-[10px] text-muted">created {new Date(k.created_at).toLocaleDateString()}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => copyKey(k.key)}
                      className="font-mono text-[10px] px-3 py-1.5 rounded border border-line text-muted hover:text-primary hover:border-signal/50 transition"
                    >
                      {copied ? 'copied ✓' : 'copy'}
                    </button>
                    <button
                      onClick={() => handleRevoke(k.id)}
                      disabled={revoking === k.id}
                      className="font-mono text-[10px] px-3 py-1.5 rounded border border-danger/40 text-danger hover:bg-danger/10 transition disabled:opacity-50"
                    >
                      {revoking === k.id ? 'revoking…' : 'revoke'}
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </>
      )}

      {activeTab === 'playground' && hasKeys && <ApiPlayground />}

      {activeTab === 'analytics' && hasKeys && (
        <div>
          {/* Key selector */}
          {keys.length > 1 && (
            <div className="flex items-center gap-3 mb-6">
              <label className="font-mono text-[10px] text-muted uppercase tracking-wide">Viewing key:</label>
              <select
                value={selectedKeyId || ''}
                onChange={(e) => setSelectedKeyId(Number(e.target.value))}
                className="bg-surface border border-line rounded px-2 py-1 text-xs text-primary font-mono"
              >
                {keys.map((k) => (
                  <option key={k.id} value={k.id}>{k.name} ({maskKey(k.key)})</option>
                ))}
              </select>
            </div>
          )}
          <CostAnalytics apiKey={selectedKey?.key} />
        </div>
      )}

      {activeTab === 'logs' && hasKeys && (
        <div>
          {/* Key selector */}
          {keys.length > 1 && (
            <div className="flex items-center gap-3 mb-6">
              <label className="font-mono text-[10px] text-muted uppercase tracking-wide">Viewing key:</label>
              <select
                value={selectedKeyId || ''}
                onChange={(e) => setSelectedKeyId(Number(e.target.value))}
                className="bg-surface border border-line rounded px-2 py-1 text-xs text-primary font-mono"
              >
                {keys.map((k) => (
                  <option key={k.id} value={k.id}>{k.name} ({maskKey(k.key)})</option>
                ))}
              </select>
            </div>
          )}
          <RequestLogs apiKey={selectedKey?.key} />
        </div>
      )}
    </div>
  )
}
