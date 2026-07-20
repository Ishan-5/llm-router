import { API_BASE, API_KEY } from './config'

function _getUserKeys() {
  try {
    const saved = localStorage.getItem('byom_config')
    if (!saved) return {}
    const parsed = JSON.parse(saved)
    const keys = {}
    Object.entries(parsed).forEach(([tier, cfg]) => {
      if (cfg.api_key) keys[tier] = cfg.api_key
    })
    return keys
  } catch {
    return {}
  }
}

export async function routeQueryStream(query, overrideTier = null, bypassCache = false, onChunk, onMeta, onDone, onError, signal) {
  const userKeys = _getUserKeys()

  const body = { query }
  if (overrideTier) body.override_tier = overrideTier
  if (bypassCache) body.bypass_cache = true
  if (Object.keys(userKeys).length > 0) body.user_api_keys = userKeys

  const res = await fetch(`${API_BASE}/route/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
    body: JSON.stringify(body),
    signal,
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

export async function routeQuery(query, overrideTier = null, bypassCache = false, signal) {
  const userKeys = _getUserKeys()

  const body = { query }
  if (overrideTier) body.override_tier = overrideTier
  if (bypassCache) body.bypass_cache = true
  if (Object.keys(userKeys).length > 0) body.user_api_keys = userKeys

  const res = await fetch(`${API_BASE}/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

export async function fetchStats(key) {
  const headers = key
    ? { 'Authorization': `Bearer ${key}` }
    : { 'Authorization': `Bearer ${API_KEY}` }
  const res = await fetch(`${API_BASE}/stats`, { headers })
  if (!res.ok) throw new Error('Could not load stats')
  return res.json()
}

export async function fetchProviders() {
  const res = await fetch(`${API_BASE}/providers`)
  if (!res.ok) throw new Error('Could not load providers')
  return res.json()
}

export async function fetchConfig() {
  let token = null
  try {
    const { supabase } = await import('./supabase')
    const { data: { session } } = await supabase.auth.getSession()
    token = session?.access_token || null
  } catch {}
  const res = await fetch(`${API_BASE}/config`, {
    headers: token ? { 'Authorization': `Bearer ${token}` } : {}
  })
  if (!res.ok) throw new Error('Could not load config')
  const data = await res.json()
  if (!token) {
    try {
      const saved = JSON.parse(localStorage.getItem('byom_config') || '{}')
      Object.entries(saved).forEach(([tier, cfg]) => {
        if (cfg.enabled) data[tier] = { model_id: cfg.model_id, provider: cfg.provider }
      })
    } catch {}
  }
  return data
}

export async function saveConfig(tierConfigs) {
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

export async function fetchLogs(limit = 50, key) {
  const safeLimit = Math.max(1, Math.min(100, Math.floor(Number(limit) || 50)))
  const authKey = key || API_KEY
  const res = await fetch(`${API_BASE}/logs?limit=${safeLimit}`, {
    headers: { 'Authorization': `Bearer ${authKey}` },
  })
  if (!res.ok) throw new Error('Could not load logs')
  return res.json()
}

export async function fetchLogDetail(logId, key) {
  const safeId = Math.floor(Number(logId))
  if (!Number.isFinite(safeId) || safeId <= 0) throw new Error('Invalid log ID')
  const authKey = key || API_KEY
  const res = await fetch(`${API_BASE}/logs/${safeId}`, {
    headers: { 'Authorization': `Bearer ${authKey}` },
  })
  if (!res.ok) throw new Error('Log entry not found')
  return res.json()
}

export async function fetchAnalytics(key) {
  const authKey = key || API_KEY
  const res = await fetch(`${API_BASE}/analytics`, {
    headers: { 'Authorization': `Bearer ${authKey}` },
  })
  if (!res.ok) throw new Error('Could not load analytics')
  return res.json()
}

// ------------------------------------------------------------------
// Admin API (requires Supabase JWT from admin user)
// ------------------------------------------------------------------

async function _adminHeaders() {
  try {
    const { supabase } = await import('./supabase')
    const { data: { session } } = await supabase.auth.getSession()
    if (session?.access_token) return { 'Authorization': `Bearer ${session.access_token}` }
  } catch {}
  return { 'Authorization': `Bearer ${API_KEY}` }
}

export async function fetchAdminStats() {
  const headers = await _adminHeaders()
  const res = await fetch(`${API_BASE}/admin/stats`, { headers })
  if (!res.ok) throw new Error('Could not load admin stats')
  return res.json()
}

export async function fetchAdminKeys() {
  const headers = await _adminHeaders()
  const res = await fetch(`${API_BASE}/admin/keys`, { headers })
  if (!res.ok) throw new Error('Could not load admin keys')
  return res.json()
}

export async function fetchAdminLogs(limit = 50) {
  const headers = await _adminHeaders()
  const res = await fetch(`${API_BASE}/admin/logs?limit=${limit}`, { headers })
  if (!res.ok) throw new Error('Could not load admin logs')
  return res.json()
}

export async function fetchAdminUsers() {
  const headers = await _adminHeaders()
  const res = await fetch(`${API_BASE}/admin/users`, { headers })
  if (!res.ok) throw new Error('Could not load admin users')
  return res.json()
}
