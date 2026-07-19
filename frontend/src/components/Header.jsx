import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import ThemeToggle from './ThemeToggle'

export default function Header({ isDark, toggleTheme, onOpenSettings, onOpenCmd, byomActive, user }) {
  const location = useLocation()
  const isHome = location.pathname === '/'
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  async function handleSignOut() {
    const { supabase } = await import('../supabase')
    await supabase.auth.signOut()
  }

  function handleAnchorLink(e, id) {
    if (isHome) {
      e.preventDefault()
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
    }
    setMobileOpen(false)
  }

  function isActive(path) {
    return location.pathname === path
  }

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-line bg-base/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
            <div className="w-2 h-2 rounded-full bg-signal" />
            <span className="font-display font-semibold text-lg tracking-tight">
              route<span className="text-signal">wise</span>
            </span>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-8 text-sm text-muted font-body" role="navigation" aria-label="Main navigation">
            <a href="/#how" onClick={(e) => handleAnchorLink(e, 'how')}
              className={`hover:text-primary transition-colors ${isHome ? 'text-primary' : ''}`}>
              How it works
            </a>
            <Link to="/pricing" className={`hover:text-primary transition-colors ${isActive('/pricing') ? 'text-primary font-medium' : ''}`}>
              Models & Pricing
            </Link>
            <Link to="/playground" className={`hover:text-primary transition-colors ${isActive('/playground') ? 'text-primary font-medium' : ''}`}>
              Playground
            </Link>
            <Link to="/guide" className={`hover:text-primary transition-colors ${isActive('/guide') ? 'text-primary font-medium' : ''}`}>
              Guide
            </Link>
            <a href="/#metrics" onClick={(e) => handleAnchorLink(e, 'metrics')} className="hover:text-primary transition-colors">
              Metrics
            </a>
            <Link to="/about" className={`hover:text-primary transition-colors ${isActive('/about') ? 'text-primary font-medium' : ''}`}>
              About
            </Link>
            {user ? (
              <>
                <Link to="/dashboard" className={`hover:text-primary transition-colors ${isActive('/dashboard') ? 'text-primary font-medium' : ''}`}>
                  Dashboard
                </Link>
                <button onClick={handleSignOut} className="hover:text-primary transition-colors">Sign out</button>
              </>
            ) : (
              <Link to="/auth" className={`hover:text-primary transition-colors ${isActive('/auth') ? 'text-primary font-medium' : ''}`}>
                Sign in
              </Link>
            )}
            <button
              onClick={onOpenSettings}
              className="relative flex items-center gap-1.5 font-mono text-xs border border-line rounded-full px-3 py-1.5 text-muted hover:text-primary hover:border-signal transition-colors"
              aria-label="Open model settings"
            >
              {byomActive && <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-signal" />}
              <span>&#9881;</span>
              <span>Models</span>
            </button>
            <ThemeToggle isDark={isDark} toggle={toggleTheme} />
          </nav>

          {/* Mobile controls */}
          <div className="flex items-center gap-3 md:hidden">
            <ThemeToggle isDark={isDark} toggle={toggleTheme} />
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="text-muted hover:text-primary transition-colors p-1"
              aria-label="Toggle menu"
            >
              {mobileOpen ? (
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <line x1="4" y1="4" x2="16" y2="16" />
                  <line x1="16" y1="4" x2="4" y2="16" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <line x1="3" y1="5" x2="17" y2="5" />
                  <line x1="3" y1="10" x2="17" y2="10" />
                  <line x1="3" y1="15" x2="17" y2="15" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Mobile menu overlay + drawer */}
      {mobileOpen && (
        <>
          <div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm md:hidden" onClick={() => setMobileOpen(false)} />
          <div className="fixed top-0 right-0 z-50 w-72 h-full bg-base border-l border-line shadow-2xl md:hidden overflow-y-auto animate-[slide-in_0.2s_ease-out]">
            <div className="flex items-center justify-between px-6 py-5 border-b border-line">
              <span className="font-display font-semibold text-sm">Menu</span>
              <button onClick={() => setMobileOpen(false)} className="text-muted hover:text-primary transition-colors p-1" aria-label="Close menu">
                <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <line x1="4" y1="4" x2="16" y2="16" />
                  <line x1="16" y1="4" x2="4" y2="16" />
                </svg>
              </button>
            </div>
            <nav className="px-6 py-4 flex flex-col gap-1">
              <a href="/#how" onClick={(e) => handleAnchorLink(e, 'how')}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                How it works
              </a>
              <Link to="/pricing" onClick={() => setMobileOpen(false)}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                Models & Pricing
              </Link>
              <Link to="/playground" onClick={() => setMobileOpen(false)}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                Playground
              </Link>
              <Link to="/guide" onClick={() => setMobileOpen(false)}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                Guide
              </Link>
              <a href="/#metrics" onClick={(e) => handleAnchorLink(e, 'metrics')}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                Metrics
              </a>
              <Link to="/about" onClick={() => setMobileOpen(false)}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                About
              </Link>
              <div className="border-t border-line my-2" />
              {user ? (
                <>
                  <Link to="/dashboard" onClick={() => setMobileOpen(false)}
                    className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                    Dashboard
                  </Link>
                  <button onClick={() => { handleSignOut(); setMobileOpen(false) }}
                    className="text-sm text-muted hover:text-primary transition-colors py-2.5 text-left">
                    Sign out
                  </button>
                </>
              ) : (
                <Link to="/auth" onClick={() => setMobileOpen(false)}
                  className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                  Sign in
                </Link>
              )}
              <button onClick={() => { onOpenSettings(); setMobileOpen(false) }}
                className="flex items-center gap-1.5 font-mono text-xs text-muted hover:text-primary transition-colors py-2.5 text-left">
                {byomActive && <span className="w-2 h-2 rounded-full bg-signal" />}
                <span>&#9881;</span>
                <span>Models</span>
              </button>
            </nav>
          </div>
        </>
      )}
    </>
  )
}
