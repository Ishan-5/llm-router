export default function TierConfigSection({ tier, label, config, activeConfig, providers, onToggle, onField }) {
  const t = config
  const providerModels = (t.provider && providers[t.provider]?.models) || []

  return (
    <div className={`border rounded-lg p-4 transition-colors ${t.enabled ? 'border-signal/50 bg-panel' : 'border-line'}`}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <span className="font-display font-semibold">{label}</span>
          <span className="font-mono text-xs text-muted ml-2">
            {t.enabled ? 'custom' : (activeConfig[tier]?.model_id ? `default: ${activeConfig[tier].model_id}` : 'default')}
          </span>
        </div>
        <button
          onClick={() => onToggle(tier)}
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
              onChange={(e) => onField(tier, 'provider', e.target.value)}
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
                onChange={(e) => onField(tier, 'model_id', e.target.value)}
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
                onChange={(e) => onField(tier, 'custom_model', e.target.value)}
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
                  onChange={(e) => onField(tier, 'price_in', e.target.value)}
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
                  onChange={(e) => onField(tier, 'price_out', e.target.value)}
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
                onChange={(e) => onField(tier, 'api_key', e.target.value)}
                placeholder="sk-... or your provider key"
                className="w-full bg-base border border-line rounded-lg px-3 py-2.5 font-mono text-xs placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50"
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
