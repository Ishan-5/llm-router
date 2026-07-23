import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { routeQuery, routeQueryStream, getSharedThreshold, setSharedThreshold } from '../api'
import { API_BASE, API_KEY } from '../config'
import ThresholdSlider from './ThresholdSlider'

const MAX_HISTORY = 15

const SNIPPET_LANGS = ['curl', 'Python', 'JavaScript']

function generateSnippet(lang, query, tier, streaming) {
  const q = query.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
  if (lang === 'curl') {
    const tierPart = tier !== 'auto' ? `  "override_tier": "${tier}",\n` : ''
    const streamPart = streaming ? '  "stream": true,\n' : ''
    return `curl -X POST ${API_BASE}/route${streaming ? '/stream' : ''} \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${API_KEY || '<your-api-key>'}" \\
  -d '{
    "query": "${q}",
${tierPart}${streamPart}}'`
  }
  if (lang === 'Python') {
    const tierArg = tier !== 'auto' ? `, override_tier="${tier}"` : ''
    if (streaming) {
      return `import requests

url = "${API_BASE}/route/stream"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${API_KEY || '<your-api-key>'}"
}
payload = {"query": "${q}"${tier !== 'auto' ? `, "override_tier": "${tier}"` : ''}, "stream": True}

resp = requests.post(url, json=payload, headers=headers, stream=True)
for line in resp.iter_lines():
    if line:
        print(line.decode())`
    }
    return `import requests

url = "${API_BASE}/route"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${API_KEY || '<your-api-key>'}"
}
payload = {"query": "${q}"${tier !== 'auto' ? `, "override_tier": "${tier}"` : ''}}

resp = requests.post(url, json=payload, headers=headers)
data = resp.json()
print(data["response"])`
  }
  if (lang === 'JavaScript') {
    if (streaming) {
      return `const res = await fetch("${API_BASE}/route/stream", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${API_KEY || '<your-api-key>'}"
  },
  body: JSON.stringify({
    query: "${q}"${tier !== 'auto' ? `,\n    override_tier: "${tier}"` : ''},
    stream: true
  })
});

const reader = res.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  console.log(decoder.decode(value));
}`
    }
    return `const res = await fetch("${API_BASE}/route", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${API_KEY || '<your-api-key>'}"
  },
  body: JSON.stringify({
    query: "${q}"${tier !== 'auto' ? `,\n    override_tier: "${tier}"` : ''}
  })
});

const data = await res.json();
console.log(data.response);`
  }
  return ''
}

function SnippetTabs({ query, tier, streaming }) {
  const [active, setActive] = useState('curl')
  const [copied, setCopied] = useState(false)
  const code = generateSnippet(active, query, tier, streaming)

  function copy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="rounded-xl border border-line overflow-hidden">
      <div className="flex items-center justify-between bg-panel px-3 py-2 border-b border-line">
        <div className="flex gap-1">
          {SNIPPET_LANGS.map((l) => (
            <button
              key={l}
              onClick={() => setActive(l)}
              className={`font-mono text-[10px] px-2.5 py-1 rounded-md transition-colors ${
                active === l
                  ? 'bg-signal/15 text-signal border border-signal/30'
                  : 'text-muted hover:text-primary border border-transparent'
              }`}
            >
              {l}
            </button>
          ))}
        </div>
        <button
          onClick={copy}
          className="font-mono text-[10px] text-muted hover:text-primary transition-colors px-2 py-1 rounded-md hover:bg-base"
        >
          {copied ? 'copied' : 'copy'}
        </button>
      </div>
      <pre className="bg-surface px-4 py-3 overflow-x-auto text-xs font-mono text-primary leading-relaxed max-h-64">
        <code>{code}</code>
      </pre>
    </div>
  )
}

function MetaBadge({ label, value, color }) {
  const colors = {
    signal: 'text-signal bg-signal/10 border-signal/30',
    cool: 'text-cool bg-cool/10 border-cool/30',
    danger: 'text-danger bg-danger/10 border-danger/30',
    muted: 'text-muted bg-surface border-line',
  }
  return (
    <div className={`inline-flex items-center gap-1.5 font-mono text-[10px] px-2 py-1 rounded-md border ${colors[color] || colors.muted}`}>
      <span className="opacity-60">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  )
}

const MCP_CONFIG_SNIPPET = `{
  "mcpServers": {
    "routewise": {
      "command": "python",
      "args": ["-m", "router.mcp_server"],
      "cwd": "/path/to/llm-router/backend"
    }
  }
}`

export default function ApiPlayground() {
  const [query, setQuery] = useState('')
  const [tier, setTier] = useState('auto')
  const [threshold, setThreshold] = useState(() => getSharedThreshold() ?? 1.0)
  const [streaming, setStreaming] = useState(false)
  const [bypassCache, setBypassCache] = useState(false)
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState(null)
  const [streamChunks, setStreamChunks] = useState([])
  const [error, setError] = useState(null)
  const [history, setHistory] = useState([])
  const [showSnippets, setShowSnippets] = useState(false)
  const [activeSnippetQuery, setActiveSnippetQuery] = useState('')
  const [showMcp, setShowMcp] = useState(false)
  const [mcpCopied, setMcpCopied] = useState(false)
  const textareaRef = useRef(null)
  const responseEndRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 140) + 'px'
  }, [query])

  useEffect(() => {
    if (streaming && streamChunks.length > 0) {
      responseEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [streamChunks, streaming])

  function handleSubmit(e) {
    if (e) e.preventDefault()
    const trimmed = query.trim()
    if (!trimmed || loading) return

    setLoading(true)
    setError(null)
    setResponse(null)
    setStreamChunks([])
    setActiveSnippetQuery(trimmed)

    const controller = new AbortController()
    abortRef.current = controller
    const start = Date.now()

    if (streaming) {
      routeQueryStream(
        trimmed,
        tier === 'auto' ? null : tier,
        bypassCache,
        (chunk) => setStreamChunks((prev) => [...prev, chunk]),
        null,
        (done) => {
          const elapsed = Date.now() - start
          addHistory({
            query: trimmed,
            tier: done?.routed_to || tier,
            model: done?.routed_to || '—',
            cost: done?.cost_usd || 0,
            latency_ms: done?.latency_ms || elapsed,
            cache_hit: done?.cache_hit || false,
            streaming: true,
            response_text: '',
            timestamp: new Date().toISOString(),
          })
          setLoading(false)
        },
        (err) => { setError(err); setLoading(false) },
        controller.signal,
        threshold,
      )
    } else {
      routeQuery(trimmed, tier === 'auto' ? null : tier, bypassCache, controller.signal, threshold)
        .then((data) => {
          setResponse(data)
          addHistory({
            query: trimmed,
            tier: data.routed_to,
            model: data.routed_to,
            cost: data.cost_usd || 0,
            latency_ms: data.latency_ms || 0,
            cache_hit: data.cache_hit || false,
            streaming: false,
            response_text: data.response || '',
            difficulty_score: data.difficulty_score,
            tokens_saved_usd: data.tokens_saved_usd,
            timestamp: new Date().toISOString(),
          })
        })
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false))
    }
  }

  function addHistory(entry) {
    setHistory((prev) => [entry, ...prev].slice(0, MAX_HISTORY))
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleSubmit()
    }
  }

  function loadFromHistory(item) {
    setQuery(item.query)
    setTier(item.tier === 'auto' || !item.tier ? 'auto' : item.tier)
  }

  function cancelRequest() {
    abortRef.current?.abort()
    setLoading(false)
  }

  const fullStreamText = streamChunks.join('')

  return (
    <div className="space-y-4">
      {/* Input area */}
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="bg-panel border border-line rounded-xl overflow-hidden focus-within:border-signal/50 focus-within:ring-1 focus-within:ring-signal/20 transition-all">
          <textarea
            ref={textareaRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a prompt to test your router..."
            rows={2}
            className="w-full bg-transparent px-4 pt-4 pb-2 font-body text-sm text-primary placeholder:text-muted resize-none focus:outline-none leading-relaxed"
          />
          <div className="flex items-center justify-between px-3 pb-3">
            <div className="flex items-center gap-2 flex-wrap">
              <select
                value={tier}
                onChange={(e) => setTier(e.target.value)}
                className="bg-surface border border-line rounded-lg px-2.5 py-1.5 font-mono text-[11px] text-muted focus:outline-none focus:ring-1 focus:ring-signal/50"
              >
                <option value="auto">Auto-route</option>
                <option value="cheap">Cheap</option>
                <option value="mid">Mid</option>
                <option value="frontier">Frontier</option>
              </select>

              <button
                type="button"
                onClick={() => setStreaming((v) => !v)}
                className={`font-mono text-[10px] px-2.5 py-1.5 rounded-lg border transition ${
                  streaming ? 'border-cool text-cool bg-cool/10' : 'border-line text-muted hover:text-primary'
                }`}
              >
                {streaming ? '⚡ streaming' : 'streaming'}
              </button>

              <button
                type="button"
                onClick={() => setBypassCache((v) => !v)}
                className={`font-mono text-[10px] px-2.5 py-1.5 rounded-lg border transition ${
                  bypassCache ? 'border-signal text-signal bg-signal/10' : 'border-line text-muted hover:text-primary'
                }`}
              >
                {bypassCache ? 'cache off' : 'cache on'}
              </button>

              <div className="w-28 sm:w-36">
                <ThresholdSlider value={threshold} onChange={(v) => { setThreshold(v); setSharedThreshold(v) }} compact />
              </div>

              <span className="font-mono text-[10px] text-muted/50 hidden sm:inline">⌘+Enter to send</span>
            </div>

            <div className="flex items-center gap-2">
              {loading && (
                <button
                  type="button"
                  onClick={cancelRequest}
                  className="font-mono text-[10px] text-danger hover:text-danger/80 transition-colors px-2 py-1"
                >
                  cancel
                </button>
              )}
              <button
                type="submit"
                disabled={loading || !query.trim()}
                className="h-8 px-4 flex items-center gap-1.5 rounded-lg bg-signal text-white text-xs font-semibold disabled:opacity-30 disabled:cursor-not-allowed hover:brightness-110 transition"
              >
                {loading ? (
                  <>
                    <svg width="12" height="12" viewBox="0 0 14 14" className="animate-spin">
                      <circle cx="7" cy="7" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="20 14" />
                    </svg>
                    Running
                  </>
                ) : (
                  <>
                    <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                      <line x1="2" y1="7" x2="12" y2="7" />
                      <polyline points="7,2 12,7 7,12" />
                    </svg>
                    Send
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </form>

      {/* Error */}
      {error && (
        <div className="bg-danger/5 border border-danger/30 rounded-xl px-4 py-3">
          <p className="font-mono text-xs text-danger">{error}</p>
        </div>
      )}

      {/* Streaming response */}
      {streaming && streamChunks.length > 0 && (
        <div className="bg-panel border border-line rounded-xl px-5 py-4 space-y-3 animate-[slide-in_0.15s_ease-out]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cool animate-pulse" />
              <span className="font-mono text-[10px] text-cool uppercase tracking-wide">Streaming response</span>
            </div>
            <span className="font-mono text-[10px] text-muted">{streamChunks.length} chunks</span>
          </div>
          <div className="prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed
            prose-p:my-1 prose-ul:my-1 prose-li:my-0.5
            prose-code:font-mono prose-code:text-[10px] prose-code:bg-base prose-code:px-1 prose-code:py-0.5 prose-code:rounded
            prose-pre:bg-base prose-pre:rounded-lg prose-pre:p-3 prose-pre:overflow-x-auto
            max-h-96 overflow-y-auto
          ">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{fullStreamText}</ReactMarkdown>
            <div ref={responseEndRef} />
          </div>
        </div>
      )}

      {/* Non-streaming response */}
      {response && !streaming && (
        <div className="bg-panel border border-line rounded-xl px-5 py-4 space-y-4 animate-[slide-in_0.15s_ease-out]">
          {/* Metadata bar */}
          <div className="flex items-center gap-2 flex-wrap">
            <MetaBadge label="tier" value={response.routed_to} color={response.routed_to === 'frontier' ? 'danger' : response.routed_to === 'mid' ? 'signal' : 'cool'} />
            {response.intended_tier && response.intended_tier !== response.routed_to && (
              <MetaBadge label="intended" value={response.intended_tier} color="muted" />
            )}
            {response.predicted_tier && (
              <MetaBadge label="predicted" value={response.predicted_tier} color="muted" />
            )}
            {response.cache_hit && <MetaBadge label="cache" value="hit" color="cool" />}
            {response.fallback_used && <MetaBadge label="fallback" value="yes" color="danger" />}
            {response.difficulty_score != null && (
              <MetaBadge label="difficulty" value={response.difficulty_score.toFixed(2)} color="muted" />
            )}
          </div>

          {/* Cost & latency */}
          <div className="flex items-center gap-4 font-mono text-[11px] text-muted">
            <span>${(response.cost_usd || 0).toFixed(4)}</span>
            <span>{(response.latency_ms || 0).toFixed(0)}ms</span>
            {response.tokens_saved_usd > 0 && (
              <span className="text-cool">${response.tokens_saved_usd.toFixed(4)} saved</span>
            )}
          </div>

          {/* Response body */}
          <div className="bg-surface rounded-lg border border-line px-4 py-3 max-h-96 overflow-y-auto">
            <div className="prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed
              prose-p:my-1 prose-ul:my-1 prose-li:my-0.5
              prose-code:font-mono prose-code:text-[10px] prose-code:bg-base prose-code:px-1 prose-code:py-0.5 prose-code:rounded
              prose-pre:bg-base prose-pre:rounded-lg prose-pre:p-3 prose-pre:overflow-x-auto
            ">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{response.response || ''}</ReactMarkdown>
            </div>
          </div>
        </div>
      )}

      {/* Code snippets */}
      {activeSnippetQuery && (
        <div className="space-y-2">
          <button
            onClick={() => setShowSnippets((v) => !v)}
            className="font-mono text-[10px] text-muted hover:text-primary transition-colors flex items-center gap-1"
          >
            {showSnippets ? '▾' : '▸'} Code snippets
          </button>
          {showSnippets && (
            <div className="animate-[cmd-slide_0.15s_ease-out]">
              <SnippetTabs query={activeSnippetQuery} tier={tier} streaming={streaming} />
            </div>
          )}
        </div>
      )}

      {/* MCP config */}
      <div className="space-y-2">
        <button
          onClick={() => setShowMcp((v) => !v)}
          className="font-mono text-[10px] text-muted hover:text-primary transition-colors flex items-center gap-1"
        >
          {showMcp ? '▾' : '▸'} MCP agent config
        </button>
        {showMcp && (
          <div className="animate-[cmd-slide_0.15s_ease-out] rounded-xl border border-line overflow-hidden">
            <div className="flex items-center justify-between bg-panel px-3 py-2 border-b border-line">
              <span className="font-mono text-[10px] text-muted uppercase">claude_desktop_config.json</span>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(MCP_CONFIG_SNIPPET)
                  setMcpCopied(true)
                  setTimeout(() => setMcpCopied(false), 2000)
                }}
                className="font-mono text-[10px] text-muted hover:text-primary transition-colors px-2 py-1 rounded-md hover:bg-base"
              >
                {mcpCopied ? 'copied' : 'copy'}
              </button>
            </div>
            <pre className="bg-surface px-4 py-3 overflow-x-auto text-xs font-mono text-primary leading-relaxed">
              <code>{MCP_CONFIG_SNIPPET}</code>
            </pre>
          </div>
        )}
      </div>

      {/* Request history */}
      {history.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-mono text-[10px] text-muted uppercase tracking-wide">History</h4>
          <div className="space-y-1 max-h-72 overflow-y-auto">
            {history.map((item, i) => (
              <button
                key={i}
                onClick={() => loadFromHistory(item)}
                className="w-full text-left px-3 py-2.5 bg-surface hover:bg-panel border border-line hover:border-signal/30 rounded-lg transition-colors group"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded border ${
                    item.tier === 'frontier' ? 'text-danger bg-danger/10 border-danger/30'
                    : item.tier === 'mid' ? 'text-signal bg-signal/10 border-signal/30'
                    : 'text-cool bg-cool/10 border-cool/30'
                  }`}>
                    {item.tier}
                  </span>
                  {item.cache_hit && (
                    <span className="font-mono text-[9px] text-cool">cache</span>
                  )}
                  {item.streaming && (
                    <span className="font-mono text-[9px] text-muted">stream</span>
                  )}
                  <span className="font-mono text-[9px] text-muted ml-auto">
                    ${item.cost.toFixed(4)} · {item.latency_ms.toFixed(0)}ms
                  </span>
                </div>
                <p className="font-mono text-[11px] text-primary truncate group-hover:text-signal transition-colors">
                  {item.query}
                </p>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
