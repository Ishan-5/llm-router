import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { describeRequestError, fetchReliability } from '../api'

const PALETTE = {
  dark: {
    line: '#232D3B', muted: '#7C8B9A', panel: '#121821', signal: '#FF9F1C',
    cool: '#3FB8AF', danger: '#E85D5D', primary: '#E6EDF3', grid: '#1A2230',
  },
  light: {
    line: '#E2E2DD', muted: '#6B7078', panel: '#F6F6F4', signal: '#C2570C',
    cool: '#0F766E', danger: '#B91C1C', primary: '#16181C', grid: '#EDEDE8',
  },
}

function Stat({ label, value, hint }) {
  return (
    <div className="bg-panel border border-line rounded-lg p-4">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted mb-2">{label}</p>
      <p className="font-display text-2xl font-semibold text-primary leading-none">{value}</p>
      {hint ? <p className="font-mono text-[10px] text-muted mt-2 leading-relaxed">{hint}</p> : null}
    </div>
  )
}

export default function ReliabilityPage({ isDark = true }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const p = isDark ? PALETTE.dark : PALETTE.light
  const tooltipStyle = {
    background: p.panel, border: `1px solid ${p.line}`, borderRadius: 8,
    fontFamily: 'JetBrains Mono', fontSize: 11, color: p.primary,
  }
  const tickStyle = { fill: p.muted, fontSize: 11, fontFamily: 'JetBrains Mono' }

  useEffect(() => {
    let alive = true
    fetchReliability()
      .then((d) => { if (alive) setData(d) })
      .catch((e) => { if (alive) setError(describeRequestError(e)) })
    return () => { alive = false }
  }, [])

  if (error) {
    return (
      <section className="max-w-6xl mx-auto px-6 py-16 border-t border-line">
        <p className="font-mono text-xs text-danger">{error}</p>
      </section>
    )
  }

  if (!data) {
    return (
      <section className="max-w-6xl mx-auto px-6 py-16 border-t border-line">
        <div className="h-4 w-24 skeleton rounded mb-4" />
        <div className="h-9 w-96 skeleton rounded mb-8" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-24 skeleton rounded-lg" />)}
        </div>
        <div className="h-72 skeleton rounded-lg" />
      </section>
    )
  }

  const empty = data.sample.total === 0
  const s = data.sample
  const pct = (v) => (v == null ? 'n/a' : `${Math.round(v * 100)}%`)
  const num = (v, digits = 3) => (v == null ? 'n/a' : v.toFixed(digits))
  const labelledShare = s.total ? s.labeled / s.total : 0

  return (
    <section className="max-w-6xl mx-auto px-6 py-16 border-t border-line">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted mb-3">Calibration</p>
      <h1 className="font-display text-3xl md:text-4xl font-semibold text-primary mb-3">
        Does the difficulty score mean what it says?
      </h1>
      <p className="font-mono text-xs text-muted leading-relaxed max-w-3xl mb-10">
        Routing turns one number into a price, so a score of 6 should mean &ldquo;about 6/10 hard&rdquo;.
        This compares the classifier&rsquo;s score against an independent LLM-as-labeler score for the
        same requests, then reports how each tier performed once it was chosen.
      </p>

      {empty ? (
        <div className="bg-panel border border-line rounded-lg p-8">
          <p className="font-display text-lg font-semibold text-primary mb-2">Nothing to calibrate yet</p>
          <p className="font-mono text-xs text-muted leading-relaxed">
            {data.message || 'Send a few routed requests first.'} Scores are recorded on every request;
            ground-truth labels arrive for a sample of traffic in the background.
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
            <Stat
              label="Mean abs. error"
              value={num(data.mae, 2)}
              hint="Average gap between predicted and labelled difficulty, in points out of 10."
            />
            <Stat
              label="Calibration error"
              value={num(data.ece, 3)}
              hint="Expected calibration error across score bins. Lower is more trustworthy."
            />
            <Stat
              label="Borderline traffic"
              value={pct(data.borderline_share)}
              hint={`Share of requests within 0.25 of ${data.thresholds.cheap_ceil} or ${data.thresholds.frontier_floor}.`}
            />
            <Stat
              label="Labelled sample"
              value={`${s.labeled} / ${s.total}`}
              hint={`${pct(labelledShare)} of analysed requests have a ground-truth label.`}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-10">
            <div className="bg-panel border border-line rounded-lg p-5">
              <h2 className="font-display text-lg font-semibold text-primary mb-1">Reliability</h2>
              <p className="font-mono text-[10px] text-muted mb-5 leading-relaxed">
                Bars should be the same height in each bin. Taller predicted bars mean the model
                overestimates difficulty; taller actual bars mean it underestimates.
              </p>
              {data.reliability.length ? (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={data.reliability} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                    <CartesianGrid stroke={p.grid} vertical={false} />
                    <XAxis dataKey="bin" tick={tickStyle} tickLine={false} axisLine={{ stroke: p.line }} />
                    <YAxis domain={[0, 10]} tick={tickStyle} tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={tooltipStyle} cursor={{ fill: p.grid, opacity: 0.4 }} />
                    <Legend wrapperStyle={{ fontFamily: 'JetBrains Mono', fontSize: 10 }} />
                    <Bar dataKey="predicted" name="Predicted" fill={p.signal} radius={[3, 3, 0, 0]} />
                    <Bar dataKey="actual" name="Labelled" fill={p.cool} radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="font-mono text-xs text-muted py-16 text-center">
                  No labelled requests yet. The bars appear once the labeler has scored a sample.
                </p>
              )}
            </div>

            <div className="bg-panel border border-line rounded-lg p-5">
              <h2 className="font-display text-lg font-semibold text-primary mb-1">Score distribution</h2>
              <p className="font-mono text-[10px] text-muted mb-5 leading-relaxed">
                Where the classifier actually puts traffic. Mass bunched at one end means the
                thresholds barely matter; vertical lines are the balanced-mode boundaries.
              </p>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={data.histogram} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke={p.grid} vertical={false} />
                  <XAxis dataKey="score" tick={tickStyle} tickLine={false} axisLine={{ stroke: p.line }} />
                  <YAxis tick={tickStyle} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: p.grid, opacity: 0.4 }} />
                  <ReferenceLine x={Math.floor(data.thresholds.cheap_ceil)} stroke={p.cool} strokeDasharray="4 3" />
                  <ReferenceLine x={Math.floor(data.thresholds.frontier_floor)} stroke={p.danger} strokeDasharray="4 3" />
                  <Bar dataKey="count" name="Requests" radius={[3, 3, 0, 0]}>
                    {data.histogram.map((d) => (
                      <Cell
                        key={d.score}
                        fill={d.score < data.thresholds.cheap_ceil ? p.cool
                          : d.score < data.thresholds.frontier_floor ? p.signal : p.danger}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-panel border border-line rounded-lg p-5 overflow-x-auto">
              <h2 className="font-display text-lg font-semibold text-primary mb-1">How each tier performed</h2>
              <p className="font-mono text-[10px] text-muted mb-4">
                Measured on served requests, not projected.
              </p>
              <table className="w-full font-mono text-[11px]">
                <thead>
                  <tr className="text-muted text-left border-b border-line">
                    <th className="py-2 pr-3 font-normal">Tier</th>
                    <th className="py-2 pr-3 font-normal text-right">n</th>
                    <th className="py-2 pr-3 font-normal text-right">Avg cost</th>
                    <th className="py-2 pr-3 font-normal text-right">Latency</th>
                    <th className="py-2 pr-3 font-normal text-right">Fallback</th>
                    <th className="py-2 pr-3 font-normal text-right">Quality</th>
                    <th className="py-2 font-normal text-right">Feedback</th>
                  </tr>
                </thead>
                <tbody>
                  {data.tiers.map((t) => (
                    <tr key={t.tier} className="border-b border-line/60 last:border-0 text-primary">
                      <td className="py-2 pr-3">{t.tier}</td>
                      <td className="py-2 pr-3 text-right">{t.requests}</td>
                      <td className="py-2 pr-3 text-right">${t.avg_cost.toFixed(6)}</td>
                      <td className="py-2 pr-3 text-right">{Math.round(t.avg_latency_ms)} ms</td>
                      <td className="py-2 pr-3 text-right">{pct(t.fallback_rate)}</td>
                      <td className="py-2 pr-3 text-right">{t.avg_quality == null ? 'n/a' : t.avg_quality.toFixed(1)}</td>
                      <td className="py-2 text-right">
                        <span className="text-cool">{t.feedback_up}</span>
                        <span className="text-muted"> / </span>
                        <span className="text-danger">{t.feedback_down}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="bg-panel border border-line rounded-lg p-5 overflow-x-auto">
              <h2 className="font-display text-lg font-semibold text-primary mb-1">Intended vs served</h2>
              <p className="font-mono text-[10px] text-muted mb-4">
                Off-diagonal rows are failovers, not errors.
              </p>
              <table className="w-full font-mono text-[11px]">
                <thead>
                  <tr className="text-muted text-left border-b border-line">
                    <th className="py-2 pr-3 font-normal">Intended</th>
                    <th className="py-2 pr-3 font-normal">Served by</th>
                    <th className="py-2 font-normal text-right">Requests</th>
                  </tr>
                </thead>
                <tbody>
                  {data.confusion.map((row) => (
                    <tr key={`${row.intended}-${row.served}`} className="border-b border-line/60 last:border-0 text-primary">
                      <td className="py-2 pr-3">{row.intended}</td>
                      <td className={`py-2 pr-3 ${row.intended === row.served ? 'text-cool' : 'text-signal'}`}>
                        {row.served}
                      </td>
                      <td className="py-2 text-right">{row.requests}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <p className="font-mono text-[10px] text-muted leading-relaxed mt-8 max-w-3xl">
            Analysed the most recent {s.total} routed requests ({s.judged} judged for quality,{' '}
            {s.with_feedback} with user feedback). Labels are produced by a separate LLM pass
            (LLM-as-labeler) that never sees the classifier&rsquo;s output, so the two scores are
            independent.
          </p>
        </>
      )}
    </section>
  )
}
