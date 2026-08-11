import { useState, useEffect } from 'react'

const SCAN_ORDER = ['cheap', 'mid', 'frontier']

export default function TierCircuit({ tiers, activeTier, score, cacheHit, loading, cheapCeil, frontierFloor }) {
  const [scanIndex, setScanIndex] = useState(-1)

  useEffect(() => {
    if (!loading) {
      setScanIndex(-1)
      return
    }
    setScanIndex(0)
    const id = setInterval(() => {
      setScanIndex((i) => (i + 1) % SCAN_ORDER.length)
    }, 400)
    return () => clearInterval(id)
  }, [loading])

  const isScanning = loading && scanIndex >= 0
  const scanTier = isScanning ? SCAN_ORDER[scanIndex] : null

  const Q = { x: 200, y: 50 }
  const T = {
    cheap:    { x: 65,  y: 190 },
    mid:      { x: 200, y: 205 },
    frontier: { x: 335, y: 190 },
  }
  const W = { x: 200, y: 350 }

  const qPath = {
    cheap:    `M${Q.x},${Q.y} C${Q.x},${Q.y + 55} ${T.cheap.x},${T.cheap.y - 50} ${T.cheap.x},${T.cheap.y}`,
    mid:      `M${Q.x},${Q.y} C${Q.x},${Q.y + 55} ${Q.x},${T.mid.y - 45} ${Q.x},${T.mid.y}`,
    frontier: `M${Q.x},${Q.y} C${Q.x},${Q.y + 55} ${T.frontier.x},${T.frontier.y - 50} ${T.frontier.x},${T.frontier.y}`,
  }

  const tWeb = {
    cheap:    `M${T.cheap.x},${T.cheap.y} C${T.cheap.x},${T.cheap.y + 55} ${W.x},${W.y - 50} ${W.x},${W.y}`,
    mid:      `M${T.mid.x},${T.mid.y} C${T.mid.x},${T.mid.y + 50} ${W.x},${W.y - 45} ${W.x},${W.y}`,
    frontier: `M${T.frontier.x},${T.frontier.y} C${T.frontier.x},${T.frontier.y + 55} ${W.x},${W.y - 50} ${W.x},${W.y}`,
  }

  const qWeb = `M${Q.x},${Q.y} C${Q.x},${Q.y + 110} ${W.x},${W.y - 80} ${W.x},${W.y}`

  const hc = cacheHit ? 'var(--color-cool)' : 'var(--color-signal)'
  const isWeb = activeTier === 'web' && !loading

  const GX = 75, GW = 250, GY = 120
  const gx = (s) => GX + (Math.min(10, Math.max(0, s)) / 10) * GW
  // use actual thresholds from last response, fall back to balanced defaults
  const cheapTick = cheapCeil ?? 4.5
  const frontierTick = frontierFloor ?? 6.0

  return (
    <svg viewBox="0 0 400 400" className="w-full h-auto">
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
      </defs>

      {/* background circuit traces */}
      <g opacity="0.04" stroke="var(--color-muted)" fill="none" strokeWidth="1">
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
      {Object.entries(qPath).map(([k, d]) => {
        const scanning = isScanning && scanTier === k
        const active = !loading && activeTier === k
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
      {Object.entries(tWeb).map(([k, d]) => (
        <path key={k} d={d} fill="none"
          stroke={isWeb ? 'var(--color-cool)' : 'var(--color-line)'}
          strokeWidth={isWeb ? 2 : 1}
          strokeDasharray={isWeb ? 'none' : '4 3'}
          opacity={isWeb ? 1 : 0.25}
          className="transition-all duration-500"
        />
      ))}

      {/* scanning particle */}
      {isScanning && (
        <circle r="3" fill="var(--color-signal)" opacity="0.4">
          <animateMotion dur="0.5s" repeatCount="indefinite" path={qPath[scanTier]} />
        </circle>
      )}

      {/* active path particle */}
      {!loading && activeTier && activeTier !== 'web' && (
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
          className="font-mono" fontSize="8" fill="var(--color-muted)" letterSpacing="0.05em">
          DIFFICULTY
        </text>
        <rect x={GX} y={GY - 1.5} width={GW} height="3" rx="1.5" fill="var(--color-line)" />
        {score != null && !loading && (
          <>
            <rect x={GX} y={GY - 1.5}
              width={Math.max(0, (score / 10) * GW)}
              height="3" rx="1.5" fill="var(--color-signal)"
              className="transition-all duration-700"
            />
            <circle cx={gx(score)} cy={GY} r="5"
              fill="var(--color-signal)" filter="url(#glow-sm)"
              className="transition-all duration-700"
            />
          </>
        )}
        <line x1={gx(cheapTick)} y1={GY - 5} x2={gx(cheapTick)} y2={GY + 5}
          stroke="var(--color-muted)" strokeWidth="1" opacity="0.4" />
        <line x1={gx(frontierTick)} y1={GY - 5} x2={gx(frontierTick)} y2={GY + 5}
          stroke="var(--color-muted)" strokeWidth="1" opacity="0.4" />
        {score != null && !loading && (
          <text x={GX + GW + 10} y={GY + 3} textAnchor="start"
            className="font-mono" fontSize="9" fontWeight="600" fill="var(--color-signal)">
            {score.toFixed(1)}
          </text>
        )}
        <text x={gx(cheapTick)} y={GY + 14} textAnchor="middle"
          className="font-mono" fontSize="7" fill="var(--color-muted)" opacity="0.5">c:{cheapTick.toFixed(1)}</text>
        <text x={gx(frontierTick)} y={GY + 14} textAnchor="middle"
          className="font-mono" fontSize="7" fill="var(--color-muted)" opacity="0.5">f:{frontierTick.toFixed(1)}</text>
      </g>

      {/* query node */}
      <g>
        <circle cx={Q.x} cy={Q.y} r="10"
          fill="var(--color-base)"
          stroke={loading ? 'var(--color-signal)' : 'var(--color-muted)'}
          strokeWidth="2"
        >
          {loading && (
            <>
              <animate attributeName="r" values="10;13;10" dur="1s" repeatCount="indefinite" />
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
        <text x={Q.x + 18} y={Q.y + 4}
          className="font-mono" fontSize="10" fill="var(--color-muted)">
          query
        </text>
        {isScanning && (
          <text x={Q.x + 18} y={Q.y + 18}
            className="font-mono" fontSize="9" fill="var(--color-muted)">
            evaluating...
          </text>
        )}
      </g>

      {/* tier nodes */}
      {tiers.map((t) => {
        const p = T[t.key]
        const scanning = isScanning && scanTier === t.key
        const active = !loading && activeTier === t.key
        const on = scanning || active
        return (
          <g key={t.key}>
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
              className="font-mono" fontSize="9" fill="var(--color-muted)"
              opacity={scanning ? 0.7 : 1}>
              {t.sub}
            </text>
            {/* cache hit label — pill badge below the tier text */}
            {active && cacheHit && (
              <g>
                <rect x={p.x - 22} y={p.y + 42} width="44" height="14" rx="7"
                  fill="var(--color-cool)" opacity="0.15" />
                <text x={p.x} y={p.y + 52} textAnchor="middle"
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
    </svg>
  )
}
