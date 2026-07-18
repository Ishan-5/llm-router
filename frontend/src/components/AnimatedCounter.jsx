import { useEffect, useRef, useState } from 'react'

export default function AnimatedCounter({ value, duration = 600, prefix = '', suffix = '' }) {
  const [display, setDisplay] = useState(0)
  const raf = useRef(null)
  const prev = useRef(0)

  useEffect(() => {
    const to = typeof value === 'number' ? value : 0
    const from = prev.current
    const start = performance.now()

    function tick(now) {
      const t = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - t, 3)
      setDisplay(Math.round(from + (to - from) * eased))
      if (t < 1) raf.current = requestAnimationFrame(tick)
      else prev.current = to
    }

    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [value, duration])

  return <span>{prefix}{display}{suffix}</span>
}
