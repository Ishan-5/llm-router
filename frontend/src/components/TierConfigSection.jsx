import { useState } from 'react'

const ACCENT = {
  cheap: { text: 'text-cool', bg: 'bg-cool/10', border: 'border-cool/30', dot: 'bg-cool', num: '01' },
  mid: { text: 'text-signal', bg: 'bg-signal/10', border: 'border-signal/30', dot: 'bg-signal', num: '02' },
  frontier: { text: 'text-danger', bg: 'bg-danger/10', border: 'border-danger/30', dot: 'bg-danger', num: '03' },
}

const labelClass = 'font-mono text-[10px] text-muted uppercase tracking-wide block mb-1.5'
const inputClass =
  'w-full bg-panel border border-line rounded-lg px-3 py-2.5 font-mono text-xs text-primary placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50 transition-shadow'

function Switch({ on, onToggle }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={onToggle}
      className={`relative w-11 h-6 rounded-full transition-colors duration-200 shrink-0 ${
        on ? 'bg-signal' : 'bg-line hover:bg-line/70'
      }`}
    >
      <span className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform duration-200 ${
        on ? 'translate-x-5' : ''
      }`} />
    </button>
  )
}

export default function TierConfigSection({ tier, label, config, activeConfig, providers, onToggle, onField }) {
  const [showKey, setShowKey] = useState(false)
  const t = config
  const providerModels = (t.provider && providers[t.provider]?.models) || []
  const a = ACCENT[tier] || ACCENT.cheap
  const resolvedModel = t.model_id === 'custom' ? t.custom_model : t.model_id

  return (
    <div className={`rounded-2xl border p-5 transition-all duration-300 ${
      t.enabled ? 'border-signal/40 bg-surface shadow-card' : 'border-line/80 bg-panel/40'
    }`}>
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <span className={`flex items-center justify-center w-9 h-9 rounded-xl border font-mono text-xs font-bold shrink-0 ${a.border} ${a.bg} ${a.text}`}>
            {a.num}
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-display font-semibold text-primary">{label}</span>
              <span className={`inline-flex items-center gap-1 font-mono text-[9px] px-1.5 py-0.5 rounded-full border ${
                t.enabled ? `${a.border} ${a.bg} ${a.text}` : 'border-line text-muted/70'
              }`}>
                {t.enabled ? (resolvedModel ? 'custom' : 'configure\u2026') : 'default'}
              </span>
            </div>
            <p className="font-mono text-[10px] text-muted mt-0.5 truncate">
              {t.enabled
                ? `${resolvedModel || 'no model selected'} \u00b7 ${t.provider || 'no provider'}`
                : activeConfig[tier]?.model_id
                  ? `default: ${activeConfig[tier].model_id}`
                  : `default: built-in ${label.toLowerCase()} tier`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2.5 shrink-0">
          <span className={`hidden sm:inline font-mono text-[10px] ${t.enabled ? 'text-muted' : 'text-muted/50'}`}>
            {t.enabled ? 'enabled' : 'disabled'}
          </span>
          <Switch on={t.enabled} onToggle={() => onToggle(tier)} />
        </div>
      </div>

      {t.enabled && (
        <div className="mt-4 pt-4 border-t border-line space-y-3">
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Provider</label>
              <select
                value={t.provider}
                onChange={(e) => onField(tier, 'provider', e.target.value)}
                className={inputClass}
              >
                <option value="">Select provider</option>
                {Object.entries(providers).map(([key, p]) => (
                  <option key={key} value={key}>{p.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass}>Model</label>
              <select
                value={t.model_id}
                onChange={(e) => onField(tier, 'model_id', e.target.value)}
                className={`${inputClass} ${!t.provider ? 'opacity-60 cursor-not-allowed' : ''}`}
                disabled={!t.provider}
              >
                <option value="">{t.provider ? 'Select model' : 'pick a provider first'}</option>
                {providerModels.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          </div>

          {t.model_id === 'custom' && (
            <div>
              <label className={labelClass}>Custom model name</label>
              <input
                type="text"
                value={t.custom_model}
                onChange={(e) => onField(tier, 'custom_model', e.target.value)}
                placeholder="e.g. gpt-4o-2024-11-20"
                className={inputClass}
              />
            </div>
          )}

          {t.model_id === 'custom' && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelClass}>Input price ($/1M tokens)</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={t.price_in}
                  onChange={(e) => onField(tier, 'price_in', e.target.value)}
                  placeholder="e.g. 0.15"
                  className={`${inputClass} num-tabular`}
                />
              </div>
              <div>
                <label className={labelClass}>Output price ($/1M tokens)</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={t.price_out}
                  onChange={(e) => onField(tier, 'price_out', e.target.value)}
                  placeholder="e.g. 0.60"
                  className={`${inputClass} num-tabular`}
                />
              </div>
            </div>
          )}

          {t.provider && (
            <div>
              <label className={labelClass}>
                API key <span className="normal-case text-muted">(browser-only)</span>
              </label>
              <div className="relative">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={t.api_key}
                  onChange={(e) => onField(tier, 'api_key', e.target.value)}
                  placeholder="sk-... or your provider key"
                  className={`${inputClass} pr-10`}
                />
                <button
                  type="button"
                  onClick={() => setShowKey((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-primary transition-colors"
                  aria-label={showKey ? 'Hide key' : 'Show key'}
                >
                  {showKey ? (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          )}

          {resolvedModel && t.provider && (
            <p className="flex items-center gap-2 font-mono text-[10px] text-cool pt-1">
              <span className={`w-1.5 h-1.5 rounded-full ${a.dot} animate-pulse`} />
              routes {label.toLowerCase()}-suitable queries to {t.provider}/{resolvedModel}
              {t.price_in && t.price_out ? ` \u00b7 $${t.price_in} in / $${t.price_out} out` : ''}
            </p>
          )}
        </div>
      )}
    </div>
  )
}