import { useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ADMIN_USER_ID } from '../config'
import ThemeToggle from './ThemeToggle'

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

  useEffect(() => { setMobileOpen(false) }, [location.pathname])

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
        className={`px-3 py-1.5 rounded-md transition-colors ${isActive('/playground') ? 'text-primary bg-surface' : 'hover:text-primary hover:bg-surface/50'}`}>
        Playground
      </Link>
      <Link to="/models"
        className={`px-3 py-1.5 rounded-md transition-colors ${isActive('/models') || isActive('/pricing') ? 'text-primary bg-surface' : 'hover:text-primary hover:bg-surface/50'}`}>
        Models
      </Link>
      <Link to="/guide"
        className={`px-3 py-1.5 rounded-md transition-colors ${isActive('/guide') ? 'text-primary bg-surface' : 'hover:text-primary hover:bg-surface/50'}`}>
        Guide
      </Link>
      <Link to="/about"
        className={`px-3 py-1.5 rounded-md transition-colors ${isActive('/about') ? 'text-primary bg-surface' : 'hover:text-primary hover:bg-surface/50'}`}>
        About
      </Link>
    </>
  )

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-line bg-base/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          {/* Left: Logo + Nav */}
          <div className="flex items-center gap-8">
            <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity shrink-0">
              <div className="w-2 h-2 rounded-full bg-signal" />
              <span className="font-display font-bold text-lg tracking-tight text-primary">
                route<span className="text-signal">wise</span>
              </span>
            </Link>
            <nav className="hidden md:flex items-center gap-1 text-[13px] text-muted font-body" role="navigation" aria-label="Main navigation">
              {navLinks}
            </nav>
          </div>

          {/* Right: Actions */}
          <div className="hidden md:flex items-center gap-2">
            <button
              onClick={onOpenSettings}
              className="relative flex items-center gap-1.5 font-mono text-[11px] border border-line rounded px-2.5 py-1 text-muted hover:text-primary hover:border-signal transition-colors"
              aria-label="Bring your own model"
            >
              {byomActive && <span className="absolute -top-1 -right-1 w-1.5 h-1.5 rounded-full bg-signal" />}
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                <line x1="12" y1="22.08" x2="12" y2="12" />
              </svg>
              <span>BYOM</span>
            </button>
            <ThemeToggle isDark={isDark} toggle={toggleTheme} />
            {user ? (
              <UserMenu user={user} isAdmin={isAdmin} onSignOut={handleSignOut} />
            ) : (
              <Link to="/auth"
                className={`px-3 py-1.5 rounded-md text-[13px] font-medium transition-colors ${isActive('/auth') ? 'text-signal bg-signal/10' : 'text-signal border border-signal/30 hover:bg-signal/10'}`}>
                Sign in
              </Link>
            )}
          </div>

          {/* Mobile controls */}
          <div className="flex items-center gap-2 md:hidden">
            <ThemeToggle isDark={isDark} toggle={toggleTheme} />
            {user ? (
              <UserMenu user={user} isAdmin={isAdmin} onSignOut={handleSignOut} />
            ) : (
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
            )}
          </div>
        </div>
      </header>

      {/* Mobile drawer — only for unauthenticated users */}
      {!user && mobileOpen && (
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
              <Link to="/about" onClick={() => setMobileOpen(false)}
                className="text-sm text-muted hover:text-primary transition-colors py-2.5">
                About
              </Link>
              <div className="border-t border-line my-2" />
              <Link to="/auth" onClick={() => setMobileOpen(false)}
                className="text-sm text-signal hover:text-primary transition-colors py-2.5 font-medium">
                Sign in
              </Link>
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
