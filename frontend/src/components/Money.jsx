import AnimatedCounter from './AnimatedCounter'

// One implementation of the animated dollar readout, because there were five and
// two of them disagreed.
//
// The previous version in MetricsBand/MetricsDashboard animated
// Math.round(value * 100) and then appended the cents of value.toFixed(2), which
// double-counted: $0.1219 of real savings rendered as "$12.12", a 98x
// overstatement of the largest number on the page. The bug is easy to reintroduce
// by eye because "$0" and ".1219" look right separately.
//
// So: split the FORMATTED string, animate the integer part, and never scale the
// value for the counter.
export default function Money({ value, size = 'lg', className = '' }) {
  const safe = Number.isFinite(Number(value)) ? Number(value) : 0
  const [int, dec] = safe.toFixed(4).split('.')
  const cls = size === 'sm' ? 'text-xl' : size === 'xl' ? 'text-4xl md:text-5xl' : 'text-2xl'
  return (
    <span className={`font-display font-bold num-tabular ${cls} ${className}`}>
      <AnimatedCounter value={Math.round(Number(int))} prefix="$" />
      .{dec}
    </span>
  )
}