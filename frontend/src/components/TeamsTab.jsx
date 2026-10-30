import { useState } from 'react'
import { createTeam, deleteTeam, describeRequestError, updateTeam } from '../api'

// One place that decides how a budget state looks, so the team card, the key
// row and the analytics banner cannot disagree about what "exhausted" means.
const STATE_STYLE = {
  ok: { bar: 'bg-cool', text: 'text-cool', chip: 'text-cool bg-cool/10 border-cool/30', label: 'within budget' },
  warning: { bar: 'bg-signal', text: 'text-signal', chip: 'text-signal bg-signal/10 border-signal/30', label: 'approaching cap' },
  exhausted: { bar: 'bg-danger', text: 'text-danger', chip: 'text-danger bg-danger/10 border-danger/30', label: 'budget exhausted' },
  unlimited: { bar: 'bg-line', text: 'text-muted', chip: 'text-muted bg-panel border-line', label: 'no cap' },
}

function money(value) {
  if (value == null) return '—'
  return `$${Number(value).toFixed(2)}`
}

function BudgetBar({ percent, state }) {
  const style = STATE_STYLE[state] || STATE_STYLE.unlimited
  const width = percent == null ? 0 : Math.min(100, Math.max(0, percent))
  return (
    <div className="bg-line rounded-full h-2 overflow-hidden">
      <div className={`h-2 rounded-full transition-all ${style.bar}`} style={{ width: `${width}%` }} />
    </div>
  )
}

function TeamCard({ team, onChanged }) {
  const style = STATE_STYLE[team.state] || STATE_STYLE.unlimited
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  function startEdit() {
    setDraft(team.monthly_budget_usd == null ? '' : String(team.monthly_budget_usd))
    setError(null)
    setEditing(true)
  }

  async function save() {
    const trimmed = draft.trim()
    let value = null
    if (trimmed !== '') {
      const parsed = Number(trimmed)
      if (!Number.isFinite(parsed) || parsed < 0) {
        setError('Budget must be zero or greater')
        return
      }
      value = parsed
    }
    setBusy(true)
    setError(null)
    try {
      await updateTeam(team.id, { monthly_budget_usd: value })
      setEditing(false)
      onChanged()
    } catch (e) {
      setError(describeRequestError(e))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!confirming) {
      setConfirming(true)
      setTimeout(() => setConfirming(false), 4000)
      return
    }
    setBusy(true)
    setError(null)
    try {
      await deleteTeam(team.id)
      onChanged()
    } catch (e) {
      setError(describeRequestError(e))
      setBusy(false)
    }
  }

  return (
    <div className="bg-surface border border-line rounded-xl shadow-card px-4 py-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="font-body text-sm font-medium truncate">{team.name}</p>
            <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded border ${style.chip}`}>
              {style.label}
            </span>
          </div>
          <p className="font-mono text-[10px] text-muted mt-0.5">
            {team.key_count} {team.key_count === 1 ? 'key' : 'keys'} · resets on the 1st
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={startEdit}
            className="font-mono text-[10px] px-2.5 py-1.5 rounded border border-line text-muted hover:text-primary hover:border-signal/50 transition"
          >
            edit budget
          </button>
          <button
            onClick={remove}
            disabled={busy}
            className="font-mono text-[10px] px-2.5 py-1.5 rounded border border-danger/40 text-danger hover:bg-danger/10 transition disabled:opacity-50"
          >
            {confirming ? 'confirm delete' : 'delete'}
          </button>
        </div>
      </div>

      <div className="mt-3 space-y-1.5">
        <div className="flex items-baseline justify-between gap-3 font-mono text-[11px]">
          <span className="text-primary">
            {money(team.spent_this_month)} spent
            <span className="text-muted"> of {money(team.monthly_budget_usd)}</span>
          </span>
          <span className={style.text}>
            {team.percent_used == null ? 'no limit' : `${team.percent_used}% used`}
          </span>
        </div>
        <BudgetBar percent={team.percent_used} state={team.state} />
        <div className="flex items-baseline justify-between gap-3 font-mono text-[10px] text-muted">
          <span>{team.remaining_usd == null ? 'unlimited headroom' : `${money(team.remaining_usd)} left this month`}</span>
          {team.state === 'exhausted' && (
            <span className="text-danger">requests continue on the cheap tier</span>
          )}
        </div>
      </div>

      {editing && (
        <div className="flex items-center gap-2 mt-3">
          <input
            type="number"
            min="0"
            step="0.01"
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') save()
              if (e.key === 'Escape') setEditing(false)
            }}
            placeholder="blank = no limit"
            className="w-40 bg-surface border border-line rounded px-2 py-1 font-mono text-xs text-primary focus:outline-none focus:ring-1 focus:ring-signal/50"
          />
          <button
            onClick={save}
            disabled={busy}
            className="font-mono text-[10px] px-2 py-1 rounded border border-signal/50 text-signal hover:bg-signal/10 transition disabled:opacity-50"
          >
            {busy ? 'saving…' : 'save'}
          </button>
          <button
            onClick={() => setEditing(false)}
            className="font-mono text-[10px] px-2 py-1 rounded border border-line text-muted hover:text-primary transition"
          >
            cancel
          </button>
        </div>
      )}

      {error && <p className="font-mono text-[10px] text-danger mt-2">{error}</p>}
    </div>
  )
}

export default function TeamsTab({ teams, onChanged }) {
  const [name, setName] = useState('')
  const [budget, setBudget] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)

  async function handleCreate(e) {
    e.preventDefault()
    if (!name.trim()) return
    let value = null
    const trimmed = budget.trim()
    if (trimmed !== '') {
      const parsed = Number(trimmed)
      if (!Number.isFinite(parsed) || parsed < 0) {
        setError('Monthly budget must be zero or greater')
        return
      }
      value = parsed
    }
    setCreating(true)
    setError(null)
    try {
      await createTeam(name.trim(), value)
      setName('')
      setBudget('')
      onChanged()
    } catch (e2) {
      setError(describeRequestError(e2))
    } finally {
      setCreating(false)
    }
  }

  return (
    <div>
      <p className="text-muted text-sm mb-8">
        A team is one monthly budget shared by every key under it. Keys carry a
        person or a service, so a team can use one shared key or one key per
        member without changing how spend is counted.
      </p>

      <div className="bg-signal/5 border border-signal/30 rounded-xl px-4 py-3 mb-8">
        <p className="font-mono text-[11px] text-primary leading-relaxed">
          Running out does not block requests. At 100% the router keeps answering
          on the <span className="text-cool">cheap tier</span>, and every response,
          log row and this dashboard says the budget is the reason.
        </p>
      </div>

      <form onSubmit={handleCreate} className="flex flex-wrap gap-3 mb-8">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Team name (e.g. growth)"
          className="flex-1 min-w-[12rem] bg-surface border border-line rounded-lg px-4 py-3 font-body text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50 focus:border-signal shadow-card"
        />
        <input
          type="number"
          min="0"
          step="0.01"
          value={budget}
          onChange={(e) => setBudget(e.target.value)}
          placeholder="Monthly budget $ (optional)"
          title="Leave blank for no cap. At the cap, requests are served by the cheap tier instead of being rejected."
          className="w-full sm:w-56 bg-surface border border-line rounded-lg px-4 py-3 font-mono text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50 focus:border-signal shadow-card"
        />
        <button
          type="submit"
          disabled={creating || !name.trim()}
          className="bg-signal text-white font-semibold text-sm px-5 py-3 rounded-lg hover:brightness-110 transition disabled:opacity-50 whitespace-nowrap"
        >
          {creating ? 'Creating…' : 'Create team'}
        </button>
      </form>

      {error && <p className="font-mono text-xs text-danger mb-4">{error}</p>}

      <div className="space-y-3">
        {teams.length === 0 ? (
          <p className="font-mono text-xs text-muted py-8">
            No teams yet — create one above, then assign keys to it. Keys without a
            team have no shared monthly cap.
          </p>
        ) : (
          teams.map((team) => (
            <TeamCard key={team.id} team={team} onChanged={onChanged} />
          ))
        )}
      </div>
    </div>
  )
}
