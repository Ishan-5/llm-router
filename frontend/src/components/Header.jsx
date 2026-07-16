import ThemeToggle from './ThemeToggle'

export default function Header({ isDark, toggleTheme, onOpenSettings, byomActive, onNavigate, page, user }) {
  async function handleSignOut() {
    const { supabase } = await import('../supabase')
    await supabase.auth.signOut()
  }
  return (
    <header className="border-b border-line">
      <div className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between">
        <button onClick={() => onNavigate('home')} className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
          <div className="w-2 h-2 rounded-full bg-signal" />
          <span className="font-display font-semibold text-lg tracking-tight">
            route<span className="text-signal">wise</span>
          </span>
        </button>
        <nav className="flex items-center gap-8 text-sm text-muted font-body">
          <a href="#how" className={`hover:text-primary transition-colors ${page === 'home' ? 'text-primary' : ''}`}>How it works</a>
          <button onClick={() => onNavigate('pricing')} className={`hover:text-primary transition-colors ${page === 'pricing' ? 'text-primary font-medium' : ''}`}>Pricing</button>
          <a href="#metrics" className="hover:text-primary transition-colors">Metrics</a>
          <button onClick={() => onNavigate('about')} className={`hover:text-primary transition-colors ${page === 'about' ? 'text-primary font-medium' : ''}`}>About</button>
          {user ? (
            <>
              <button onClick={() => onNavigate('dashboard')} className={`hover:text-primary transition-colors ${page === 'dashboard' ? 'text-primary font-medium' : ''}`}>Dashboard</button>
              <button onClick={handleSignOut} className="hover:text-primary transition-colors">Sign out</button>
            </>
          ) : (
            <button onClick={() => onNavigate('auth')} className={`hover:text-primary transition-colors ${page === 'auth' ? 'text-primary font-medium' : ''}`}>Sign in</button>
          )}
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
