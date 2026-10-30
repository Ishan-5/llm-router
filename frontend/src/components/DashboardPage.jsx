import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../supabase'
import { API_BASE } from '../config'
import { fetchLogs, fetchLogDetail, fetchAnalytics, fetchTeams } from '../api'
import RequestLogs from './RequestLogs'
import CostAnalytics from './CostAnalytics'
import ApiPlayground from './ApiPlayground'
import TeamsTab from './TeamsTab'

async function authHeaders() {
  const { data: { session } } = await supabase.auth.getSession()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session?.access_token}`,
  }
}

const ALERT_TYPES = [
  { value: 'daily_spend', label: 'Daily Spend', unit: '$', placeholder: '1.00', hint: 'Alert when daily spend exceeds this amount in USD' },
  { value: 'error_rate', label: 'Error Rate', unit: '%', placeholder: '5', hint: 'Alert when error rate exceeds this % in the last hour' },
  { value: 'latency', label: 'Avg Latency', unit: 'ms', placeholder: '3000', hint: 'Alert when average latency exceeds this in the last hour' },
]

// A key's cap state, in the same three colours the rest of the dashboard uses.
const BUDGET_CHIP = {
  ok: 'text-cool bg-cool/10 border-cool/30',
  warning: 'text-signal bg-signal/10 border-signal/30',
  exhausted: 'text-danger bg-danger/10 border-danger/30',
}

function describeBudget(budget) {
  if (!budget || budget.state === 'unlimited') return null
  if (budget.state === 'exhausted') {
    return { text: 'budget exhausted · routing cheap', cls: BUDGET_CHIP.exhausted }
  }
  if (budget.state === 'warning') {
    return { text: `${budget.percent_used}% of budget used`, cls: BUDGET_CHIP.warning }
  }
  return { text: `${budget.percent_used}% of budget used`, cls: BUDGET_CHIP.ok }
}

function StatTile({ label, value, hint, accent = 'text-muted' }) {
  return (
    <div className="rounded-xl border border-line bg-base/60 px-4 py-3.5">
      <div className="flex items-center gap-1.5">
        <span className={`h-1.5 w-1.5 rounded-full bg-current ${accent}`} aria-hidden />
        <p className="font-mono text-[10px] uppercase tracking-wide text-muted">{label}</p>
      </div>
      <p className="font-display text-2xl font-semibold mt-1.5 text-primary">{value}</p>
      <p className="font-mono text-[10px] text-muted mt-0.5 truncate">{hint}</p>
    </div>
  )
}

function summarizeBudget(keys) {
  const states = keys.map((k) => k.budget?.state).filter((s) => s && s !== 'unlimited')
  const exhausted = states.filter((s) => s === 'exhausted').length
  const warning = states.filter((s) => s === 'warning').length
  if (exhausted > 0) {
    return {
      label: 'Exhausted',
      hint: `${exhausted} ${exhausted === 1 ? 'key is' : 'keys are'} routing cheap`,
      accent: 'text-danger',
    }
  }
  if (warning > 0) {
    return {
      label: 'Warning',
      hint: `${warning} ${warning === 1 ? 'key is' : 'keys are'} past 80%`,
      accent: 'text-signal',
    }
  }
  if (states.length === 0) {
    return { label: 'Unlimited', hint: 'no caps set yet', accent: 'text-muted' }
  }
  return {
    label: 'On track',
    hint: `${states.length} ${states.length === 1 ? 'key' : 'keys'} under cap`,
    accent: 'text-cool',
  }
}

const TAB_META = {
  overview: {
    eyebrow: 'FinOps console',
    title: 'Workspace overview',
    sub: 'Spend, budget health and the routing decisions behind them.',
  },
  keys: {
    eyebrow: 'Access',
    title: 'API keys',
    sub: 'One key per person or service. Caps are optional; exhausted keys keep working.',
  },
  teams: {
    eyebrow: 'Governance',
    title: 'Teams',
    sub: 'Shared monthly budgets. The tightest cap decides which tier answers.',
  },
  analytics: {
    eyebrow: 'Cost',
    title: 'Analytics',
    sub: 'Where the money went, and what routing saved.',
  },
  logs: {
    eyebrow: 'Audit',
    title: 'Request logs',
    sub: 'Every request, the tier it used and why it was downgraded.',
  },
  playground: {
    eyebrow: 'Try it',
    title: 'Playground',
    sub: 'Send a live query and watch the router pick a tier.',
  },
  alerts: {
    eyebrow: 'Ops',
    title: 'Alerts',
    sub: 'Webhooks for spend, error rate and latency thresholds.',
  },
}

function Panel({ title, action, children, className = '' }) {
  return (
    <section className={`rounded-2xl border border-line bg-surface shadow-card ${className}`}>
      <div className="flex items-center justify-between gap-3 px-4 sm:px-5 pt-4 pb-3 border-b border-line/70">
        <h2 className="font-display text-sm font-semibold text-primary">{title}</h2>
        {action}
      </div>
      <div className="p-4 sm:p-5">{children}</div>
    </section>
  )
}

function PanelLink({ onClick, children }) {
  return (
    <button
      onClick={onClick}
      className="font-mono text-[10px] text-muted hover:text-signal transition-colors"
    >
      {children}
    </button>
  )
}

function KeySwitcher({ keys, selectedKeyId, onChange, mask }) {
  if (keys.length < 2) return null
  return (
    <label className="flex items-center gap-2 font-mono text-[10px] text-muted">
      key
      <select
        value={selectedKeyId || ''}
        onChange={(e) => onChange(Number(e.target.value))}
        className="bg-base border border-line rounded px-2 py-1 text-[10px] text-primary font-mono focus:outline-none focus:ring-1 focus:ring-signal/50"
      >
        {keys.map((k) => (
          <option key={k.id} value={k.id}>{k.name} ({mask(k.key)})</option>
        ))}
      </select>
    </label>
  )
}

function TeamBudgetBar({ team }) {
  const hasCap = team.monthly_budget_usd != null
  const pct = Math.min(100, Math.max(0, Number(team.percent_used) || 0))
  const tone =
    team.state === 'exhausted'
      ? 'bg-danger'
      : team.state === 'warning'
        ? 'bg-signal'
        : 'bg-cool'
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <p className="font-body text-xs text-primary truncate">{team.name}</p>
        <p className="font-mono text-[10px] text-muted shrink-0">
          ${Number(team.spent_this_month || 0).toFixed(2)}
          {hasCap ? ` / $${Number(team.monthly_budget_usd).toFixed(2)}` : ' spent'}
        </p>
      </div>
      <div className="mt-1.5 h-1.5 rounded-full bg-line overflow-hidden">
        <div
          className={`h-full rounded-full ${hasCap ? tone : 'bg-muted/40'}`}
          style={{ width: `${hasCap ? pct : 0}%` }}
        />
      </div>
      <p className="font-mono text-[10px] text-muted mt-1">
        {hasCap
          ? team.state === 'exhausted'
            ? `${pct}% · cap exhausted, routing cheap`
            : `${pct}% used · ${team.key_count} ${team.key_count === 1 ? 'key' : 'keys'}`
          : `${team.key_count} ${team.key_count === 1 ? 'key' : 'keys'} · no cap`}
      </p>
    </div>
  )
}

function SetupStep({ done, title, body }) {
  return (
    <div className="flex items-start gap-3">
      <span
        className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border font-mono text-[10px] ${
          done ? 'border-cool/40 bg-cool/10 text-cool' : 'border-line text-muted'
        }`}
      >
        {done ? '✓' : '·'}
      </span>
      <div className="min-w-0">
        <p className={`font-body text-xs ${done ? 'text-muted' : 'text-primary'}`}>{title}</p>
        <p className="font-mono text-[10px] text-muted mt-0.5">{body}</p>
      </div>
    </div>
  )
}

function BudgetControl({ label, suffix, value, editing, draft, saving, onStart, onChange, onSave, onCancel }) {
  if (editing) {
    return (
      <div className="flex items-center gap-2">
        <input
          type="number"
          min="0"
          step="0.01"
          autoFocus
          value={draft}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onSave()
            if (e.key === 'Escape') onCancel()
          }}
          placeholder="blank = no limit"
          className="w-36 bg-surface border border-line rounded px-2 py-1 font-mono text-xs text-primary focus:outline-none focus:ring-1 focus:ring-signal/50"
        />
        <button
          onClick={onSave}
          disabled={saving}
          className="font-mono text-[10px] px-2 py-1 rounded border border-signal/50 text-signal hover:bg-signal/10 transition disabled:opacity-50"
        >
          {saving ? 'saving…' : 'save'}
        </button>
        <button
          onClick={onCancel}
          className="font-mono text-[10px] px-2 py-1 rounded border border-line text-muted hover:text-primary transition"
        >
          cancel
        </button>
      </div>
    )
  }
  return (
    <button
      onClick={onStart}
      title={`Set a ${label} spend cap for this key`}
      className="font-mono text-[10px] text-muted hover:text-signal transition text-left"
    >
      {value == null
        ? `${label} budget: none — set one`
        : `${label} budget: $${value.toFixed(2)}${suffix} — edit`}
    </button>
  )
}

function AlertsTab() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [alertType, setAlertType] = useState('daily_spend')
  const [threshold, setThreshold] = useState('')
  const [webhookUrl, setWebhookUrl] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  useEffect(() => { loadAlerts() }, [])

  async function loadAlerts() {
    setLoading(true)
    const headers = await authHeaders()
    const res = await fetch(`${API_BASE}/alerts`, { headers })
    if (res.ok) setAlerts(await res.json())
    setLoading(false)
  }

  async function handleCreate(e) {
    e.preventDefault()
    if (!threshold || !webhookUrl) return
    setCreating(true)
    setError(null)
    setSuccess(null)
    const headers = await authHeaders()
    const res = await fetch(`${API_BASE}/alerts`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ alert_type: alertType, threshold: parseFloat(threshold), webhook_url: webhookUrl }),
    })
    if (res.ok) {
      setThreshold('')
      setWebhookUrl('')
      setSuccess('Alert created.')
      loadAlerts()
    } else {
      const err = await res.json().catch(() => ({}))
      setError(err.detail || 'Failed to create alert')
    }
    setCreating(false)
  }

  async function handleDelete(id) {
    const headers = await authHeaders()
    await fetch(`${API_BASE}/alerts/${id}`, { method: 'DELETE', headers })
    setAlerts((prev) => prev.filter((a) => a.id !== id))
  }

  const selectedType = ALERT_TYPES.find((t) => t.value === alertType)

  return (
    <div>
      <p className="text-muted text-sm mb-8">
        Get notified via webhook when cost, error rate, or latency crosses a threshold.
        Works with Slack, Discord, or any HTTP endpoint.
      </p>

      <form onSubmit={handleCreate} className="bg-surface border border-line rounded-xl shadow-card p-5 mb-8 flex flex-col gap-4">
        <p className="font-mono text-[10px] text-muted uppercase tracking-wide">New alert rule</p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="flex flex-col gap-1">
            <label className="font-mono text-[10px] text-muted">Alert type</label>
            <select
              value={alertType}
              onChange={(e) => setAlertType(e.target.value)}
              className="bg-surface border border-line rounded-lg px-3 py-2.5 font-mono text-xs text-primary focus:outline-none focus:ring-1 focus:ring-signal/50"
            >
              {ALERT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className="font-mono text-[10px] text-muted">Threshold ({selectedType?.unit})</label>
            <input
              type="number"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              placeholder={selectedType?.placeholder}
              min="0"
              step="any"
              className="bg-surface border border-line rounded-lg px-3 py-2.5 font-mono text-xs text-primary placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-signal/50"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="font-mono text-[10px] text-muted">Webhook URL (https://)</label>
            <input
              type="url"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://hooks.slack.com/..."
              className="bg-surface border border-line rounded-lg px-3 py-2.5 font-mono text-xs text-primary placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-signal/50"
            />
          </div>
        </div>

        {selectedType && (
          <p className="font-mono text-[10px] text-muted">{selectedType.hint}</p>
        )}

        {error && <p className="font-mono text-xs text-danger">{error}</p>}
        {success && <p className="font-mono text-xs text-cool">{success}</p>}

        <button
          type="submit"
          disabled={creating || !threshold || !webhookUrl}
          className="self-start bg-signal text-white font-semibold text-xs px-5 py-2.5 rounded-lg hover:brightness-110 transition disabled:opacity-50"
        >
          {creating ? 'Creating…' : 'Create alert'}
        </button>
      </form>

      <div className="space-y-3">
        {loading ? (
          <div className="py-4 flex flex-col gap-3">
            {[1, 2].map((i) => <div key={i} className="h-14 bg-line rounded-xl animate-pulse" />)}
          </div>
        ) : alerts.length === 0 ? (
          <p className="font-mono text-xs text-muted py-8">No alert rules yet.</p>
        ) : (
          alerts.map((a) => {
            const type = ALERT_TYPES.find((t) => t.value === a.alert_type)
            return (
              <div key={a.id} className="group flex items-center justify-between gap-4 bg-surface border border-line rounded-xl shadow-card px-4 py-4 hover:border-signal/30 transition-colors">
                <div className="flex-1 min-w-0">
                  <p className="font-body text-sm font-medium">{type?.label} &gt; {a.threshold}{type?.unit}</p>
                  <p className="font-mono text-[10px] text-muted truncate">{a.webhook_url}</p>
                  {a.last_fired_at && (
                    <p className="font-mono text-[10px] text-signal">last fired {new Date(a.last_fired_at).toLocaleString()}</p>
                  )}
                </div>
                <button
                  onClick={() => handleDelete(a.id)}
                  className="font-mono text-[10px] px-3 py-1.5 rounded border border-danger/40 text-danger hover:bg-danger/10 transition shrink-0"
                >
                  delete
                </button>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const [keys, setKeys] = useState([])
  const [teams, setTeams] = useState([])
  const [keyName, setKeyName] = useState('')
  const [newKey, setNewKey] = useState(null)
  const [loadingKeys, setLoadingKeys] = useState(true)
  const [creating, setCreating] = useState(false)
  const [revoking, setRevoking] = useState(null)
const [keyBudget, setKeyBudget] = useState('')
const [keyMonthlyBudget, setKeyMonthlyBudget] = useState('')
const [keyTeamId, setKeyTeamId] = useState('')
const [editingBudget, setEditingBudget] = useState(null)
const [budgetDraft, setBudgetDraft] = useState('')
const [savingBudget, setSavingBudget] = useState(false)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)
  const [activeTab, setActiveTab] = useState('overview')
  const [selectedKeyId, setSelectedKeyId] = useState(null)

  useEffect(() => { loadKeys(); loadTeams() }, [])

  useEffect(() => {
    if (keys.length > 0 && !selectedKeyId) {
      setSelectedKeyId(keys[0].id)
    }
  }, [keys])

  async function loadTeams() {
    try {
      setTeams(await fetchTeams())
    } catch {
      // A missing session just means no teams to show; keys still load.
    }
  }

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
    // Blank means unlimited; anything typed must be a real non-negative number.
    const body = { name: keyName.trim() }
    for (const [field, raw] of [['daily_budget_usd', keyBudget], ['monthly_budget_usd', keyMonthlyBudget]]) {
      const trimmed = raw.trim()
      if (trimmed === '') continue
      const parsed = Number(trimmed)
      if (!Number.isFinite(parsed) || parsed < 0) {
        setError('Budgets must be zero or greater')
        setCreating(false)
        return
      }
      body[field] = parsed
    }
    if (keyTeamId !== '') body.team_id = Number(keyTeamId)
    const res = await fetch(`${API_BASE}/keys`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })
    if (res.ok) {
      const data = await res.json()
      setNewKey(data.key)
      setKeyName('')
      setKeyBudget('')
      setKeyMonthlyBudget('')
      setKeyTeamId('')
      loadKeys()
      loadTeams()
    } else {
      const err = await res.json().catch(() => ({}))
      setError(err.detail || 'Failed to create key')
    }
    setCreating(false)
  }

  function startEditBudget(k, field) {
    setEditingBudget(`${k.id}:${field}`)
    setBudgetDraft(k[field] == null ? '' : String(k[field]))
  }

  async function saveBudget(id, field) {
    const trimmed = budgetDraft.trim()
    let value = null
    if (trimmed !== '') {
      const parsed = Number(trimmed)
      if (!Number.isFinite(parsed) || parsed < 0) {
        setError('Budget must be zero or greater')
        return
      }
      value = parsed
    }
    setSavingBudget(true)
    setError(null)
    const headers = await authHeaders()
    const res = await fetch(`${API_BASE}/keys/${id}`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ [field]: value }),
    })
    if (res.ok) {
      const updated = await res.json()
      setKeys((prev) => prev.map((k) => (k.id === id ? updated : k)))
      setEditingBudget(null)
      setBudgetDraft('')
    } else {
      const err = await res.json().catch(() => ({}))
      setError(err.detail || 'Failed to update budget')
    }
    setSavingBudget(false)
  }

  async function assignTeam(id, teamId) {
    setError(null)
    const headers = await authHeaders()
    const res = await fetch(`${API_BASE}/keys/${id}`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ team_id: teamId === '' ? null : Number(teamId) }),
    })
    if (res.ok) {
      const updated = await res.json()
      setKeys((prev) => prev.map((k) => (k.id === id ? updated : k)))
      loadTeams()
    } else {
      const err = await res.json().catch(() => ({}))
      setError(err.detail || 'Failed to move key')
    }
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
  const monthSpend = keys.reduce((sum, k) => sum + (Number(k.spent_this_month) || 0), 0)
  const budgetSummary = summarizeBudget(keys)
  const budgetedTeams = teams.filter((t) => t.monthly_budget_usd != null).length
  const cappedTeams = teams.filter((t) => t.state === 'exhausted').length

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'keys', label: 'API keys', count: keys.length },
    { id: 'teams', label: 'Teams', count: teams.length },
    ...(hasKeys ? [
      { id: 'playground', label: 'Playground' },
      { id: 'analytics', label: 'Analytics' },
      { id: 'logs', label: 'Request logs' },
      { id: 'alerts', label: 'Alerts' },
    ] : []),
  ]
  const meta = TAB_META[activeTab] || TAB_META.overview

  return (
    <div className="mx-auto max-w-[1440px] px-4 sm:px-6 py-6 sm:py-10">
      <div className="flex flex-col lg:flex-row gap-5 lg:gap-6">
        {/* Persistent workspace nav, the way a console is usually laid out */}
        <aside className="lg:w-60 xl:w-64 shrink-0">
          <div className="lg:sticky lg:top-24 space-y-3">
            <div className="rounded-2xl border border-line bg-surface shadow-card p-3.5">
              <div className="flex items-center gap-2.5 px-1">
                <span className="grid h-9 w-9 place-items-center rounded-xl border border-signal/30 bg-signal/10 font-display text-base font-semibold text-signal">
                  R
                </span>
                <div className="min-w-0">
                  <p className="font-display text-sm font-semibold leading-tight text-primary truncate">RouteWise</p>
                  <p className="font-mono text-[10px] text-muted">FinOps console</p>
                </div>
              </div>
              <nav aria-label="Dashboard sections" className="mt-3.5 flex lg:flex-col gap-1 overflow-x-auto pb-1 lg:pb-0">
                {tabs.map((tab) => {
                  const on = activeTab === tab.id
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      aria-current={on ? 'page' : undefined}
                      className={`flex items-center justify-between gap-2 whitespace-nowrap rounded-lg border px-3 py-2 font-body text-[13px] transition-colors ${
                        on
                          ? 'border-signal/25 bg-signal/10 text-signal'
                          : 'border-transparent text-muted hover:bg-panel hover:text-primary'
                      }`}
                    >
                      <span>{tab.label}</span>
                      {tab.count != null && (
                        <span className={`font-mono text-[10px] ${on ? 'text-signal' : 'text-muted'}`}>{tab.count}</span>
                      )}
                    </button>
                  )
                })}
              </nav>
            </div>

            <div className="hidden lg:block rounded-2xl border border-line bg-panel p-4">
              <p className="font-mono text-[10px] uppercase tracking-wide text-muted">Spend this month</p>
              <p className="font-display text-2xl font-semibold text-primary mt-1">${monthSpend.toFixed(2)}</p>
              <p className="font-mono text-[10px] text-muted mt-0.5">
                {keys.length} {keys.length === 1 ? 'key' : 'keys'} · UTC month
              </p>
              <div className="mt-3 flex items-start gap-1.5">
                <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-current ${budgetSummary.accent}`} aria-hidden />
                <p className={`font-mono text-[10px] leading-relaxed ${budgetSummary.accent}`}>
                  {budgetSummary.label} — {budgetSummary.hint}
                </p>
              </div>
              <div className="mt-4 flex flex-col gap-1.5">
                <Link to="/guide" className="font-mono text-[10px] text-muted hover:text-signal transition-colors">Read the guide →</Link>
                <Link to="/models" className="font-mono text-[10px] text-muted hover:text-signal transition-colors">Model pricing →</Link>
              </div>
            </div>
          </div>
        </aside>

        <main className="flex-1 min-w-0">
          <header className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="min-w-0">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-signal">{meta.eyebrow}</p>
              <h1 className="font-display text-2xl sm:text-3xl font-semibold text-primary mt-1.5">{meta.title}</h1>
              <p className="text-muted text-sm mt-1.5 max-w-2xl">{meta.sub}</p>
            </div>
            <div className="flex flex-wrap gap-2 shrink-0">
              {activeTab !== 'keys' && (
                <button
                  onClick={() => setActiveTab('keys')}
                  className="inline-flex items-center bg-signal text-white font-semibold text-xs px-4 py-2.5 rounded-lg hover:brightness-110 shadow-card transition"
                >
                  New key
                </button>
              )}
              <Link
                to="/playground"
                className="inline-flex items-center font-mono text-xs text-primary bg-surface border border-line px-4 py-2.5 rounded-lg hover:border-signal/50 hover:shadow-card transition"
              >
                Playground
              </Link>
            </div>
          </header>

          {activeTab === 'overview' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
                <StatTile
                  label="API keys"
                  value={keys.length}
                  hint={hasKeys ? `${keys.filter((k) => k.team_id).length} attached to a team` : 'create one to start'}
                  accent={hasKeys ? 'text-cool' : 'text-muted'}
                />
                <StatTile
                  label="Teams"
                  value={teams.length}
                  hint={
                    cappedTeams > 0
                      ? `${cappedTeams} ${cappedTeams === 1 ? 'budget is' : 'budgets are'} exhausted`
                      : teams.length > 0
                        ? `${budgetedTeams} with monthly caps`
                        : 'no shared budgets yet'
                  }
                  accent={cappedTeams > 0 ? 'text-danger' : teams.length > 0 ? 'text-cool' : 'text-muted'}
                />
                <StatTile
                  label="Spend this month"
                  value={`$${monthSpend.toFixed(2)}`}
                  hint="sum of key spend, UTC month"
                  accent={monthSpend > 0 ? 'text-signal' : 'text-muted'}
                />
                <StatTile
                  label="Budget health"
                  value={budgetSummary.label}
                  hint={budgetSummary.hint}
                  accent={budgetSummary.accent}
                />
              </div>

              <div className="grid gap-4 xl:grid-cols-3">
                <div className="xl:col-span-2 space-y-4">
                  <Panel
                    title="Spend & routing"
                    action={
                      <KeySwitcher
                        keys={keys}
                        selectedKeyId={selectedKeyId}
                        onChange={setSelectedKeyId}
                        mask={maskKey}
                      />
                    }
                  >
                    {hasKeys && selectedKey ? (
                      <CostAnalytics apiKey={selectedKey.key} />
                    ) : (
                      <div className="space-y-4">
                        <div className="space-y-3">
                          <SetupStep done={keys.length > 0} title="Create an API key" body="One key per person or service." />
                          <SetupStep done={teams.length > 0} title="Create a team with a monthly budget" body="Every key under it shares the cap." />
                          <SetupStep done={false} title="Send your first request" body="Spend, savings and routing reasons land here." />
                        </div>
                        <button
                          onClick={() => setActiveTab('keys')}
                          className="font-mono text-[10px] px-3 py-1.5 rounded border border-signal/40 text-signal hover:bg-signal/10 transition"
                        >
                          Create a key
                        </button>
                      </div>
                    )}
                  </Panel>

                  <Panel
                    title="Recent requests"
                    action={hasKeys ? <PanelLink onClick={() => setActiveTab('logs')}>View all</PanelLink> : null}
                  >
                    {hasKeys ? (
                      <RequestLogs apiKey={selectedKey?.key} showTitle={false} />
                    ) : (
                      <p className="font-mono text-[11px] text-muted py-4">
                        Nothing routed yet. Each request appears here with the tier used and the budget reason behind it.
                      </p>
                    )}
                  </Panel>
                </div>

                <div className="space-y-4">
                  <Panel
                    title="Budget by team"
                    action={<PanelLink onClick={() => setActiveTab('teams')}>{teams.length > 0 ? 'Manage' : 'Create'}</PanelLink>}
                  >
                    {teams.length === 0 ? (
                      <p className="font-mono text-[11px] text-muted leading-relaxed">
                        No teams yet. A team is the monthly budget bucket your keys share, so one number covers everyone under it.
                      </p>
                    ) : (
                      <div className="space-y-3.5">
                        {teams.slice(0, 4).map((team) => <TeamBudgetBar key={team.id} team={team} />)}
                        {teams.length > 4 && (
                          <PanelLink onClick={() => setActiveTab('teams')}>+{teams.length - 4} more teams</PanelLink>
                        )}
                      </div>
                    )}
                  </Panel>

                  <Panel title="Keys" action={<PanelLink onClick={() => setActiveTab('keys')}>Manage</PanelLink>}>
                    {keys.length === 0 ? (
                      <p className="font-mono text-[11px] text-muted">No keys yet.</p>
                    ) : (
                      <div className="space-y-2.5">
                        {keys.slice(0, 4).map((k) => (
                          <div key={k.id} className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="font-body text-xs text-primary truncate">{k.name}</p>
                              <p className="font-mono text-[10px] text-muted truncate">
                                {k.team_name || 'no team'} · ${Number(k.spent_this_month || 0).toFixed(2)}
                              </p>
                            </div>
                            <span
                              className={`font-mono text-[9px] px-1.5 py-0.5 rounded border shrink-0 ${
                                k.budget?.state === 'exhausted'
                                  ? BUDGET_CHIP.exhausted
                                  : k.budget?.state === 'warning'
                                    ? BUDGET_CHIP.warning
                                    : 'border-line text-muted'
                              }`}
                            >
                              {k.budget?.state === 'exhausted'
                                ? 'cheap'
                                : k.budget?.state === 'warning'
                                  ? `${k.budget.percent_used}%`
                                  : 'ok'}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </Panel>

                  <Panel title="Quickstart">
                    <pre className="font-mono text-[10px] leading-relaxed text-muted bg-base border border-line rounded-lg p-3 overflow-x-auto whitespace-pre">{`curl ${API_BASE}/route \\
  -H "Authorization: Bearer $ROUTEWISE_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"query":"summarise this ticket"}'`}</pre>
                    <p className="font-mono text-[10px] text-muted mt-2 leading-relaxed">
                      OpenAI clients: point <span className="text-primary">base_url</span> at{' '}
                      <span className="text-primary">{API_BASE}/v1</span>.
                    </p>
                  </Panel>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'keys' && (
        <>
          <p className="text-muted text-sm mb-8">
            Use these keys in the <code className="font-mono text-xs bg-line px-1.5 py-0.5 rounded">Authorization: Bearer &lt;key&gt;</code> header when calling <code className="font-mono text-xs bg-line px-1.5 py-0.5 rounded">/route</code>.
            A key can belong to a team and carries optional daily and monthly caps.
            When a cap is exhausted the key keeps working on the cheap tier.
          </p>

          {/* Create key */}
          <div className="rounded-xl border border-line bg-panel/40 p-4 sm:p-5 mb-8">
            <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
              <p className="font-mono text-[10px] uppercase tracking-wide text-muted">Create a key</p>
              <p className="font-mono text-[10px] text-muted">caps optional · exhausted keys keep working</p>
            </div>
            <form onSubmit={handleCreate} className="flex flex-wrap gap-3">
            <input
              type="text"
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              placeholder="Key name (e.g. my-app)"
              className="flex-1 min-w-[12rem] bg-surface border border-line rounded-lg px-4 py-3 font-body text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50 focus:border-signal shadow-card"
            />
            <input
              type="number"
              min="0"
              step="0.01"
              value={keyBudget}
              onChange={(e) => setKeyBudget(e.target.value)}
              placeholder="Daily budget $ (optional)"
              title="Once this key's spend today passes the cap, the router forces it to the cheap tier. Leave blank for no cap."
              className="w-full sm:w-48 bg-surface border border-line rounded-lg px-4 py-3 font-mono text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50 focus:border-signal shadow-card"
            />
            <input
              type="number"
              min="0"
              step="0.01"
              value={keyMonthlyBudget}
              onChange={(e) => setKeyMonthlyBudget(e.target.value)}
              placeholder="Monthly budget $ (optional)"
              title="A cap just for this key, inside its team budget. Leave blank to inherit only the team's cap."
              className="w-full sm:w-48 bg-surface border border-line rounded-lg px-4 py-3 font-mono text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50 focus:border-signal shadow-card"
            />
            <select
              value={keyTeamId}
              onChange={(e) => setKeyTeamId(e.target.value)}
              title="Keys inherit the team's monthly budget and use its name as the default spend tag."
              className="w-full sm:w-48 bg-surface border border-line rounded-lg px-3 py-3 font-mono text-sm text-primary focus:outline-none focus:ring-2 focus:ring-signal/50 focus:border-signal shadow-card"
            >
              <option value="">No team</option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>{team.name}</option>
              ))}
            </select>
            <button
              type="submit"
              disabled={creating}
              className="bg-signal text-white font-semibold text-sm px-5 py-3 rounded-lg hover:brightness-110 transition disabled:opacity-50 whitespace-nowrap"
            >
              {creating ? 'Creating…' : 'Generate key'}
            </button>
            </form>
          </div>

          {error && <p className="font-mono text-xs text-danger mb-4">{error}</p>}

          {/* Newly created key — show once */}
          {newKey && (
            <div className="border border-signal/40 bg-signal/5 rounded-xl p-4 mb-8 shadow-card">
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
          <div className="space-y-3">
            {loadingKeys ? (
              <div className="py-8 flex flex-col gap-3">
                {[1, 2].map((i) => (
                  <div key={i} className="h-14 bg-line rounded-xl animate-pulse" />
                ))}
              </div>
            ) : keys.length === 0 ? (
              <div className="rounded-xl border border-dashed border-line bg-panel/50 px-6 py-10 text-center">
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-signal mb-2">No keys yet</p>
                <p className="font-display text-lg font-semibold text-primary">Create your first key above</p>
                <p className="text-muted text-sm mt-2 max-w-md mx-auto">
                  Point any OpenAI client at this workspace, or call <code className="font-mono text-xs bg-line px-1.5 py-0.5 rounded">/route</code> directly.
                  Spend and budget state fill in as soon as traffic starts.
                </p>
                <div className="mt-5 flex flex-wrap justify-center gap-2">
                  <Link
                    to="/playground"
                    className="inline-flex items-center bg-signal text-white font-semibold text-xs px-4 py-2.5 rounded-lg hover:brightness-110 shadow-card transition"
                  >
                    Try the playground
                  </Link>
                  <Link
                    to="/guide"
                    className="inline-flex items-center font-mono text-xs text-muted border border-line px-4 py-2.5 rounded-lg hover:text-primary hover:border-signal/50 transition"
                  >
                    Read the guide
                  </Link>
                </div>
              </div>
            ) : (
              keys.map((k) => {
                const chip = describeBudget(k.budget)
                return (
                <div key={k.id} className="group flex items-start justify-between gap-4 bg-surface border border-line rounded-xl shadow-card px-4 py-4 hover:border-signal/30 hover:shadow-card-hover transition-all">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-body text-sm font-medium group-hover:text-signal transition-colors">{k.name}</p>
                      {chip && (
                        <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded border ${chip.cls}`}>
                          {chip.text}
                        </span>
                      )}
                    </div>
                    <p className="font-mono text-[10px] text-muted">{maskKey(k.key)}</p>
                    <p className="font-mono text-[10px] text-muted">
                      created {new Date(k.created_at).toLocaleDateString()}
                      <span className="mx-1.5">·</span>
                      {k.team_name ? (
                        <span className="text-signal">{k.team_name}</span>
                      ) : (
                        <span>no team</span>
                      )}
                      {k.spent_this_month > 0 && (
                        <>
                          <span className="mx-1.5">·</span>
                          <span>${k.spent_this_month.toFixed(2)} spent this month</span>
                        </>
                      )}
                    </p>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1.5">
                      <BudgetControl
                        label="daily"
                        suffix="/day"
                        value={k.daily_budget_usd}
                        editing={editingBudget === `${k.id}:daily_budget_usd`}
                        draft={budgetDraft}
                        saving={savingBudget}
                        onStart={() => startEditBudget(k, 'daily_budget_usd')}
                        onChange={setBudgetDraft}
                        onSave={() => saveBudget(k.id, 'daily_budget_usd')}
                        onCancel={() => setEditingBudget(null)}
                      />
                      <BudgetControl
                        label="monthly"
                        suffix="/mo"
                        value={k.monthly_budget_usd}
                        editing={editingBudget === `${k.id}:monthly_budget_usd`}
                        draft={budgetDraft}
                        saving={savingBudget}
                        onStart={() => startEditBudget(k, 'monthly_budget_usd')}
                        onChange={setBudgetDraft}
                        onSave={() => saveBudget(k.id, 'monthly_budget_usd')}
                        onCancel={() => setEditingBudget(null)}
                      />
                    </div>
                    {teams.length > 0 && (
                      <label className="flex items-center gap-1.5 mt-1.5 font-mono text-[10px] text-muted">
                        team:
                        <select
                          value={k.team_id ?? ''}
                          onChange={(e) => assignTeam(k.id, e.target.value)}
                          className="bg-surface border border-line rounded px-1.5 py-0.5 font-mono text-[10px] text-primary focus:outline-none focus:ring-1 focus:ring-signal/50"
                        >
                          <option value="">no team (no shared cap)</option>
                          {teams.map((team) => (
                            <option key={team.id} value={team.id}>{team.name}</option>
                          ))}
                        </select>
                      </label>
                    )}
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
                )
              })
            )}
          </div>
        </>
      )}

      {activeTab === 'teams' && (
        <TeamsTab
          teams={teams}
          onChanged={() => { loadTeams(); loadKeys() }}
        />
      )}

          {activeTab === 'playground' && hasKeys && <ApiPlayground />}

          {activeTab === 'analytics' && hasKeys && (
            <div>
              <div className="mb-4">
                <KeySwitcher keys={keys} selectedKeyId={selectedKeyId} onChange={setSelectedKeyId} mask={maskKey} />
              </div>
              <CostAnalytics apiKey={selectedKey?.key} />
            </div>
          )}

          {activeTab === 'logs' && hasKeys && (
            <div>
              <div className="mb-4">
                <KeySwitcher keys={keys} selectedKeyId={selectedKeyId} onChange={setSelectedKeyId} mask={maskKey} />
              </div>
              <RequestLogs apiKey={selectedKey?.key} showTitle={false} />
            </div>
          )}

          {activeTab === 'alerts' && hasKeys && <AlertsTab />}
        </main>
      </div>
    </div>
  )
}
