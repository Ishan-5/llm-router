import { Link } from 'react-router-dom'

const STACK = ['FastAPI', 'LightGBM', 'sentence-transformers', 'Groq', 'Ollama', 'Supabase', 'React']

export default function Footer() {
  return (
    <footer className="border-t border-line bg-panel">
      <div className="max-w-6xl mx-auto px-6 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
          <div>
            <div className="flex items-center gap-2.5 mb-3">
              <div className="w-2 h-2 rounded-full bg-signal" />
              <span className="font-display font-semibold text-lg tracking-tight">
                route<span className="text-signal">wise</span>
              </span>
            </div>
            <p className="text-sm text-muted leading-relaxed max-w-xs">
              Cost-aware LLM request router. Scores every query for difficulty, routes to the cheapest tier that can handle it.
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <h4 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-1">Product</h4>
            <Link to="/" className="text-sm text-muted hover:text-primary transition-colors">Live demo</Link>
            <Link to="/models" className="text-sm text-muted hover:text-primary transition-colors">Models</Link>
            <Link to="/about" className="text-sm text-muted hover:text-primary transition-colors">About</Link>
          </div>
          <div className="flex flex-col gap-2">
            <h4 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-1">Developers</h4>
            <a href="https://github.com/Ishan-5/llm-router" target="_blank" rel="noreferrer" className="text-sm text-muted hover:text-primary transition-colors">GitHub</a>
            <a href="https://pypi.org/project/routewise/" target="_blank" rel="noreferrer" className="text-sm text-muted hover:text-primary transition-colors">PyPI package</a>
            <a href="https://github.com/Ishan-5/llm-router#readme" target="_blank" rel="noreferrer" className="text-sm text-muted hover:text-primary transition-colors">Documentation</a>
          </div>
        </div>
        <div className="border-t border-line pt-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div className="flex flex-wrap gap-2">
            {STACK.map((s) => (
              <span key={s} className="font-mono text-[10px] text-muted border border-line rounded-full px-2 py-0.5">
                {s}
              </span>
            ))}
          </div>
          <p className="font-mono text-[10px] text-muted">
            Built by Devansh Kumar Pandey
          </p>
        </div>
      </div>
    </footer>
  )
}
