import { useState } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE, API_KEY } from '../config'

const COPY_RESET_MS = 2000

const TABS = [
  { id: 'quickstart', label: 'Quick Start' },
  { id: 'sdk', label: 'Python SDK' },
  { id: 'openai', label: 'OpenAI SDK' },
  { id: 'cli', label: 'Terminal CLI' },
  { id: 'rest', label: 'REST API' },
  { id: 'streaming', label: 'Streaming' },
  { id: 'byom', label: 'BYOM' },
  { id: 'config', label: 'Configuration' },
  { id: 'mcp', label: 'MCP' },
]

const AUDIENCES = [
  {
    id: 'curious',
    title: 'Just curious',
    desc: 'Play with the live router, grab a free key, and ask anything from your browser.',
    tab: 'quickstart',
  },
  {
    id: 'builder',
    title: 'Building an app',
    desc: 'Integrate with the Python SDK, OpenAI SDK, or plain REST — inside your codebase in minutes.',
    tab: 'sdk',
  },
  {
    id: 'tinkerer',
    title: 'Terminal power user',
    desc: 'Install one CLI and route, stream, chat, and read analytics right from your shell.',
    tab: 'cli',
  },
  {
    id: 'ops',
    title: 'Team lead / ops',
    desc: 'Self-host the router, wire the MCP gateway, tune config, and control cost per person.',
    tab: 'config',
  },
]

const EXAMPLES = {
  quickstart: {
    title: 'Get started in 30 seconds',
    description: 'Install the SDK, set your key, and start routing.',
    sections: [
      {
        label: 'Install',
        code: 'pip install routewise',
        lang: 'bash',
      },
      {
        label: 'Python',
        code: `from routewise import RouteWiseClient

client = RouteWiseClient(api_key="rw_your_key_here")

result = client.ask("What is the capital of France?")
print(result["response"])
# → "The capital of France is Paris."

print(f"Routed to: {result['routed_to']}")
print(f"Cost: $" + f"{result['cost_usd']:.4f}")
print(f"Latency: {result['latency_ms']:.0f}ms")`,
        lang: 'python',
      },
      {
        label: 'Terminal (curl)',
        code: `curl -X POST ${API_BASE}/route \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${API_KEY || 'rw_your_key_here'}" \\
  -d '{"query": "What is the capital of France?"}'`,
        lang: 'bash',
      },
    ],
  },
  sdk: {
    title: 'Python SDK',
    description: 'The `routewise` package wraps all API endpoints into simple method calls.',
    sections: [
      {
        label: 'Install & setup',
        code: `pip install routewise

from routewise import RouteWiseClient

client = RouteWiseClient(api_key="rw_your_key_here")`,
        lang: 'python',
      },
      {
        label: 'Basic routing',
        code: `# Auto-route (ML classifier picks the cheapest tier)
result = client.ask("What is 2+2?")
print(result["response"])

# Force a specific tier
result = client.ask("Explain quantum entanglement", override_tier="frontier")

# Skip cache
result = client.ask("What is 2+2?", bypass_cache=True)

# Per-request key override
result = client.ask("hello", user_api_keys={"frontier": "sk-..."})`,
        lang: 'python',
      },
      {
        label: 'Streaming',
        code: `for item in client.ask_stream("Explain how transformers work"):
    if isinstance(item, str):
        print(item, end="", flush=True)
    else:
        # final metadata dict
        print(f"\\n\\nTier: {item['tier']}, Cost: $\\{item['cost_usd']:.4f}")`,
        lang: 'python',
      },
      {
        label: 'Observability',
        code: `# Recent logs
logs = client.get_logs(limit=20)
for log in logs:
    print(f"{log['tier']:8s} | \${log['cost_usd']:.4f} | {log['query'][:50]}")

# Detailed analytics
analytics = client.get_analytics()
print(f"Total cost: \${analytics['summary']['total_cost']:.4f}")
print(f"Savings: {analytics['summary']['savings_pct']}%")`,
        lang: 'python',
      },
    ],
  },
  openai: {
    title: 'OpenAI SDK (drop-in)',
    description: 'Use the OpenAI Python SDK directly — no wrapper needed. Just point it at the Routewise endpoint.',
    sections: [
      {
        label: 'Setup',
        code: `pip install openai

from openai import OpenAI

client = OpenAI(
    api_key="${API_KEY || 'rw_your_key_here'}",
    base_url="${API_BASE}"
)`,
        lang: 'python',
      },
      {
        label: 'Chat completion',
        code: `response = client.chat.completions.create(
    model="auto",          # "auto" = ML routing, or "cheap"/"mid"/"frontier"
    messages=[
        {"role": "user", "content": "Explain the CAP theorem"}
    ]
)

print(response.choices[0].message.content)
print(f"Tier: {response.headers.get('x-routewise-tier', 'unknown')}")`,
        lang: 'python',
      },
      {
        label: 'Streaming',
        code: `stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "What is DNS?"}],
    stream=True
)

for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.content:
        print(delta.content, end="", flush=True)`,
        lang: 'python',
      },
    ],
  },
  cli: {
    title: 'Terminal CLI',
    description: 'The `routewise` npm CLI brings routing, streaming chat, analytics, and BYOM straight to your shell.',
    sections: [
      {
        label: 'Install',
        code: 'npm i -g routewise',
        lang: 'bash',
      },
      {
        label: 'Set your key and run a self-check',
        code: `routewise config set rw_your_key_here
routewise doctor        # self-check: config, network, live ask
routewise whoami        # identity + usage snapshot`,
        lang: 'bash',
      },
      {
        label: 'Route a query',
        code: `# single answer (metadata goes to stderr)
routewise ask "What is 2+2?"

# stream tokens as they arrive
routewise stream "Explain how transformers work"

# interactive multi-turn chat
routewise chat`,
        lang: 'bash',
      },
      {
        label: 'Usage, cost & feedback',
        code: `routewise stats          # usage, cost and savings summary
routewise logs --limit 10
routewise analytics       # cost analytics + daily breakdown
routewise pricing         # model price list

# thumb up/down to tune routing quality
routewise feedback <log_id> up --reason "great answer"`,
        lang: 'bash',
      },
      {
        label: 'Bring your own model',
        code: `# save a custom model for any tier, once
routewise byom set frontier --provider openrouter --model deepseek/deepseek-v4-flash --key sk-or-v1-...

routewise byom list      # see saved config
routewise ask "..."      # auto-applies your saved models`,
        lang: 'bash',
      },
    ],
  },
  rest: {
    title: 'REST API',
    description: 'Call the API directly from any language or tool.',
    sections: [
      {
        label: 'POST /route — standard routing',
        code: `curl -X POST ${API_BASE}/route \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${API_KEY || 'rw_your_key_here'}" \\
  -d '{
    "query": "Explain the difference between TCP and UDP",
    "override_tier": "auto",
    "bypass_cache": false
  }'

# Response:
# {
#   "response": "TCP is connection-oriented...",
#   "routed_to": "cheap",
#   "cost_usd": 0.000012,
#   "latency_ms": 342,
#   "cache_hit": false,
#   "difficulty_score": 0.35
# }`,
        lang: 'bash',
      },
      {
        label: 'GET /analytics — cost analytics',
        code: `curl ${API_BASE}/analytics \\
  -H "Authorization: Bearer ${API_KEY || 'rw_your_key_here'}"

# Returns: tier costs, model costs, daily breakdown, latency, top expensive queries`,
        lang: 'bash',
      },
      {
        label: 'GET /logs — request logs',
        code: `curl "${API_BASE}/logs?limit=10" \\
  -H "Authorization: Bearer ${API_KEY || 'rw_your_key_here'}"

# Returns: recent requests with query, tier, cost, latency, tokens`,
        lang: 'bash',
      },
      {
        label: 'JavaScript (fetch)',
        code: `const res = await fetch("${API_BASE}/route", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${API_KEY || 'rw_your_key_here'}"
  },
  body: JSON.stringify({
    query: "What is a hash table?"
  })
});

const data = await res.json();
console.log(data.response);
console.log(\`Cost: $\${data.cost_usd}\`);`,
        lang: 'javascript',
      },
    ],
  },
  streaming: {
    title: 'Streaming',
    description: 'Get responses token-by-token for lower perceived latency.',
    sections: [
      {
        label: 'Python (native)',
        code: `from routewise import RouteWiseClient

client = RouteWiseClient(api_key="rw_your_key")

for item in client.ask_stream("Write a haiku about coding"):
    if isinstance(item, str):
        print(item, end="", flush=True)
    else:
        print(f"\\n\\nDone — {item['tier']} tier, \${item['cost_usd']:.6f}")`,
        lang: 'python',
      },
      {
        label: 'Python (OpenAI SDK)',
        code: `from openai import OpenAI

client = OpenAI(api_key="rw_your_key", base_url="${API_BASE}")

stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Write a haiku about coding"}],
    stream=True
)

for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)`,
        lang: 'python',
      },
      {
        label: 'curl (SSE)',
        code: `curl -N -X POST ${API_BASE}/route/stream \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${API_KEY || 'rw_your_key_here'}" \\
  -d '{"query": "Hello world"}'

# SSE events:
# data: {"type": "meta", "routed_to": "cheap", ...}
# data: {"type": "chunk", "text": "Hello"}
# data: {"type": "chunk", "text": "!"}
# data: {"type": "done", "routed_to": "cheap", "cost_usd": 0.00001}`,
        lang: 'bash',
      },
    ],
  },
  byom: {
    title: 'Bring Your Own Model',
    description: 'Override any tier with your own provider and API key. Keys are sent per-request and never stored.',
    sections: [
      {
        label: 'SDK — configure + ask',
        code: `from routewise import RouteWiseClient

client = RouteWiseClient(api_key="rw_your_key")

# Set custom models for any tier
client.configure(
    cheap={"provider": "openrouter", "model_id": "deepseek/deepseek-v4-flash", "api_key": "sk-or-v1-..."},
    mid={"provider": "openai", "model_id": "gpt-4o-mini", "api_key": "sk-..."},
    frontier={"provider": "anthropic", "model_id": "claude-sonnet-4-5", "api_key": "sk-ant-..."},
)

# Now every ask() uses your custom models
result = client.ask("Explain distributed systems")
print(result["response"])

# Reset to defaults
client.reset()`,
        lang: 'python',
      },
      {
        label: 'REST API — per-request keys',
        code: `curl -X POST ${API_BASE}/route \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${API_KEY || 'rw_your_key_here'}" \\
  -d '{
    "query": "Hello",
    "user_api_keys": {
      "frontier": "sk-your-openai-key",
      "mid": "gsk-your-groq-key"
    }
  }'`,
        lang: 'bash',
      },
    ],
  },
  mcp: {
    title: 'MCP Gateway — Agent Tool Use',
    description: 'Run Routewise as a local MCP server so agents (Claude Desktop, Cursor, etc.) can call it as a tool. The full routing pipeline runs in-process — no HTTP round-trip.',
    sections: [
      {
        label: 'Install',
        code: `# From the llm-router/backend directory
pip install mcp`,
        lang: 'bash',
      },
      {
        label: 'Start the server',
        code: `# Runs via stdio — MCP clients launch this automatically
cd llm-router/backend
python -m router.mcp_server`,
        lang: 'bash',
      },
      {
        label: 'Claude Desktop (~/.claude/claude_desktop_config.json)',
        code: `{
  "mcpServers": {
    "routewise": {
      "command": "python",
      "args": ["-m", "router.mcp_server"],
      "cwd": "/path/to/llm-router/backend"
    }
  }
}`,
        lang: 'json',
      },
      {
        label: 'Cursor / other MCP clients (mcp.json)',
        code: `{
  "mcpServers": {
    "routewise": {
      "command": "python",
      "args": ["-m", "router.mcp_server"],
      "cwd": "/path/to/llm-router/backend"
    }
  }
}`,
        lang: 'json',
      },
      {
        label: 'Tool schema — what the agent sees',
        code: `tool: ask_routewise

parameters:
  query        string   required  — the question or task
  override_tier  enum   optional  — "cheap" | "mid" | "frontier"
  threshold    number   optional  — 0.0 (economy) → 1.0 (balanced) → 2.0 (quality)

returns:
  [tier score=X.XX $0.00123]
  <response text>

  or [cache:mid] <cached response>
  or [web] <live search result>`,
        lang: 'bash',
      },
    ],
  },
  config: {
    title: 'Configuration',
    description: 'Environment variables and settings.',
    sections: [
      {
        label: 'Python client options',
        code: `from routewise import RouteWiseClient

client = RouteWiseClient(
    api_key="rw_your_key_here",   # your API key
    base_url="${API_BASE}",       # default: production
    timeout=30,                    # request timeout in seconds
)`,
        lang: 'python',
      },
      {
        label: 'Environment variables',
        code: `# Backend (.env)
DATABASE_URL=postgresql://...       # Supabase Postgres
GROQ_API_KEY=gsk_...                # Default Groq key
GEMINI_API_KEY=...                  # Fallback provider
TAVILY_API_KEY=...                  # Web search (optional)
GROQ_KEYS_CHEAP=gsk_a,gsk_b,gsk_c  # 3 keys per tier
GROQ_KEYS_MID=gsk_d,gsk_e,gsk_f    # round-robin load balancing
GROQ_KEYS_FRONTIER=gsk_g,gsk_h,gsk_i

# Frontend (.env)
VITE_API_BASE=${API_BASE}
VITE_API_KEY=${API_KEY || 'rw_your_key_here'}`,
        lang: 'bash',
      },
      {
        label: 'Supported providers',
        code: `# Run this to see all available providers and models:
providers = client.get_providers()
# → groq, openrouter, openai, anthropic, gemini, deepseek, perplexity, mistral, xai, ollama

# Each tier config:
{
  "provider": "openrouter",            # provider name
  "model_id": "deepseek/deepseek-v4-flash",  # model identifier
  "api_key": "sk-or-v1-..."            # your API key for this provider
}`,
        lang: 'python',
      },
    ],
  },
}

function CodeBlock({ code, lang }) {
  const [copied, setCopied] = useState(false)

  function copy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), COPY_RESET_MS)
    })
  }

  return (
    <div className="relative group rounded-2xl border border-line bg-surface overflow-hidden shadow-card">
      <div className="flex items-center justify-between bg-panel px-4 py-2.5 border-b border-line">
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-danger/60" />
            <span className="w-2.5 h-2.5 rounded-full bg-signal/60" />
            <span className="w-2.5 h-2.5 rounded-full bg-cool/60" />
          </div>
          <span className="font-mono text-[10px] text-primary">routewise.{lang}</span>
        </div>
        <button
          onClick={copy}
          className={`flex items-center gap-1.5 font-mono text-[10px] px-3 py-1 rounded-full border transition ${
            copied
              ? 'border-cool/30 bg-cool/10 text-cool'
              : 'border-line text-muted hover:text-primary hover:border-signal/50 hover:shadow-card'
          }`}
        >
          {copied && (
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          )}
          {copied ? 'copied' : 'copy'}
        </button>
      </div>
      <pre className="bg-panel/40 px-5 py-4 overflow-x-auto text-xs font-mono text-primary leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  )
}

function PillTabBar({ tabs, active, onSelect }) {
  return (
    <div className="flex gap-1.5 flex-wrap">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onSelect(tab.id)}
          className={`px-4 py-2 font-mono text-xs rounded-full border transition-all ${
            active === tab.id
              ? 'border-signal bg-signal/10 text-signal shadow-card'
              : 'border-line text-muted hover:text-primary hover:border-signal/40 hover:shadow-card'
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

function EndpointBadge({ method, path }) {
  const colors = {
    GET: 'text-cool bg-cool/10 border-cool/30',
    POST: 'text-signal bg-signal/10 border-signal/30',
    DELETE: 'text-danger bg-danger/10 border-danger/30',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 font-mono text-[10px] px-2 py-0.5 rounded border shrink-0 ${colors[method] || 'text-muted bg-surface border-line'}`}>
      <span className="font-semibold">{method}</span>
      <span>{path}</span>
    </span>
  )
}

const ENDPOINT_GROUPS = [
  {
    label: 'Routing',
    dot: 'bg-signal',
    items: [
      { method: 'POST', path: '/route', desc: 'Standard routing — ML picks the tier' },
      { method: 'POST', path: '/route/stream', desc: 'Streaming routing — SSE chunks' },
      { method: 'POST', path: '/v1/chat/completions', desc: 'OpenAI-compatible endpoint' },
    ],
  },
  {
    label: 'Observability',
    dot: 'bg-cool',
    items: [
      { method: 'GET', path: '/analytics', desc: 'Cost analytics for your key' },
      { method: 'GET', path: '/logs', desc: 'Recent request logs' },
      { method: 'GET', path: '/logs/{id}', desc: 'Full detail of a single log' },
      { method: 'GET', path: '/stats', desc: 'Aggregate system stats' },
    ],
  },
  {
    label: 'System',
    dot: 'bg-danger',
    items: [
      { method: 'GET', path: '/pricing', desc: 'All model pricing' },
      { method: 'GET', path: '/providers', desc: 'Supported providers list' },
      { method: 'GET', path: '/config', desc: 'Current model config' },
      { method: 'POST', path: '/config', desc: 'Save BYOM config' },
      { method: 'DELETE', path: '/config', desc: 'Reset to defaults' },
      { method: 'GET', path: '/health', desc: 'Health check (no auth)' },
    ],
  },
]

function CopyCurlButton({ method, path }) {
  const [copied, setCopied] = useState(false)
  function copy() {
    const curl = `curl -X ${method} ${API_BASE}${path} \\\n  -H "Authorization: Bearer <your-key>"`
    navigator.clipboard.writeText(curl).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), COPY_RESET_MS)
    })
  }
  return (
    <button
      onClick={copy}
      className={`font-mono text-[10px] px-2 py-0.5 rounded-full border transition shrink-0 ${
        copied ? 'border-cool/30 bg-cool/10 text-cool' : 'border-line text-muted hover:text-primary hover:border-signal/50'
      }`}
    >
      {copied ? 'copied' : 'curl'}
    </button>
  )
}

function ApiReference() {
  return (
    <div className="space-y-8">
      {ENDPOINT_GROUPS.map((group) => (
        <div key={group.label}>
          <h3 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-3 flex items-center gap-2">
            <span className={`w-1.5 h-1.5 rounded-full ${group.dot}`} />
            {group.label}
            <span className="font-mono text-[9px] text-muted/50 ml-1">({group.items.length})</span>
          </h3>
          <div className="space-y-2">
            {group.items.map((ep) => (
              <div
                key={`${ep.method}-${ep.path}`}
                className="flex flex-wrap sm:flex-nowrap items-center gap-3 py-3 px-4 bg-surface rounded-xl border border-line shadow-card hover:shadow-card-hover hover:-translate-y-0.5 hover:border-signal/30 transition-all duration-200"
              >
                <EndpointBadge method={ep.method} path={ep.path} />
                <span className="flex-1 font-body text-xs text-muted">{ep.desc}</span>
                <CopyCurlButton method={ep.method} path={ep.path} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function GuidePage() {
  const [activeTab, setActiveTab] = useState('quickstart')
  const current = EXAMPLES[activeTab]

  function switchTo(tab) {
    setActiveTab(tab)
    document.getElementById('guide-tabs')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="relative max-w-4xl mx-auto px-6 py-20">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 dot-grid opacity-30 [mask-image:radial-gradient(ellipse_70%_40%_at_50%_0%,black,transparent)]"
      />

      {/* Hero */}
      <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4">Documentation</p>
      <h1 className="font-display text-3xl font-semibold mb-2">Developer Guide</h1>
      <p className="text-muted text-sm mb-10 max-w-xl">
        Everything you need to integrate Routewise into your app — via the Python SDK, the terminal CLI, the
        OpenAI-compatible endpoint, or the REST API directly.
      </p>

      {/* Pick your path */}
      <div className="mb-8">
        <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-3 flex items-center gap-2">
          <span className="w-1 h-1 rounded-full bg-cool" />
          Pick your path
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {AUDIENCES.map((a) => (
            <button
              key={a.id}
              onClick={() => switchTo(a.tab)}
              className="group relative text-left rounded-xl border border-line bg-surface p-4 shadow-card hover:shadow-card-hover hover:-translate-y-0.5 hover:border-signal/30 transition-all duration-200"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="w-1.5 h-1.5 rounded-full bg-signal" />
                <span className="text-sm font-semibold text-primary">{a.title}</span>
              </div>
              <p className="text-xs text-muted leading-relaxed mb-3">{a.desc}</p>
              <span className="font-mono text-[10px] text-signal group-hover:underline">Start here →</span>
            </button>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div id="guide-tabs" className="mb-8">
        <PillTabBar tabs={TABS} active={activeTab} onSelect={setActiveTab} />
      </div>

      {/* Content */}
      <div key={activeTab} className="space-y-6 animate-[page-fade-in_0.2s_ease-out]">
        <div>
          <h2 className="font-display text-xl font-semibold mb-1">{current.title}</h2>
          <p className="text-muted text-sm">{current.description}</p>
        </div>

        <div className="space-y-4">
          {current.sections.map((section) => (
            <div key={section.label}>
              <h3 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-2 flex items-center gap-2">
                <span className="w-1 h-1 rounded-full bg-signal" />
                {section.label}
              </h3>
              <CodeBlock code={section.code} lang={section.lang} />
            </div>
          ))}
        </div>
      </div>

      {/* API Reference */}
      <div className="mt-16 border-t border-line pt-10">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-6">
          <h2 className="font-display text-xl font-semibold">API Reference</h2>
          <span className="font-mono text-[9px] uppercase tracking-wide text-muted px-2.5 py-1 rounded-full border border-line">
            13 endpoints · Bearer auth
          </span>
        </div>
        <p className="text-muted text-sm mb-6">All available endpoints. Most require <code className="font-mono text-[10px] bg-panel px-1 py-0.5 rounded">Authorization: Bearer &lt;key&gt;</code> header.</p>
        <ApiReference />
      </div>

      {/* Closing CTA */}
      <div className="relative mt-16 rounded-2xl border border-line bg-surface overflow-hidden shadow-card">
        <div aria-hidden className="pointer-events-none absolute inset-0">
          <div className="absolute -top-20 -left-16 w-64 h-64 rounded-full bg-cool/10 blur-3xl" />
          <div className="absolute -bottom-24 -right-16 w-64 h-64 rounded-full bg-signal/10 blur-3xl" />
        </div>
        <div className="relative px-8 py-10 text-center">
          <p className="font-mono text-[10px] text-signal uppercase tracking-wide mb-3">Ready when you are</p>
          <h2 className="font-display text-2xl font-semibold mb-2">Start routing in 30 seconds</h2>
          <p className="text-sm text-muted mb-7 max-w-md mx-auto">
            Grab your API key and send your first query — the router picks the cheapest tier that gets it right.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              to="/get-started"
              className="bg-signal text-white font-semibold text-sm px-7 py-3 rounded-full shadow-card hover:brightness-110 transition"
            >
              Get your API key
            </Link>
            <Link
              to="/"
              className="font-mono text-sm text-muted border border-line px-7 py-3 rounded-full hover:text-primary hover:border-signal/50 hover:shadow-card transition"
            >
              ← Back to live demo
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}