import { useState, useRef, useEffect } from 'react'

const MAX_QUERY_LENGTH = 1000

const SUGGESTIONS = [
  'What is 2+2?',
  'Explain quantum entanglement',
  "Who is OpenAI's CEO?",
  'Summarize today\'s news',
]

export default function QueryForm({ onSubmit, loading, tiers, activeConfig }) {
  const [query, setQuery] = useState('')
  const [override, setOverride] = useState('auto')
  const [bypassCache, setBypassCache] = useState(false)
  const [showOptions, setShowOptions] = useState(false)
  const [clientError, setClientError] = useState(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }, [query])

  function handleSubmit(e) {
    if (e) e.preventDefault()
    setClientError(null)
    const trimmed = query.trim()
    if (!trimmed) return
    if (trimmed.length > MAX_QUERY_LENGTH) {
      setClientError(`Too long (${trimmed.length}/${MAX_QUERY_LENGTH})`)
      return
    }
    onSubmit(trimmed, override, bypassCache)
    setQuery('')
    setClientError(null)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  function handleSuggestion(text) {
    onSubmit(text, 'auto', false)
  }

  return (
    <div className="relative">
      <form onSubmit={handleSubmit} className="relative">
        <div className="bg-panel border border-line rounded-2xl overflow-hidden focus-within:border-signal/50 focus-within:ring-1 focus-within:ring-signal/20 transition-all">
          <textarea
            ref={textareaRef}
            value={query}
            onChange={(e) => { setQuery(e.target.value); setClientError(null) }}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything..."
            rows={1}
            maxLength={MAX_QUERY_LENGTH + 50}
            className="w-full bg-transparent px-4 pt-4 pb-2 font-body text-sm text-primary placeholder:text-muted resize-none focus:outline-none leading-relaxed"
          />
          <div className="flex items-center justify-between px-3 pb-3">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowOptions((v) => !v)}
                className="font-mono text-[10px] text-muted hover:text-primary transition-colors px-2 py-1 rounded-md hover:bg-base"
              >
                {showOptions ? '▾' : '▸'} Options
              </button>
              {clientError && (
                <span className="font-mono text-[10px] text-danger">{clientError}</span>
              )}
            </div>
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-signal text-white disabled:opacity-30 disabled:cursor-not-allowed hover:brightness-110 transition"
              aria-label="Send"
            >
              {loading ? (
                <svg width="14" height="14" viewBox="0 0 14 14" className="animate-spin">
                  <circle cx="7" cy="7" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="20 14" />
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                  <line x1="2" y1="7" x2="12" y2="7" />
                  <polyline points="7,2 12,7 7,12" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {showOptions && (
          <div className="flex gap-2 mt-2 px-1 animate-[cmd-slide_0.15s_ease-out]">
            <select
              value={override}
              onChange={(e) => setOverride(e.target.value)}
              className="bg-panel border border-line rounded-lg px-3 py-1.5 font-mono text-[11px] text-muted flex-1 focus:outline-none focus:ring-1 focus:ring-signal/50"
            >
              <option value="auto">Auto-route</option>
              {tiers.map((t) => (
                <option key={t.key} value={t.key}>Force: {t.label}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setBypassCache((v) => !v)}
              className={`font-mono text-[11px] px-3 py-1.5 rounded-lg border transition ${
                bypassCache ? 'border-signal text-signal bg-signal/10' : 'border-line text-muted hover:text-primary'
              }`}
            >
              Skip cache
            </button>
          </div>
        )}
      </form>
    </div>
  )
}

export function ChatSuggestions({ onSelect }) {
  return (
    <div className="flex flex-wrap gap-2">
      {SUGGESTIONS.map((q) => (
        <button
          key={q}
          onClick={() => onSelect(q)}
          className="font-mono text-[11px] text-muted border border-line rounded-full px-3 py-1.5 hover:text-signal hover:border-signal/40 transition-colors"
        >
          {q}
        </button>
      ))}
    </div>
  )
}
