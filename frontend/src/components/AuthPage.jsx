import { useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../supabase'

export default function AuthPage() {
  const [mode, setMode] = useState('login') // 'login' | 'signup'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setMessage(null)

    if (mode === 'signup') {
      const { error } = await supabase.auth.signUp({ email, password })
      if (error) setError(error.message)
      else setMessage('Check your email to confirm your account.')
    } else {
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) setError(error.message)
    }
    setLoading(false)
  }

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2 mb-8">
          <div className="w-2 h-2 rounded-full bg-signal" />
          <span className="font-display font-semibold text-lg">routewise</span>
        </div>

        <h1 className="font-display text-2xl font-semibold mb-1">
          {mode === 'login' ? 'Sign in' : 'Create account'}
        </h1>
        <p className="font-mono text-xs text-muted mb-8">
          {mode === 'login' ? 'Access your API keys and model config.' : 'Get your API key and start routing.'}
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="font-mono text-[10px] text-muted uppercase tracking-wide block mb-1.5">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full bg-panel border border-line rounded-lg px-4 py-3 font-body text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50 focus:border-signal"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="font-mono text-[10px] text-muted uppercase tracking-wide block mb-1.5">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full bg-panel border border-line rounded-lg px-4 py-3 font-body text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-signal/50 focus:border-signal"
              placeholder="••••••••"
            />
          </div>

          {error && <p className="font-mono text-xs text-danger">{error}</p>}
          {message && <p className="font-mono text-xs text-cool">{message}</p>}

          <button
            type="submit"
            disabled={loading}
            className="bg-signal text-white font-semibold text-sm px-6 py-3 rounded-lg hover:brightness-110 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <p className="font-mono text-xs text-muted mt-6 text-center">
          {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
          <button
            onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError(null); setMessage(null) }}
            className="text-signal hover:underline"
          >
            {mode === 'login' ? 'Sign up' : 'Sign in'}
          </button>
        </p>

        <div className="mt-8 pt-6 border-t border-line text-center">
          <Link to="/playground" className="font-mono text-xs text-muted hover:text-primary transition-colors">
            Continue without account →
          </Link>
        </div>
      </div>
    </div>
  )
}
