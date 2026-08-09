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

function _getByomConfig() {
  try {
    const saved = localStorage.getItem('byom_config')
    if (!saved) return {}
    const parsed = JSON.parse(saved)
    const config = {}
    Object.entries(parsed).forEach(([tier, cfg]) => {
      if (cfg.provider && cfg.model_id) config[tier] = { provider: cfg.provider, model_id: cfg.model_id }
    })
    return config
  } catch {
    return {}
  }
}

const THRESHOLD_KEY = 'router_threshold'
let _sharedThreshold = (() => {
  try { return parseFloat(localStorage.getItem(THRESHOLD_KEY)) || 1.0 } catch { return 1.0 }
})()
export function getSharedThreshold() { return _sharedThreshold }
export function setSharedThreshold(v) { _sharedThreshold = v; localStorage.setItem(THRESHOLD_KEY, String(v)) }

export async function routeQueryStream(query, overrideTier = null, bypassCache = false, onChunk, onMeta, onDone, onError, signal, threshold = null, messages = null) {
  const userKeys = _getUserKeys()
  const byomConfig = _getByomConfig()

  const body = { query }
  if (overrideTier) body.override_tier = overrideTier
  if (bypassCache) body.bypass_cache = true
  if (Object.keys(userKeys).length > 0) body.user_api_keys = userKeys
  if (Object.keys(byomConfig).length > 0) body.byom_config = byomConfig
  const t = threshold ?? _sharedThreshold
  if (t != null) body.threshold = t
  if (messages && messages.length > 0) body.messages = messages

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

export async function routeQuery(query, overrideTier = null, bypassCache = false, signal, threshold = null, messages = null) {
  const userKeys = _getUserKeys()
  const byomConfig = _getByomConfig()

  const body = { query }
  if (overrideTier) body.override_tier = overrideTier
  if (bypassCache) body.bypass_cache = true
  if (Object.keys(userKeys).length > 0) body.user_api_keys = userKeys
  if (Object.keys(byomConfig).length > 0) body.byom_config = byomConfig
  const t = threshold ?? _sharedThreshold
  if (t != null) body.threshold = t
  if (messages && messages.length > 0) body.messages = messages

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

export async function sendFeedback(requestLogId, feedback, reason = '') {
  const res = await fetch(`${API_BASE}/route/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
    body: JSON.stringify({ request_log_id: requestLogId, feedback, reason }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Feedback failed' }))
    throw new Error(err.detail || 'Feedback failed')
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

export async function fetchSettings() {
  let token = null
  try {
    const { supabase } = await import('./supabase')
    const { data: { session } } = await supabase.auth.getSession()
    token = session?.access_token || null
  } catch {}
  if (!token) {
    const local = _sharedThreshold ?? 1.0
    return { router_threshold: local }
  }
  const res = await fetch(`${API_BASE}/settings`, {
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!res.ok) return { router_threshold: _sharedThreshold ?? 1.0 }
  const data = await res.json()
  _sharedThreshold = data.router_threshold ?? _sharedThreshold ?? 1.0
  localStorage.setItem(THRESHOLD_KEY, String(_sharedThreshold))
  return data
}

export async function saveSettings(router_threshold) {
  let token = null
  try {
    const { supabase } = await import('./supabase')
    const { data: { session } } = await supabase.auth.getSession()
    token = session?.access_token || null
  } catch {}
  if (!token) {
    _sharedThreshold = router_threshold
    localStorage.setItem(THRESHOLD_KEY, String(router_threshold))
    return { router_threshold }
  }
  const res = await fetch(`${API_BASE}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    body: JSON.stringify({ router_threshold }),
  })
  if (!res.ok) throw new Error('Failed to save settings')
  return res.json()
}

export async function fetchCalibrate() {
  const headers = {}
  try {
    const { supabase } = await import('./supabase')
    const { data: { session } } = await supabase.auth.getSession()
    if (session?.access_token) headers['Authorization'] = `Bearer ${session.access_token}`
  } catch {}
  if (!headers['Authorization'] && API_KEY) headers['Authorization'] = `Bearer ${API_KEY}`
  if (!headers['Authorization']) throw new Error('Sign in or configure an API key to calibrate')
  const res = await fetch(`${API_BASE}/calibrate`, { headers })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to calibrate')
  }
  return res.json()
}

export async function fetchCompare() {
  const headers = {}
  try {
    const { supabase } = await import('./supabase')
    const { data: { session } } = await supabase.auth.getSession()
    if (session?.access_token) headers['Authorization'] = `Bearer ${session.access_token}`
  } catch {}
  if (!headers['Authorization'] && API_KEY) headers['Authorization'] = `Bearer ${API_KEY}`
  if (!headers['Authorization']) throw new Error('Sign in or configure an API key to compare')
  const res = await fetch(`${API_BASE}/compare`, { headers })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to compare')
  }
  return res.json()
}

export async function evaluateQueries(queries) {
  const res = await fetch(`${API_BASE}/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ queries }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Evaluation failed — is the backend running?')
  }
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

async function _adminFetch(url, opts = {}) {
  const headers = await _adminHeaders()
  const res = await fetch(url, { headers, ...opts })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { const body = await res.json(); detail = body.detail || detail } catch {}
    throw new Error(detail)
  }
  return res.json()
}

export async function fetchAdminStats() {
  return _adminFetch(`${API_BASE}/admin/stats`)
}

export async function fetchAdminKeys() {
  return _adminFetch(`${API_BASE}/admin/keys`)
}

export async function fetchAdminLogs(limit = 50) {
  return _adminFetch(`${API_BASE}/admin/logs?limit=${limit}`)
}

export async function fetchAdminUsers() {
  return _adminFetch(`${API_BASE}/admin/users`)
}
