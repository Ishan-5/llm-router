import { useState, useEffect } from 'react'
import { fetchAdminStats, fetchAdminKeys, fetchAdminLogs, fetchAdminUsers } from '../api'

function Stat({ label, value, sub }) {
  return (
    <div className="bg-surface border border-line rounded-lg px-4 py-3">
      <div className="text-muted text-[10px] uppercase tracking-wide mb-1">{label}</div>
      <div className="text-primary font-mono text-lg font-semibold">{value}</div>
      {sub && <div className="text-muted text-[10px] mt-0.5">{sub}</div>}
    </div>
  )
}

function maskKey(key) {
  if (!key || key.length < 16) return key
  return key.slice(0, 8) + '...' + key.slice(-4)
}

export default function AdminPage() {
  const [tab, setTab] = useState('overview')
  const [stats, setStats] = useState(null)
  const [keys, setKeys] = useState([])
  const [logs, setLogs] = useState([])
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchAdminStats().catch(() => null),
      fetchAdminKeys().catch(() => []),
      fetchAdminLogs(100).catch(() => []),
      fetchAdminUsers().catch(() => []),
    ]).then(([s, k, l, u]) => {
      setStats(s)
      setKeys(k)
      setLogs(l)
      setUsers(u)
      setLoading(false)
    }).catch((e) => {
      setError(e.message)
      setLoading(false)
    })
  }, [])

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-20">
        <div className="h-4 w-24 bg-line rounded animate-pulse mb-4" />
        <div className="h-8 w-48 bg-line rounded animate-pulse mb-8" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => <div key={i} className="h-20 bg-line rounded-lg animate-pulse" />)}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-20">
        <p className="font-mono text-xs text-danger">Failed to load admin data: {error}</p>
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-20">
      <div className="flex items-center gap-3 mb-6">
        <p className="font-mono text-xs text-signal tracking-wide uppercase">Admin</p>
        <span className="font-mono text-[10px] px-2 py-0.5 rounded border border-signal/30 bg-signal/10 text-signal">admin</span>
      </div>
      <h1 className="font-display text-3xl font-semibold mb-6">System Overview</h1>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-line mb-8">
        {[
          { id: 'overview', label: 'Overview' },
          { id: 'users', label: 'Users' },
          { id: 'keys', label: 'All Keys' },
          { id: 'logs', label: 'All Logs' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 font-mono text-xs border-b-2 transition-colors ${
              tab === t.id
                ? 'border-signal text-primary'
                : 'border-transparent text-muted hover:text-primary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && stats && (
        <div className="space-y-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Total requests" value={stats.total_requests} />
            <Stat label="Total cost" value={`$${stats.total_actual_cost?.toFixed(4)}`} />
            <Stat label="Total saved" value={`$${stats.total_savings_usd?.toFixed(4)}`} />
            <Stat label="Cache hit rate" value={`${Math.round((stats.cache_hit_rate || 0) * 100)}%`} />
          </div>

          {stats.user_breakdown?.length > 0 && (
            <div>
              <h3 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-3">Cost by user</h3>
              <div className="bg-surface border border-line rounded-lg overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="text-left px-3 py-2 text-muted font-mono text-[10px] uppercase">User ID</th>
                      <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Requests</th>
                      <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.user_breakdown.map((u) => (
                      <tr key={u.user_id} className="border-b border-line/50 hover:bg-panel transition-colors">
                        <td className="px-3 py-2 font-mono text-muted truncate max-w-[200px]">{u.user_id}</td>
                        <td className="px-3 py-2 text-primary font-mono text-right">{u.requests}</td>
                        <td className="px-3 py-2 text-primary font-mono text-right">${u.cost_usd?.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {stats.tier_costs && Object.keys(stats.tier_costs).length > 0 && (
            <div>
              <h3 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-3">Cost by tier</h3>
              <div className="flex gap-4">
                {Object.entries(stats.tier_costs).map(([tier, cost]) => (
                  <div key={tier} className="bg-surface border border-line rounded-lg px-4 py-3 flex-1">
                    <p className="font-mono text-[10px] text-muted uppercase">{tier}</p>
                    <p className="font-mono text-lg font-semibold text-primary">${cost?.toFixed(4)}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'users' && (
        <div>
          {users.length === 0 ? (
            <p className="font-mono text-xs text-muted py-8">No users with API keys yet.</p>
          ) : (
            <div className="bg-surface border border-line rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-line">
                    <th className="text-left px-3 py-2 text-muted font-mono text-[10px] uppercase">User ID</th>
                    <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Keys</th>
                    <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Requests</th>
                    <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.user_id} className="border-b border-line/50 hover:bg-panel transition-colors">
                      <td className="px-3 py-2 font-mono text-muted truncate max-w-[200px]">{u.user_id}</td>
                      <td className="px-3 py-2 text-primary font-mono text-right">{u.active_keys}</td>
                      <td className="px-3 py-2 text-primary font-mono text-right">{u.total_requests}</td>
                      <td className="px-3 py-2 text-primary font-mono text-right">${u.total_cost_usd?.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'keys' && (
        <div>
          {keys.length === 0 ? (
            <p className="font-mono text-xs text-muted py-8">No API keys exist yet.</p>
          ) : (
            <div className="bg-surface border border-line rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-line">
                    <th className="text-left px-3 py-2 text-muted font-mono text-[10px] uppercase">Name</th>
                    <th className="text-left px-3 py-2 text-muted font-mono text-[10px] uppercase">Key</th>
                    <th className="text-left px-3 py-2 text-muted font-mono text-[10px] uppercase">User</th>
                    <th className="text-center px-3 py-2 text-muted font-mono text-[10px] uppercase">Status</th>
                    <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Budget</th>
                    <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {keys.map((k) => (
                    <tr key={k.id} className="border-b border-line/50 hover:bg-panel transition-colors">
                      <td className="px-3 py-2 text-primary font-medium">{k.name}</td>
                      <td className="px-3 py-2 font-mono text-muted">{maskKey(k.key)}</td>
                      <td className="px-3 py-2 font-mono text-muted truncate max-w-[120px]">{k.user_id || '—'}</td>
                      <td className="px-3 py-2 text-center">
                        <span className={`font-mono px-1.5 py-0.5 rounded text-[10px] ${k.is_active ? 'text-cool bg-cool/10' : 'text-danger bg-danger/10'}`}>
                          {k.is_active ? 'active' : 'revoked'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-primary font-mono text-right">{k.daily_budget_usd != null ? `$${k.daily_budget_usd}` : '—'}</td>
                      <td className="px-3 py-2 text-muted font-mono text-right">{k.created_at ? new Date(k.created_at).toLocaleDateString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'logs' && (
        <div>
          {logs.length === 0 ? (
            <p className="font-mono text-xs text-muted py-8">No request logs yet.</p>
          ) : (
            <div className="bg-surface border border-line rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-line">
                    <th className="text-left px-3 py-2 text-muted font-mono text-[10px] uppercase">Query</th>
                    <th className="text-left px-3 py-2 text-muted font-mono text-[10px] uppercase">Tier</th>
                    <th className="text-left px-3 py-2 text-muted font-mono text-[10px] uppercase">Model</th>
                    <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Cost</th>
                    <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Latency</th>
                    <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Key ID</th>
                    <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((l) => (
                    <tr key={l.id} className="border-b border-line/50 hover:bg-panel transition-colors">
                      <td className="px-3 py-2 text-primary truncate max-w-[200px]">{l.query}</td>
                      <td className="px-3 py-2">
                        <span className={`font-mono px-1.5 py-0.5 rounded border text-[10px] ${
                          l.tier === 'cheap' ? 'text-cool bg-cool/10 border-cool/30'
                          : l.tier === 'mid' ? 'text-signal bg-signal/10 border-signal/30'
                          : l.tier === 'frontier' ? 'text-danger bg-danger/10 border-danger/30'
                          : 'text-muted bg-panel border-line'
                        }`}>{l.tier}</span>
                      </td>
                      <td className="px-3 py-2 text-muted font-mono">{l.model_id?.split('/').pop()}</td>
                      <td className="px-3 py-2 text-primary font-mono text-right">${l.cost_usd?.toFixed(4)}</td>
                      <td className="px-3 py-2 text-primary font-mono text-right">{l.latency_ms?.toFixed(0)}ms</td>
                      <td className="px-3 py-2 text-muted font-mono text-right">{l.api_key_id}</td>
                      <td className="px-3 py-2 text-muted font-mono text-right">{l.created_at ? new Date(l.created_at).toLocaleString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
