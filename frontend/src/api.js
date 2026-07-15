const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
const API_KEY = import.meta.env.VITE_API_KEY || ''

export async function routeQueryStream(query, overrideTier = null, bypassCache = false, onChunk, onMeta, onDone, onError) {
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
  if (bypassCache) body.bypass_cache = true
  if (Object.keys(userKeys).length > 0) body.user_api_keys = userKeys

  const res = await fetch(`${API_BASE}/route/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail || 'Request failed')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const event = JSON.parse(line.slice(6))
        if (event.type === 'chunk') onChunk?.(event.text)
        else if (event.type === 'meta') onMeta?.(event)
        else if (event.type === 'done') onDone?.(event)
        else if (event.type === 'error') onError?.(event.detail)
      } catch {}
    }
  }
}

export async function routeQuery(query, overrideTier = null, bypassCache = false) {
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
  if (bypassCache) body.bypass_cache = true
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

export async function fetchPricing() {
  const res = await fetch(`${API_BASE}/pricing`)
  if (!res.ok) throw new Error('Could not load pricing')
  return res.json()
}
