const STACK = ['FastAPI', 'LightGBM', 'sentence-transformers', 'Groq', 'Ollama', 'Supabase', 'React']

export default function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="max-w-6xl mx-auto px-6 py-10 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex flex-wrap gap-2">
          {STACK.map((s) => (
            <span key={s} className="font-mono text-[11px] text-muted border border-line rounded-full px-2.5 py-1">
              {s}
            </span>
          ))}
        </div>
        <a href="https://github.com" target="_blank" rel="noreferrer" className="font-mono text-xs text-muted hover:text-primary transition-colors">
          View source →
        </a>
      </div>
    </footer>
  )
}
