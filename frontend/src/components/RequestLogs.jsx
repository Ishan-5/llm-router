import { useEffect, useState } from 'react'
import { fetchLogs, fetchLogDetail } from '../api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const TIER_STYLES = {
  cheap: 'text-cool bg-cool/10 border-cool/30',
  mid: 'text-signal bg-signal/10 border-signal/30',
  frontier: 'text-danger bg-danger/10 border-danger/30',
  web: 'text-cool bg-cool/10 border-cool/30',
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function LogRow({ log, isExpanded, onToggle, apiKey }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (isExpanded && !detail) {
      setLoading(true)
      fetchLogDetail(log.id, apiKey).then(setDetail).catch(() => {}).finally(() => setLoading(false))
    }
  }, [isExpanded])

  const tierClass = TIER_STYLES[log.tier] || 'text-muted bg-panel border-line'

  return (
    <div className="border border-line rounded-lg overflow-hidden mb-2 transition-all duration-200 hover:border-signal/30">
      {/* Summary row */}
      <button
        onClick={onToggle}
        className="w-full text-left px-4 py-3 bg-surface hover:bg-panel transition-colors flex items-center gap-3 text-xs"
      >
        <span className={`font-mono px-1.5 py-0.5 rounded-md border shrink-0 ${tierClass}`}>
          {log.tier}
        </span>
        <span className="text-primary truncate flex-1 font-mono">
          {log.query}
        </span>
        <span className="text-muted shrink-0 font-mono">
          ${log.cost_usd?.toFixed(4)}
        </span>
        <span className="text-muted shrink-0 font-mono">
          {log.latency_ms?.toFixed(0)}ms
        </span>
        {log.cache_hit && (
          <span className="text-cool shrink-0 font-mono">cache</span>
        )}
        <span className="text-muted shrink-0">
          {formatTime(log.created_at)}
        </span>
        <span className="text-muted shrink-0 ml-1">
          {isExpanded ? '▾' : '▸'}
        </span>
      </button>

      {/* Expanded detail */}
      {isExpanded && (
        <div className="border-t border-line bg-panel px-4 py-3 space-y-3 text-xs animate-[slide-in_0.15s_ease-out]">
          {/* Metadata grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <MetaCell label="Model" value={log.model_id} />
            <MetaCell label="Difficulty" value={log.difficulty_score?.toFixed(2) ?? '—'} />
            <MetaCell label="Input tokens" value={log.input_tokens?.toLocaleString() ?? '—'} />
            <MetaCell label="Output tokens" value={log.output_tokens?.toLocaleString() ?? '—'} />
            <MetaCell label="Cost" value={`$${log.cost_usd?.toFixed(4)}`} />
            <MetaCell label="Latency" value={`${log.latency_ms?.toFixed(0)}ms`} />
            <MetaCell
              label="Cache similarity"
              value={log.cache_similarity != null ? log.cache_similarity.toFixed(3) : '—'}
            />
            <MetaCell
              label="Tokens saved"
              value={log.tokens_saved_usd != null ? `$${log.tokens_saved_usd.toFixed(4)}` : '—'}
            />
            <MetaCell label="Fallback" value={log.fallback_used ? 'Yes' : 'No'} />
            <MetaCell label="Intended tier" value={log.intended_tier ?? '—'} />
          </div>

          {/* Query + Response */}
          {loading ? (
            <div className="text-muted py-4 text-center">Loading detail…</div>
          ) : detail ? (
            <div className="space-y-2">
              <DetailSection title="Query">
                <p className="text-primary leading-relaxed">{detail.query}</p>
              </DetailSection>
              <DetailSection title="Response">
                {detail.response ? (
                  <div className="prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed
                    prose-p:my-1 prose-ul:my-1 prose-li:my-0.5
                    prose-code:font-mono prose-code:text-[10px] prose-code:bg-base prose-code:px-1 prose-code:py-0.5 prose-code:rounded
                    prose-pre:bg-base prose-pre:rounded-lg prose-pre:p-3 prose-pre:overflow-x-auto
                  ">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{detail.response}</ReactMarkdown>
                  </div>
                ) : (
                  <p className="text-muted italic">No response recorded</p>
                )}
              </DetailSection>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

function MetaCell({ label, value }) {
  return (
    <div className="bg-surface rounded-md px-2 py-1.5 border border-line">
      <div className="text-muted text-[10px] uppercase tracking-wide mb-0.5">{label}</div>
      <div className="text-primary font-mono truncate">{value}</div>
    </div>
  )
}

function DetailSection({ title, children }) {
  return (
    <div>
      <div className="text-muted text-[10px] uppercase tracking-wide mb-1.5 font-mono">{title}</div>
      <div className="bg-surface rounded-lg border border-line px-3 py-2">{children}</div>
    </div>
  )
}

export default function RequestLogs({ apiKey }) {
  const [logs, setLogs] = useState([])
  const [error, setError] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [limit, setLimit] = useState(30)

  function load() {
    setError(null)
    fetchLogs(limit, apiKey).then(setLogs).catch((e) => setError(e.message))
  }

  useEffect(load, [limit, apiKey])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-display text-lg font-semibold">Request Logs</h3>
        <div className="flex items-center gap-2">
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="bg-panel border border-line rounded px-2 py-1 text-xs text-primary font-mono"
          >
            <option value={10}>10</option>
            <option value={30}>30</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
          <button
            onClick={load}
            className="text-muted hover:text-primary transition-colors text-xs font-mono"
          >
            ↻ refresh
          </button>
        </div>
      </div>

      {error && (
        <p className="font-mono text-xs text-danger">Failed to load logs: {error}</p>
      )}

      {logs.length === 0 && !error ? (
        <p className="text-muted text-xs py-8 text-center">No logs yet. Send a query to get started.</p>
      ) : (
        <div className="space-y-0">
          {logs.map((log) => (
            <LogRow
              key={log.id}
              log={log}
              isExpanded={expandedId === log.id}
              onToggle={() => setExpandedId(expandedId === log.id ? null : log.id)}
              apiKey={apiKey}
            />
          ))}
        </div>
      )}
    </div>
  )
}
