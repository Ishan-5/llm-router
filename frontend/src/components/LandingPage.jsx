import { useState, useEffect, Suspense, lazy } from 'react'
import { Link } from 'react-router-dom'
import Reveal from './Reveal'
import HowItWorks from './HowItWorks'
import AnimatedCounter from './AnimatedCounter'
import { fetchTiers } from '../api'
import { TIERS, TIER_ORDER, SAVINGS_PCT, SAVINGS_EXACT_PCT, FRONTIER_VS_CHEAP, DATASETS, EASY_BAND_AB_FOOTNOTE } from '../productMetrics'

const Features = lazy(() => import('./Features'))

/* Tier prices live in productMetrics, which mirrors backend/router/config.py.
   They are only a fallback for when /tiers answers and only if it never does.
/tiers resolves through the same path /route uses, so the live numbers cannot
   drift from the prices the router actually charges. The old hardcoded TIER
   block here is what mislabelled cheap and frontier after a re-tier, which is
   why it now lives in one shared module rather than being copied per page. */
const TIER_SNAPSHOT = Object.fromEntries(
  TIER_ORDER.map((k) => [
    k,
    { model: TIERS[k].model, provider: TIERS[k].provider, in: TIERS[k].priceIn, out: TIERS[k].priceOut },
  ])
)
/* Industry reference point, clearly labelled as not our config. */
const TYPICAL_FRONTIER = { in: 3.0, out: 15.0 }

const perRequest = (p, tokIn, tokOut) =>
  (tokIn / 1e6) * p.in + (tokOut / 1e6) * p.out

function money(n) {
  if (n >= 1000) return '$' + Math.round(n).toLocaleString()
  if (n >= 100) return '$' + n.toFixed(0)
  if (n >= 10) return '$' + n.toFixed(1)
  if (n >= 1) return '$' + n.toFixed(2)
  return '$' + n.toFixed(3)
}

function ArrowRight({ className = '' }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <line x1="2" y1="7" x2="12" y2="7" />
      <polyline points="7,2 12,7 7,12" />
    </svg>
  )
}

const IN_PATH = 'M 4 168 L 108 168'
const MID_PATH = 'M 132 160 C 172 148, 196 96, 246 84'
const FRONTIER_PATH = 'M 132 176 C 176 190, 200 244, 246 252'

function RoutingVisual() {
  return (
    <div className="relative">
      <style>{`
        @keyframes rw-flow { to { stroke-dashoffset: -44; } }
        @keyframes rw-halo {
          0%   { r: 16; opacity: .55; }
          100% { r: 46; opacity: 0; }
        }
        @keyframes rw-blink { 0%,100% { opacity: 1 } 50% { opacity: .35 } }
        .rw-flow   { stroke-dasharray: 6 8; animation: rw-flow 1.1s linear infinite; }
        .rw-halo   { animation: rw-halo 2.6s ease-out infinite; }
        .rw-blink  { animation: rw-blink 2.6s ease-in-out infinite; }
      `}</style>

      <svg viewBox="0 0 320 320" className="w-full h-auto" role="img" aria-label="Requests flowing into a router, then splitting: most to a cheaper mid tier, a few to the frontier tier">
        <defs>
          <linearGradient id="rw-mid" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--color-cool)" stopOpacity=".25" />
            <stop offset="100%" stopColor="var(--color-cool)" stopOpacity="1" />
          </linearGradient>
          <linearGradient id="rw-frontier" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--color-signal)" stopOpacity=".2" />
            <stop offset="100%" stopColor="var(--color-signal)" stopOpacity="1" />
          </linearGradient>
        </defs>

        {/* lanes */}
        <path id="rw-in" d={IN_PATH} fill="none" stroke="var(--color-line)" strokeWidth="2" />
        <path id="rw-mid-path" d={MID_PATH} fill="none" stroke="var(--color-line)" strokeWidth="2" />
        <path id="rw-frontier-path" d={FRONTIER_PATH} fill="none" stroke="var(--color-line)" strokeWidth="2" />

        {/* flowing accents */}
        <path d={MID_PATH} fill="none" stroke="url(#rw-mid)" strokeWidth="2" className="rw-flow" />
        <path d={FRONTIER_PATH} fill="none" stroke="url(#rw-frontier)" strokeWidth="2" className="rw-flow" style={{ animationDuration: '2.4s' }} />

        {/* incoming requests */}
        {[0, 1, 2, 3, 4].map((i) => (
          <circle key={i} r="3.5" fill="var(--color-muted)" opacity=".7">
            <animateMotion dur="2.6s" begin={`${i * 0.52}s`} repeatCount="indefinite">
              <mpath href="#rw-in" />
            </animateMotion>
          </circle>
        ))}

        {/* the router */}
        <circle className="rw-halo" cx="120" cy="168" r="16" fill="none" stroke="var(--color-signal)" strokeWidth="1.5" />
        <circle cx="120" cy="168" r="16" fill="var(--color-base)" stroke="var(--color-signal)" strokeWidth="2" />
        <g stroke="var(--color-signal)" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="120" cy="168" r="4.5" />
          <line x1="114" y1="168" x2="107" y2="168" />
          <line x1="126" y1="168" x2="133" y2="168" />
        </g>

        {/* majority flow: dots heading to mid */}
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <circle key={i} r="3" fill="var(--color-cool)">
            <animateMotion dur="2.2s" begin={`${i * 0.3}s`} repeatCount="indefinite">
              <mpath href="#rw-mid-path" />
            </animateMotion>
          </circle>
        ))}

        {/* minority flow: one dot heading to frontier */}
        <circle r="4" fill="var(--color-signal)">
          <animateMotion dur="3.4s" begin="0.9s" repeatCount="indefinite">
            <mpath href="#rw-frontier-path" />
          </animateMotion>
        </circle>

        {/* mid node */}
        <circle cx="262" cy="80" r="13" fill="var(--color-base)" stroke="var(--color-cool)" strokeWidth="2" />
        <text x="262" y="106" textAnchor="middle" className="fill-[var(--color-cool)]" style={{ font: '600 11px ui-monospace, monospace' }}>mid</text>
        <text x="262" y="120" textAnchor="middle" className="fill-[var(--color-muted)]" style={{ font: '10px ui-monospace, monospace' }}>most traffic</text>
        <text x="262" y="134" textAnchor="middle" className="fill-[var(--color-cool)]" style={{ font: '10px ui-monospace, monospace' }}>${TIERS.mid.priceIn.toFixed(2)} / 1M</text>

        {/* frontier node */}
        <circle cx="262" cy="252" r="13" fill="var(--color-base)" stroke="var(--color-signal)" strokeWidth="2" />
        <text x="262" y="278" textAnchor="middle" className="fill-[var(--color-signal)]" style={{ font: '600 11px ui-monospace, monospace' }}>frontier</text>
        <text x="262" y="292" textAnchor="middle" className="fill-[var(--color-muted)]" style={{ font: '10px ui-monospace, monospace' }}>when earned</text>
        <text x="262" y="306" textAnchor="middle" className="fill-[var(--color-signal)]" style={{ font: '10px ui-monospace, monospace' }}>${TIERS.frontier.priceIn.toFixed(2)} / 1M</text>
      </svg>

      <span className="absolute top-0 left-0 font-mono text-[10px] text-muted/70">incoming</span>
      <span className="absolute bottom-0 right-0 font-mono text-[10px] text-muted/70 rw-blink">scored in &lt;1ms</span>
    </div>
  )
}

function CostSimulator() {
  const [requests, setRequests] = useState(100000)
  const [hardShare, setHardShare] = useState(20)
  const [tokIn, setTokIn] = useState(500)
  const [tokOut, setTokOut] = useState(500)
  const [tier, setTier] = useState(TIER_SNAPSHOT)
  const [live, setLive] = useState(false)
  const [asOf, setAsOf] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetchTiers()
      .then((d) => {
        if (cancelled || !d?.tiers?.length) return
        setTier(
          Object.fromEntries(
            d.tiers.map((t) => [
              t.tier,
              {
                model: t.model_id,
                provider: t.provider,
                in: t.input_per_m,
                out: t.output_per_m,
              },
            ]),
          ),
        )
        setLive(true)
        setAsOf(new Date())
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const cost = (t) => perRequest(t, tokIn, tokOut) * requests
  const allFrontier = cost(tier.frontier)
  const allTypical = perRequest(TYPICAL_FRONTIER, tokIn, tokOut) * requests
  // 3-way split instead of the old 2-way mid/frontier blend, so the slider
  // means what the router actually does.
  const routed =
    perRequest(tier.frontier, tokIn, tokOut) * requests * (hardShare / 100) +
    perRequest(tier.mid, tokIn, tokOut) *
      requests *
      ((100 - hardShare) / 100) *
      0.5 +
    perRequest(tier.cheap, tokIn, tokOut) *
      requests *
      ((100 - hardShare) / 100) *
      0.5

  const savedVsTypical = allTypical - routed
  const pctVsTypical = allTypical > 0 ? (1 - routed / allTypical) * 100 : 0
  const savedVsOurFrontier = allFrontier - routed
  const pctVsOurFrontier =
    allFrontier > 0 ? (1 - routed / allFrontier) * 100 : 0

  const barMax = Math.max(allTypical, allFrontier, routed)
  const midPct = Math.round(((100 - hardShare) / 2) * 10) / 10
  const cheapPct = Math.round(((100 - hardShare) / 2) * 10) / 10

  return (
    <div className="bg-surface border border-line rounded-2xl shadow-card overflow-hidden">
      <div className="grid lg:grid-cols-[0.9fr_1.1fr]">
        {/* controls */}
        <div className="p-6 md:p-8 border-b lg:border-b-0 lg:border-r border-line">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal mb-1">
            Slide it yourself
          </p>
          <h3 className="font-display text-xl font-semibold tracking-tight mb-6">
            What is your traffic worth?
          </h3>

          <label className="block mb-7">
            <span className="flex items-baseline justify-between mb-2">
              <span className="text-sm text-primary">Requests per month</span>
              <span className="font-mono text-xs text-signal num-tabular">
                {requests.toLocaleString()}
              </span>
            </span>
            <input
              type="range"
              min="1000"
              max="1000000"
              step="1000"
              value={requests}
              onChange={(e) => setRequests(Number(e.target.value))}
              className="w-full accent-[var(--color-signal)]"
            />
            <span className="flex justify-between font-mono text-[10px] text-muted mt-1">
              <span>1k</span>
              <span>1M</span>
            </span>
          </label>

          <label className="block mb-7">
            <span className="flex items-baseline justify-between mb-2">
              <span className="text-sm text-primary">
                Traffic that genuinely needs a frontier model
              </span>
              <span className="font-mono text-xs text-signal num-tabular">
                {hardShare}%
              </span>
            </span>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={hardShare}
              onChange={(e) => setHardShare(Number(e.target.value))}
              className="w-full accent-[var(--color-signal)]"
            />
            <span className="flex justify-between font-mono text-[10px] text-muted mt-1">
              <span>everything is easy</span>
              <span>everything is hard</span>
            </span>
          </label>

          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Input tokens / request', value: tokIn, set: setTokIn },
              { label: 'Output tokens / request', value: tokOut, set: setTokOut },
            ].map((f) => (
              <label key={f.label} className="block">
                <span className="flex items-baseline justify-between mb-1.5">
                  <span className="text-xs text-primary">{f.label}</span>
                  {f.value === 500 && (
                    <span className="font-mono text-[9px] uppercase tracking-wider text-muted">
                      typical
                    </span>
                  )}
                </span>
                <input
                  type="number"
                  min="0"
                  step="50"
                  value={f.value}
                  onChange={(e) => f.set(Math.max(0, Number(e.target.value) || 0))}
                  className="w-full bg-panel border border-line rounded-md px-2 py-1.5 font-mono text-xs num-tabular focus:outline-none focus:border-signal"
                />
              </label>
            ))}
          </div>

          <p className="font-mono text-[10px] text-muted mt-5 leading-relaxed">
            {live ? (
              <>
                Tier prices read live from the running router
                {asOf && (
                  <>
                    {' '}
                    &middot;{' '}
                    {asOf.toLocaleDateString(undefined, {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                    })}
                  </>
                )}
                . Our numbers, not a marketing number.
              </>
            ) : (
              'Loading live tier prices&hellip;'
            )}
          </p>
        </div>

        {/* result */}
        <div className="p-6 md:p-8 bg-panel/50">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-cool mb-1">
            Per month
          </p>
          <div className="flex items-end gap-3 mb-1">
            <span className="font-display text-5xl font-bold text-cool num-tabular leading-none">
              {money(routed)}
            </span>
            <span className="font-mono text-xs text-muted mb-1.5">
              with routewise
            </span>
          </div>
          <p className="text-sm text-muted mb-7">
            <span className="text-primary font-semibold">
              {money(savedVsTypical)}
            </span>{' '}
            saved each month &mdash;{' '}
            <span className="text-primary font-semibold">
              {money(savedVsTypical * 12)}
            </span>{' '}
            a year ({pctVsTypical.toFixed(0)}% less).
          </p>

          <div className="space-y-3">
            {[
              {
                label: 'Typical frontier API',
                sub: '$3 / $15 per 1M — industry reference',
                value: allTypical,
                cls: 'text-muted',
                bar: 'bg-muted/40',
              },
              {
                label: 'All traffic → our frontier tier',
                sub: `${tier.frontier.model} · ${tier.frontier.provider}`,
                value: allFrontier,
                cls: 'text-signal',
                bar: 'bg-signal/50',
              },
              {
                label: 'With routewise',
                sub: `${hardShare}% frontier · ${midPct}% mid · ${cheapPct}% cheap`,
                value: routed,
                cls: 'text-cool',
                bar: 'bg-cool',
              },
            ].map((row) => (
              <div key={row.label}>
                <div className="flex items-baseline justify-between mb-1.5">
                  <span className="text-xs text-primary">{row.label}</span>
                  <span
                    className={`font-mono text-xs num-tabular ${row.cls}`}
                  >
                    {money(row.value)}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-line/60 overflow-hidden">
                  <div
                    className={`h-full ${row.bar} rounded-full transition-all duration-500`}
                    style={{
                      width: `${barMax > 0 ? (row.value / barMax) * 100 : 0}%`,
                    }}
                  />
                </div>
                <p className="font-mono text-[10px] text-muted mt-1">
                  {row.sub}
                </p>
              </div>
            ))}
          </div>

          {/* the actual ladder, at list price, no markup */}
          <div className="mt-6 pt-5 border-t border-line/70">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted mb-3">
              What we actually route to
            </p>
            <div className="space-y-1.5">
              {['cheap', 'mid', 'frontier'].map((k) => (
                <div
                  key={k}
                  className="flex items-baseline justify-between gap-3 font-mono text-[11px]"
                >
                  <span className="text-muted w-16 shrink-0">{k}</span>
                  <span className="text-primary truncate">{tier[k].model}</span>
                  <span className="text-muted num-tabular shrink-0">
                    ${tier[k].in} / ${tier[k].out}
                  </span>
                </div>
              ))}
            </div>
            <p className="font-mono text-[10px] text-muted mt-3 leading-relaxed">
              List price, per 1M tokens. We add no markup and take no cut of your
              spend &mdash; the saving comes from picking a smaller model, not from
              a discount.
            </p>
          </div>

          {/* the honest second number, and the way to a real one */}
          <div className="mt-5 pt-5 border-t border-line/70">
            <p className="text-xs text-muted leading-relaxed mb-3">
              Measured against our own frontier tier instead of the industry
              reference, that is{' '}
              <span className="text-primary font-semibold">
                {money(savedVsOurFrontier)}
              </span>
              /mo ({pctVsOurFrontier.toFixed(0)}%). The headline figure of{' '}
              {SAVINGS_PCT}% is the one measured on our own logged traffic; your
              number depends on how much of your traffic is genuinely hard, so
              score your own prompts rather than trusting ours.
            </p>
            <Link
              to="/calculator"
              className="inline-flex items-center gap-2 text-xs font-medium text-signal hover:underline"
            >
              Score your own prompts for an exact number
              <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

const PROBLEMS = [
  {
    art: 'flood',
    title: 'One model for everything',
    body: 'A "hi," a one-line factual question, and a genuinely hard system-design question all get sent to the same expensive, powerful model. Most queries do not need that much firepower.',
  },
  {
    art: 'price',
    title: 'Frontier prices for trivial work',
    body: 'Somebody is paying top-tier rates to answer questions a much cheaper model could handle just as well — and the bill is easy to miss until the invoice lands.',
  },
  {
    art: 'loop',
    title: 'Failure is invisible until it is expensive',
    body: 'When a provider rate-limits or falls over, the naive fix is to retry the same provider. That burns the retry budget without improving the odds of an answer.',
  },
]

function ProblemArt({ kind }) {
  if (kind === 'flood') {
    return (
      <svg viewBox="0 0 120 60" className="w-full h-auto" aria-hidden>
        {[6, 18, 30, 42, 54].map((y) => (
          <g key={y}>
            <circle cx="6" cy={y} r="2.5" fill="var(--color-muted)" opacity=".55" />
            <path
              d={`M 11 ${y} C 50 ${y}, 68 32, 90 32`}
              fill="none"
              stroke="var(--color-muted)"
              strokeWidth="1"
              opacity=".4"
            />
          </g>
        ))}
        <circle cx="104" cy="32" r="14" fill="var(--color-danger)" opacity=".1" />
        <circle cx="104" cy="32" r="14" fill="none" stroke="var(--color-danger)" strokeWidth="1.6" />
        <circle cx="104" cy="32" r="5" fill="var(--color-danger)" />
      </svg>
    )
  }
  if (kind === 'price') {
    return (
      <svg viewBox="0 0 120 60" className="w-full h-auto" aria-hidden>
        <rect x="16" y="44" width="20" height="12" rx="3" fill="var(--color-cool)" />
        <text x="26" y="38" textAnchor="middle" fill="var(--color-cool)" style={{ font: '9px ui-monospace, monospace' }}>
          $0.07
        </text>
        <rect x="66" y="8" width="20" height="48" rx="3" fill="var(--color-signal)" />
        <text x="76" y="38" textAnchor="middle" fill="var(--color-signal)" style={{ font: '9px ui-monospace, monospace' }}>
          $3.00
        </text>
        <path
          d="M 42 48 C 52 44, 54 26, 62 20"
          fill="none"
          stroke="var(--color-danger)"
          strokeWidth="1.3"
          strokeDasharray="3 3"
          opacity=".8"
        />
        <path d="M 58 19 L 64 19 L 61 25" fill="none" stroke="var(--color-danger)" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 120 60" className="w-full h-auto" aria-hidden>
      <path
        d="M 88 32 A 24 24 0 1 1 72 12"
        fill="none"
        stroke="var(--color-danger)"
        strokeWidth="1.5"
        strokeDasharray="4 4"
        opacity=".85"
      />
      <path
        d="M 68 8 L 76 12 L 69 18"
        fill="none"
        stroke="var(--color-danger)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="98" cy="32" r="8" fill="var(--color-danger)" opacity=".12" />
      <circle cx="98" cy="32" r="8" fill="none" stroke="var(--color-danger)" strokeWidth="1.5" />
      <line x1="94.5" y1="28.5" x2="101.5" y2="35.5" stroke="var(--color-danger)" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="101.5" y1="28.5" x2="94.5" y2="35.5" stroke="var(--color-danger)" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

const SNIPPET = `from openai import OpenAI

client = OpenAI(
    base_url="https://llm-router-d2b2.onrender.com/v1",  # <- this line
    api_key=os.environ["ROUTEWISE_API_KEY"],
)

client.chat.completions.create(
    model="routewise",   # cheap, mid, or frontier — decided per request
    messages=[{"role": "user", "content": "..."}],
)`

function CodeBlock() {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(SNIPPET)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {}
  }

  return (
    <div className="relative rounded-2xl border border-line bg-base shadow-pop overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-line bg-panel/60">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-danger/60" />
          <span className="w-2.5 h-2.5 rounded-full bg-signal/60" />
          <span className="w-2.5 h-2.5 rounded-full bg-cool/60" />
          <span className="font-mono text-[10px] text-muted ml-2">
            routewise.py
          </span>
        </div>
        <button
          onClick={copy}
          className="font-mono text-[10px] text-muted hover:text-primary transition-colors flex items-center gap-1.5"
        >
          {copied ? (
            <>
              <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-cool">
                <polyline points="2,7 5.5,10.5 12,3.5" />
              </svg>
              <span className="text-cool">copied</span>
            </>
          ) : (
            <>
              <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <rect x="4.5" y="4.5" width="8" height="8" rx="1.5" />
                <path d="M9.5 2.5H3A.5.5 0 0 0 2.5 3v6.5" />
              </svg>
              copy
            </>
          )}
        </button>
      </div>
      <pre className="p-4 md:p-5 overflow-x-auto text-[12px] leading-relaxed font-mono">
        <code>
          <span className="text-muted">{'from openai import OpenAI\n\n'}</span>
          <span className="text-primary">client</span>
          <span className="text-muted">{' = OpenAI(\n'}</span>
          <span className="text-signal">{'    base_url'}</span>
          <span className="text-muted">{'='}</span>
          <span className="text-cool">
            {'"https://llm-router-d2b2.onrender.com/v1"'}
          </span>
          <span className="text-signal">{',  # <- this line\n'}</span>
          <span className="text-signal">{'    api_key'}</span>
          <span className="text-muted">{'=os.environ['}</span>
          <span className="text-cool">{'"ROUTEWISE_API_KEY"'}</span>
          <span className="text-muted">{'],\n)\n\n'}</span>
          <span className="text-primary">client</span>
          <span className="text-muted">{'.'}</span>
          <span className="text-primary">chat</span>
          <span className="text-muted">{'.'}</span>
          <span className="text-primary">completions</span>
          <span className="text-muted">{'.'}</span>
          <span className="text-primary">create</span>
          <span className="text-muted">{'(\n'}</span>
          <span className="text-signal">{'    model'}</span>
          <span className="text-muted">{'='}</span>
          <span className="text-cool">{'"routewise"'}</span>
          <span className="text-muted">
            {',   # cheap, mid, or frontier — decided per request\n'}
          </span>
          <span className="text-signal">{'    messages'}</span>
          <span className="text-muted">{'=[{'}</span>
          <span className="text-cool">{'"role"'}</span>
          <span className="text-muted">{': '}</span>
          <span className="text-cool">{'"user"'}</span>
          <span className="text-muted">{', '}</span>
          <span className="text-cool">{'"content"'}</span>
          <span className="text-muted">{': '}</span>
          <span className="text-cool">{'"..."'}</span>
          <span className="text-muted">{'}],\n)'}</span>
        </code>
      </pre>
    </div>
  )
}

const PROOF = [
  {
    value: DATASETS.emma.trainRows,
    format: (n) => n.toLocaleString(),
    label: 'Claude-gold labels',
    detail: 'training set',
  },
  {
    value: 0,
    format: (n) => String(n),
    label: 'Extra API calls',
    detail: 'to score difficulty',
  },
  {
    value: 2,
    format: (n) => String(n),
    label: 'Independent providers',
    detail: 'for failover',
  },
  {
    value: SAVINGS_PCT,
    suffix: '%',
    format: (n) => String(n),
    label: 'Off the frontier tier',
    detail: `at our measured traffic mix (${SAVINGS_EXACT_PCT}% unrounded)`,
  },
]

export default function LandingPage() {
  return (
    <>
      {/* ---------------------------------------------------------------- hero */}
      <section className="relative overflow-hidden border-b border-line bg-panel">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-40 -right-32 w-[36rem] h-[36rem] rounded-full opacity-[0.15] dark:opacity-[0.18]"
          style={{
            background:
              'radial-gradient(circle, var(--color-signal) 0%, transparent 65%)',
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-48 -left-32 w-[32rem] h-[32rem] rounded-full opacity-[0.10] dark:opacity-[0.14]"
          style={{
            background:
              'radial-gradient(circle, var(--color-cool) 0%, transparent 65%)',
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              'radial-gradient(ellipse at center, transparent 55%, var(--color-base) 100%)',
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 right-0 w-[40%] overflow-hidden [mask-image:radial-gradient(ellipse_at_center,black_10%,transparent_70%)]"
          style={{
            backgroundImage:
              'radial-gradient(var(--color-muted) 0.6px, transparent 0.6px)',
            backgroundSize: '22px 22px',
            opacity: 0.18,
          }}
        />

        <div className="max-w-6xl mx-auto px-6 pt-14 sm:pt-20 pb-16 sm:pb-20 relative">
          <div className="grid lg:grid-cols-[1.05fr_0.95fr] gap-12 lg:gap-8 items-center">
            <div>
              <p className="font-mono text-xs text-signal tracking-wide uppercase mb-5 flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-signal opacity-60" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-signal" />
                </span>
                Difficulty-scored request routing
              </p>
              <h1 className="font-display text-4xl sm:text-5xl md:text-6xl font-semibold leading-[1.03] tracking-tight mb-6">
                Difficulty is a number.
                <br />
                Cost{' '}
                <span className="relative inline-block">
                  <span className="relative z-10 bg-gradient-to-r from-[var(--color-signal)] to-[var(--color-cool)] bg-clip-text text-transparent">
                    should be too.
                  </span>
                  <span
                    aria-hidden
                    className="absolute left-0 -bottom-1 h-[3px] w-full rounded-full bg-gradient-to-r from-[var(--color-signal)] to-[var(--color-cool)] opacity-40"
                  />
                </span>
              </h1>
              <p className="text-muted text-base leading-relaxed max-w-lg mb-9">
                You already know &ldquo;what is 2+2&rdquo; does not need a
                frontier model &mdash; but nothing in your stack knows which
                requests those are. routewise scores every request in under a
                millisecond, then sends it to the cheapest tier that can
                actually answer it.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <a
                  href="#the-math"
                  className="inline-flex items-center gap-2 bg-signal text-white font-semibold text-sm px-6 py-3 rounded-full hover:brightness-110 hover:shadow-card-hover shadow-card transition-all"
                >
                  Show me the money
                  <ArrowRight />
                </a>
                <Link
                  to="/"
                  className="inline-flex items-center gap-2 font-mono text-xs text-primary bg-base border border-line rounded-full px-6 py-3 hover:border-signal/50 hover:shadow-card transition-all"
                >
                  See it running
                </Link>
              </div>
            </div>

            <div className="lg:pl-4">
              <RoutingVisual />
            </div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------- problem */}
      <section className="border-b border-line">
        <div className="max-w-6xl mx-auto px-6 py-16 sm:py-20">
          <Reveal>
            <div className="max-w-2xl mb-12">
              <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-danger mb-3">
                The problem
              </p>
              <h2 className="font-display text-2xl sm:text-3xl font-semibold tracking-tight">
                LLM spend is mostly accidental.
              </h2>
              <p className="text-muted text-sm leading-relaxed mt-4">
                Not a single bug — the default behaviour of every integration.
                Point everything at the best model you can afford, and send it
                all of your traffic.
              </p>
            </div>
          </Reveal>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {PROBLEMS.map((item, i) => (
              <Reveal key={item.title} delay={i * 60}>
                <div className="h-full bg-surface border border-line rounded-2xl shadow-card p-6 flex flex-col">
                  <div className="mb-5 rounded-xl border border-line bg-panel/60 px-3 py-2">
                    <ProblemArt kind={item.art} />
                  </div>
                  <span className="font-mono text-[10px] text-danger mb-2 block">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <h3 className="font-display text-lg font-semibold tracking-tight mb-2">
                    {item.title}
                  </h3>
                  <p className="text-muted text-sm leading-relaxed">
                    {item.body}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ----------------------------------------------------------- the math */}
      <section id="the-math" className="border-b border-line scroll-mt-16">
        <div className="max-w-6xl mx-auto px-6 py-16 sm:py-20">
          <Reveal>
            <div className="max-w-2xl mb-10">
              <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal mb-3">
                The math
              </p>
              <h2 className="font-display text-2xl sm:text-3xl font-semibold tracking-tight">
                The cheap tier costs {FRONTIER_VS_CHEAP.toFixed(1)}x less than the frontier one.
              </h2>
              <p className="text-muted text-sm leading-relaxed mt-4">
                Same shape of request, a smaller model. The only question is how
                much of your traffic actually earns the expensive one. Drag the
                sliders, and if you want your real prompts scored instead of a
                guess, the calculator does that too.
              </p>
            </div>
          </Reveal>

          <Reveal delay={60}>
            <CostSimulator />
          </Reveal>
        </div>
      </section>

      {/* -------------------------------------------------------- integration */}
      <section className="border-b border-line bg-panel">
        <div className="max-w-6xl mx-auto px-6 py-16 sm:py-20">
          <div className="grid lg:grid-cols-[0.85fr_1.15fr] gap-10 lg:gap-14 items-center">
            <Reveal>
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal mb-3">
                  Integration
                </p>
                <h2 className="font-display text-2xl sm:text-3xl font-semibold tracking-tight mb-4">
                  You already have an OpenAI client. Keep it.
                </h2>
                <p className="text-muted text-sm leading-relaxed mb-6">
                  routewise speaks the OpenAI wire format, so adopting it is one
                  line: point your <code className="font-mono text-xs text-primary">base_url</code>{' '}
                  at the router. Streaming, tools, retries, and your existing
                  error handling all keep working.
                </p>
                <ul className="space-y-2.5">
                  {[
                    'No SDK, no new dependency',
                    'Force a tier any time with model="cheap" | "mid" | "frontier"',
                    'Same responses, tracked per request with real cost',
                  ].map((line) => (
                    <li key={line} className="flex items-start gap-2.5 text-sm text-muted">
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 14 14"
                        fill="none"
                        stroke="var(--color-cool)"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className="mt-0.5 shrink-0"
                      >
                        <polyline points="2,7 5.5,10.5 12,3.5" />
                      </svg>
                      {line}
                    </li>
                  ))}
                </ul>
              </div>
            </Reveal>

            <Reveal delay={60}>
              <CodeBlock />
            </Reveal>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------- what it does */}
      <Reveal>
        <Suspense
          fallback={
            <div className="max-w-6xl mx-auto px-6 py-16">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-40 bg-line/50 rounded-lg animate-pulse"
                  />
                ))}
              </div>
            </div>
          }
        >
          <Features />
        </Suspense>
      </Reveal>

      {/* -------------------------------------------------------- how it works */}
      <Reveal>
        <HowItWorks />
      </Reveal>

      {/* ---------------------------------------------------------------- proof */}
      <Reveal>
        <section className="border-y border-line bg-panel">
          <div className="max-w-6xl mx-auto px-6 py-12 md:py-14">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal mb-2">
              By the numbers
            </p>
            <h2 className="font-display text-2xl sm:text-3xl font-semibold tracking-tight mb-7">
              Not a wrapper. A trained, tested system.
            </h2>
            <div className="grid grid-cols-2 lg:grid-cols-4 border border-line rounded-xl overflow-hidden bg-surface divide-x divide-y lg:divide-y-0 divide-line">
              {PROOF.map((stat) => (
                <div key={stat.label} className="p-5 md:p-6">
                  <p className="font-display text-3xl font-bold text-signal num-tabular">
                    <AnimatedCounter
                      value={stat.value}
                      suffix={stat.suffix || ''}
                      duration={1100}
                    />
                    <span className="sr-only">{stat.format(stat.value)}</span>
                  </p>
                  <p className="text-sm text-primary mt-1">{stat.label}</p>
                  <p className="font-mono text-[10px] text-muted mt-1">
                    {stat.detail}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </Reveal>

      {/* --------------------------------------------------------------- handoff */}
      <section className="relative overflow-hidden border-t border-line bg-panel">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-32 left-1/2 -translate-x-1/2 w-[44rem] h-[28rem] rounded-full opacity-10 dark:opacity-15"
          style={{
            background:
              'radial-gradient(ellipse, var(--color-cool) 0%, transparent 70%)',
          }}
        />
        <div className="max-w-6xl mx-auto px-6 py-20 sm:py-24 text-center relative">
          <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4 flex items-center justify-center gap-2">
            <span className="w-1 h-4 rounded-full bg-signal" />
            Now see it work
          </p>
          <h2 className="font-display text-3xl md:text-4xl font-semibold mb-4 text-primary">
            Cut your LLM bill without cutting quality.
          </h2>
          <p className="text-muted text-sm max-w-lg mx-auto mb-8">
            Every routing decision, tier, and real cost in the demo is the actual
            running system — not a mockup.
          </p>
          <p className="text-muted text-xs max-w-xl mx-auto mb-8 font-mono">
            {EASY_BAND_AB_FOOTNOTE}
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              to="/"
              className="inline-flex items-center gap-2 bg-signal text-white font-semibold text-sm px-6 py-3 rounded-full hover:brightness-110 hover:shadow-card-hover shadow-card transition-all"
            >
              Open the live demo
              <ArrowRight />
            </Link>
            <Link
              to="/playground"
              className="inline-flex items-center gap-2 font-mono text-xs text-primary bg-base border border-line rounded-full px-6 py-3 hover:border-signal/50 hover:shadow-card transition-all"
            >
              Try the API
            </Link>
            <Link
              to="/metrics"
              className="inline-flex items-center gap-2 font-mono text-xs text-muted bg-base border border-line rounded-full px-6 py-3 hover:border-signal/50 hover:text-primary hover:shadow-card transition-all"
            >
              Live metrics
            </Link>
          </div>
        </div>
      </section>
    </>
  )
}
