export default function AboutPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-20">

      {/* Problem */}
      <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4">About routewise</p>
      <h1 className="font-display text-4xl font-semibold leading-tight tracking-tight mb-8">
        The problem I kept running into
      </h1>
      <p className="text-muted text-base leading-relaxed mb-4">
        Every time I looked at how people use LLM APIs, the same waste showed up: a "hi," a one-line
        factual question, and a genuinely hard system-design question all get sent to the same expensive,
        powerful model. Most queries don't need that much firepower. Somebody's paying frontier-model
        prices for questions a much cheaper model could answer just as well.
      </p>
      <p className="text-muted text-base leading-relaxed mb-16">
        routewise is my attempt at fixing that — a router that sits between an app and its LLM providers,
        figures out how hard each incoming query actually is, and sends it to the cheapest model that can
        handle it properly.
      </p>

      {/* What it does */}
      <div className="border-t border-line pt-12 mb-16">
        <h2 className="font-display text-2xl font-semibold mb-8">What it actually does</h2>
        <div className="flex flex-col gap-6">
          {[
            {
              title: 'Scores difficulty in real time',
              body: 'A regression model trained on 6,500 labeled queries predicts how hard a request is on a 0–10 scale, directly from the text — no API call needed, so it doesn\'t add meaningful latency of its own.',
            },
            {
              title: 'Routes across four tiers',
              body: 'From a free local model up to frontier-class models, biased conservatively — when a query is borderline, it errs toward the safer, more capable tier rather than the cheaper one.',
            },
            {
              title: 'Remembers near-duplicate questions',
              body: 'A semantic cache recognizes when a new query is close enough to one it\'s already answered, and returns that instantly — while staying deliberately cautious about how similar is similar enough, since two almost-identical questions can have very different correct answers.',
            },
            {
              title: 'Doesn\'t fall over when a provider does',
              body: 'If one model or provider fails or gets rate-limited, the request automatically steps down to a different tier — and if an entire provider goes down, it fails over to a completely independent second provider (Gemini) rather than just retrying the same one.',
            },
            {
              title: 'Screens for bad input before doing anything else',
              body: 'Prompt-injection attempts and personal information get caught and handled before a query ever reaches a model.',
            },
            {
              title: 'Lets you bring your own models',
              body: 'If you already have API keys for OpenAI, Anthropic, or others, you can wire them into your own tier configuration instead of using the defaults.',
            },
          ].map(({ title, body }) => (
            <div key={title} className="border-l-2 border-line pl-5">
              <p className="font-display font-semibold text-primary mb-1">{title}</p>
              <p className="text-muted text-sm leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </div>

      {/* What I actually built */}
      <div className="border-t border-line pt-12 mb-16">
        <h2 className="font-display text-2xl font-semibold mb-4">What I actually built, not just designed</h2>
        <p className="text-muted text-base leading-relaxed">
          This wasn't a weekend script. It's a full system: a trained ML model with real, honestly-reported
          accuracy numbers; a production-style FastAPI backend with authentication, rate limiting, and
          per-key budget controls; a React dashboard; a published Python SDK (<code className="font-mono text-xs bg-line px-1.5 py-0.5 rounded">pip install routewise</code>);
          an automated test suite; and a live, deployed instance you can actually use right now, not just read about.
        </p>
      </div>

      {/* What it isn't */}
      <div className="border-t border-line pt-12 mb-16">
        <h2 className="font-display text-2xl font-semibold mb-4">What it isn't</h2>
        <p className="text-muted text-base leading-relaxed">
          I'd rather say this plainly than let someone find it out and wonder why I didn't mention it.
          This is a portfolio-scale project, not a production SaaS serving real paying customers. Some
          things reflect that honestly: the local model tier only runs where I demo it locally (cloud
          hosting has no GPU for it), rate limiting works for a single server instance rather than a
          distributed fleet, and the injection/PII screening is pattern-based rather than a trained
          classifier. None of that is hidden — it's documented in the project's technical README,
          alongside the reasoning behind every real engineering tradeoff I made.
        </p>
      </div>

      {/* Try it */}
      <div className="border-t border-line pt-12 mb-16 bg-panel -mx-6 px-6 py-12 -my-12">
        <h2 className="font-display text-2xl font-semibold mb-4">Try it</h2>
        <p className="text-muted text-base leading-relaxed mb-6">
          The live demo is a real, working instance — type anything into it and watch the actual routing
          decision happen. No account needed.
        </p>
        <div className="flex flex-wrap gap-4">
          <a href="/" className="font-mono text-xs px-4 py-2 rounded-lg border border-signal text-signal hover:bg-signal/10 transition">
            Live demo
          </a>
          <a href="https://github.com/Ishan-5/llm-router" target="_blank" rel="noreferrer" className="font-mono text-xs px-4 py-2 rounded-lg border border-line text-muted hover:text-primary hover:border-signal/50 transition">
            GitHub
          </a>
          <a href="https://pypi.org/project/routewise/" target="_blank" rel="noreferrer" className="font-mono text-xs px-4 py-2 rounded-lg border border-line text-muted hover:text-primary hover:border-signal/50 transition">
            pip install routewise
          </a>
        </div>
      </div>

      {/* About me */}
      <div className="border-t border-line pt-12">
        <h2 className="font-display text-2xl font-semibold mb-6">Built by</h2>
        <div className="flex flex-col gap-1 mb-6">
          <p className="font-display font-semibold text-xl">Devansh Kumar Pandey</p>
          <p className="font-mono text-xs text-muted">B.Tech Electronics Engineering · HBTU Kanpur · 2024–2028</p>
        </div>
        <p className="text-muted text-sm leading-relaxed mb-8 max-w-xl">
          I build things to understand them. routewise started as a question — "does query difficulty
          actually predict which model tier you need?" — and turned into a full system worth shipping.
          I'm interested in the intersection of ML and backend infrastructure, and I'm actively looking
          for opportunities where I can keep doing exactly that.
        </p>
        <div className="flex flex-wrap gap-4">
          <a href="https://www.linkedin.com/in/devansh584" target="_blank" rel="noreferrer" className="font-mono text-xs px-4 py-2 rounded-lg border border-line text-muted hover:text-primary hover:border-signal/50 transition">
            LinkedIn
          </a>
          <a href="https://github.com/Ishan-5" target="_blank" rel="noreferrer" className="font-mono text-xs px-4 py-2 rounded-lg border border-line text-muted hover:text-primary hover:border-signal/50 transition">
            GitHub
          </a>
          <a href="mailto:devansh.7711@gmail.com" className="font-mono text-xs px-4 py-2 rounded-lg border border-line text-muted hover:text-primary hover:border-signal/50 transition">
            devansh.7711@gmail.com
          </a>
        </div>
      </div>

    </div>
  )
}
