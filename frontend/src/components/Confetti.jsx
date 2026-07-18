import { useEffect, useState } from 'react'

const COLORS = ['var(--color-signal)', 'var(--color-cool)', '#FF9F1C', '#3FB8AF', '#4F46E5', '#E85D5D']

export default function Confetti({ active }) {
  const [particles, setParticles] = useState([])

  useEffect(() => {
    if (!active) { setParticles([]); return }
    setParticles(Array.from({ length: 20 }, (_, i) => ({
      id: i,
      x: 10 + Math.random() * 80,
      color: COLORS[i % COLORS.length],
      delay: Math.random() * 0.3,
      duration: 0.8 + Math.random() * 0.7,
      size: 4 + Math.random() * 4,
    })))
  }, [active])

  if (!particles.length) return null

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden z-10">
      {particles.map((p) => (
        <div
          key={p.id}
          className="absolute rounded-sm confetti-fall"
          style={{
            left: `${p.x}%`,
            top: '-8px',
            width: `${p.size}px`,
            height: `${p.size}px`,
            backgroundColor: p.color,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
          }}
        />
      ))}
    </div>
  )
}
