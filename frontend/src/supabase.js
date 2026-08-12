import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY

function createSupabaseStub() {
  return {
    auth: {
      getSession: async () => ({ data: { session: null } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      signUp: async () => ({ error: { message: 'Supabase not configured' } }),
      signInWithPassword: async () => ({ error: { message: 'Supabase not configured' } }),
      signInWithOAuth: async () => ({ error: { message: 'Supabase not configured' } }),
      resetPasswordForEmail: async () => ({ error: { message: 'Supabase not configured' } }),
      signOut: async () => {},
    },
  }
}

export const supabase = SUPABASE_URL && SUPABASE_ANON_KEY
  ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : createSupabaseStub()

export async function fetchEnabledProviders() {
  if (!SUPABASE_URL) return {}
  try {
    const res = await fetch(`${SUPABASE_URL}/auth/v1/settings`)
    if (!res.ok) return {}
    const json = await res.json()
    return json.external || {}
  } catch {
    return {}
  }
}
