import { useState } from 'react'

const CATEGORIES = [
  { key: 'overall', label: 'Best Overall', icon: '★' },
  { key: 'coding', label: 'Coding', icon: '<>' },
  { key: 'writing', label: 'Creative Writing', icon: '✎' },
  { key: 'fast', label: 'Fast & Cheap', icon: '⚡' },
  { key: 'reasoning', label: 'Reasoning', icon: '🧠' },
]

const PICKS = {
  overall: [
    { model: 'claude-3.5-sonnet', provider: 'anthropic', why: 'Best all-round quality. Strong at code, writing, analysis, and instruction-following.' },
    { model: 'gpt-4o', provider: 'openai', why: 'Versatile, fast, and reliable. Handles multimodal inputs well.' },
    { model: 'gemini-2.0-flash', provider: 'gemini', why: 'Near-frontier quality at a fraction of the cost. Great default choice.' },
    { model: 'deepseek-v3', provider: 'deepseek', why: 'Top-tier performance at budget pricing. punches well above its price.' },
    { model: 'llama-3.3-70b', provider: 'groq', why: 'Best open-source option. Runs fast on Groq infrastructure.' },
  ],
  coding: [
    { model: 'deepseek-v3', provider: 'deepseek', why: 'Rivals GPT-4 on code benchmarks at ~1/10th the price.' },
    { model: 'claude-3.5-sonnet', provider: 'anthropic', why: 'Excellent at complex refactoring, debugging, and code review.' },
    { model: 'codestral', provider: 'mistral', why: 'Purpose-built for code. Fast inference on Mistral\'s API.' },
    { model: 'llama-3.3-70b', provider: 'groq', why: 'Strong code generation, free-tier friendly via Groq.' },
    { model: 'qwen-coder-32b', provider: 'groq', why: 'Open-source coder with strong multi-language support.' },
  ],
  writing: [
    { model: 'claude-3.5-sonnet', provider: 'anthropic', why: 'Most natural prose. Best at tone, style, and long-form coherence.' },
    { model: 'gpt-4o', provider: 'openai', why: 'Excellent creative output with strong prompt adherence.' },
    { model: 'gemini-2.0-flash', provider: 'gemini', why: 'Surprisingly good writing quality at very low cost.' },
    { model: 'mistral-large', provider: 'mistral', why: 'Strong multilingual creative writing. Good at structured content.' },
    { model: 'llama-3.3-70b', provider: 'groq', why: 'Best free option for creative tasks. Good at following style instructions.' },
  ],
  fast: [
    { model: 'llama3.2:3b', provider: 'ollama', why: 'Runs locally. Zero latency, zero cost. Great for simple queries.' },
    { model: 'llama-3.1-8b', provider: 'groq', why: 'Sub-100ms inference on Groq. Handles basic tasks well.' },
    { model: 'gemini-2.0-flash', provider: 'gemini', why: 'Fast API responses, very cheap. Handles most simple queries.' },
    { model: 'deepseek-v3', provider: 'deepseek', why: 'Fast and cheap. Great bang for buck on straightforward tasks.' },
    { model: 'gemma-2-9b', provider: 'groq', why: 'Lightweight, fast, free. Good for classification and simple Q&A.' },
  ],
  reasoning: [
    { model: 'claude-3.5-sonnet', provider: 'anthropic', why: 'Strongest at multi-step reasoning, math, and logic puzzles.' },
    { model: 'gpt-4o', provider: 'openai', why: 'Excellent analytical reasoning. Handles ambiguous questions well.' },
    { model: 'deepseek-r1', provider: 'deepseek', why: 'Purpose-built reasoning model. Chain-of-thought out of the box.' },
    { model: 'gemini-2.0-flash', provider: 'gemini', why: 'Good reasoning at low cost. Handles most analytical tasks.' },
    { model: 'llama-3.3-70b', provider: 'groq', reason: 'Best open-source reasoning. Strong at math and logic.' },
  ],
}

const PROVIDER_COLORS = {
  anthropic: 'text-cool border-cool/30 bg-cool/5',
  openai: 'text-primary border-line bg-panel',
  gemini: 'text-signal border-signal/30 bg-signal/5',
  deepseek: 'text-cool border-cool/30 bg-cool/5',
  groq: 'text-signal border-signal/30 bg-signal/5',
  mistral: 'text-signal border-signal/30 bg-signal/5',
  ollama: 'text-muted border-line bg-panel',
}

export default function TopModels() {
  const [active, setActive] = useState('overall')
  const picks = PICKS[active] || []

  return (
    <div className="mb-16">
      <p className="font-mono text-[10px] text-signal uppercase tracking-wide mb-2">Curated picks</p>
      <h2 className="font-display text-2xl font-semibold mb-2">Top models by use case</h2>
      <p className="text-sm text-muted mb-6">Hand-picked recommendations based on quality, speed, and cost-effectiveness.</p>

      {/* category tabs */}
      <div className="flex flex-wrap gap-2 mb-8">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.key}
            onClick={() => setActive(cat.key)}
            className={`flex items-center gap-1.5 font-mono text-xs px-3 py-1.5 rounded-full border transition-colors ${
              active === cat.key
                ? 'border-signal bg-signal/10 text-signal'
                : 'border-line text-muted hover:border-signal/40 hover:text-primary'
            }`}
          >
            <span className="text-[11px]">{cat.icon}</span>
            {cat.label}
          </button>
        ))}
      </div>

      {/* picks grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {picks.map((pick, i) => {
          const colorClass = PROVIDER_COLORS[pick.provider] || 'text-muted border-line bg-panel'
          return (
            <div
              key={pick.model}
              className="border border-line rounded-xl p-4 hover:border-signal/30 transition-colors bg-panel/50"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-mono text-[10px] text-muted shrink-0">#{i + 1}</span>
                  <h4 className="font-display font-semibold text-sm truncate">{pick.model}</h4>
                </div>
                <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded-md border shrink-0 ${colorClass}`}>
                  {pick.provider}
                </span>
              </div>
              <p className="text-xs text-muted leading-relaxed">{pick.why}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
