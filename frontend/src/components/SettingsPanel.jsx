import { useState, useEffect } from 'react'
import { supabase } from '../supabase'
import { fetchProviders, fetchSettings, saveSettings, fetchCalibrate, setSharedThreshold } from '../api'
import { API_BASE } from '../config'
import TierConfigSection from './TierConfigSection'
import ThresholdSlider from './ThresholdSlider'
import useFocusTrap from '../useFocusTrap'

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
  if (!token) return null
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
  if (!token) return null
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
  const [threshold, setThreshold] = useState(1.0)
  const [calibrating, setCalibrating] = useState(false)
  const [calibrateResult, setCalibrateResult] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [confirmReset, setConfirmReset] = useState(false)
  const trapRef = useFocusTrap(true)

  useEffect(() => {
    fetchProviders().then(setProviders).catch(() => {})
    fetchConfigForUser().then(setActiveConfig).catch(() => {})
    fetchSettings().then((s) => { setThreshold(s.router_threshold ?? 1.0); setSharedThreshold(s.router_threshold ?? 1.0) }).catch(() => {})
  }, [])

  function handleThresholdChange(v) {
    setThreshold(v)
    setSharedThreshold(v)
  }

  async function handleCalibrate() {
    setCalibrating(true)
    setCalibrateResult(null)
    try {
      const data = await fetchCalibrate()
      setCalibrateResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setCalibrating(false)
    }
  }

  function handleApplyCalibrate(margin) {
    handleThresholdChange(margin)
  }

  useEffect(() => {
    function handleEscape(e) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

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
      await handleReset()
      return
    }

    try {
      await saveConfigForUser(payload)
      try { await saveSettings(threshold) } catch {}

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
      setSuccess('Config and router threshold saved successfully.')
      setTimeout(() => { onSaved && onSaved() }, 800)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm px-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div ref={trapRef} className="bg-base border border-line rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-pop animate-[cmd-slide_0.18s_ease-out]">

        <div className="flex items-start justify-between gap-4 px-6 py-5 border-b border-line">
          <div className="flex items-start gap-3.5 min-w-0">
            <span className="mt-0.5 flex items-center justify-center w-10 h-10 rounded-xl bg-signal/10 border border-signal/30 text-signal shrink-0">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <polyline points="9 12 11 14 15 10" />
              </svg>
            </span>
            <div className="min-w-0">
              <h2 className="font-display font-semibold text-lg text-primary leading-tight">Bring your own model</h2>
              <p className="font-mono text-xs text-muted mt-1 leading-relaxed">
                Override any tier with your own provider + model. Unset tiers keep built-in defaults.
              </p>
              <div className="flex flex-wrap gap-1.5 mt-3">
                {['OpenAI-compatible', 'Keys stay client-side', 'Swappable in one click'].map((b) => (
                  <span key={b} className="font-mono text-[9px] px-2 py-1 rounded-full border border-line bg-surface text-muted">
                    {b}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <button onClick={onClose} className="text-muted hover:text-primary transition-colors text-xl leading-none shrink-0" aria-label="Close settings">&#10005;</button>
        </div>

        <div className="px-6 py-4 border-b border-line bg-surface/40">
          <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-2.5">Current active config</p>
          <div className="flex flex-wrap gap-2">
            {TIERS.map((t) => {
              const dot = t === 'cheap' ? 'bg-cool' : t === 'mid' ? 'bg-signal' : 'bg-danger'
              return (
                <div key={t} className="flex items-center gap-2 font-mono text-[10px] px-3 py-1.5 rounded-full border border-line bg-base">
                  <span className={`w-1.5 h-1.5 rounded-full ${dot} ${activeConfig[t]?.model_id ? 'animate-pulse' : 'opacity-40'}`} />
                  <span className="text-muted capitalize">{t}:</span>
                  <span className="text-primary truncate max-w-[150px]">{activeConfig[t]?.model_id || 'built-in'}</span>
                  {activeConfig[t]?.provider && <span className="text-muted/70">{activeConfig[t].provider}</span>}
                </div>
              )
            })}
          </div>
        </div>

        <div className="px-6 py-5 border-b border-line">
          <ThresholdSlider value={threshold} onChange={handleThresholdChange} />

          <div className="mt-4 pt-4 border-t border-line">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] text-muted uppercase tracking-wide">Calibrate from traffic</span>
              <button
                type="button"
                onClick={handleCalibrate}
                disabled={calibrating}
                className="font-mono text-[10px] px-3 py-1 rounded-full border border-line text-muted hover:text-primary hover:border-signal/50 hover:shadow-card transition disabled:opacity-50"
              >
                {calibrating ? 'Analyzing...' : 'Run calibration'}
              </button>
            </div>
            {calibrateResult && calibrateResult.modes && (
              <div className="space-y-2 mt-2">
                <p className="font-mono text-[10px] text-muted">
                  Based on {calibrateResult.analyzed_requests} recent requests:
                </p>
                <div className="grid grid-cols-3 gap-2">
                  {calibrateResult.modes.map((m) => (
                    <button
                      key={m.mode}
                      type="button"
                      onClick={() => handleApplyCalibrate(m.margin)}
                      className={`text-left p-2.5 rounded-xl border transition-all duration-200 ${
                        Math.abs(threshold - m.margin) < 0.05
                          ? 'border-signal bg-signal/10 shadow-card'
                          : 'border-line hover:border-signal/30 bg-surface hover:shadow-card hover:-translate-y-0.5'
                      }`}
                    >
                      <div className="font-mono text-[10px] font-semibold text-primary capitalize">{m.mode}</div>
                      <div className="font-mono text-[9px] text-muted mt-0.5">
                        C:{m.cheap_pct}% M:{m.mid_pct}% F:{m.frontier_pct}%
                      </div>
                      <div className="font-mono text-[9px] text-cool">Save {m.savings_pct}%</div>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {calibrateResult && !calibrateResult.modes && (
              <p className="font-mono text-[10px] text-muted mt-2">{calibrateResult.message}</p>
            )}
            {!calibrateResult && !calibrating && (
              <p className="font-mono text-[10px] text-muted/60 mt-2">
                Analyze your traffic to find the best threshold automatically. Needs at least 5 routed requests.
              </p>
            )}
          </div>
        </div>

        <div className="px-6 py-6 space-y-4">
          <div className="flex items-center justify-between">
            <p className="font-mono text-[10px] text-muted uppercase tracking-wide">Tier overrides</p>
            <p className="font-mono text-[9px] text-muted/60 num-tabular">
              {Object.values(tiers).filter((t) => t.enabled).length}/3 customized
            </p>
          </div>
          {TIERS.map((tier) => (
            <TierConfigSection
              key={tier}
              tier={tier}
              label={TIER_LABELS[tier]}
              config={tiers[tier]}
              activeConfig={activeConfig}
              providers={providers}
              onToggle={handleToggle}
              onField={handleField}
            />
          ))}
        </div>

        <div className="px-6 py-5 border-t border-line bg-surface/40 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex-1 min-w-[180px]">
            {error && <p className="font-mono text-xs text-danger">{error}</p>}
            {success && <p className="font-mono text-xs text-cool">{success}</p>}
            {!error && !success && (
              <p className="font-mono text-[9px] text-muted/70 flex items-start gap-1.5">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 shrink-0">
                  <rect x="3" y="11" width="18" height="11" rx="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
                Keys are used from your browser at request time — never stored server-side.
              </p>
            )}
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleReset}
              disabled={saving}
              className={`font-mono text-xs px-4 py-2.5 rounded-full border transition disabled:opacity-50 disabled:cursor-not-allowed ${
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
              className="font-mono text-xs px-5 py-2.5 rounded-full bg-signal text-white font-semibold hover:brightness-110 shadow-card transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Validating & saving\u2026' : 'Save config'}
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
