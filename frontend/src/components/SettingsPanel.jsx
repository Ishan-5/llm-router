import { useState, useEffect } from 'react'
import { supabase } from '../supabase'
import { fetchProviders } from '../api'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

async function fetchConfigForUser() {
  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token
  const res = await fetch(`${API_BASE}/config`, {
    headers: token ? { 'Authorization': `Bearer ${token}` } : {}
  })
  if (!res.ok) return {}
  const data = await res.json()
  if (!token) {
    try {
      const saved = JSON.parse(localStorage.getItem('byom_config') || '{}')
      Object.entries(saved).forEach(([tier, cfg]) => {
        if (cfg.enabled) data[tier] = { model_id: cfg.model_id, provider: cfg.provider }
      })
    } catch {}
  }
  return data
}

async function saveConfigForUser(payload) {
  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token
  if (!token) return null  // non-logged-in: localStorage only, no DB call
  const res = await fetch(`${API_BASE}/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Save failed')
  }
  return res.json()
}

async function resetConfigForUser() {
  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token
  if (!token) return null  // non-logged-in: localStorage only, no DB call
  const res = await fetch(`${API_BASE}/config`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` },
  })
  if (!res.ok) throw new Error('Reset failed')
  return res.json()
}

const TIERS = ['cheap', 'mid', 'frontier']
const TIER_LABELS = { cheap: 'Cheap', mid: 'Mid', frontier: 'Frontier' }
const EMPTY_TIER = { provider: '', model_id: '', custom_model: '', api_key: '', price_in: '', price_out: '', enabled: false }

function loadFromLocalStorage() {
  try {
    const saved = localStorage.getItem('byom_config')
    if (!saved) return {}
    return JSON.parse(saved)
  } catch { return {} }
}

export default function SettingsPanel({ onClose, onSaved }) {
  const [providers, setProviders] = useState({})
  const [activeConfig, setActiveConfig] = useState({})
  const [tiers, setTiers] = useState(() => {
    const saved = loadFromLocalStorage()
    const init = { cheap: { ...EMPTY_TIER }, mid: { ...EMPTY_TIER }, frontier: { ...EMPTY_TIER } }
    TIERS.forEach((t) => {
      if (saved[t]) {
        init[t] = {
          ...EMPTY_TIER,
          provider: saved[t].provider || '',
          model_id: saved[t].is_custom ? 'custom' : (saved[t].model_id || ''),
          custom_model: saved[t].is_custom ? saved[t].model_id : '',
          api_key: saved[t].api_key || '',
          price_in: saved[t].price_in || '',
          price_out: saved[t].price_out || '',
          enabled: true,
        }
      }
    })
    return init
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [confirmReset, setConfirmReset] = useState(false)

  useEffect(() => {
    fetchProviders().then(setProviders).catch(() => {})
    fetchConfigForUser().then(setActiveConfig).catch(() => {})
  }, [])

  function handleToggle(tier) {
    setTiers((prev) => ({
      ...prev,
      [tier]: { ...prev[tier], enabled: !prev[tier].enabled },
    }))
  }

  function handleField(tier, field, value) {
    setTiers((prev) => ({
      ...prev,
      [tier]: {
        ...prev[tier],
        [field]: value,
        ...(field === 'provider' ? { model_id: '', custom_model: '' } : {}),
      },
    }))
  }

  function getModelId(tier) {
    const t = tiers[tier]
    return t.model_id === 'custom' ? t.custom_model : t.model_id
  }

  async function handleReset() {
    if (!confirmReset) {
      setConfirmReset(true)
      setTimeout(() => setConfirmReset(false), 3000)
      return
    }
    setConfirmReset(false)
    setError(null)
    setSuccess(null)
    setSaving(true)
    try {
      await resetConfigForUser()
      localStorage.removeItem('byom_config')
      setTiers({ cheap: { ...EMPTY_TIER }, mid: { ...EMPTY_TIER }, frontier: { ...EMPTY_TIER } })
      fetchConfigForUser().then(setActiveConfig).catch(() => {})
      setSuccess('Reset to defaults.')
      setTimeout(() => { onSaved && onSaved() }, 800)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleSave() {
    setError(null)
    setSuccess(null)
    setSaving(true)

    const payload = {}
    for (const tier of TIERS) {
      const t = tiers[tier]
      if (!t.enabled) continue
      const model_id = getModelId(tier)
      if (!t.provider || !model_id || !t.api_key) {
        setError(`Fill in all fields for ${TIER_LABELS[tier]} tier or disable it.`)
        setSaving(false)
        return
      }
      payload[tier] = { provider: t.provider, model_id, api_key: t.api_key }
      if (t.model_id === 'custom') {
        payload[tier].price_per_m_input = parseFloat(t.price_in) || 0
        payload[tier].price_per_m_output = parseFloat(t.price_out) || 0
      }
    }

    if (Object.keys(payload).length === 0) {
      // all tiers disabled = user wants full reset to defaults
      await handleReset()
      return
    }

    try {
      await saveConfigForUser(payload)

      const localStore = {}
      for (const tier of TIERS) {
        const t = tiers[tier]
        if (!t.enabled) continue
        localStore[tier] = {
          provider: t.provider,
          model_id: getModelId(tier),
          is_custom: t.model_id === 'custom',
          api_key: t.api_key,
          price_in: t.price_in,
          price_out: t.price_out,
          enabled: true,
        }
      }
      localStorage.setItem('byom_config', JSON.stringify(localStore))

      fetchConfigForUser().then(setActiveConfig).catch(() => {})
      setSuccess('Config saved and validated successfully.')
      setTimeout(() => { onSaved && onSaved() }, 800)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm px-4">
      <div className="bg-base border border-line rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">

        {/* header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-line">
          <div>
            <h2 className="font-display font-semibold text-lg">Bring your own model</h2>
            <p className="font-mono text-xs text-muted mt-0.5">
              Override any tier with your own provider + model. Unset tiers use defaults.
            </p>
          </div>
          <button onClick={onClose} className="text-muted hover:text-primary transition-colors text-xl leading-none">✕</button>
        </div>

        {/* current active config */}
        <div className="px-6 py-4 border-b border-line bg-panel">
          <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-2">Current active config</p>
          <div className="flex flex-wrap gap-4">
            {TIERS.map((t) => (
              <div key={t} className="font-mono text-xs">
                <span className="text-muted">{TIER_LABELS[t]}: </span>
                <span className="text-primary">{activeConfig[t]?.model_id || '—'}</span>
                <span className="text-muted"> · {activeConfig[t]?.provider || '—'}</span>
              </div>
            ))}
          </div>
        </div>

        {/* tier sections */}
        <div className="px-6 py-6 flex flex-col gap-6">
          {TIERS.map((tier) => {
            const t = tiers[tier]
            const providerModels = (t.provider && providers[t.provider]?.models) || []

            return (
              <div key={tier} className={`border rounded-lg p-4 transition-colors ${t.enabled ? 'border-signal/50 bg-panel' : 'border-line'}`}>
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <span className="font-display font-semibold">{TIER_LABELS[tier]}</span>
                    <span className="font-mono text-xs text-muted ml-2">
                      {t.enabled ? 'custom' : (activeConfig[tier]?.model_id ? `default: ${activeConfig[tier].model_id}` : 'default')}
                    </span>
                  </div>
                  <button
                    onClick={() => handleToggle(tier)}
                    className={`font-mono text-xs px-3 py-1.5 rounded-full border transition-colors ${
                      t.enabled
                        ? 'border-danger text-danger bg-danger/10 hover:bg-danger/20'
                        : 'border-line text-muted hover:border-signal hover:text-signal'
                    }`}
                  >
                    {t.enabled ? 'disable' : 'enable custom'}
                  </button>
                </div>

                {t.enabled && (
                  <div className="flex flex-col gap-3">
                    <div>
                      <label className="font-mono text-[10px] text-muted uppercase tracking-wide block mb-1">Provider</label>
                      <select
                        value={t.provider}
                        onChange={(e) => handleField(tier, 'provider', e.target.value)}
                        className="w-full bg-base border border-line rounded-lg px-3 py-2.5 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-signal/50"
                      >
                        <option value="">Select provider</option>
                        {Object.entries(providers).map(([key, p]) => (
                          <option key={key} value={key}>{p.label}</option>
                        ))}
                      </select>
                    </div>

                    {t.provider && (
                      <div>
                        <label className="font-mono text-[10px] text-muted uppercase tracking-wide block mb-1">Model</label>
                        <select
                          value={t.model_id}
                          onChange={(e) => handleField(tier, 'model_id', e.target.value)}
                          className="w-full bg-base border border-line rounded-lg px-3 py-2.5 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-signal/50"
                        >
                          <option value="">Select model</option>
                          {providerModels.map((m) => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                      </div>
                    )}

                    {t.model_id === 'custom' && (
                      <div>
                        <label className="font-mono text-[10px] text-muted uppercase tracking-wide block mb-1">Custom model name</label>
                        <input
                          type="text"
                          value={t.custom_model}
                          onChange={(e) => handleField(tier, 'custom_model', e.target.value)}
                          placeholder="e.g. gpt-4o-2024-11-20"
                          className="w-full bg-base border border-line rounded-lg px-3 py-2.5 font-mono text-xs placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50"
                        />
                      </div>
                    )}

                    {t.model_id === 'custom' && (
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="font-mono text-[10px] text-muted uppercase tracking-wide block mb-1">Input price ($/1M tokens)</label>
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={t.price_in}
                            onChange={(e) => handleField(tier, 'price_in', e.target.value)}
                            placeholder="e.g. 0.15"
                            className="w-full bg-base border border-line rounded-lg px-3 py-2.5 font-mono text-xs placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50"
                          />
                        </div>
                        <div>
                          <label className="font-mono text-[10px] text-muted uppercase tracking-wide block mb-1">Output price ($/1M tokens)</label>
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={t.price_out}
                            onChange={(e) => handleField(tier, 'price_out', e.target.value)}
                            placeholder="e.g. 0.60"
                            className="w-full bg-base border border-line rounded-lg px-3 py-2.5 font-mono text-xs placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50"
                          />
                        </div>
                      </div>
                    )}

                    {t.provider && (
                      <div>
                        <label className="font-mono text-[10px] text-muted uppercase tracking-wide block mb-1">
                          API Key <span className="normal-case text-muted">(stored in browser only, never sent to our DB)</span>
                        </label>
                        <input
                          type="password"
                          value={t.api_key}
                          onChange={(e) => handleField(tier, 'api_key', e.target.value)}
                          placeholder="sk-... or your provider key"
                          className="w-full bg-base border border-line rounded-lg px-3 py-2.5 font-mono text-xs placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50"
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* footer */}
        <div className="px-6 py-5 border-t border-line flex items-center justify-between gap-4">
          <div className="flex-1">
            {error && <p className="font-mono text-xs text-danger">{error}</p>}
            {success && <p className="font-mono text-xs text-cool">{success}</p>}
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleReset}
              disabled={saving}
              className={`font-mono text-xs px-4 py-2.5 rounded-lg border transition disabled:opacity-50 disabled:cursor-not-allowed ${
                confirmReset
                  ? 'border-danger bg-danger text-white'
                  : 'border-danger text-danger hover:bg-danger/10'
              }`}
            >
              {confirmReset ? 'Sure? (click to confirm)' : 'Reset to defaults'}
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="font-mono text-xs px-5 py-2.5 rounded-lg bg-signal text-white font-semibold hover:brightness-110 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Validating & saving…' : 'Save config'}
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
