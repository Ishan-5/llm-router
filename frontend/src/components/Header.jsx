import { useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ADMIN_USER_ID } from '../config'
import ThemeToggle from './ThemeToggle'

const BYOM_TIER_DOT = { cheap: 'bg-cool', mid: 'bg-signal', frontier: 'bg-danger' }

function readByomTiers() {
  try {
    const cfg = JSON.parse(localStorage.getItem('byom_config') || '{}')
    return ['cheap', 'mid', 'frontier'].map((tier) => ({
      tier,
      byom: !!(cfg[tier]?.enabled && cfg[tier]?.provider),
      model: cfg[tier]?.model_id,
      provider: cfg[tier]?.provider,
    }))
  } catch {
    return []
  }
}

function UserMenu({ user, isAdmin, onSignOut }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function handleClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  function close() { setOpen(false) }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="w-8 h-8 rounded-full border border-line bg-surface flex items-center justify-center text-xs font-semibold text-primary hover:border-signal transition-colors"
        aria-label="User menu"
      >
        {user.email?.[0]?.toUpperCase() || 'U'}
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-2 w-56 bg-base border border-line rounded-lg shadow-xl overflow-hidden z-50">
          <div className="px-4 py-3 border-b border-line">
            <p className="text-xs text-primary font-mono truncate">{user.email}</p>
            {isAdmin && (
              <span className="inline-block mt-1 px-1.5 py-0.5 rounded border border-signal/30 bg-signal/10 text-signal text-[10px] font-semibold uppercase">admin</span>
            )}
          </div>
          <div className="py-1">
            <Link to="/dashboard" onClick={close}
              className="block px-4 py-2 text-sm text-muted hover:text-primary hover:bg-surface transition-colors">
              Dashboard
            </Link>
            {isAdmin && (
              <Link to="/admin" onClick={close}
                className="block px-4 py-2 text-sm text-muted hover:text-primary hover:bg-surface transition-colors">
                Admin
              </Link>
            )}
          </div>
          <div className="border-t border-line py-1">
            <button onClick={() => { onSignOut(); close() }}
              className="w-full text-left px-4 py-2 text-sm text-muted hover:text-primary hover:bg-surface transition-colors">
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Header({ isDark, toggleTheme, onOpenSettings, byomActive, user }) {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const [byomOpen, setByomOpen] = useState(false)
  const byomRef = useRef(null)

  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  useEffect(() => {
    function handleClickOutside(e) {
      if (byomRef.current && !byomRef.current.contains(e.target)) setByomOpen(false)
    }
    if (byomOpen) document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [byomOpen])

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  async function handleSignOut() {
    const { supabase } = await import('../supabase')
    await supabase.auth.signOut()
  }

  function isActive(path) {
    return location.pathname === path
  }

  const isAdmin = user && user.id === ADMIN_USER_ID

  const navLinks = (
    <>
      <Link to="/playground"
        className={`px-3 py-1.5 rounded-full transition-all ${isActive('/playground') ? 'text-primary bg-line/60 shadow-card' : 'hover:text-primary hover:bg-line/30'}`}>
        Playground
      </Link>
      <Link to="/models"
        className={`px-3 py-1.5 rounded-full transition-all ${isActive('/models') || isActive('/pricing') ? 'text-primary bg-line/60 shadow-card' : 'hover:text-primary hover:bg-line/30'}`}>
        Models
      </Link>
      <Link to="/guide"
        className={`px-3 py-1.5 rounded-full transition-all ${isActive('/guide') ? 'text-primary bg-line/60 shadow-card' : 'hover:text-primary hover:bg-line/30'}`}>
        Guide
      </Link>
      <Link to="/metrics"
        className={`px-3 py-1.5 rounded-full transition-all ${isActive('/metrics') ? 'text-primary bg-line/60 shadow-card' : 'hover:text-primary hover:bg-line/30'}`}>
        Metrics
      </Link>
      <Link to="/evaluate"
        className={`px-3 py-1.5 rounded-full transition-all ${isActive('/evaluate') ? 'text-primary bg-line/60 shadow-card' : 'hover:text-primary hover:bg-line/30'}`}>
        Evaluate
      </Link>
      <Link to="/about"
        className={`px-3 py-1.5 rounded-full transition-all ${isActive('/about') ? 'text-primary bg-line/60 shadow-card' : 'hover:text-primary hover:bg-line/30'}`}>
        About
      </Link>
    </>
  )

  return (
    <>
      <header id="top" className={`sticky top-0 z-40 border-b bg-base/80 backdrop-blur-xl transition-shadow duration-300 ${scrolled ? 'border-line shadow-card' : 'border-line'}`}>
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          {/* Left: Logo + Nav */}
          <div className="flex items-center gap-8">
            <Link to="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity shrink-0">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-signal opacity-40 animate-ping" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-signal shadow-[0_0_10px_var(--color-signal)]" />
              </span>
              <span className="font-display font-bold text-lg tracking-tight text-primary">
                route<span className="text-signal">wise</span>
              </span>
            </Link>
            <nav className="hidden md:flex items-center gap-1.5 text-[13px] text-muted font-body border border-line rounded-full px-1.5 py-1 bg-base/50" role="navigation" aria-label="Main navigation">
              {navLinks}
            </nav>
          </div>

          {/* Right: Actions */}
          <div className="hidden md:flex items-center gap-2.5">
            <div className="relative" ref={byomRef}>
              <button
                onClick={() => setByomOpen((v) => !v)}
                className={`relative flex items-center gap-1.5 font-mono text-[11px] border rounded-full px-3.5 py-2 transition-all ${
                  byomActive
                    ? 'border-signal/40 bg-signal/5 text-primary hover:border-signal/60 hover:shadow-card'
                    : 'border-line text-muted hover:text-primary hover:border-signal/50 hover:shadow-card'
                }`}
                aria-label="Bring your own model"
                aria-expanded={byomOpen}
              >
                {byomActive && <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-signal ring-2 ring-base" />}
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                  <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                  <line x1="12" y1="22.08" x2="12" y2="12" />
                </svg>
                <span>BYOM</span>
                {byomActive && <span className="w-1.5 h-1.5 rounded-full bg-cool animate-pulse" />}
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                  className={`transition-transform duration-200 ${byomOpen ? 'rotate-180' : ''}`}>
                  <path d="M2 3.5 L5 6.5 L8 3.5" />
                </svg>
              </button>

              {byomOpen && (
                <div className="absolute right-0 top-full mt-2 w-80 bg-base border border-line rounded-2xl shadow-pop overflow-hidden z-50 animate-[cmd-slide_0.15s_ease-out]">
                  <div className="px-4 py-3 border-b border-line flex items-center justify-between gap-2">
                    <span className="font-display font-semibold text-sm text-primary">Bring your own model</span>
                    <span className={`font-mono text-[9px] px-2 py-0.5 rounded-full border shrink-0 ${
                      byomActive ? 'border-cool/30 bg-cool/10 text-cool' : 'border-line text-muted'
                    }`}>
                      {byomActive ? 'active' : 'defaults'}
                    </span>
                  </div>
                  <div className="p-3 space-y-1.5">
                    {readByomTiers().map((t) => (
                      <div key={t.tier} className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-surface border border-line">
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${BYOM_TIER_DOT[t.tier] || 'bg-line'}`} />
                        <span className="font-mono text-[10px] text-muted w-14 capitalize shrink-0">{t.tier}</span>
                        <span className={`font-mono text-[10px] truncate flex-1 text-right ${t.byom ? 'text-primary' : 'text-muted/60'}`}>
                          {t.byom ? `${t.provider}/${t.model}` : 'built-in default'}
                        </span>
                      </div>
                    ))}
                    <p className="px-3 pt-1.5 font-mono text-[9px] text-muted/70 flex items-start gap-1.5">
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 shrink-0">
                        <rect x="3" y="11" width="18" height="11" rx="2" />
                        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                      </svg>
                      Keys stay in your browser — never sent to our DB.
                    </p>
                  </div>
                  <div className="border-t border-line p-2">
                    <button
                      onClick={() => { setByomOpen(false); onOpenSettings() }}
                      className="w-full flex items-center justify-center gap-2 font-mono text-xs px-4 py-2.5 rounded-xl bg-signal text-white font-semibold hover:brightness-110 transition"
                    >
                      Open configurator
                      <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="2" y1="7" x2="12" y2="7" />
                        <polyline points="7,2 12,7 7,12" />
                      </svg>
                    </button>
                  </div>
                </div>
              )}
            </div>
            <ThemeToggle isDark={isDark} toggle={toggleTheme} />
            {user ? (
              <UserMenu user={user} isAdmin={isAdmin} onSignOut={handleSignOut} />
            ) : (
              <Link to="/auth"
                className={`px-4 py-2 rounded-full text-[13px] font-semibold transition-all ${
                  isActive('/auth') ? 'text-white bg-signal shadow-card' : 'text-white bg-signal shadow-card hover:brightness-110'
                }`}>
                Sign in
              </Link>
            )}
          </div>

          {/* Mobile controls */}
          <div className="flex items-center gap-1.5 md:hidden">
            <ThemeToggle isDark={isDark} toggle={toggleTheme} />
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="text-muted hover:text-primary transition-colors p-2 rounded-md"
              aria-label="Toggle menu"
              aria-expanded={mobileOpen}
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

      {/* Mobile drawer — all users */}
      {mobileOpen && (
        <>
          <div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm md:hidden" onClick={() => setMobileOpen(false)} />
          <div className="fixed top-0 right-0 z-50 w-72 h-full bg-base border-l border-line shadow-2xl md:hidden overflow-y-auto animate-[slide-in_0.2s_ease-out]">
            <div className="flex items-center justify-between px-6 py-5 border-b border-line">
              <span className="font-display font-semibold text-sm text-primary">Menu</span>
              <button onClick={() => setMobileOpen(false)} className="text-muted hover:text-primary transition-colors p-1" aria-label="Close menu">
                <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <line x1="4" y1="4" x2="16" y2="16" />
                  <line x1="16" y1="4" x2="4" y2="16" />
                </svg>
              </button>
            </div>
            <nav className="px-6 py-4 flex flex-col gap-1">
              <Link to="/playground" onClick={() => setMobileOpen(false)}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                Playground
              </Link>
              <Link to="/models" onClick={() => setMobileOpen(false)}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                Models
              </Link>
              <Link to="/guide" onClick={() => setMobileOpen(false)}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                Guide
              </Link>
              <Link to="/evaluate" onClick={() => setMobileOpen(false)}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                Evaluate
              </Link>
              <Link to="/metrics" onClick={() => setMobileOpen(false)}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                Metrics
              </Link>
              <Link to="/about" onClick={() => setMobileOpen(false)}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                About
              </Link>
              {user && (
                <>
                  <div className="border-t border-line my-2" />
                  <Link to="/dashboard" onClick={() => setMobileOpen(false)}
                    className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                    Dashboard
                  </Link>
                  {isAdmin && (
                    <Link to="/admin" onClick={() => setMobileOpen(false)}
                      className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                      Admin
                    </Link>
                  )}
                </>
              )}
              <div className="border-t border-line my-2" />
              {user ? (
                <button onClick={() => { onSignOut(); setMobileOpen(false) }}
                  className="text-left text-sm text-signal hover:text-primary transition-colors py-2.5 font-medium">
                  Sign out
                </button>
              ) : (
                <Link to="/auth" onClick={() => setMobileOpen(false)}
                  className="text-sm text-signal hover:text-primary transition-colors py-2.5 font-medium">
                  Sign in
                </Link>
              )}
              <button onClick={() => { onOpenSettings(); setMobileOpen(false) }}
                className="flex items-center gap-1.5 font-mono text-xs text-muted hover:text-primary transition-colors py-2.5 text-left">
                {byomActive && <span className="w-2 h-2 rounded-full bg-signal" />}
                <span>BYOM</span>
              </button>
            </nav>
          </div>
        </>
      )}
    </>
  )
}
