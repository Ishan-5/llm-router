const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
const API_KEY = import.meta.env.VITE_API_KEY || ''

export async function routeQuery(query, overrideTier = null) {
  // read user's provider api keys from localStorage to send with request
  let userKeys = {}
  try {
    const saved = localStorage.getItem('byom_config')
    if (saved) {
      const parsed = JSON.parse(saved)
      Object.entries(parsed).forEach(([tier, cfg]) => {
        if (cfg.api_key) userKeys[tier] = cfg.api_key
      })
    }
  } catch {}

  const body = { query }
  if (overrideTier) body.override_tier = overrideTier
  if (Object.keys(userKeys).length > 0) body.user_api_keys = userKeys

  const res = await fetch(`${API_BASE}/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

export async function fetchStats() {
  const res = await fetch(`${API_BASE}/stats`)
  if (!res.ok) throw new Error('Could not load stats')
  return res.json()
}

export async function fetchProviders() {
  const res = await fetch(`${API_BASE}/providers`)
  if (!res.ok) throw new Error('Could not load providers')
  return res.json()
}

export async function fetchConfig() {
  const res = await fetch(`${API_BASE}/config`)
  if (!res.ok) throw new Error('Could not load config')
  return res.json()
}

export async function saveConfig(tierConfigs) {
  // tierConfigs: { cheap?: { provider, model_id, api_key }, mid?: {...}, frontier?: {...} }
  const res = await fetch(`${API_BASE}/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
    body: JSON.stringify(tierConfigs),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Save failed' }))
    throw new Error(err.detail || 'Save failed')
  }
  return res.json()
}

export async function resetConfig() {
  const res = await fetch(`${API_BASE}/config`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${API_KEY}` },
  })
  if (!res.ok) throw new Error('Reset failed')
  return res.json()
}
