import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../supabase'

const inputClass =
  'w-full bg-base border border-line rounded-lg pl-10 pr-4 py-2.5 text-sm text-primary placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/40 focus:border-signal transition-colors'
const passwordClass =
  'w-full bg-base border border-line rounded-lg pl-10 pr-10 py-2.5 text-sm text-primary placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/40 focus:border-signal transition-colors'

function MailIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none">
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
    </svg>
  )
}

function UserIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none">
      <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  )
}

function LockIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none">
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

const FEATURES = [
  {
    title: 'Difficulty-scored routing',
    desc: 'LightGBM trained on 8,200 Claude-gold labels',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />
      </svg>
    ),
  },
  {
    title: 'Live tier fallbacks',
    desc: 'Cheap → mid → frontier with cross-provider failover',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
        <polyline points="16 7 22 7 22 13" />
      </svg>
    ),
  },
  {
    title: 'Near-zero overhead',
    desc: '~20ms local scoring — no extra API call',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
      </svg>
    ),
  },
]

export default function AuthPage() {
  const [mode, setMode] = useState('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [enabledProviders, setEnabledProviders] = useState({})

  useEffect(() => {
    let active = true
    supabase.auth
      .getSettings()
      .then(({ data }) => {
        const external = data?.settings?.external || {}
        if (active) setEnabledProviders(external)
      })
      .catch(() => {})
    return () => { active = false }
  }, [])

  const socialProviders = ['google', 'github'].filter((p) => enabledProviders[p])

  function switchMode(next) {
    setMode(next)
    setError(null)
    setMessage(null)
  }

  function validate() {
    if (mode === 'signup') {
      if (password.length < 6) {
        setError('Password must be at least 6 characters.')
        return false
      }
      if (password !== confirm) {
        setError('Passwords do not match.')
        return false
      }
    }
    return true
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setMessage(null)
    if (!validate()) return
    setLoading(true)

    if (mode === 'signup') {
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { full_name: name } },
      })
      if (error) setError(error.message)
      else setMessage('Check your email to confirm your account.')
    } else {
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) {
        if (String(error.message).includes('Invalid login')) setError('Invalid email or password.')
        else setError(error.message)
      }
    }
    setLoading(false)
  }

  async function handleForgotPassword() {
    if (!email) {
      setError('Enter your email first.')
      return
    }
    setLoading(true)
    setError(null)
    setMessage(null)
    const { error } = await supabase.auth.resetPasswordForEmail(email)
    if (error) setError(error.message)
    else setMessage('Password reset link sent — check your inbox.')
    setLoading(false)
  }

  async function handleOAuth(provider) {
    setLoading(true)
    setError(null)
    setMessage(null)
    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: `${window.location.origin}/get-started` },
    })
    if (error) {
      const label = provider === 'google' ? 'Google' : 'GitHub'
      setError(`${label} sign-in isn't enabled on this instance yet — use email instead.`)
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex bg-base font-body">
      {/* Left showcase */}
      <div
        className="hidden lg:flex flex-col justify-between w-[46%] max-w-xl px-12 py-14 text-white relative overflow-hidden shrink-0"
        style={{ background: 'linear-gradient(160deg, #131820 0%, #1A202C 55%, #2A1708 100%)' }}
      >
        <div className="absolute -top-24 -right-24 w-72 h-72 rounded-full bg-signal/25 blur-3xl" />
        <div className="absolute bottom-0 -left-24 w-80 h-80 rounded-full bg-cool/15 blur-3xl" />

        <div className="relative">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-signal auth-pulse" />
            <span className="font-display font-bold text-xl tracking-tight text-white">
              route<span className="text-signal">wise</span>
            </span>
          </div>

          <h1 className="font-display text-4xl font-semibold leading-tight mt-12">
            Every query.
            <br />
            The right model.
            <br />
            <span className="text-signal">Automatically.</span>
          </h1>
          <p className="text-sm text-white/60 mt-4 max-w-sm leading-relaxed">
            routewise scores each request for difficulty, then sends it to the cheapest model that can actually answer it — no waste, no surprises.
          </p>

          <div className="mt-10 border border-white/10 rounded-xl bg-white/5 px-6 py-5">
            <div className="flex items-center justify-between mb-4">
              <span className="font-mono text-[10px] text-white/50 uppercase tracking-wider">live routing</span>
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                <span className="font-mono text-[10px] text-white/50 uppercase tracking-wider">online</span>
              </span>
            </div>
            <div className="relative h-10 flex items-center justify-between">
              <span className="auth-flow-dot absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-signal shadow-[0_0_12px_2px_rgba(255,159,28,0.55)]" />
              {[
                { label: 'cheap', active: false },
                { label: 'mid', active: false },
                { label: 'frontier', active: true },
              ].map((tier) => (
                <div key={tier.label} className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${tier.active ? 'bg-signal' : 'bg-white/25'}`} />
                  <span className={`font-mono text-[10px] uppercase tracking-wider ${tier.active ? 'text-white/80' : 'text-white/45'}`}>{tier.label}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between mt-5 pt-4 border-t border-white/10">
              <span className="font-mono text-[10px] text-white/45">difficulty score</span>
              <span className="font-mono text-[10px] text-white/70">7.4 → frontier</span>
            </div>
          </div>

          <div className="mt-8 space-y-5">
            {FEATURES.map((f) => (
              <div key={f.title} className="flex items-start gap-3">
                <div className="mt-0.5 w-8 h-8 rounded-lg bg-signal/15 border border-signal/25 text-signal flex items-center justify-center shrink-0">
                  {f.icon}
                </div>
                <div>
                  <p className="text-sm font-medium text-white">{f.title}</p>
                  <p className="text-xs text-white/55 mt-0.5">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative grid grid-cols-3 gap-4 border-t border-white/10 pt-6 mt-12">
          {[
            { value: '77.5%', label: 'Tier accuracy' },
            { value: '56%', label: 'Cheaper', accent: true },
            { value: '~20ms', label: 'Per decision' },
          ].map((s) => (
            <div key={s.label}>
              <p className={`font-display text-2xl font-semibold ${s.accent ? 'text-signal' : 'text-white'}`}>{s.value}</p>
              <p className="font-mono text-[10px] text-white/50 uppercase tracking-wider mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Right form */}
      <div className="flex-1 flex items-center justify-center px-6 py-16 relative overflow-hidden">
        <div className="absolute top-10 -right-20 w-72 h-72 rounded-full bg-signal/10 blur-3xl" />
        <div className="absolute bottom-10 -left-20 w-72 h-72 rounded-full bg-cool/10 blur-3xl" />

        <div className="w-full max-w-md animate-slide-in relative">
          {/* Mobile logo */}
          <div className="flex lg:hidden items-center justify-center gap-2 mb-8">
            <div className="w-2.5 h-2.5 rounded-full bg-signal" />
            <span className="font-display font-bold text-xl tracking-tight text-primary">
              route<span className="text-signal">wise</span>
            </span>
          </div>

          <div className="border border-line rounded-2xl bg-panel/80 backdrop-blur p-8">
            {/* Mode tabs */}
            <div className="grid grid-cols-2 gap-1 p-1 bg-base border border-line rounded-lg mb-8">
              {[
                { key: 'login', label: 'Sign in' },
                { key: 'signup', label: 'Create account' },
              ].map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => switchMode(tab.key)}
                  className={`rounded-md py-2 text-sm font-medium transition-colors ${
                    mode === tab.key ? 'bg-signal text-white shadow-sm' : 'text-muted hover:text-primary'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <h2 className="font-display text-xl font-semibold text-primary mb-1">
              {mode === 'login' ? 'Welcome back' : 'Create your account'}
            </h2>
            <p className="text-sm text-muted mb-6">
              {mode === 'login'
                ? 'Sign in to access your dashboard and API keys.'
                : 'Get started with cost-aware LLM routing.'}
            </p>

            {/* Social */}
            {socialProviders.length > 0 && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  {socialProviders.map((provider) => (
                    <button
                      key={provider}
                      type="button"
                      onClick={() => handleOAuth(provider)}
                      disabled={loading}
                      className="flex items-center justify-center gap-2 border border-line rounded-lg px-3 py-2.5 text-sm text-primary hover:border-signal hover:bg-signal/5 transition disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {provider === 'google' ? (
                        <svg width="15" height="15" viewBox="0 0 24 24">
                          <path fill="#EA4335" d="M12 5.04c1.57 0 2.98.54 4.09 1.6l3.06-3.06A10.94 10.94 0 0 0 12 0C7.31 0 3.26 2.69 1.28 6.61l3.56 2.76C5.94 6.4 8.73 4.5 12 4.5" />
                          <path fill="#4285F4" d="M23.49 12.27c0-.79-.07-1.55-.2-2.27H12v4.51h6.47a5.5 5.5 0 0 1-2.39 3.58l3.44 2.67C21.68 18.09 23.49 15.36 23.49 12.27" />
                          <path fill="#FBBC05" d="M4.84 14.63A6.6 6.6 0 0 1 4.5 12c0-.9.15-1.77.4-2.6L1.31 6.62A10.94 10.94 0 0 0 1 12c0 1.77.45 3.43 1.24 4.9l3.65-2.69" />
                          <path fill="#34A853" d="M12 23.5c2.97 0 5.46-.98 7.28-2.66l-3.44-2.67c-.98.66-2.23 1.04-3.84 1.04-3.27 0-6.06-1.9-7.28-4.57l-3.56 2.76C3.26 21.31 7.31 23.5 12 23.5" />
                        </svg>
                      ) : (
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.55v-2.17c-3.2.7-3.87-1.36-3.87-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.7 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11.1 11.1 0 0 1 5.8 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.43-2.69 5.41-5.25 5.69.41.36.78 1.07.78 2.16v3.2c0 .3.21.67.8.55A11.51 11.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
                        </svg>
                      )}
                      <span className="text-sm">{provider === 'google' ? 'Google' : 'GitHub'}</span>
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-3 my-6">
                  <div className="flex-1 h-px bg-line" />
                  <span className="font-mono text-[10px] text-muted uppercase tracking-wider">or with email</span>
                  <div className="flex-1 h-px bg-line" />
                </div>
              </>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              {mode === 'signup' && (
                <div>
                  <label className="font-mono text-[10px] text-muted uppercase tracking-wide block mb-1.5">Full name</label>
                  <div className="relative">
                    <UserIcon />
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                      autoComplete="name"
                      className={inputClass}
                      placeholder="Jane Smith"
                    />
                  </div>
                </div>
              )}

              <div>
                <label className="font-mono text-[10px] text-muted uppercase tracking-wide block mb-1.5">Email</label>
                <div className="relative">
                  <MailIcon />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoComplete="email"
                    className={inputClass}
                    placeholder="you@company.com"
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="font-mono text-[10px] text-muted uppercase tracking-wide">Password</label>
                  {mode === 'login' && (
                    <button
                      type="button"
                      onClick={handleForgotPassword}
                      disabled={loading}
                      className="font-mono text-[10px] text-signal hover:underline transition-colors disabled:opacity-50"
                    >
                      Forgot password?
                    </button>
                  )}
                </div>
                <div className="relative">
                  <LockIcon />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={6}
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                    className={passwordClass}
                    placeholder={mode === 'signup' ? 'At least 6 characters' : '••••••••'}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-primary transition-colors"
                    tabIndex={-1}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                        <line x1="1" y1="1" x2="23" y2="23" />
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              {mode === 'signup' && (
                <div>
                  <label className="font-mono text-[10px] text-muted uppercase tracking-wide block mb-1.5">Confirm password</label>
                  <div className="relative">
                    <LockIcon />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={confirm}
                      onChange={(e) => setConfirm(e.target.value)}
                      required
                      autoComplete="new-password"
                      className={passwordClass}
                      placeholder="Repeat your password"
                    />
                  </div>
                </div>
              )}

              {/* Error / Success */}
              {error && (
                <div className="flex items-start gap-2 bg-danger/10 border border-danger/20 rounded-lg px-3 py-2.5 animate-slide-in">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-danger shrink-0 mt-0.5">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="15" y1="9" x2="9" y2="15" />
                    <line x1="9" y1="9" x2="15" y2="15" />
                  </svg>
                  <p className="font-mono text-xs text-danger leading-relaxed">{error}</p>
                </div>
              )}
              {message && (
                <div className="flex items-start gap-2 bg-cool/10 border border-cool/20 rounded-lg px-3 py-2.5 animate-slide-in">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-cool shrink-0 mt-0.5">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                  <p className="font-mono text-xs text-cool leading-relaxed">{message}</p>
                </div>
              )}

              {/* Submit */}
              <button
                type="submit"
                disabled={loading}
                className="w-full bg-signal text-white font-semibold text-sm py-2.5 rounded-lg hover:brightness-110 hover:shadow-[0_4px_16px_-4px_var(--color-signal)] transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                    </svg>
                    Please wait…
                  </span>
                ) : mode === 'login' ? 'Sign in' : 'Create account'}
              </button>
            </form>
          </div>

          {/* Continue without account */}
          <div className="mt-6 text-center">
            <Link to="/playground" className="font-mono text-xs text-muted hover:text-primary transition-colors group">
              Continue without account{' '}
              <span className="inline-block transition-transform group-hover:translate-x-0.5">→</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
