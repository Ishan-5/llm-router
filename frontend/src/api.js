const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
const API_KEY = import.meta.env.VITE_API_KEY || ''

export async function routeQuery(query, overrideTier = null) {
  const res = await fetch(`${API_BASE}/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
    body: JSON.stringify(
      overrideTier ? { query, override_tier: overrideTier } : { query }
    ),
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
