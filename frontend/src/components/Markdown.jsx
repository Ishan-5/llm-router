import { useState, useRef, isValidElement } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { prettifyMath } from '../mathText'

// Every answer surface (chat, request logs, playground) renders model output the
// same way through this component, so code blocks get one implementation of
// highlighting + copy, and tables get one implementation of horizontal scroll.
// It replaces the four separate <ReactMarkdown> call sites that had already
// started to drift apart.

const LANGUAGE_RE = /language-([\w-]+)/

function findCodeNode(children) {
  const nodes = Array.isArray(children) ? children : [children]
  for (const node of nodes) {
    if (isValidElement(node) && node.type === 'code') return node
  }
  for (const node of nodes) {
    if (isValidElement(node)) {
      const found = findCodeNode(node.props?.children)
      if (found) return found
    }
  }
  return null
}

function languageOf(codeNode) {
  const className = codeNode?.props?.className
  if (!className) return ''
  const match = LANGUAGE_RE.exec(Array.isArray(className) ? className.join(' ') : className)
  return match ? match[1] : ''
}

// react-markdown hands the <pre> override its <code> child. We render that child
// untouched inside our own <pre>, so the highlighted tokens keep working.
function CodeBlock({ children }) {
  const [copied, setCopied] = useState(false)
  const ref = useRef(null)
  const language = languageOf(findCodeNode(children))
  const label = language === 'plaintext' ? 'text' : language

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(ref.current?.textContent ?? '')
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {}
  }

  return (
    <div className="not-prose group relative my-3 overflow-hidden rounded-xl border border-line bg-panel2 shadow-card">
      <div className="flex items-center justify-between gap-2 border-b border-line bg-panel px-3 py-1.5">
        <span className="truncate font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          {label || 'code'}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          aria-label={copied ? 'Code copied' : 'Copy code'}
          className="flex shrink-0 items-center gap-1 font-mono text-[10px] text-muted transition-colors hover:text-primary"
        >
          {copied ? (
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          ) : (
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
          )}
          {copied ? 'copied' : 'copy'}
        </button>
      </div>
      <pre ref={ref} className="overflow-x-auto px-4 py-3 font-mono text-[12px] leading-relaxed text-primary">
        {children}
      </pre>
    </div>
  )
}

// Wide GFM tables used to push the whole message wider than its bubble. A scroll
// container keeps the table intact without breaking the layout on small screens.
function Table({ children }) {
  return (
    <div className="my-3 w-full overflow-x-auto">
      <table>{children}</table>
    </div>
  )
}

function Link({ href = '', children, ...props }) {
  // react-markdown passes `node` (the hast element) to custom components; it must
  // not be spread onto the DOM node.
  const { node, ...rest } = props
  const external = /^https?:\/\//i.test(href)
  return (
    <a
      href={href}
      {...rest}
      {...(external ? { target: '_blank', rel: 'noreferrer noopener' } : {})}
    >
      {children}
    </a>
  )
}

const COMPONENTS = { pre: CodeBlock, table: Table, a: Link }

export default function Markdown({ children }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[[rehypeHighlight, { detect: false }]]}
      components={COMPONENTS}
    >
      {prettifyMath(children || '')}
    </ReactMarkdown>
  )
}
