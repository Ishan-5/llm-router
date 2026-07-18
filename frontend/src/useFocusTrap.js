import { useEffect, useRef } from 'react'

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

export default function useFocusTrap(open) {
  const ref = useRef(null)
  const previousRef = useRef(null)

  useEffect(() => {
    if (!open) return
    previousRef.current = document.activeElement
    const el = ref.current
    if (!el) return
    const first = el.querySelector(FOCUSABLE)
    if (first) setTimeout(() => first.focus(), 50)

    function handleKey(e) {
      if (e.key !== 'Tab') return
      const focusable = el.querySelectorAll(FOCUSABLE)
      if (!focusable.length) return
      const firstEl = focusable[0]
      const lastEl = focusable[focusable.length - 1]
      if (e.shiftKey) {
        if (document.activeElement === firstEl) { e.preventDefault(); lastEl.focus() }
      } else {
        if (document.activeElement === lastEl) { e.preventDefault(); firstEl.focus() }
      }
    }

    el.addEventListener('keydown', handleKey)
    return () => {
      el.removeEventListener('keydown', handleKey)
      if (previousRef.current && previousRef.current.focus) previousRef.current.focus()
    }
  }, [open])

  return ref
}
