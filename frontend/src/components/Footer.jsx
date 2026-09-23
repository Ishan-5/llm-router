import { Link } from 'react-router-dom'

const STACK = ['FastAPI', 'LightGBM', 'sentence-transformers', 'Groq', 'Ollama', 'Supabase', 'React']

const PRODUCT_LINKS = [
  { to: '/', label: 'Live demo' },
  { to: '/metrics', label: 'Metrics' },
  { to: '/models', label: 'Models' },
  { to: '/about', label: 'About' },
]

const DEV_LINKS = [
  { to: '/guide', label: 'Developer guide' },
  { to: '/evaluate', label: 'Evaluate' },
  { to: '/get-started', label: 'Get started' },
  { href: 'https://www.npmjs.com/package/routewise', label: 'Terminal CLI', external: true },
  { href: 'https://github.com/Ishan-5/llm-router#readme', label: 'Documentation', external: true },
]

const SOCIAL_ICONS = [
  {
    href: 'https://github.com/Ishan-5/llm-router',
    label: 'GitHub — star, fork, self-host',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" stroke="none" aria-hidden>
        <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.2.7-3.88-1.54-3.88-1.54-.52-1.33-1.28-1.68-1.28-1.68-1.04-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.76 2.7 1.25 3.35.96.1-.75.4-1.25.72-1.54-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11.1 11.1 0 0 1 5.8 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.83 1.19 3.09 0 4.41-2.7 5.38-5.26 5.66.41.35.77 1.05.77 2.12 0 1.53-.01 2.77-.01 3.15 0 .31.21.67.8.56A10.51 10.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5z" />
      </svg>
    ),
  },
  {
    href: 'https://www.npmjs.com/package/routewise',
    label: 'npm — routewise terminal CLI',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" stroke="none" aria-hidden>
        <path d="M1.763 0C.787 0 0 .787 0 1.763v20.474C0 23.213.787 24 1.763 24h20.474c.976 0 1.763-.787 1.763-1.763V1.763C24 .787 23.213 0 22.237 0zM5.13 5.323l13.837.019-.009 13.658h-3.464l.01-10.053h-2.828V19.24H5.128z" />
      </svg>
    ),
  },
  {
    href: 'https://pypi.org/project/routewise/',
    label: 'PyPI — routewise Python SDK',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
        <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
        <line x1="12" y1="22.08" x2="12" y2="12" />
      </svg>
    ),
  },
]

function LinkRow({ item }) {
  return item.href ? (
    <a
      href={item.href}
      target={item.external ? '_blank' : undefined}
      rel={item.external ? 'noreferrer' : undefined}
      className="group flex items-center gap-1.5 text-sm text-muted hover:text-primary transition-colors w-fit"
    >
      {item.label}
      <svg width="9" height="9" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        className="opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all">
        <line x1="2" y1="7" x2="12" y2="7" />
        <polyline points="7,2 12,7 7,12" />
      </svg>
    </a>
  ) : (
    <Link to={item.to} className="group flex items-center gap-1.5 text-sm text-muted hover:text-primary transition-colors w-fit">
      {item.label}
      <svg width="9" height="9" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        className="opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all">
        <line x1="2" y1="7" x2="12" y2="7" />
        <polyline points="7,2 12,7 7,12" />
      </svg>
    </Link>
  )
}

export default function Footer({ backendOnline }) {
  return (
    <footer className="relative border-t border-line bg-panel overflow-hidden">
      <div className="relative h-px bg-gradient-to-r from-transparent via-signal/40 to-transparent" />
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute -top-16 -left-24 w-72 h-72 rounded-full bg-cool/5 blur-3xl" />
        <div className="absolute -top-20 -right-24 w-72 h-72 rounded-full bg-signal/5 blur-3xl" />
        <div
          className="absolute inset-0 opacity-[0.15] dot-grid [mask-image:radial-gradient(ellipse_80%_60%_at_50%_100%,black,transparent)]"
        />
      </div>

      <div className="relative max-w-6xl mx-auto px-6 pt-14 pb-10">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 mb-10">
          <div className="md:col-span-5">
            <div className="flex items-center gap-2.5 mb-3">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-signal opacity-40 animate-ping" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-signal shadow-[0_0_10px_var(--color-signal)]" />
              </span>
              <span className="font-display font-semibold text-lg tracking-tight">
                route<span className="text-signal">wise</span>
              </span>
            </div>
            <p className="text-sm text-muted leading-relaxed max-w-xs mb-5">
              Cost-aware LLM request router. Scores every query for difficulty, routes to the cheapest tier that can handle it.
            </p>
            <div className={`inline-flex items-center gap-2 font-mono text-[10px] rounded-full border px-3 py-1.5 shadow-card ${backendOnline ? 'border-cool/30 bg-cool/10 text-cool' : 'border-danger/30 bg-danger/10 text-danger'}`}>
              <span className="relative flex h-1.5 w-1.5">
                <span className={`absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping ${backendOnline ? 'bg-cool' : 'bg-danger'}`} />
                <span className={`relative inline-flex rounded-full h-1.5 w-1.5 ${backendOnline ? 'bg-cool' : 'bg-danger'}`} />
              </span>
              {backendOnline ? 'All systems operational' : 'Backend offline'}
            </div>
          </div>

          <div className="md:col-span-2">
            <h4 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-3 flex items-center gap-2">
              <span className="w-1 h-1 rounded-full bg-signal" />Product
            </h4>
            <div className="flex flex-col gap-2.5">
              {PRODUCT_LINKS.map((item) => <LinkRow key={item.label} item={item} />)}
            </div>
          </div>

          <div className="md:col-span-2">
            <h4 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-3 flex items-center gap-2">
              <span className="w-1 h-1 rounded-full bg-cool" />Developers
            </h4>
            <div className="flex flex-col gap-2.5">
              {DEV_LINKS.map((item) => <LinkRow key={item.label} item={item} />)}
            </div>
          </div>

          <div className="md:col-span-3">
            <h4 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-3 flex items-center gap-2">
              <span className="w-1 h-1 rounded-full bg-danger" />Connect
            </h4>
            <div className="flex items-center gap-2.5 mb-4">
              {SOCIAL_ICONS.map((s) => (
                <a
                  key={s.label}
                  href={s.href}
                  title={s.label}
                  aria-label={s.label}
                  target="_blank"
                  rel="noreferrer"
                  className="w-10 h-10 rounded-xl flex items-center justify-center bg-base border border-line/70 text-primary shadow-card transition-all hover:text-signal hover:border-signal/40 hover:-translate-y-0.5 hover:shadow-card-hover"
                >
                  {s.icon}
                </a>
              ))}
            </div>
            <p className="font-mono text-[10px] text-muted/70 leading-relaxed mb-3">
              Open-source router.<br />Star it, fork it, self-host it.
            </p>
            <a
              href="#top"
              className="group inline-flex items-center gap-1.5 font-mono text-[10px] text-muted hover:text-primary transition-colors scroll-smooth"
            >
              Back to top
              <svg width="10" height="10" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="group-hover:-translate-y-0.5 transition-transform">
                <line x1="7" y1="12" x2="7" y2="2" />
                <polyline points="3,6 7,2 11,6" />
              </svg>
            </a>
          </div>
        </div>

        <div className="border-t border-line pt-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div className="flex flex-wrap gap-2">
            {STACK.map((s) => (
              <span key={s} className="font-mono text-[10px] text-muted bg-base border border-line rounded-full px-2.5 py-1 shadow-sm">
                {s}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-4">
            <span className="font-mono text-[10px] text-muted/70">© 2026</span>
            <span className="w-px h-3 bg-line" />
            <p className="font-mono text-[10px] text-muted">
              Built by Devansh Kumar Pandey
            </p>
            <span className="w-px h-3 bg-line" />
            <div className="flex items-center gap-3">
              <Link to="/privacy" className="font-mono text-[10px] text-muted hover:text-signal transition-colors">Privacy</Link>
              <Link to="/terms" className="font-mono text-[10px] text-muted hover:text-signal transition-colors">Terms</Link>
            </div>
          </div>
        </div>
      </div>
    </footer>
  )
}