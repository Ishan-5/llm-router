import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import useFocusTrap from '../useFocusTrap'

const NAV = [
  { label: 'Home', path: '/', key: 'h' },
  { label: 'Pricing', path: '/pricing', key: 'p' },
  { label: 'About', path: '/about', key: 'a' },
  { label: 'Dashboard', path: '/dashboard', key: 'd' },
  { label: 'Sign in', path: '/auth', key: 's' },
]

const ACTIONS = [
  { label: 'Toggle theme', action: 'theme', key: 't' },
  { label: 'Open settings', action: 'settings', key: 'm' },
]

export default function CommandPalette({ open, onClose, onAction }) {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const inputRef = useRef(null)
  const navigate = useNavigate()
  const trapRef = useFocusTrap(open)

  const items = [
    ...NAV.map((n) => ({ ...n, type: 'nav' })),
    ...ACTIONS.map((a) => ({ ...a, type: 'action' })),
  ]

  const filtered = items.filter((item) =>
    item.label.toLowerCase().includes(query.toLowerCase())
  )

  useEffect(() => {
    if (open) {
      setQuery('')
      setSelected(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  function handleKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelected((s) => Math.min(s + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelected((s) => Math.max(s - 1, 0))
    } else if (e.key === 'Enter' && filtered[selected]) {
      const item = filtered[selected]
      if (item.type === 'nav') navigate(item.path)
      else onAction(item.action)
      onClose()
    } else if (e.key === 'Escape') {
      onClose()
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]" onClick={onClose}>
      <div className="absolute inset-0 bg-primary/40 backdrop-blur-sm" />
      <div
        ref={trapRef}
        className="relative w-full max-w-lg bg-base border border-line rounded-xl shadow-2xl overflow-hidden animate-[cmd-slide_0.15s_ease-out]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-line">
          <span className="text-muted font-mono text-xs">⌘K</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelected(0) }}
            onKeyDown={handleKeyDown}
            placeholder="Search or jump to..."
            className="flex-1 bg-transparent font-body text-sm text-primary placeholder:text-muted focus:outline-none"
          />
          <kbd className="font-mono text-[10px] text-muted border border-line rounded px-1.5 py-0.5">esc</kbd>
        </div>
        <div className="max-h-64 overflow-y-auto py-2">
          {filtered.length === 0 && (
            <p className="px-4 py-6 font-mono text-xs text-muted text-center">No results</p>
          )}
          {filtered.map((item, i) => (
            <button
              key={item.label}
              onClick={() => {
                if (item.type === 'nav') navigate(item.path)
                else onAction(item.action)
                onClose()
              }}
              onMouseEnter={() => setSelected(i)}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors ${
                i === selected ? 'bg-panel text-primary' : 'text-muted hover:bg-panel/50'
              }`}
            >
              <span className="font-mono text-xs text-muted w-5">{item.key}</span>
              <span>{item.label}</span>
              {item.type === 'nav' && (
                <span className="ml-auto font-mono text-[10px] text-muted">{item.path}</span>
              )}
            </button>
          ))}
        </div>
        <div className="border-t border-line px-4 py-2 flex items-center gap-4">
          <span className="font-mono text-[10px] text-muted">↑↓ navigate</span>
          <span className="font-mono text-[10px] text-muted">↵ select</span>
          <span className="font-mono text-[10px] text-muted">esc close</span>
        </div>
      </div>
    </div>
  )
}
