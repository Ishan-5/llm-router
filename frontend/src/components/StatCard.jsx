import AnimatedCounter from './AnimatedCounter'

export default function StatCard({ label, value, tone, big }) {
  const color = tone === 'cool' ? 'text-cool' : tone === 'signal' ? 'text-signal' : tone === 'danger' ? 'text-danger' : 'text-primary'
  const border = tone === 'cool' ? 'border-cool' : tone === 'signal' ? 'border-signal' : tone === 'danger' ? 'border-danger' : 'border-line'

  const str = String(value)
  const match = str.match(/^([\d.]+)(.*)$/)
  const num = match ? parseFloat(match[1]) : 0
  const sfx = match ? match[2] : ''

  return (
    <div className={`border-l-2 ${border} pl-4`}>
      <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-1.5">{label}</p>
      <p className={`font-display font-semibold ${big ? 'text-4xl' : 'text-3xl'} ${color}`}>
        <AnimatedCounter value={num} suffix={sfx} />
      </p>
    </div>
  )
}
