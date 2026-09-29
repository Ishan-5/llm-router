import { MODEL_LIST } from '../models'

// Solid accent values. This Tailwind setup does NOT emit opacity modifiers on
// CSS custom-property colors (bg-cool/10, border-cool/50, etc.), so borders and
// backgrounds that must show up are done with inline styles instead.
const ACCENT = {
  cool: { hex: '#3FB8AF', chip: 'bg-cool text-base' },
  signal: { hex: '#FF9F1C', chip: 'bg-signal text-base' },
  danger: { hex: '#E85D5D', chip: 'bg-danger text-base' },
}

const COLOR = { color: 'var(--color-primary)' }
const MUTED = { color: 'var(--color-muted)' }

// Two-step flow: first click opens the model's details (description + example
// questions), the second click starts the chat. The description does not sit in
// the hero — it appears here, on the model you are actually choosing.
export default function ModelPicker({ value, onSelect, onStart, onExample, availableModes = [] }) {
  const selectable =
    availableModes.length > 0
      ? MODEL_LIST.filter(
          (m) => m.supportMode === 'generic' || availableModes.includes(m.supportMode)
        )
      : MODEL_LIST

  return (
    <div className="w-full max-w-md mb-8">
      <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4 flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-signal opacity-60" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-signal" />
        </span>
        Pick a model
        <span className="font-mono text-[10px] text-muted opacity-60 normal-case tracking-normal ml-1">
          select to review
        </span>
      </p>

      <div className="grid gap-2.5">
        {selectable.map((m) => {
          const selected = m.id === value
          const a = ACCENT[m.accent] || ACCENT.cool
          return (
            <div
              key={m.id}
              role="radio"
              aria-checked={selected}
              className={`rounded-2xl bg-surface shadow-card transition-all ${selected ? 'border-2' : 'border border-line'}`}
              style={{ borderColor: selected ? a.hex : undefined }}
            >
              {/* header — click to select */}
              <button
                type="button"
                onClick={() => onSelect(m.id)}
                className="w-full p-4 text-left"
              >
                <div className="flex items-center gap-3.5">
                  <span
                    className={`h-10 w-10 rounded-xl grid place-items-center font-display text-lg font-semibold shrink-0 ${selected ? a.chip : 'bg-panel text-muted'}`}
                  >
                    {m.name[0]}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="font-display text-lg font-semibold leading-none" style={COLOR}>
                        {m.name}
                      </span>
                      {selected && (
                        <span
                          className="h-4 w-4 rounded-full grid place-items-center"
                          style={{ backgroundColor: a.hex }}
                        >
                          <svg width="8" height="8" viewBox="0 0 10 8" fill="none" stroke="var(--color-base)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="1,4 3.5,6.5 9,1" />
                          </svg>
                        </span>
                      )}
                    </span>
                    <span className="block font-mono text-[10px] uppercase tracking-[0.2em] mt-1" style={{ color: selected ? a.hex : undefined, ...(selected ? {} : MUTED) }}>
                      {m.tagline}
                    </span>
                  </span>
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 14 14"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    style={{ color: 'var(--color-muted)', transform: selected ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}
                  >
                    <polyline points="3,5 7,9 11,5" />
                  </svg>
                </div>
              </button>

              {/* details — appears after selecting */}
              {selected && (
                <div className="px-4 pb-4">
                  <p className="text-xs leading-relaxed font-medium" style={COLOR}>
                    {m.description}
                  </p>

                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] mt-4 mb-2" style={MUTED}>
                    Try
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {m.examples.map((ex) => (
                      <button
                        key={ex}
                        type="button"
                        onClick={() => onExample(m.id, ex)}
                        className="font-mono text-[11px] rounded-full px-3.5 py-1.5 border transition-all"
                        style={{
                          color: 'var(--color-primary)',
                          borderColor: 'var(--color-line)',
                          backgroundColor: 'var(--color-base)',
                        }}
                      >
                        {ex}
                      </button>
                    ))}
                  </div>

                  <button
                    type="button"
                    onClick={() => onStart(m.id)}
                    className="mt-4 w-full inline-flex items-center justify-center gap-2 text-white font-semibold text-sm px-5 py-2.5 rounded-full transition-all hover:brightness-110 shadow-card"
                    style={{ backgroundColor: a.hex }}
                  >
                    Start chat with {m.name}
                    <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="2" y1="7" x2="12" y2="7" />
                      <polyline points="7,2 12,7 7,12" />
                    </svg>
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}