import { useEffect, useState } from 'react'
import { fetchAnalytics } from '../api'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, CartesianGrid,
} from 'recharts'

const TIER_COLORS = { cheap: '#38bdf8', mid: '#facc15', frontier: '#f87171' }
const PIE_COLORS = ['#38bdf8', '#facc15', '#f87171', '#a78bfa', '#34d399', '#fb923c', '#94a3b8']

function Stat({ label, value, sub }) {
  return (
    <div className="bg-surface border border-line rounded-lg px-4 py-3">
      <div className="text-muted text-[10px] uppercase tracking-wide mb-1">{label}</div>
      <div className="text-white font-mono text-lg font-semibold">{value}</div>
      {sub && <div className="text-muted text-[10px] mt-0.5">{sub}</div>}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="space-y-2">
      <h4 className="font-mono text-[10px] text-muted uppercase tracking-wide">{title}</h4>
      {children}
    </div>
  )
}

function TooltipStyle({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-panel border border-line rounded-lg px-3 py-2 text-xs font-mono">
      <div className="text-muted mb-1">{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color }} className="flex justify-between gap-4">
          <span>{p.name}</span>
          <span>{typeof p.value === 'number' && p.name?.includes('cost') ? `$${p.value.toFixed(4)}` : p.value}</span>
        </div>
      ))}
    </div>
  )
}

export default function CostAnalytics({ apiKey }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchAnalytics(apiKey).then(setData).catch((e) => setError(e.message))
  }, [apiKey])

  if (error) return <p className="font-mono text-xs text-danger">Failed to load analytics: {error}</p>
  if (!data) return <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-20 bg-line rounded-lg animate-pulse" />)}</div>

  const { summary, tier_costs, model_costs, daily, latency_by_tier, top_expensive } = data

  const tierPieData = Object.entries(tier_costs).map(([name, value]) => ({ name, value: Math.round(value * 10000) / 10000 }))
  const modelBarData = Object.entries(model_costs)
    .map(([name, value]) => ({ name: name.split('/').pop(), fullName: name, cost: Math.round(value * 10000) / 10000 }))
    .sort((a, b) => b.cost - a.cost)

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Total Spent" value={`$${summary.total_cost.toFixed(4)}`} />
        <Stat label="Savings" value={`$${summary.savings.toFixed(4)}`} sub={`${summary.savings_pct}% vs frontier`} />
        <Stat label="Cache Hit Rate" value={`${summary.cache_hit_rate}%`} sub={`$${summary.cache_savings.toFixed(4)} saved`} />
        <Stat label="Fallback Rate" value={`${summary.fallback_rate}%`} />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cost Over Time */}
        {daily.length > 0 && (
          <Section title="Cost Over Time">
            <div className="bg-surface border border-line rounded-lg p-4 h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={daily}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#64748b' }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis tick={{ fontSize: 10, fill: '#64748b' }} tickFormatter={(v) => `$${v}`} width={55} />
                  <Tooltip content={<TooltipStyle />} />
                  <Line type="monotone" dataKey="cost" stroke="#facc15" strokeWidth={2} dot={false} name="cost_usd" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Section>
        )}

        {/* Cost by Tier (Pie) */}
        {tierPieData.length > 0 && (
          <Section title="Cost by Tier">
            <div className="bg-surface border border-line rounded-lg p-4 h-56 flex items-center">
              <ResponsiveContainer width="50%" height="100%">
                <PieChart>
                  <Pie data={tierPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} innerRadius={35}>
                    {tierPieData.map((entry) => (
                      <Cell key={entry.name} fill={TIER_COLORS[entry.name] || '#64748b'} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => `$${v.toFixed(4)}`} contentStyle={{ bg: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 11, fontFamily: 'monospace' }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-1.5 pl-2">
                {tierPieData.map((d) => (
                  <div key={d.name} className="flex items-center gap-2 text-xs">
                    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: TIER_COLORS[d.name] || '#64748b' }} />
                    <span className="text-muted flex-1">{d.name}</span>
                    <span className="font-mono text-white">${d.value.toFixed(4)}</span>
                  </div>
                ))}
              </div>
            </div>
          </Section>
        )}

        {/* Cost by Model (Bar) */}
        {modelBarData.length > 0 && (
          <Section title="Cost by Model">
            <div className="bg-surface border border-line rounded-lg p-4 h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={modelBarData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis type="number" tick={{ fontSize: 10, fill: '#64748b' }} tickFormatter={(v) => `$${v}`} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: '#64748b' }} width={100} />
                  <Tooltip content={<TooltipStyle />} />
                  <Bar dataKey="cost" fill="#38bdf8" radius={[0, 4, 4, 0]} name="cost_usd" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Section>
        )}

        {/* Latency by Tier */}
        {Object.keys(latency_by_tier).length > 0 && (
          <Section title="Avg Latency by Tier">
            <div className="bg-surface border border-line rounded-lg p-4">
              <div className="space-y-3">
                {Object.entries(latency_by_tier).map(([tier, ms]) => (
                  <div key={tier} className="flex items-center gap-3">
                    <span className={`font-mono text-xs px-2 py-0.5 rounded border ${
                      tier === 'cheap' ? 'text-cool bg-cool/10 border-cool/30'
                      : tier === 'mid' ? 'text-signal bg-signal/10 border-signal/30'
                      : 'text-danger bg-danger/10 border-danger/30'
                    }`}>{tier}</span>
                    <div className="flex-1 bg-line rounded-full h-2">
                      <div
                        className="h-2 rounded-full transition-all"
                        style={{
                          width: `${Math.min(100, (ms / 5000) * 100)}%`,
                          background: tier === 'cheap' ? '#38bdf8' : tier === 'mid' ? '#facc15' : '#f87171',
                        }}
                      />
                    </div>
                    <span className="font-mono text-xs text-white w-16 text-right">{ms.toFixed(0)}ms</span>
                  </div>
                ))}
              </div>
            </div>
          </Section>
        )}
      </div>

      {/* Top Expensive Queries */}
      {top_expensive.length > 0 && (
        <Section title="Most Expensive Queries">
          <div className="bg-surface border border-line rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-line">
                  <th className="text-left px-3 py-2 text-muted font-mono text-[10px] uppercase">Query</th>
                  <th className="text-left px-3 py-2 text-muted font-mono text-[10px] uppercase">Tier</th>
                  <th className="text-left px-3 py-2 text-muted font-mono text-[10px] uppercase">Model</th>
                  <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Tokens</th>
                  <th className="text-right px-3 py-2 text-muted font-mono text-[10px] uppercase">Cost</th>
                </tr>
              </thead>
              <tbody>
                {top_expensive.map((r) => (
                  <tr key={r.id} className="border-b border-line/50 hover:bg-panel transition-colors">
                    <td className="px-3 py-2 text-white truncate max-w-[200px]">{r.query}</td>
                    <td className="px-3 py-2">
                      <span className={`font-mono px-1.5 py-0.5 rounded border text-[10px] ${
                        r.tier === 'cheap' ? 'text-cool bg-cool/10 border-cool/30'
                        : r.tier === 'mid' ? 'text-signal bg-signal/10 border-signal/30'
                        : 'text-danger bg-danger/10 border-danger/30'
                      }`}>{r.tier}</span>
                    </td>
                    <td className="px-3 py-2 text-muted font-mono">{r.model?.split('/').pop()}</td>
                    <td className="px-3 py-2 text-white font-mono text-right">{r.tokens?.toLocaleString()}</td>
                    <td className="px-3 py-2 text-white font-mono text-right">${r.cost?.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </div>
  )
}
