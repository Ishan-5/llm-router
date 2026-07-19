import{r,j as e,A as s,l as i}from"./index-CEfiGuh9.js";const c=2e3,d=[{id:"quickstart",label:"Quick Start"},{id:"sdk",label:"Python SDK"},{id:"openai",label:"OpenAI SDK"},{id:"rest",label:"REST API"},{id:"streaming",label:"Streaming"},{id:"byom",label:"BYOM"},{id:"config",label:"Configuration"}],p={quickstart:{title:"Get started in 30 seconds",description:"Install the SDK, set your key, and start routing.",sections:[{label:"Install",code:"pip install routewise",lang:"bash"},{label:"Python",code:`from routewise import RouteWiseClient

client = RouteWiseClient(api_key="rw_your_key_here")

result = client.ask("What is the capital of France?")
print(result["response"])
# → "The capital of France is Paris."

print(f"Routed to: {result['routed_to']}")
print(f"Cost: $" + f"{result['cost_usd']:.4f}")
print(f"Latency: {result['latency_ms']:.0f}ms")`,lang:"python"},{label:"Terminal (curl)",code:`curl -X POST ${s}/route \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${i}" \\
  -d '{"query": "What is the capital of France?"}'`,lang:"bash"}]},sdk:{title:"Python SDK",description:"The `routewise` package wraps all API endpoints into simple method calls.",sections:[{label:"Install & setup",code:`pip install routewise

from routewise import RouteWiseClient

client = RouteWiseClient(api_key="rw_your_key_here")`,lang:"python"},{label:"Basic routing",code:`# Auto-route (ML classifier picks the cheapest tier)
result = client.ask("What is 2+2?")
print(result["response"])

# Force a specific tier
result = client.ask("Explain quantum entanglement", override_tier="frontier")

# Skip cache
result = client.ask("What is 2+2?", bypass_cache=True)

# Per-request key override
result = client.ask("hello", user_api_keys={"frontier": "sk-..."})`,lang:"python"},{label:"Streaming",code:`for item in client.ask_stream("Explain how transformers work"):
    if isinstance(item, str):
        print(item, end="", flush=True)
    else:
        # final metadata dict
        print(f"\\n\\nTier: {item['tier']}, Cost: \${item['cost_usd']:.4f}")`,lang:"python"},{label:"Observability",code:`# Recent logs
logs = client.get_logs(limit=20)
for log in logs:
    print(f"{log['tier']:8s} | \${log['cost_usd']:.4f} | {log['query'][:50]}")

# Detailed analytics
analytics = client.get_analytics()
print(f"Total cost: \${analytics['summary']['total_cost']:.4f}")
print(f"Savings: {analytics['summary']['savings_pct']}%")`,lang:"python"}]},openai:{title:"OpenAI SDK (drop-in)",description:"Use the OpenAI Python SDK directly — no wrapper needed. Just point it at the Routewise endpoint.",sections:[{label:"Setup",code:`pip install openai

from openai import OpenAI

client = OpenAI(
    api_key="${i}",
    base_url="${s}"
)`,lang:"python"},{label:"Chat completion",code:`response = client.chat.completions.create(
    model="auto",          # "auto" = ML routing, or "cheap"/"mid"/"frontier"
    messages=[
        {"role": "user", "content": "Explain the CAP theorem"}
    ]
)

print(response.choices[0].message.content)
print(f"Tier: {response.headers.get('x-routewise-tier', 'unknown')}")`,lang:"python"},{label:"Streaming",code:`stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "What is DNS?"}],
    stream=True
)

for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.content:
        print(delta.content, end="", flush=True)`,lang:"python"}]},rest:{title:"REST API",description:"Call the API directly from any language or tool.",sections:[{label:"POST /route — standard routing",code:`curl -X POST ${s}/route \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${i}" \\
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
# }`,lang:"bash"},{label:"GET /analytics — cost analytics",code:`curl ${s}/analytics \\
  -H "Authorization: Bearer ${i}"

# Returns: tier costs, model costs, daily breakdown, latency, top expensive queries`,lang:"bash"},{label:"GET /logs — request logs",code:`curl "${s}/logs?limit=10" \\
  -H "Authorization: Bearer ${i}"

# Returns: recent requests with query, tier, cost, latency, tokens`,lang:"bash"},{label:"JavaScript (fetch)",code:`const res = await fetch("${s}/route", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${i}"
  },
  body: JSON.stringify({
    query: "What is a hash table?"
  })
});

const data = await res.json();
console.log(data.response);
console.log(\`Cost: $\${data.cost_usd}\`);`,lang:"javascript"}]},streaming:{title:"Streaming",description:"Get responses token-by-token for lower perceived latency.",sections:[{label:"Python (native)",code:`from routewise import RouteWiseClient

client = RouteWiseClient(api_key="rw_your_key")

for item in client.ask_stream("Write a haiku about coding"):
    if isinstance(item, str):
        print(item, end="", flush=True)
    else:
        print(f"\\n\\nDone — {item['tier']} tier, \${item['cost_usd']:.6f}")`,lang:"python"},{label:"Python (OpenAI SDK)",code:`from openai import OpenAI

client = OpenAI(api_key="rw_your_key", base_url="${s}")

stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Write a haiku about coding"}],
    stream=True
)

for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)`,lang:"python"},{label:"curl (SSE)",code:`curl -N -X POST ${s}/route/stream \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${i}" \\
  -d '{"query": "Hello world"}'

# SSE events:
# data: {"type": "meta", "routed_to": "cheap", ...}
# data: {"type": "chunk", "text": "Hello"}
# data: {"type": "chunk", "text": "!"}
# data: {"type": "done", "routed_to": "cheap", "cost_usd": 0.00001}`,lang:"bash"}]},byom:{title:"Bring Your Own Model",description:"Override any tier with your own provider and API key. Keys are sent per-request and never stored.",sections:[{label:"SDK — configure + ask",code:`from routewise import RouteWiseClient

client = RouteWiseClient(api_key="rw_your_key")

# Set custom models for any tier
client.configure(
    cheap={"provider": "groq", "model_id": "llama-3.1-8b-instant", "api_key": "gsk_..."},
    mid={"provider": "openai", "model_id": "gpt-4o-mini", "api_key": "sk-..."},
    frontier={"provider": "anthropic", "model_id": "claude-sonnet-4-20250514", "api_key": "sk-ant-..."},
)

# Now every ask() uses your custom models
result = client.ask("Explain distributed systems")
print(result["response"])

# Reset to defaults
client.reset()`,lang:"python"},{label:"REST API — per-request keys",code:`curl -X POST ${s}/route \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${i}" \\
  -d '{
    "query": "Hello",
    "user_api_keys": {
      "frontier": "sk-your-openai-key",
      "mid": "gsk-your-groq-key"
    }
  }'`,lang:"bash"}]},config:{title:"Configuration",description:"Environment variables and settings.",sections:[{label:"Python client options",code:`from routewise import RouteWiseClient

client = RouteWiseClient(
    api_key="rw_your_key_here",   # your API key
    base_url="${s}",       # default: production
    timeout=30,                    # request timeout in seconds
)`,lang:"python"},{label:"Environment variables",code:`# Backend (.env)
DATABASE_URL=postgresql://...       # Supabase Postgres
GROQ_API_KEY=gsk_...                # Default Groq key
GEMINI_API_KEY=...                  # Fallback provider
TAVILY_API_KEY=...                  # Web search (optional)
GROQ_KEYS_CHEAP=gsk_a,gsk_b,gsk_c  # 3 keys per tier
GROQ_KEYS_MID=gsk_d,gsk_e,gsk_f    # round-robin load balancing
GROQ_KEYS_FRONTIER=gsk_g,gsk_h,gsk_i

# Frontend (.env)
VITE_API_BASE=${s}
VITE_API_KEY=${i}`,lang:"bash"},{label:"Supported providers",code:`# Run this to see all available providers and models:
providers = client.get_providers()
# → groq, openai, anthropic, gemini, deepseek, perplexity, mistral, xai, ollama

# Each tier config:
{
  "provider": "groq",           # provider name
  "model_id": "llama-3.1-8b-instant",  # model identifier
  "api_key": "gsk_..."         # your API key for this provider
}`,lang:"python"}]}};function u({code:n,lang:o}){const[a,t]=r.useState(!1);function l(){navigator.clipboard.writeText(n).then(()=>{t(!0),setTimeout(()=>t(!1),c)})}return e.jsxs("div",{className:"relative group rounded-xl border border-line overflow-hidden",children:[e.jsxs("div",{className:"flex items-center justify-between bg-panel px-3 py-2 border-b border-line",children:[e.jsx("span",{className:"font-mono text-[10px] text-muted uppercase",children:o}),e.jsx("button",{onClick:l,className:"font-mono text-[10px] text-muted hover:text-primary transition-colors px-2 py-0.5 rounded hover:bg-base",children:a?"copied":"copy"})]}),e.jsx("pre",{className:"bg-surface px-4 py-3 overflow-x-auto text-xs font-mono text-primary leading-relaxed",children:e.jsx("code",{children:n})})]})}function m({method:n,path:o}){const a={GET:"text-cool bg-cool/10 border-cool/30",POST:"text-signal bg-signal/10 border-signal/30",DELETE:"text-danger bg-danger/10 border-danger/30"};return e.jsxs("span",{className:`inline-flex items-center gap-1.5 font-mono text-[10px] px-2 py-0.5 rounded border ${a[n]||"text-muted bg-surface border-line"}`,children:[e.jsx("span",{className:"font-semibold",children:n}),e.jsx("span",{children:o})]})}function h(){const n=[{method:"POST",path:"/route",desc:"Standard routing — ML picks the tier"},{method:"POST",path:"/route/stream",desc:"Streaming routing — SSE chunks"},{method:"POST",path:"/v1/chat/completions",desc:"OpenAI-compatible endpoint"},{method:"GET",path:"/analytics",desc:"Cost analytics for your key"},{method:"GET",path:"/logs",desc:"Recent request logs"},{method:"GET",path:"/logs/{id}",desc:"Full detail of a single log"},{method:"GET",path:"/stats",desc:"Aggregate system stats"},{method:"GET",path:"/pricing",desc:"All model pricing"},{method:"GET",path:"/providers",desc:"Supported providers list"},{method:"GET",path:"/config",desc:"Current model config"},{method:"POST",path:"/config",desc:"Save BYOM config"},{method:"DELETE",path:"/config",desc:"Reset to defaults"},{method:"GET",path:"/health",desc:"Health check (no auth)"}];return e.jsx("div",{className:"space-y-2",children:n.map(o=>e.jsxs("div",{className:"flex items-center gap-3 py-2 px-3 bg-surface rounded-lg border border-line hover:border-signal/30 transition-colors",children:[e.jsx(m,{method:o.method,path:o.path}),e.jsx("span",{className:"font-body text-xs text-muted",children:o.desc})]},`${o.method}-${o.path}`))})}function y(){const[n,o]=r.useState("quickstart"),a=p[n];return e.jsxs("div",{className:"max-w-4xl mx-auto px-6 py-20",children:[e.jsx("p",{className:"font-mono text-xs text-signal tracking-wide uppercase mb-4",children:"Documentation"}),e.jsx("h1",{className:"font-display text-3xl font-semibold mb-2",children:"Developer Guide"}),e.jsx("p",{className:"text-muted text-sm mb-10 max-w-xl",children:"Everything you need to integrate Routewise into your app. Use the SDK, call the OpenAI-compatible endpoint, or talk to the REST API directly."}),e.jsx("div",{className:"flex gap-1 border-b border-line mb-8 overflow-x-auto",children:d.map(t=>e.jsx("button",{onClick:()=>o(t.id),className:`px-4 py-2.5 font-mono text-xs border-b-2 transition-colors whitespace-nowrap ${n===t.id?"border-signal text-primary":"border-transparent text-muted hover:text-primary"}`,children:t.label},t.id))}),e.jsxs("div",{className:"space-y-6 animate-[slide-in_0.15s_ease-out]",children:[e.jsxs("div",{children:[e.jsx("h2",{className:"font-display text-xl font-semibold mb-1",children:a.title}),e.jsx("p",{className:"text-muted text-sm",children:a.description})]}),e.jsx("div",{className:"space-y-4",children:a.sections.map(t=>e.jsxs("div",{children:[e.jsx("h3",{className:"font-mono text-[10px] text-muted uppercase tracking-wide mb-2",children:t.label}),e.jsx(u,{code:t.code,lang:t.lang})]},t.label))})]}),e.jsxs("div",{className:"mt-16 border-t border-line pt-10",children:[e.jsx("h2",{className:"font-display text-xl font-semibold mb-2",children:"API Reference"}),e.jsxs("p",{className:"text-muted text-sm mb-6",children:["All available endpoints. Most require ",e.jsx("code",{className:"font-mono text-[10px] bg-panel px-1 py-0.5 rounded",children:"Authorization: Bearer <key>"})," header."]}),e.jsx(h,{})]})]})}export{y as default};
