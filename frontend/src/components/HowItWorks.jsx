import { useState, useEffect, useCallback, useRef } from 'react'

const STEPS = [
  {
    n: '01',
    title: 'Screen',
    short: 'Block bad input',
    body: 'PII and prompt-injection attempts are caught and rejected before a query ever touches a model.',
  },
  {
    n: '02',
    title: 'Score',
    short: 'Classify difficulty',
    body: 'A LightGBM ensemble trained on 8,200 Claude-gold labels predicts a 0–10 difficulty score directly from the text — ~20ms, no API call.',
  },
  {
    n: '03',
    title: 'Route',
    short: 'Pick cheapest tier',
    body: 'Score maps to cheap, mid, or frontier. Time-sensitive queries intercept to live web search. A safety margin biases toward the safer tier.',
  },
  {
    n: '04',
    title: 'Respond',
    short: 'Stream + fallback',
    body: 'Response streams token by token. Semantic cache serves near-duplicates instantly. If the tier fails or rate-limits, it steps down automatically.',
  },
]

function ScreenShield({ active }) {
  return (
    <svg viewBox="0 0 100 60" className="w-full h-auto">
      <path
        d="M 50 5 L 80 18 L 80 38 C 80 50 50 58 50 58 C 50 58 20 50 20 38 L 20 18 Z"
        fill="none" stroke={active ? 'var(--color-signal)' : 'var(--color-line)'}
        strokeWidth="2" strokeLinejoin="round"
        strokeDasharray="200" strokeDashoffset={active ? 0 : 200}
        style={{ transition: 'stroke-dashoffset 0.8s ease-out, stroke 0.3s' }}
      />
      {active && (
        <>
          <polyline points="38,30 46,38 64,22" fill="none" stroke="var(--color-cool)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"
            strokeDasharray="40" strokeDashoffset="40"
            style={{ animation: 'shield-check 0.4s ease-out 0.6s forwards' }} />
          <g opacity="0.5">
            <line x1="25" y1="14" x2="21" y2="10" stroke="var(--color-danger)" strokeWidth="1.5" strokeLinecap="round" />
            <text x="18" y="9" className="fill-danger" fontSize="5" fontFamily="var(--font-mono)">!</text>
          </g>
          <g opacity="0.5">
            <line x1="75" y1="14" x2="79" y2="10" stroke="var(--color-danger)" strokeWidth="1.5" strokeLinecap="round" />
            <text x="80" y="9" className="fill-danger" fontSize="5" fontFamily="var(--font-mono)">!</text>
          </g>
        </>
      )}
      <text x="50" y="50" textAnchor="middle" className="fill-muted" fontSize="6" fontFamily="var(--font-mono)">
        {active ? 'injection · pii · jailbreak' : '—'}
      </text>
    </svg>
  )
}

function ScoreGauge({ active }) {
  const [angle, setAngle] = useState(-90)
  useEffect(() => {
    if (!active) { setAngle(-90); return }
    let frame
    const target = 35
    const start = performance.now()
    function tick(now) {
      const t = Math.min((now - start) / 800, 1)
      const ease = 1 - Math.pow(1 - t, 3)
      setAngle(-90 + target * ease)
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [active])

  const rad = (angle * Math.PI) / 180
  const nx = 50 + 35 * Math.cos(rad)
  const ny = 50 + 35 * Math.sin(rad)

  return (
    <svg viewBox="0 0 100 70" className="w-full h-auto">
      <defs>
        <linearGradient id="gauge-grad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--color-cool)" />
          <stop offset="50%" stopColor="var(--color-signal)" />
          <stop offset="100%" stopColor="var(--color-danger)" />
        </linearGradient>
      </defs>
      <path d="M 15 55 A 35 35 0 0 1 85 55" fill="none" stroke="url(#gauge-grad)" strokeWidth="4" strokeLinecap="round" opacity="0.2" />
      <path d="M 15 55 A 35 35 0 0 1 85 55" fill="none" stroke="url(#gauge-grad)" strokeWidth="4" strokeLinecap="round"
        strokeDasharray="110" strokeDashoffset={active ? 0 : 110}
        style={{ transition: 'stroke-dashoffset 0.8s ease-out' }} />
      <line x1="50" y1="55" x2={active ? nx : 50} y2={active ? ny : 20} stroke="var(--color-primary)" strokeWidth="2" strokeLinecap="round"
        style={{ transition: 'all 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)' }} />
      <circle cx="50" cy="55" r="3" fill="var(--color-primary)" />
      <text x="50" y="68" textAnchor="middle" className="fill-muted" fontSize="7" fontFamily="var(--font-mono)">
        {active ? '3.5 / 10' : '—'}
      </text>
    </svg>
  )
}

function RouteBranch({ active }) {
  return (
    <svg viewBox="0 0 100 60" className="w-full h-auto">
      <circle cx="12" cy="30" r="5" fill="var(--color-signal)" opacity={active ? 1 : 0.2}
        style={{ transition: 'opacity 0.3s' }} />
      {active && <circle cx="12" cy="30" r="5" fill="none" stroke="var(--color-signal)" strokeWidth="1.5" opacity="0.4">
        <animate attributeName="r" from="5" to="14" dur="1.5s" repeatCount="indefinite" />
        <animate attributeName="opacity" from="0.4" to="0" dur="1.5s" repeatCount="indefinite" />
      </circle>}

      <path d="M 17 30 Q 40 30 45 12 L 75 12" fill="none" stroke="var(--color-cool)" strokeWidth="2" strokeLinecap="round"
        strokeDasharray="80" strokeDashoffset={active ? 0 : 80} style={{ transition: 'stroke-dashoffset 0.6s ease-out 0.1s' }} />
      <path d="M 17 30 Q 40 30 45 30 L 75 30" fill="none" stroke="var(--color-signal)" strokeWidth="2" strokeLinecap="round"
        strokeDasharray="80" strokeDashoffset={active ? 0 : 80} style={{ transition: 'stroke-dashoffset 0.6s ease-out 0.3s' }} />
      <path d="M 17 30 Q 40 30 45 48 L 75 48" fill="none" stroke="var(--color-muted)" strokeWidth="2" strokeLinecap="round"
        strokeDasharray="80" strokeDashoffset={active ? 0 : 80} style={{ transition: 'stroke-dashoffset 0.6s ease-out 0.5s' }} />

      <circle cx="80" cy="12" r="4" fill="var(--color-cool)" opacity={active ? 1 : 0.15}
        style={{ transition: 'opacity 0.3s 0.6s' }} />
      <circle cx="80" cy="30" r="4" fill="var(--color-signal)" opacity={active ? 1 : 0.15}
        style={{ transition: 'opacity 0.3s 0.6s' }} />
      <circle cx="80" cy="48" r="4" fill="var(--color-muted)" opacity={active ? 1 : 0.15}
        style={{ transition: 'opacity 0.3s 0.6s' }} />

      {active && <>
        <text x="80" y="6" textAnchor="middle" className="fill-cool" fontSize="6" fontFamily="var(--font-mono)">cheap</text>
        <text x="80" y="25" textAnchor="middle" className="fill-signal" fontSize="6" fontFamily="var(--font-mono)">mid</text>
        <text x="80" y="43" textAnchor="middle" className="fill-muted" fontSize="6" fontFamily="var(--font-mono)">frontier</text>
      </>}

      {active && (
        <g>
          <rect x="36" y="5" width="28" height="10" rx="2" fill="var(--color-panel2)" stroke="var(--color-signal)" strokeWidth="0.8" opacity="0.8" />
          <text x="50" y="12" textAnchor="middle" className="fill-signal" fontSize="5" fontFamily="var(--font-mono)">web?</text>
          <path d="M 30 20 L 36 10" fill="none" stroke="var(--color-signal)" strokeWidth="0.8" strokeDasharray="3 2" opacity="0.6" />
        </g>
      )}
    </svg>
  )
}

function StreamTokens({ active }) {
  const tokens = ['The', 'answer', 'is', '42.', 'If', 'this', 'fails,', 'it', 'retries...']
  return (
    <svg viewBox="0 0 100 45" className="w-full h-auto overflow-visible">
      {tokens.map((t, i) => (
        <g key={i} opacity={active ? 1 : 0}
          style={{ transition: `opacity 0.2s ease ${i * 0.12}s` }}>
          <rect x={i * 11 - 2} y="8" width={t.length * 4.5 + 6} height="16" rx="3"
            fill="var(--color-panel2)" stroke="var(--color-line)" strokeWidth="0.5" />
          <text x={i * 11 + t.length * 2.25 + 1} y="19" textAnchor="middle"
            className="fill-primary" fontSize="6" fontFamily="var(--font-mono)">{t}</text>
        </g>
      ))}
      {active && <rect x={tokens.length * 11} y="10" width="1" height="12" fill="var(--color-signal)" opacity="1">
        <animate attributeName="opacity" values="1;0;1" dur="0.8s" repeatCount="indefinite" />
      </rect>}

      {active && (
        <g style={{ animation: 'token-cache 0.5s ease 1.5s both' }}>
          <rect x="0" y="30" width="65" height="12" rx="2" fill="var(--color-cool)" opacity="0.12" />
          <text x="4" y="39" className="fill-cool" fontSize="5" fontFamily="var(--font-mono)">
            cache hit — 0ms · $0.00
          </text>
        </g>
      )}
      {active && (
        <g style={{ animation: 'token-fallback 0.5s ease 2s both' }}>
          <rect x="68" y="30" width="32" height="12" rx="2" fill="var(--color-danger)" opacity="0.1" />
          <text x="70" y="39" className="fill-danger" fontSize="4.5" fontFamily="var(--font-mono)">
            fail → step down
          </text>
        </g>
      )}
    </svg>
  )
}

const ANIMATIONS = [ScreenShield, ScoreGauge, RouteBranch, StreamTokens]

export default function HowItWorks() {
  const [activeStep, setActiveStep] = useState(-1)
  const [playing, setPlaying] = useState(false)
  const [hasAutoPlayed, setHasAutoPlayed] = useState(false)
  const sectionRef = useRef(null)

  const advance = useCallback(() => {
    setActiveStep((prev) => {
      if (prev >= 3) return -1
      return prev + 1
    })
  }, [])

  useEffect(() => {
    if (!playing) return
    const id = setInterval(advance, 2200)
    advance()
    return () => clearInterval(id)
  }, [playing, advance])

  // auto-play when section scrolls into view
  useEffect(() => {
    if (hasAutoPlayed) return
    const el = sectionRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasAutoPlayed(true)
          setPlaying(true)
          observer.disconnect()
        }
      },
      { threshold: 0.25 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasAutoPlayed])

  function handleManualToggle() {
    setPlaying((p) => {
      if (!p) setActiveStep(-1)
      return !p
    })
  }

  function handleDotClick(i) {
    setPlaying(false)
    setActiveStep(i)
  }

  return (
    <section ref={sectionRef} id="how" className="max-w-6xl mx-auto px-6 py-24 border-t border-line">
      <div className="flex items-end justify-between mb-16">
        <div>
          <p className="font-mono text-[10px] text-signal uppercase tracking-wide mb-3">Pipeline</p>
          <h2 className="font-display text-3xl font-semibold">How it works</h2>
        </div>
        <button
          onClick={handleManualToggle}
          className="flex items-center gap-2 font-mono text-xs border border-line rounded-full px-4 py-2 text-muted hover:text-primary hover:border-signal transition-colors"
        >
          {playing ? (
            <><span className="w-2 h-2 rounded-full bg-signal animate-pulse" /> Playing</>
          ) : (
            <><svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><polygon points="2,0 12,6 2,12" /></svg> Play demo</>
          )}
        </button>
      </div>

      {/* Desktop: horizontal pipeline */}
      <div className="hidden md:block">
        <div className="relative flex items-start gap-0 mb-8">
          {STEPS.map((step, i) => {
            const isActive = i <= activeStep
            const isCurrent = i === activeStep
            const Anim = ANIMATIONS[i]
            return (
              <div key={step.n} className="flex-1 relative">
                {i > 0 && (
                  <div className="absolute top-5 left-0 right-0 h-px">
                    <div className={`h-full transition-all duration-500 ${i <= activeStep ? 'bg-signal' : 'bg-line'}`}
                      style={{ width: i <= activeStep ? '100%' : '0%' }} />
                  </div>
                )}
                <div className="flex flex-col items-center px-3">
                  <div className={`relative z-10 w-10 h-10 rounded-full border-2 flex items-center justify-center transition-all duration-300 mb-6 ${
                    isCurrent
                      ? 'border-signal bg-signal text-white scale-110 shadow-lg shadow-signal/20'
                      : isActive
                        ? 'border-signal bg-signal/10 text-signal'
                        : 'border-line bg-base text-muted'
                  }`}>
                    <span className="font-mono text-xs font-semibold">{step.n}</span>
                    {isCurrent && <span className="absolute inset-0 rounded-full border-2 border-signal animate-ping opacity-20" />}
                  </div>

                  <div className={`w-full bg-panel rounded-xl p-4 mb-4 border transition-all duration-300 ${
                    isCurrent ? 'border-signal/40 shadow-lg shadow-signal/5' : isActive ? 'border-line' : 'border-line/50 opacity-50'
                  }`}>
                    <Anim active={isCurrent} />
                  </div>

                  <div className="text-center">
                    <h3 className={`font-display text-base font-semibold mb-1 transition-colors ${isCurrent ? 'text-primary' : isActive ? 'text-primary' : 'text-muted'}`}>
                      {step.title}
                    </h3>
                    <p className="font-mono text-[10px] text-signal mb-2">{step.short}</p>
                    <p className={`text-xs leading-relaxed transition-colors ${isCurrent ? 'text-muted' : 'text-muted/60'}`}>
                      {step.body}
                    </p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Mobile: vertical pipeline */}
      <div className="md:hidden flex flex-col gap-0">
        {STEPS.map((step, i) => {
          const isActive = i <= activeStep
          const isCurrent = i === activeStep
          const Anim = ANIMATIONS[i]
          return (
            <div key={step.n} className="relative flex gap-4">
              <div className="flex flex-col items-center">
                <div className={`relative z-10 w-9 h-9 rounded-full border-2 flex items-center justify-center shrink-0 transition-all duration-300 ${
                  isCurrent
                    ? 'border-signal bg-signal text-white shadow-lg shadow-signal/20'
                    : isActive
                      ? 'border-signal bg-signal/10 text-signal'
                      : 'border-line bg-base text-muted'
                }`}>
                  <span className="font-mono text-[10px] font-semibold">{step.n}</span>
                  {isCurrent && <span className="absolute inset-0 rounded-full border-2 border-signal animate-ping opacity-20" />}
                </div>
                {i < STEPS.length - 1 && (
                  <div className={`w-px flex-1 min-h-[20px] transition-colors duration-300 ${i < activeStep ? 'bg-signal' : 'bg-line'}`} />
                )}
              </div>

              <div className={`pb-8 pt-1 flex-1 transition-opacity duration-300 ${isActive ? 'opacity-100' : 'opacity-40'}`}>
                <div className={`bg-panel rounded-xl p-3 mb-3 border transition-all duration-300 ${
                  isCurrent ? 'border-signal/40' : 'border-line/50'
                }`}>
                  <Anim active={isCurrent} />
                </div>
                <h3 className="font-display text-sm font-semibold mb-0.5">{step.title}</h3>
                <p className="font-mono text-[10px] text-signal mb-1">{step.short}</p>
                <p className="text-xs text-muted leading-relaxed">{step.body}</p>
              </div>
            </div>
          )
        })}
      </div>

      {/* Step controls */}
      <div className="flex items-center justify-center gap-2 mt-8">
        {STEPS.map((_, i) => (
          <button
            key={i}
            onClick={() => handleDotClick(i)}
            className={`h-1.5 rounded-full transition-all duration-300 ${
              i === activeStep ? 'w-8 bg-signal' : i <= activeStep ? 'w-4 bg-signal/40' : 'w-4 bg-line hover:bg-line/80'
            }`}
          />
        ))}
      </div>
    </section>
  )
}
