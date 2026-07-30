import { useState, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function UserBubble({ text }) {
  return (
    <div className="flex justify-end mb-4 animate-[slide-in_0.2s_ease-out]">
      <div className="max-w-[85%] bg-signal text-white rounded-2xl rounded-br-md px-4 py-3 text-sm leading-relaxed">
        {text}
      </div>
    </div>
  )
}

export function AssistantBubble({ result }) {
  const [copied, setCopied] = useState(false)
  const copyTimer = useRef(null)

  function handleCopy() {
    navigator.clipboard.writeText(result?.response || '').then(() => {
      setCopied(true)
      clearTimeout(copyTimer.current)
      copyTimer.current = setTimeout(() => setCopied(false), 2000)
    })
  }

  if (!result) return null

  const tierColors = {
    cheap: 'text-cool bg-cool/10 border-cool/30',
    mid: 'text-signal bg-signal/10 border-signal/30',
    frontier: 'text-danger bg-danger/10 border-danger/30',
    web: 'text-cool bg-cool/10 border-cool/30',
  }
  const tierClass = tierColors[result.routed_to] || 'text-muted bg-panel border-line'

  return (
    <div className="flex justify-start mb-4 animate-[slide-in_0.25s_ease-out]">
      <div className="max-w-[85%]">
        <div className="bg-panel border border-line rounded-2xl rounded-bl-md px-4 py-3">
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
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.response}</ReactMarkdown>
          </div>
        </div>

        {/* metadata chips */}
        <div className="flex flex-wrap items-center gap-1.5 mt-1.5 px-1">
          <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded-md border ${tierClass}`}>
            {result.routed_to === 'web' ? 'web search' : result.routed_to}
          </span>
          {result.difficulty_score != null && (
            <span className="font-mono text-[10px] text-muted px-1.5 py-0.5 rounded-md bg-base border border-line">
              score {result.difficulty_score.toFixed(1)}
            </span>
          )}
          <span className="font-mono text-[10px] text-muted px-1.5 py-0.5 rounded-md bg-base border border-line">
            ${result.cost_usd?.toFixed(4)}
          </span>
          <span className="font-mono text-[10px] text-muted px-1.5 py-0.5 rounded-md bg-base border border-line">
            {result.latency_ms?.toFixed(0)}ms
          </span>
          {result.cache_hit && (
            <span className="font-mono text-[10px] text-cool px-1.5 py-0.5 rounded-md bg-cool/10 border border-cool/30">
              cache
            </span>
          )}
          {result.fallback_used && (
            <span className="font-mono text-[10px] text-danger px-1.5 py-0.5 rounded-md bg-danger/10 border border-danger/30">
              fallback
            </span>
          )}
          {result.route_reason && (
            <span
              className="font-mono text-[10px] text-muted px-1.5 py-0.5 rounded-md bg-base border border-line max-w-[200px] truncate"
              title={result.route_reason}
            >
              {result.route_reason}
            </span>
          )}
          <button
            onClick={handleCopy}
            className="font-mono text-[10px] text-muted hover:text-primary transition-colors px-1.5 py-0.5 rounded-md hover:bg-base"
          >
            {copied ? 'copied ✓' : 'copy'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function TypingIndicator() {
  return (
    <div className="flex justify-start mb-4">
      <div className="bg-panel border border-line rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-muted typing-dot" />
        <span className="w-1.5 h-1.5 rounded-full bg-muted typing-dot" style={{ animationDelay: '0.15s' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-muted typing-dot" style={{ animationDelay: '0.3s' }} />
      </div>
    </div>
  )
}
