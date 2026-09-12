const STEPS = [
  {
    number: '01',
    title: 'Protect',
    description: 'Reject known injection patterns and redact sensitive values before logging.',
    detail: 'Edge checks',
    icon: 'shield',
  },
  {
    number: '02',
    title: 'Evaluate',
    description: 'Score difficulty while checking the semantic cache in parallel.',
    detail: 'Score + cache',
    icon: 'gauge',
  },
  {
    number: '03',
    title: 'Route',
    description: 'Select the most cost-effective tier for the work required.',
    detail: 'Policy decision',
    icon: 'route',
  },
  {
    number: '04',
    title: 'Deliver',
    description: 'Stream the response, cache successful results, and fail over if needed.',
    detail: 'Stream + fallback',
    icon: 'stream',
  },
]

function StepIcon({ name }) {
  if (name === 'shield') return <svg viewBox="0 0 24 24" fill="none"><path d="M12 3 19 6v5c0 4.6-2.9 8.2-7 10-4.1-1.8-7-5.4-7-10V6l7-3Z" stroke="currentColor" strokeWidth="1.7" /><path d="m8.5 11.8 2.1 2.1 4.8-4.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
  if (name === 'gauge') return <svg viewBox="0 0 24 24" fill="none"><path d="M5 18a7 7 0 1 1 14 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /><path d="m12 11 3 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /><circle cx="12" cy="18" r="1.3" fill="currentColor" /></svg>
  if (name === 'route') return <svg viewBox="0 0 24 24" fill="none"><path d="M4 6h6c3 0 3 6 6 6h4M4 18h6c3 0 3-6 6-6h4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /><path d="m16 9 4 3-4 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
  return <svg viewBox="0 0 24 24" fill="none"><path d="M4 8h7M4 12h13M4 16h10" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /><path d="m16 5 4 3-4 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
}

export default function HowItWorks() {
  return (
    <section id="how" className="border-y border-line bg-panel">
      <div className="max-w-6xl mx-auto px-6 py-12 md:py-14">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-7">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal mb-2">How it works</p>
            <h2 className="font-display text-2xl sm:text-3xl font-semibold tracking-tight">A simpler path to the right model.</h2>
          </div>
          <p className="max-w-sm text-sm leading-relaxed text-muted sm:text-right">Four lightweight decisions between a prompt and a response.</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 border border-line rounded-xl overflow-hidden bg-surface divide-y sm:divide-y-0 sm:divide-x divide-line">
          {STEPS.map((step) => (
            <article key={step.number} className="group relative min-h-[190px] p-5 md:p-6 bg-surface transition-colors hover:bg-base">
              <span aria-hidden className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-signal to-transparent opacity-0 group-hover:opacity-70 transition-opacity" />
              <div className="flex items-start justify-between gap-3">
                <span className="grid place-items-center size-9 rounded-lg border border-signal/25 bg-signal/10 text-signal"><span className="size-5"><StepIcon name={step.icon} /></span></span>
                <span className="font-mono text-[10px] text-muted">{step.number}</span>
              </div>
              <h3 className="mt-6 font-display text-lg font-semibold tracking-tight">{step.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{step.description}</p>
              <p className="mt-5 font-mono text-[10px] text-signal">{step.detail}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
