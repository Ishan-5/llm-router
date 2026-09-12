/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        base: 'var(--color-base)',
        panel: 'var(--color-panel)',
        panel2: 'var(--color-panel2)',
        surface: 'var(--color-surface)',
        line: 'var(--color-line)',
        signal: 'var(--color-signal)',
        cool: 'var(--color-cool)',
        danger: 'var(--color-danger)',
        primary: 'var(--color-primary)',
        muted: 'var(--color-muted)',
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        'card-hover': 'var(--shadow-card-hover)',
        pop: 'var(--shadow-pop)',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
