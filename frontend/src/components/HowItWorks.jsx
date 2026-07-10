const STEPS = [
  {
    n: '01',
    title: 'Score',
    body: 'A LightGBM model trained on 6,500 labeled queries predicts a 0–10 difficulty score directly from the query text — no API call, sub-100ms.',
  },
  {
    n: '02',
    title: 'Route',
    body: 'The score maps to a tier: cheap (local model), mid, or frontier. A safety margin biases borderline queries toward the safer tier, not the cheaper one.',
  },
  {
    n: '03',
    title: 'Respond',
    body: 'A semantic cache checks for near-duplicate queries first. If the assigned tier fails or rate-limits, the request automatically steps down instead of erroring out.',
  },
]

export default function HowItWorks() {
  return (
    <section id="how" className="max-w-6xl mx-auto px-6 py-20 border-t border-line">
      <h2 className="font-display text-2xl font-semibold mb-14">How it works</h2>

      <div className="relative grid grid-cols-1 md:grid-cols-3 gap-10 md:gap-8">
        {/* connecting line through all three steps, echoing the hero diagram */}
        <div className="hidden md:block absolute top-[7px] left-[8.5%] right-[8.5%] h-px bg-line" />

        {STEPS.map((s) => (
          <div key={s.n} className="relative pl-0">
            <div className="hidden md:block absolute -top-[3px] left-0 w-3.5 h-3.5 rounded-full border-2 border-signal bg-base" />
            <span className="font-mono text-xs text-signal block mb-4 md:mb-6 md:mt-6">{s.n}</span>
            <h3 className="font-display text-lg font-semibold mb-2">{s.title}</h3>
            <p className="text-sm text-muted leading-relaxed">{s.body}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
