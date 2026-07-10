import ThemeToggle from './ThemeToggle'

export default function Header({ isDark, toggleTheme }) {
  return (
    <header className="border-b border-line">
      <div className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-2 h-2 rounded-full bg-signal" />
          <span className="font-display font-semibold text-lg tracking-tight">
            routewise
          </span>
        </div>
        <nav className="flex items-center gap-8 text-sm text-muted font-body">
          <a href="#how" className="hover:text-primary transition-colors">How it works</a>
          <a href="#metrics" className="hover:text-primary transition-colors">Metrics</a>
          <a href="https://github.com" target="_blank" rel="noreferrer" className="hover:text-primary transition-colors">GitHub</a>
          <ThemeToggle isDark={isDark} toggle={toggleTheme} />
        </nav>
      </div>
    </header>
  )
}
