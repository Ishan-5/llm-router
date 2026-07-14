import ThemeToggle from './ThemeToggle'

export default function Header({ isDark, toggleTheme, onOpenSettings, byomActive, onNavigate, page }) {
  return (
    <header className="border-b border-line">
      <div className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between">
        <button onClick={() => onNavigate('home')} className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
          <div className="w-2 h-2 rounded-full bg-signal" />
          <span className="font-display font-semibold text-lg tracking-tight">
            routewise
          </span>
        </button>
        <nav className="flex items-center gap-8 text-sm text-muted font-body">
          <a href="#how" className={`hover:text-primary transition-colors ${page === 'home' ? 'text-primary' : ''}`}>How it works</a>
          <button onClick={() => onNavigate('pricing')} className={`hover:text-primary transition-colors ${page === 'pricing' ? 'text-primary font-medium' : ''}`}>Pricing</button>
          <a href="#metrics" className="hover:text-primary transition-colors">Metrics</a>
          <a href="https://github.com/Ishan-5/llm-router" target="_blank" rel="noreferrer" className="hover:text-primary transition-colors">GitHub</a>
          <button
            onClick={onOpenSettings}
            className="relative flex items-center gap-1.5 font-mono text-xs border border-line rounded-full px-3 py-1.5 text-muted hover:text-primary hover:border-signal transition-colors"
          >
            {byomActive && (
              <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-signal" />
            )}
            <span>⚙</span>
            <span>Models</span>
          </button>
          <ThemeToggle isDark={isDark} toggle={toggleTheme} />
        </nav>
      </div>
    </header>
  )
}
