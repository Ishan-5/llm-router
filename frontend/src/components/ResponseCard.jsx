import { useState, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { explainRoute, sendFeedback } from '../api'

function formatCost(cost) {
  if (cost == null) return ''
  if (cost === 0) return '$0'
  const s = cost.toFixed(6).replace(/0+$/, '').replace(/\.$/, '')
  return `$${s}`
}

function formatLatency(ms) {
  if (ms == null) return ''
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}

const TIER_META = {
  cheap: { chip: 'text-cool bg-cool/10 border-cool/30', dot: 'bg-cool' },
  mid: { chip: 'text-signal bg-signal/10 border-signal/30', dot: 'bg-signal' },
  frontier: { chip: 'text-danger bg-danger/10 border-danger/30', dot: 'bg-danger' },
  web: { chip: 'text-cool bg-cool/10 border-cool/30', dot: 'bg-cool' },
}

function formatTier(tier) {
  return tier === 'web' ? 'web search' : tier
}

function CopyIcon({ done }) {
  return done ? (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ) : (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

function ThumbsUp({ active }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill={active ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 10v12" />
      <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z" />
    </svg>
  )
}

function ThumbsDown({ active }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill={active ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 14V2" />
      <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z" />
    </svg>
  )
}

function RefreshIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
      <polyline points="21 3 21 9 15 9" />
    </svg>
  )
}

function ActionButton({ title, onClick, active, danger, disabled, children, spinning }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={title}
      className={`h-7 w-7 flex items-center justify-center rounded-full border transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
        spinning
          ? 'border-signal/40 text-signal'
          : active && danger
          ? 'border-danger/40 bg-danger/10 text-danger'
          : active
          ? 'border-signal/40 bg-signal/10 text-signal'
          : 'border-line text-muted hover:text-primary hover:border-signal/40 hover:bg-base'
      }`}
    >
      {spinning ? (
        <svg className="animate-spin" width="12" height="12" viewBox="0 0 14 14" fill="none">
          <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.6" strokeDasharray="20 14" />
        </svg>
      ) : children}
    </button>
  )
}

function Chip({ className = '', children, title }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 font-mono text-[11px] px-1.5 py-0.5 rounded-md border whitespace-nowrap min-w-0 ${className}`}>
      <span className="min-w-0 truncate">{children}</span>
    </span>
  )
}

function AssistantMetaBar({ result, logId, onRegenerate, regenerating }) {
  const [copied, setCopied] = useState(false)
  const [feedback, setFeedback] = useState(null)
  const [feedbackSaving, setFeedbackSaving] = useState(false)
  const [showReason, setShowReason] = useState(false)
  const [reason, setReason] = useState('')
  const [showExplain, setShowExplain] = useState(false)
  const [explain, setExplain] = useState(null)
  const [explainLoading, setExplainLoading] = useState(false)
  const [explainError, setExplainError] = useState(null)
  const copyTimer = useRef(null)
  const reasonRef = useRef(null)

  function handleCopy() {
    navigator.clipboard.writeText(result?.response || '').then(() => {
      setCopied(true)
      clearTimeout(copyTimer.current)
      copyTimer.current = setTimeout(() => setCopied(false), 2000)
    })
  }

  async function handleFeedback(vote) {
    if (!logId) return
    setFeedbackSaving(true)
    try {
      if (vote === 'down') {
        setFeedback('down')
        setShowReason(true)
        setTimeout(() => reasonRef.current?.focus(), 0)
      } else {
        setFeedback('up')
        setShowReason(false)
        await sendFeedback(logId, 'up')
      }
    } catch {
      setFeedback(null)
    } finally {
      setFeedbackSaving(false)
    }
  }

  async function handleSubmitReason() {
    if (!logId || !reason.trim()) return
    setFeedbackSaving(true)
    try {
      await sendFeedback(logId, 'down', reason)
      setShowReason(false)
    } catch {
      setFeedback('down')
    } finally {
      setFeedbackSaving(false)
    }
  }

  const explainCtx = result?._explain

  async function handleExplain() {
    if (showExplain) {
      setShowExplain(false)
      return
    }
    if (!explainCtx?.query) return
    if (explain) {
      setShowExplain(true)
      return
    }
    setExplainLoading(true)
    setExplainError(null)
    try {
      const data = await explainRoute(explainCtx.query, {
        overrideTier: explainCtx.override,
        threshold: explainCtx.threshold,
        messages: explainCtx.messages,
        supportMode: explainCtx.supportMode,
      })
      setExplain(data)
      setShowExplain(true)
    } catch (e) {
      setExplainError(e.message || 'Explain failed')
      setShowExplain(true)
    } finally {
      setExplainLoading(false)
    }
  }

  const tier = TIER_META[result.routed_to] || { chip: 'text-muted bg-panel border-line', dot: 'bg-muted' }
  const modelName = (result.model_id || '').split('/').pop()

  return (
    <div className="mt-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <Chip className={tier.chip}>
          <span className={`w-1.5 h-1.5 rounded-full ${tier.dot}`} />
          {formatTier(result.routed_to)}
        </Chip>

        {result.model_id && (
          <Chip className="text-muted bg-base border-line" title={result.model_id}>
            {modelName}
          </Chip>
        )}

        {result.difficulty_score != null && (
          <Chip className="text-muted bg-base border-line">score {result.difficulty_score.toFixed(1)}</Chip>
        )}

        <Chip className="text-muted bg-base border-line">{formatLatency(result.latency_ms)}</Chip>

        <Chip className="text-muted bg-base border-line">{formatCost(result.cost_usd)}</Chip>

        {result.cache_hit && (
          <Chip className="text-cool bg-cool/10 border-cool/30">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6 9 17l-5-5" />
            </svg>
            cached
          </Chip>
        )}

        {result.fallback_used && <Chip className="text-danger bg-danger/10 border-danger/30">fallback</Chip>}

        {result.route_reason && (
          <Chip className="text-muted bg-base border-line max-w-[180px] truncate" title={result.route_reason}>
            {result.route_reason}
          </Chip>
        )}

        {explainCtx?.query && (
          <button
            type="button"
            onClick={handleExplain}
            title="Show how this route was decided (no model call)"
            className="font-mono text-[11px] text-muted hover:text-signal underline decoration-dotted underline-offset-2 transition-colors"
          >
            {explainLoading ? 'analysing…' : showExplain ? 'hide why' : 'why?'}
          </button>
        )}

        <span className="ml-auto flex items-center gap-1">
          <ActionButton title={copied ? 'Copied to clipboard' : 'Copy answer'} onClick={handleCopy}>
            <CopyIcon done={copied} />
          </ActionButton>

          {logId && (
            <>
              <ActionButton
                title="Good answer"
                onClick={() => handleFeedback('up')}
                active={feedback === 'up'}
                disabled={feedbackSaving}
              >
                <ThumbsUp active={feedback === 'up'} />
              </ActionButton>
              <ActionButton
                title="Bad answer"
                onClick={() => handleFeedback('down')}
                active={feedback === 'down'}
                danger
                disabled={feedbackSaving}
              >
                <ThumbsDown active={feedback === 'down'} />
              </ActionButton>
            </>
          )}

          <span className="w-px h-3.5 bg-line" />

          <ActionButton
            title="Regenerate this answer"
            onClick={onRegenerate}
            disabled={regenerating || !onRegenerate}
            spinning={regenerating}
          >
            <RefreshIcon />
          </ActionButton>
        </span>
      </div>

      {showReason && (
        <div className="flex items-center gap-2 mt-2 animate-[slide-in_0.15s_ease-out]">
          <input
            ref={reasonRef}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSubmitReason()
            }}
            placeholder="What was wrong? (optional)"
            className="flex-1 bg-base border border-line rounded-lg px-3 py-1.5 text-xs text-primary placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-signal/40 focus:border-signal"
          />
          <button
            type="button"
            onClick={handleSubmitReason}
            disabled={feedbackSaving || !reason.trim()}
            className="font-mono text-[11px] text-primary border border-line rounded-lg px-2.5 py-1.5 hover:border-signal/50 hover:text-signal transition disabled:opacity-50"
          >
            send
          </button>
          <button
            type="button"
            onClick={() => { setShowReason(false); setFeedback(null); setReason('') }}
            className="font-mono text-[11px] text-muted hover:text-primary transition-colors"
          >
            cancel
          </button>
        </div>
      )}

      {showExplain && (
        <div className="mt-2 rounded-lg border border-line bg-base p-3 animate-[slide-in_0.15s_ease-out]">
          {explainError ? (
            <p className="text-xs text-danger">{explainError}</p>
          ) : !explain ? (
            <p className="font-mono text-[11px] text-muted">scoring…</p>
          ) : (
            <>
              <p className="text-xs leading-relaxed text-primary">{explain.summary}</p>

              <div className="mt-2 flex flex-wrap gap-1.5">
                <Chip className="text-muted bg-panel border-line">
                  decided by {explain.boundary.decided_by.replace('_', ' ')} · {explain.boundary.distance} away
                </Chip>
                {explain.slider && Object.entries(explain.slider).map(([name, s]) => (
                  <Chip key={name} className="text-muted bg-panel border-line">
                    {name} → {formatTier(s.tier)}
                  </Chip>
                ))}
              </div>

              {explain.tiers?.length > 0 && (
                <div className="mt-2 grid gap-1">
                  {explain.tiers.map((t) => (
                    <div key={t.tier} className="flex items-center justify-between font-mono text-[10px]">
                      <span className={t.chosen ? 'text-signal' : 'text-muted'}>
                        {formatTier(t.tier)}{t.chosen ? ' · chosen' : ''}
                      </span>
                      <span className="text-muted">
                        {t.price_per_m_input != null ? `$${t.price_per_m_input}/M in` : 'price n/a'}
                        {t.input_price_vs_chosen != null && t.input_price_vs_chosen !== 1 ? ` · ×${t.input_price_vs_chosen}` : ''}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              <p className="mt-2 font-mono text-[10px] text-muted">{explain.note}</p>
            </>
          )}
        </div>
      )}
    </div>
  )
}

export function UserBubble({ text }) {
  return (
    <div className="flex justify-end mb-4 chat-in">
      <div className="flex items-end gap-2 max-w-[85%]">
        <div className="bg-signal text-white rounded-2xl rounded-br-md px-4 py-2.5 text-sm leading-relaxed shadow-[0_4px_16px_-6px_var(--color-signal)]">
          {text}
        </div>
        <span className="h-6 w-6 shrink-0 rounded-full border border-line bg-base flex items-center justify-center text-muted">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        </span>
      </div>
    </div>
  )
}

export function AssistantBubble({ result, logId, onRegenerate, regenerating, streaming }) {
  if (!result) return null

  return (
    <div className="flex justify-start mb-4 chat-in">
      <div className="flex items-start gap-2 max-w-[88%]">
        <span className="h-6 w-6 shrink-0 rounded-full bg-signal/15 border border-signal/25 flex items-center justify-center text-signal">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="none">
            <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z" />
          </svg>
        </span>
        <div className="min-w-0 flex-1">
          <div className="bg-panel border border-line rounded-2xl rounded-tl-md px-4 py-3">
            <div className="prose prose-sm dark:prose-invert max-w-none
              text-sm leading-relaxed
              prose-headings:font-display prose-headings:font-semibold prose-headings:mt-3 prose-headings:mb-1.5
              prose-p:my-1
              prose-ul:my-1 prose-ul:pl-4 prose-li:my-0.5
              prose-ol:my-1 prose-ol:pl-4
              prose-code:font-mono prose-code:text-xs prose-code:bg-line prose-code:px-1 prose-code:py-0.5 prose-code:rounded
              prose-pre:bg-base prose-pre:text-primary prose-pre:rounded-lg prose-pre:p-3 prose-pre:overflow-x-auto prose-pre:border prose-pre:border-line
              prose-strong:font-semibold
              prose-blockquote:border-l-2 prose-blockquote:border-signal prose-blockquote:pl-3 prose-blockquote:text-muted
            ">
              {result.response ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.response}</ReactMarkdown>
              ) : null}
            </div>
            {streaming && (
              <div className="mt-2 flex items-center gap-2">
                <span className="stream-cursor" />
                <span className="font-mono text-[10px] text-signal tracking-wide uppercase">generating</span>
              </div>
            )}
          </div>

          <AssistantMetaBar
            result={result}
            logId={logId}
            onRegenerate={onRegenerate}
            regenerating={regenerating}
          />
        </div>
      </div>
    </div>
  )
}

export function TypingIndicator() {
  return (
    <div className="flex justify-start mb-4 chat-in">
      <div className="flex items-start gap-2 max-w-[88%]">
        <span className="h-6 w-6 shrink-0 rounded-full bg-signal/15 border border-signal/25 flex items-center justify-center text-signal">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="none">
            <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z" />
          </svg>
        </span>
        <div className="bg-panel border border-line rounded-2xl rounded-tl-md px-4 py-3 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-muted typing-dot" />
          <span className="w-1.5 h-1.5 rounded-full bg-muted typing-dot" style={{ animationDelay: '0.15s' }} />
          <span className="w-1.5 h-1.5 rounded-full bg-muted typing-dot" style={{ animationDelay: '0.3s' }} />
        </div>
      </div>
    </div>
  )
}