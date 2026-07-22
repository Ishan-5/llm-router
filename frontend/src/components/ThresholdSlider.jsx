import { useState } from 'react'

const PRESETS = [
  { value: 0.0, label: 'Economy', color: 'cool' },
  { value: 1.0, label: 'Balanced', color: 'signal' },
  { value: 2.0, label: 'Quality', color: 'danger' },
]

const DESCRIPTIONS = {
  Economy: 'Routes most queries to cheap models. Best for simple Q&A, summaries, and high-volume apps.',
  Balanced: 'Routes by difficulty. Complex questions get better models, simple ones stay cheap.',
  Quality: 'Favors frontier models for higher accuracy. Best for reasoning, code generation, and critical tasks.',
}

function getNearestPreset(val) {
  return PRESETS.reduce((a, b) => Math.abs(a.value - val) < Math.abs(b.value - val) ? a : b)
}

function getLabel(val) {
  if (val <= 0.3) return 'Economy'
  if (val >= 1.7) return 'Quality'
  if (val >= 0.7 && val <= 1.3) return 'Balanced'
  return null
}

export default function ThresholdSlider({ value, onChange, compact = false }) {
  const [dragging, setDragging] = useState(false)
  const nearest = getNearestPreset(value)
  const label = getLabel(value)

  const pct = ((value - 0.0) / 2.0) * 100

  function handleChange(e) {
    onChange(parseFloat(e.target.value))
  }

  if (compact) {
    return (
      <div className="font-mono space-y-1.5">
        <div className="relative">
          <input
            type="range"
            min="0"
            max="2"
            step="0.05"
            value={value}
            onChange={handleChange}
            onMouseDown={() => setDragging(true)}
            onMouseUp={() => setDragging(false)}
            onTouchStart={() => setDragging(true)}
            onTouchEnd={() => setDragging(false)}
            className="w-full h-1.5 bg-line rounded-full appearance-none cursor-pointer
              [&::-webkit-slider-thumb]:appearance-none
              [&::-webkit-slider-thumb]:w-4
              [&::-webkit-slider-thumb]:h-4
              [&::-webkit-slider-thumb]:rounded-full
              [&::-webkit-slider-thumb]:border-2
              [&::-webkit-slider-thumb]:border-signal
              [&::-webkit-slider-thumb]:bg-base
              [&::-webkit-slider-thumb]:cursor-pointer
              [&::-webkit-slider-thumb]:shadow-md
              [&::-moz-range-thumb]:w-4
              [&::-moz-range-thumb]:h-4
              [&::-moz-range-thumb]:rounded-full
              [&::-moz-range-thumb]:border-2
              [&::-moz-range-thumb]:border-signal
              [&::-moz-range-thumb]:bg-base
              [&::-moz-range-thumb]:cursor-pointer"
            style={{
              background: `linear-gradient(to right, #3FB8AF 0%, #FF9F1C 50%, #E85D5D 100%)`,
              opacity: 0.6 + pct / 250,
            }}
          />
        </div>
        <div className="flex justify-between">
          {PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => onChange(p.value)}
              className={`text-[9px] px-1.5 py-0.5 rounded transition-colors ${
                nearest.value === p.value
                  ? 'text-primary bg-surface border border-line'
                  : 'text-muted hover:text-primary'
              }`}
            >
              {p.label.charAt(0)}
            </button>
          ))}
        </div>
        {label && (
          <p className="font-mono text-[9px] text-muted leading-snug">
            {DESCRIPTIONS[label]}
          </p>
        )}
        {!label && (
          <p className="font-mono text-[9px] text-muted leading-snug">
            Custom threshold ({value.toFixed(2)}). Closest to {nearest.label.toLowerCase()} mode.
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="font-mono space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-muted uppercase tracking-wide">Router threshold</span>
        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
          label === 'Economy' ? 'text-cool border-cool/30 bg-cool/10'
          : label === 'Balanced' ? 'text-signal border-signal/30 bg-signal/10'
          : label === 'Quality' ? 'text-danger border-danger/30 bg-danger/10'
          : 'text-muted border-line bg-surface'
        }`}>
          {label || `Custom (${value.toFixed(1)})`}
        </span>
      </div>

      <div className="relative">
        <input
          type="range"
          min="0"
          max="2"
          step="0.05"
          value={value}
          onChange={handleChange}
          onMouseDown={() => setDragging(true)}
          onMouseUp={() => setDragging(false)}
          onTouchStart={() => setDragging(true)}
          onTouchEnd={() => setDragging(false)}
          className="w-full h-1.5 bg-line rounded-full appearance-none cursor-pointer
            [&::-webkit-slider-thumb]:appearance-none
            [&::-webkit-slider-thumb]:w-4
            [&::-webkit-slider-thumb]:h-4
            [&::-webkit-slider-thumb]:rounded-full
            [&::-webkit-slider-thumb]:border-2
            [&::-webkit-slider-thumb]:border-signal
            [&::-webkit-slider-thumb]:bg-base
            [&::-webkit-slider-thumb]:cursor-pointer
            [&::-webkit-slider-thumb]:shadow-md
            [&::-moz-range-thumb]:w-4
            [&::-moz-range-thumb]:h-4
            [&::-moz-range-thumb]:rounded-full
            [&::-moz-range-thumb]:border-2
            [&::-moz-range-thumb]:border-signal
            [&::-moz-range-thumb]:bg-base
            [&::-moz-range-thumb]:cursor-pointer"
          style={{
            background: `linear-gradient(to right, #3FB8AF 0%, #FF9F1C 50%, #E85D5D 100%)`,
            opacity: 0.6 + pct / 250,
          }}
        />

        <div className="flex justify-between mt-1.5">
          {PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => onChange(p.value)}
              className={`text-[9px] px-1.5 py-0.5 rounded transition-colors ${
                nearest.value === p.value
                  ? 'text-primary bg-surface border border-line'
                  : 'text-muted hover:text-primary'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {label ? (
        <p className="text-[11px] text-muted leading-snug">
          {DESCRIPTIONS[label]}
        </p>
      ) : (
        <p className="text-[11px] text-muted leading-snug">
          Custom threshold ({value.toFixed(2)}). Closest to {nearest.label.toLowerCase()} mode.
        </p>
      )}
    </div>
  )
}
