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
      <div ref={trapRef} className="bg-base border border-line rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">

        <div className="flex items-center justify-between px-6 py-5 border-b border-line">
          <div>
            <h2 className="font-display font-semibold text-lg">Bring your own model</h2>
            <p className="font-mono text-xs text-muted mt-0.5">
              Override any tier with your own provider + model. Unset tiers use defaults.
            </p>
          </div>
          <button onClick={onClose} className="text-muted hover:text-primary transition-colors text-xl leading-none" aria-label="Close settings">&#10005;</button>
        </div>

        <div className="px-6 py-4 border-b border-line bg-panel">
          <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-2">Current active config</p>
          <div className="flex flex-wrap gap-4">
            {TIERS.map((t) => (
              <div key={t} className="font-mono text-xs">
                <span className="text-muted">{TIER_LABELS[t]}: </span>
                <span className="text-primary">{activeConfig[t]?.model_id || '\u2014'}</span>
                <span className="text-muted"> · {activeConfig[t]?.provider || '\u2014'}</span>
              </div>
            ))}
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
                className="font-mono text-[10px] px-2.5 py-1 rounded border border-line text-muted hover:text-primary hover:border-signal/50 transition disabled:opacity-50"
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
                      className={`text-left p-2 rounded-lg border transition-colors ${
                        Math.abs(threshold - m.margin) < 0.05
                          ? 'border-signal bg-signal/10'
                          : 'border-line hover:border-signal/30 bg-surface'
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

        <div className="px-6 py-6 flex flex-col gap-6">
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
              {saving ? 'Validating & saving\u2026' : 'Save config'}
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
