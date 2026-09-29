import { useState, useEffect } from 'react'

// Layout is derived from the tier list so a 2-tier policy renders two nodes
// instead of a 3-node diagram with a hole in it. tierKeys comes from the policy
// the backend actually used, so the diagram cannot disagree with the router.
function tierKeysFrom(tiers) {
  const keys = (tiers || []).map((t) => t.key)
  return keys.length ? keys : ['cheap', 'mid', 'frontier']
}

export default function TierCircuit({ tiers, activeTier, score, cacheHit, loading, streaming = false, cheapCeil, frontierFloor, chaosActive = false, crossProviderFallback = false, intendedTier = null }) {
  const [scanIndex, setScanIndex] = useState(-1)
  const tierKeys = tierKeysFrom(tiers)
  const scanOrder = tierKeys

  useEffect(() => {
    if (!loading) {
      setScanIndex(-1)
      return
    }
    setScanIndex(0)
    const id = setInterval(() => {
      setScanIndex((i) => (i + 1) % scanOrder.length)
    }, 400)
    return () => clearInterval(id)
  }, [loading, scanOrder.length])

  const isScanning = loading && scanIndex >= 0 && !activeTier
  const scanTier = isScanning ? scanOrder[scanIndex] : null

  const Q = { x: 200, y: 50 }
  // Spread 2 or 3 tier nodes evenly across the same horizontal band.
  const T = tierKeys.reduce((acc, k, i) => {
    const n = tierKeys.length
    const x = n === 1 ? Q.x : 65 + (i * (335 - 65)) / (n - 1)
    acc[k] = { x, y: n === 3 && k === 'mid' ? 205 : 190 }
    return acc
  }, {})
  const W = { x: 200, y: 350 }
  const G = { x: 200, y: 475 }

  const qPath = tierKeys.reduce((acc, k) => {
    const p = T[k]
    acc[k] = `M${Q.x},${Q.y} C${Q.x},${Q.y + 55} ${p.x},${p.y - 50} ${p.x},${p.y}`
    return acc
  }, {})

  const tWeb = tierKeys.reduce((acc, k) => {
    const p = T[k]
    acc[k] = `M${p.x},${p.y} C${p.x},${p.y + 55} ${W.x},${W.y - 50} ${W.x},${W.y}`
    return acc
  }, {})

  const tGemini = tierKeys.reduce((acc, k) => {
    const p = T[k]
    acc[k] = `M${p.x},${p.y} C${p.x},${p.y + 135} ${G.x},${G.y - 60} ${G.x},${G.y}`
    return acc
  }, {})

  const qWeb = `M${Q.x},${Q.y} C${Q.x},${Q.y + 110} ${W.x},${W.y - 80} ${W.x},${W.y}`

  const hc = cacheHit ? 'var(--color-cool)' : 'var(--color-signal)'
  const isWeb = activeTier === 'web'
  const isGemini = activeTier === 'gemini' || crossProviderFallback

  const GX = 75, GW = 250, GY = 120
  const gx = (s) => GX + (Math.min(10, Math.max(0, s)) / 10) * GW
  // Actual thresholds from the last response when we have them, otherwise the
  // caller has already substituted the selected model's own bands.
  const cheapTick = cheapCeil ?? 4.5
  const frontierTick = frontierFloor ?? 6.0
  // Vega has one cut: no mid band, so there is no second boundary to draw.
  const showMidBand = tiers.length > 2 && frontierTick > cheapTick

  return (
    <div className="relative">
      <div className="flex items-center justify-between mb-2 px-1">
        <span className="font-mono text-[10px] tracking-[0.2em] text-muted uppercase">routing engine</span>
        <span className="flex items-center gap-1.5 font-mono text-[10px] text-muted">
          <span className={`relative flex h-1.5 w-1.5 ${loading ? 'animate-pulse' : ''}`}>
            <span className={`absolute inline-flex h-full w-full rounded-full opacity-60 ${loading ? 'animate-ping bg-signal' : 'bg-cool'}`} />
            <span className={`relative inline-flex rounded-full h-1.5 w-1.5 ${loading ? 'bg-signal' : 'bg-cool'}`} />
          </span>
          {loading ? (streaming ? 'streaming…' : 'routing…') : 'live'}
        </span>
      </div>
      <div className="bg-base/60 backdrop-blur-sm border border-line rounded-2xl shadow-card p-4">
        <svg viewBox="0 0 400 520" className="w-full h-auto">
          <defs>
            <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="glow-sm" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="2.5" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <linearGradient id="difficulty-grad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--color-cool)" />
              <stop offset="55%" stopColor="var(--color-signal)" />
              <stop offset="100%" stopColor="var(--color-danger)" />
            </linearGradient>
          </defs>

          {/* background circuit traces */}
          <g opacity="0.05" stroke="var(--color-muted)" fill="none" strokeWidth="1">
            <line x1="35" y1="0" x2="35" y2="400" />
            <line x1="365" y1="0" x2="365" y2="400" />
            <line x1="35" y1="195" x2="365" y2="195" />
            <circle cx="35" cy="50" r="2.5" fill="var(--color-muted)" stroke="none" />
            <circle cx="365" cy="50" r="2.5" fill="var(--color-muted)" stroke="none" />
            <circle cx="35" cy="350" r="2.5" fill="var(--color-muted)" stroke="none" />
            <circle cx="365" cy="350" r="2.5" fill="var(--color-muted)" stroke="none" />
            <circle cx="35" cy="195" r="2.5" fill="var(--color-muted)" stroke="none" />
            <circle cx="365" cy="195" r="2.5" fill="var(--color-muted)" stroke="none" />
            <line x1="35" y1="120" x2="365" y2="120" strokeDasharray="2 6" />
          </g>

      {/* paths: query → tier */}
      {tierKeys.map((k) => {
        const d = qPath[k]
        const scanning = isScanning && scanTier === k
        const active = activeTier === k
        const on = scanning || active
        return (
          <path key={k} d={d} fill="none"
            stroke={on ? hc : 'var(--color-line)'}
            strokeWidth={active ? 2.5 : scanning ? 2 : 1.5}
            opacity={scanning ? 0.6 : 1}
            className="transition-all duration-300"
          />
        )
      })}

      {/* paths: tier → web */}
      {tierKeys.map((k) => (
        <path key={k} d={tWeb[k]} fill="none"
          stroke={isWeb ? 'var(--color-cool)' : 'var(--color-line)'}
          strokeWidth={isWeb ? 2 : 1}
          strokeDasharray={isWeb ? 'none' : '4 3'}
          opacity={isWeb ? 1 : 0.25}
          className="transition-all duration-500"
        />
      ))}

      {/* paths: tier → gemini last resort */}
      {tierKeys.map((k) => (
        <path key={k} d={tGemini[k]} fill="none"
          stroke={isGemini ? 'var(--color-danger)' : 'var(--color-line)'}
          strokeWidth={isGemini ? 2 : 1}
          strokeDasharray={isGemini ? 'none' : '4 3'}
          opacity={isGemini ? 1 : (chaosActive ? 0.35 : 0.15)}
          className="transition-all duration-500"
        />
      ))}

      {/* scanning particle */}
      {isScanning && (
        <circle r="3" fill="var(--color-signal)" opacity="0.4">
          <animateMotion dur="0.5s" repeatCount="indefinite" path={qPath[scanTier]} />
        </circle>
      )}

      {isGemini && (
        <circle r="4" fill="var(--color-danger)" filter="url(#glow-sm)">
          <animateMotion dur="1.1s" repeatCount="indefinite" path={tGemini[intendedTier] || tGemini[tierKeys[0]]} />
        </circle>
      )}

      {/* active path particle */}
      {!loading && activeTier && activeTier !== 'web' && activeTier !== 'gemini' && (
        <circle r="4" fill={hc} filter="url(#glow-sm)">
          <animateMotion dur="0.7s" repeatCount="indefinite" path={qPath[activeTier]} />
        </circle>
      )}

      {/* web routing particle */}
      {!loading && activeTier === 'web' && (
        <circle r="4" fill="var(--color-cool)" filter="url(#glow-sm)">
          <animateMotion dur="1s" repeatCount="indefinite" path={qWeb} />
        </circle>
      )}

      {/* difficulty gauge */}
      <g>
        <text x={GX - 8} y={GY + 3} textAnchor="end"
          className="font-mono" fontSize="8" fill="var(--color-muted)" letterSpacing="0.08em">
          DIFFICULTY
        </text>
        <rect x={GX} y={GY - 1.5} width={GW} height="3" rx="1.5" fill="var(--color-line)" />
        {score != null && (
          <>
            <rect x={GX} y={GY - 1.5} width={GW} height="3" rx="1.5" fill="none" opacity="0.25" />
            <rect x={GX} y={GY - 1.5}
              width={Math.max(0, (score / 10) * GW)}
              height="3" rx="1.5" fill="url(#difficulty-grad)"
              className="transition-all duration-700"
            />
            <circle cx={gx(score)} cy={GY} r="5"
              fill="var(--color-base)" stroke="var(--color-signal)" strokeWidth="2"
              filter="url(#glow-sm)"
              className="transition-all duration-700"
            />
            <circle cx={gx(score)} cy={GY} r="5" fill="none" stroke="var(--color-signal)" strokeWidth="1" opacity="0.4">
              <animate attributeName="r" values="5;8;5" dur="2.2s" repeatCount="indefinite" />
            </circle>
          </>
        )}
        <line x1={gx(cheapTick)} y1={GY - 5} x2={gx(cheapTick)} y2={GY + 5}
          stroke="var(--color-muted)" strokeWidth="1" opacity="0.4" />
        {showMidBand && (
          <line x1={gx(frontierTick)} y1={GY - 5} x2={gx(frontierTick)} y2={GY + 5}
            stroke="var(--color-muted)" strokeWidth="1" opacity="0.4" />
        )}
        {/* Shade the mid band only when the selected model actually has one. */}
        {showMidBand && (
          <rect
            x={gx(cheapTick)} y={GY - 1.5}
            width={Math.max(0, gx(frontierTick) - gx(cheapTick))} height="3"
            fill="var(--color-signal)" opacity="0.22" rx="1.5"
          />
        )}
        {score != null && (
          <text x={GX + GW + 10} y={GY + 3} textAnchor="start"
            className="font-mono" fontSize="10" fontWeight="600" fill="var(--color-signal)">
            {score.toFixed(1)}
          </text>
        )}
        {showMidBand ? (
          <>
            <text x={gx(cheapTick)} y={GY + 14} textAnchor="middle"
              className="font-mono" fontSize="7" fill="var(--color-muted)" opacity="0.5">c:{cheapTick.toFixed(1)}</text>
            <text x={(gx(cheapTick) + gx(frontierTick)) / 2} y={GY + 14} textAnchor="middle"
              className="font-mono" fontSize="7" fill="var(--color-muted)" opacity="0.5">mid</text>
            <text x={gx(frontierTick)} y={GY + 14} textAnchor="middle"
              className="font-mono" fontSize="7" fill="var(--color-muted)" opacity="0.5">f:{frontierTick.toFixed(1)}</text>
          </>
        ) : (
          // Single-cut model: one boundary at exactly one spot. Render only the
          // cut label here, or the c: and cut: text overlap.
          <text x={gx(cheapTick)} y={GY + 14} textAnchor="middle"
            className="font-mono" fontSize="7" fill="var(--color-muted)" opacity="0.5">cut:{cheapTick.toFixed(1)}</text>
        )}
      </g>

      {/* query node */}
      <g>
        <circle cx={Q.x} cy={Q.y} r="11"
          fill="var(--color-base)"
          stroke={loading ? 'var(--color-signal)' : 'var(--color-muted)'}
          strokeWidth="2"
        >
          {loading && (
            <>
              <animate attributeName="r" values="11;14;11" dur="1s" repeatCount="indefinite" />
              <animate attributeName="stroke-opacity" values="1;0.4;1" dur="1s" repeatCount="indefinite" />
            </>
          )}
        </circle>
        <circle cx={Q.x} cy={Q.y} r="3"
          fill={loading ? 'var(--color-signal)' : 'var(--color-muted)'}
          className="transition-all duration-300"
        >
          {loading && <animate attributeName="r" values="3;5;3" dur="1s" repeatCount="indefinite" />}
        </circle>
        <text x={Q.x + 19} y={Q.y + 4}
          className="font-mono" fontSize="10" fill="var(--color-muted)">
          query
        </text>
        {isScanning && (
          <text x={Q.x + 19} y={Q.y + 18}
            className="font-mono" fontSize="9" fill="var(--color-muted)">
            evaluating…
          </text>
        )}
      </g>

      {/* tier nodes */}
      {tierKeys.map((k) => {
        const p = T[k]
        const t = (tiers || []).find((x) => x.key === k) || { label: k, sub: '' }
        const scanning = isScanning && scanTier === k
        const active = activeTier === k
        const on = scanning || active
        return (
          <g key={k}>
            <circle cx={p.x} cy={p.y} r={on ? (active ? 13 : 11) : 9}
              fill={active ? hc : 'var(--color-base)'}
              stroke={on ? hc : 'var(--color-line)'}
              strokeWidth={on ? 2 : 1.5}
              filter={active ? 'url(#glow)' : 'none'}
              opacity={scanning ? 0.7 : 1}
              className="transition-all duration-300"
            />
            {active && (
              <circle cx={p.x} cy={p.y} r="13"
                fill="none" stroke={hc} strokeWidth="1" opacity="0.3">
                <animate attributeName="r" values="13;20;13" dur="2s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.3;0;0.3" dur="2s" repeatCount="indefinite" />
              </circle>
            )}
            <text x={p.x} y={p.y + 24} textAnchor="middle"
              className="font-display font-semibold" fontSize="14"
              fill={on ? hc : 'var(--color-primary)'}
              opacity={scanning ? 0.7 : 1}>
              {t.label}
            </text>
            <text x={p.x} y={p.y + 38} textAnchor="middle"
              className="font-mono" fontSize="8.5" fill="var(--color-muted)"
              opacity={scanning ? 0.7 : 0.9}>
              {t.sub}
            </text>
            {/* cache hit label — pill badge below the tier text */}
            {active && cacheHit && (
              <g>
                <rect x={p.x - 24} y={p.y + 40} width="48" height="15" rx="7.5"
                  fill="var(--color-cool)" opacity="0.12" />
                <rect x={p.x - 24} y={p.y + 40} width="48" height="15" rx="7.5" fill="none"
                  stroke="var(--color-cool)" strokeOpacity="0.3" />
                <text x={p.x} y={p.y + 51} textAnchor="middle"
                  className="font-mono" fontSize="8" fontWeight="600" fill="var(--color-cool)">
                  cache hit
                </text>
              </g>
            )}
          </g>
        )
      })}

      {/* web node */}
      {(() => {
        const on = !loading && activeTier === 'web'
        return (
          <g>
            <circle cx={W.x} cy={W.y} r={on ? 13 : 9}
              fill={on ? 'var(--color-cool)' : 'var(--color-base)'}
              stroke={on ? 'var(--color-cool)' : 'var(--color-line)'}
              strokeWidth="2"
              strokeDasharray={on ? 'none' : '4 3'}
              filter={on ? 'url(#glow)' : 'none'}
              className="transition-all duration-500"
            />
            {on && (
              <circle cx={W.x} cy={W.y} r="13"
                fill="none" stroke="var(--color-cool)" strokeWidth="1" opacity="0.3">
                <animate attributeName="r" values="13;20;13" dur="2s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.3;0;0.3" dur="2s" repeatCount="indefinite" />
              </circle>
            )}
            <text x={W.x + 18} y={W.y - 6}
              className="font-display font-semibold" fontSize="14"
              fill={on ? 'var(--color-cool)' : 'var(--color-primary)'}>
              Web
            </text>
            <text x={W.x + 18} y={W.y + 10}
              className="font-mono" fontSize="9" fill="var(--color-muted)">
              tavily/search · live
            </text>
          </g>
        )
      })()}

      {/* gemini last-resort node */}
      {(() => {
        const on = isGemini
        return (
          <g>
            <circle cx={G.x} cy={G.y} r={on ? 13 : 9}
              fill={on ? 'var(--color-danger)' : 'var(--color-base)'}
              stroke={on ? 'var(--color-danger)' : 'var(--color-line)'}
              strokeWidth="2"
              strokeDasharray={on ? 'none' : '4 3'}
              filter={on ? 'url(#glow)' : 'none'}
              className="transition-all duration-500"
            />
            {on && (
              <circle cx={G.x} cy={G.y} r="13"
                fill="none" stroke="var(--color-danger)" strokeWidth="1" opacity="0.3">
                <animate attributeName="r" values="13;20;13" dur="2s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.3;0;0.3" dur="2s" repeatCount="indefinite" />
              </circle>
            )}
            <text x={G.x + 18} y={G.y - 6}
              className="font-display font-semibold" fontSize="14"
              fill={on ? 'var(--color-danger)' : 'var(--color-primary)'}>
              Gemini
            </text>
            <text x={G.x + 18} y={G.y + 10}
              className="font-mono" fontSize="9" fill="var(--color-muted)">
              last resort
            </text>
          </g>
        )
      })()}
          </svg>
        </div>
    </div>
  )
}
