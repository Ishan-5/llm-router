import { useState, useMemo, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE, API_KEY } from '../config'

const COPY_RESET_MS = 2000

// tailwind.config maps colors to bare var(--x) references, so `bg-cool/10`
// style opacity modifiers silently generate nothing. color-mix() is the only
// way to get a themed translucent fill, and index.css already relies on it.
const tint = (name, pct) => `color-mix(in srgb, var(--color-${name}) ${pct}%, transparent)`

const KEY = API_KEY || 'rw_your_key_here'

const TABS = [
  { id: 'quickstart', label: 'Quick Start', group: 'Start' },
  { id: 'support', label: 'Support bot', group: 'Start', badge: 'new' },
  { id: 'teams', label: 'Teams', group: 'Start', badge: 'new' },
  { id: 'how', label: 'How it works', group: 'Reference' },
  { id: 'policies', label: 'Policies', group: 'Reference' },
  { id: 'sdk', label: 'Python SDK', group: 'Reference' },
  { id: 'openai', label: 'OpenAI SDK', group: 'Reference' },
  { id: 'cli', label: 'Terminal CLI', group: 'Reference' },
  { id: 'rest', label: 'REST API', group: 'Reference' },
  { id: 'streaming', label: 'Streaming', group: 'Reference' },
  { id: 'byom', label: 'BYOM', group: 'Reference' },
  { id: 'config', label: 'Configuration', group: 'Reference' },
  { id: 'mcp', label: 'MCP', group: 'Reference' },
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
    id: 'support',
    title: 'Running a support bot',
    desc: 'Keep your chatbot and your memory. Swap only the model call, and route with kate or lisa.',
    tab: 'support',
    accent: 'cool',
    badge: 'most common',
  },
  {
    id: 'team',
    title: 'Rolling out to a team',
    desc: 'Issue a key per person, cap spend with alerts, set one routing threshold for everyone.',
    tab: 'teams',
    accent: 'signal',
    badge: 'new',
  },
  {
    id: 'tinkerer',
    title: 'Terminal power user',
    desc: 'Install one CLI and route, stream, chat, and read analytics right from your shell.',
    tab: 'cli',
  },
  {
    id: 'ops',
    title: 'Self-hosting / ops',
    desc: 'Run the router yourself, wire the MCP gateway, and pick the right difficulty policy.',
    tab: 'mcp',
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
print(f"Latency: {result['latency_ms']:.0f}ms")

# Three routing policies: emma (generic, the default), lisa (3-tier
# support) and kate (2-tier support). See the Policies tab.
result = client.ask("I want a refund", model="lisa")`,
        lang: 'python',
      },
      {
        label: 'Terminal (curl)',
        code: `curl -X POST ${API_BASE}/route \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${KEY}" \\
  -d '{"query": "What is the capital of France?"}'`,
        lang: 'bash',
      },
      {
        label: 'Not sure which policy?',
        kind: 'note',
        title: 'Start with emma, move to kate when the traffic is support',
        body: `emma is the general-purpose model and the default — use it unless your
queries are support tickets. If they are, kate is the safer default because it
sends 14.0% of genuinely-hard tickets to a cheap model versus lisa's 19.6%.

Not building a bot? You can skip all of this. emma is the right answer until
your traffic looks like tickets.`,
      },
    ],
  },

  support: {
    title: 'Putting it behind a customer support bot',
    description:
      'You keep your chatbot, your memory, and your UX. Only the model call changes — point it at Routewise and pick a support policy.',
    sections: [
      {
        label: 'The drop-in',
        code: `from openai import OpenAI

# This is the entire integration. Nothing else about your bot changes.
router = OpenAI(api_key="${KEY}", base_url="${API_BASE}")

def ask_router(turns):
    """turns = your existing message list, exactly as your bot already builds it."""
    resp = router.chat.completions.create(model="kate", messages=turns)
    return resp.choices[0].message.content

# Your existing call site stays the same shape:
answer = ask_router([
    {"role": "user",      "content": "my app keeps crashing when I sync"},
    {"role": "assistant", "content": "Sorry about that — can you send the error code?"},
    {"role": "user",      "content": "it says 500 every time"},
])
print(answer)

# Which tier actually served it, straight off the response headers:
print(resp.headers.get("x-routewise-tier"))     # cheap | mid | frontier
print(resp.headers.get("x-routewise-cost"))     # e.g. 0.000188`,
        lang: 'python',
      },
      {
        label: 'Routewise keeps no memory — you must',
        kind: 'warn',
        title: 'Pass the whole conversation, every single turn',
        body: `Routewise is stateless. It stores no sessions and never reads your
history back. It scores the NEWEST message to pick a model, then forwards
whatever messages array you gave it.

So if you pass only the latest turn, a follow-up like "now draw it in python"
gets judged on its own — it looks trivial, goes to the cheap model, and then
has to reason about something complex with a weak model. Routewise scores the
last 4 turns as context too, but it can only do that if you SEND them.

  ✗ messages=[{"role":"user","content":"now draw it in python"}]
  ✓ messages=[*full_turn_history, {"role":"user","content":"now draw it in python"}]`,
      },
      {
        label: 'kate or lisa?',
        kind: 'table',
        title: 'Both are support models on the same regressors — only the cut rule differs',
        columns: ['', 'kate (2-tier)', 'lisa (3-tier)'],
        rows: [
          ['cheap when', 'score ≤ 4.0', 'score ≤ 2.0'],
          ['frontier when', 'anything above 4.0', 'score ≥ 4.5'],
          ['mid band', 'none', '2.0 < score < 4.5'],
          ['frontier recall', '86.0%', '80.4%'],
          ['frontier escape', '14.0%', '19.6%'],
          ['traffic c/m/f', '66 / 0 / 34', '46 / 24 / 29'],
        ],
        body: `Default to kate. A support bot that answers "I can't log in" with the
cheap model is a bad experience, and kate's 4.0 cut keeps far more of those on
a capable tier. Choose lisa only if mid-tier answers are genuinely good enough
for your product and you want the cheaper mix.`,
      },
      {
        label: 'Turn the cache off for follow-ups',
        kind: 'warn',
        title: 'A cache hit replays nothing — it returns a stored answer verbatim',
        body: `The semantic cache matches on the NEWEST message only, scoped to your
API key, at 0.95 cosine similarity. It does not know which conversation it
belongs to.

A follow-up like "yes" or "draw it" is very close to someone else's "yes" or
"draw it" from a different conversation — and a hit returns that stored answer
without calling a model at all. No history is replayed, so it cannot possibly
know what "it" meant.

The safe integration is to bypass the cache on every turn after the first:

  # OpenAI endpoint has no per-request bypass flag, so switch to /route,
  # which does (bypass_cache: true):
  resp = requests.post(f"{API_BASE}/route", json={
      "query": last_user_text,
      "messages": turns,
      "support_mode": "2tier",     # kate
      "bypass_cache": len(turns) > 1,
  }, headers={"Authorization": "Bearer rw_..."})`,
      },
      {
        label: 'Already have a bot? per-turn REST',
        code: `import requests

BASE = "${API_BASE}"
HEADERS = {"Authorization": "Bearer rw_your_key_here"}

def route_turn(turns):
    """Send the full transcript; the router picks the tier per turn."""
    r = requests.post(f"{BASE}/route", headers={**HEADERS, "Content-Type": "application/json"}, json={
        "query": turns[-1]["content"],   # newest message drives the score
        "messages": turns,               # full context — this is what fixes follow-ups
        "support_mode": "2tier",         # kate  ("3tier" = lisa, omit = emma)
        "bypass_cache": len(turns) > 1,  # never serve a stored answer to a follow-up
    }, timeout=30)
    r.raise_for_status()
    d = r.json()
    return {
        "reply":        d["response"],
        "tier":         d["routed_to"],
        "difficulty":   d["difficulty_score"],
        "cost_usd":     d["cost_usd"],
        "log_id":       d["request_log_id"],   # hook thumbs up/down to this
    }`,
        lang: 'python',
      },
      {
        label: 'Measure it before you ship',
        code: `import requests

# What did the policy actually do on YOUR traffic?
# (replays your last 500 logged scores through each policy's own rule)
stats = requests.get(f"{BASE}/policy-analytics", headers=HEADERS).json()

for m in stats["models"]:
    if m["available"]:
        print(m["id"], m["traffic"], f"{m['savings_pct']}% saved")

# Per-request detail, newest first
for log in requests.get(f"{BASE}/logs?limit=20", headers=HEADERS).json():
    print(f"{log['tier']:9s} score={log['difficulty_score']:.2f}  {log['query'][:60]}")

# Thumbs up/down feeds back into routing quality
requests.post(f"{BASE}/route/feedback", headers=HEADERS, json={
    "request_log_id": 1234, "feedback": "down", "reason": "wrong policy tier",
})`,
        lang: 'python',
      },
      {
        label: 'Before you ship',
        kind: 'warn',
        title: 'Know these before your bot answers a paying customer',
        body: `• The score is length-sensitive. "Prove the halting problem is
  undecidable" scores 3.60 (cheap); the same question spelled out at length
  scores 8.35 (frontier). Short-but-hard tickets can be under-routed. If your
  tickets are terse, prefer kate over lisa, and spot-check /logs weekly.

• Support models are domain-specific. Lisa and kate were trained on 17,600
  support tickets across four domains (account_access, orders_billing,
  technical, delivery_general). Point kate at a general or coding question
  and it will under-route, because that is out of distribution for it. Use
  emma for anything that is not a support ticket.

• lisa routes "thanks, that fixed it!" to the mid tier (score 2.17, cut 2.0).
  Support traffic is full of short conversational turns that land in mid.
  Harmless, but do not read it as a bug.

• The frontier floor is deliberately conservative — the design prefers a
  correct cheap answer over an expensive wrong one.`,
      },
    ],
  },

  teams: {
    title: 'Rolling out to a team',
    description:
      'What a lead actually does on day one: issue a key per person, set one routing threshold for everyone, and put a webhook on spend before anything else.',
    sections: [
      {
        label: 'Day 1 — issue one key per person',
        code: `# Keys are per-user, per-key, and revocable. Never share one key.
# The endpoints below need a Supabase JWT (any logged-in user), not an rw_ key.

curl -X POST ${API_BASE}/keys \\
  -H "Authorization: Bearer <your-jwt>" \\
  -H "Content-Type: application/json" \\
  -d '{"name": "priya — support-bot"}'

curl ${API_BASE}/keys -H "Authorization: Bearer <your-jwt>"
# → [{"id": 7, "name": "priya — support-bot", ...}]

# Revoke instantly when someone leaves
curl -X DELETE ${API_BASE}/keys/7 -H "Authorization: Bearer <your-jwt>"`,
        lang: 'bash',
      },
      {
        label: 'Set one threshold for the whole team',
        code: `curl -X POST ${API_BASE}/settings \\
  -H "Authorization: Bearer <your-jwt>" \\
  -H "Content-Type: application/json" \\
  -d '{"router_threshold": 1.0}'

# 0.0 economy  cheap ≤ 5.25   frontier ≥ 6.75   cheapest, misses more hard work
# 1.0 balanced  cheap ≤ 4.50   frontier ≥ 6.00   the default
# 2.0 quality   cheap ≤ 3.75   frontier ≥ 5.25   priciest, escalates the most

# Per-request override always wins, so a teammate can test without changing
# the team default:
curl -X POST ${API_BASE}/route -H "Authorization: Bearer rw_..." \\
  -H "Content-Type: application/json" \\
  -d '{"query": "Explain Raft consensus", "threshold": 2.0}'`,
        lang: 'bash',
      },
      {
        label: 'Put a webhook on spend first',
        code: `curl -X POST ${API_BASE}/alerts \\
  -H "Authorization: Bearer <your-jwt>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "alert_type": "daily_spend",
    "threshold": 25.0,
    "webhook_url": "https://hooks.slack.com/services/..."
  }'

# alert_type is one of: daily_spend | error_rate | latency
curl ${API_BASE}/alerts -H "Authorization: Bearer <your-jwt>"
curl -X DELETE ${API_BASE}/alerts/1 -H "Authorization: Bearer <your-jwt>"`,
        lang: 'bash',
      },
      {
        label: 'What each person can see',
        kind: 'table',
        title: 'Visibility follows the key, not the person',
        columns: ['surface', 'scope', 'who'],
        rows: [
          ['/logs, /stats, /analytics', 'their own key only', 'any developer'],
          ['/compare, /calibrate, /policy-analytics', 'their own key', 'any developer'],
          ['/keys, /settings, /alerts', 'their own user', 'any developer'],
          ['/admin/*', 'every user on the instance', 'ADMIN_USER_ID only'],
        ],
        body: `Because analytics are scoped per API key, each developer sees only their
own traffic. To review the whole team you need the admin surface, which is
gated on the ADMIN_USER_ID environment variable.`,
      },
      {
        label: 'Budget caps — what actually exists',
        kind: 'warn',
        title: 'Per-key daily budgets are enforced, but not settable over the API yet',
        body: `Every API key has a daily_budget_usd column and the router honours it:
when a key's spend for the day crosses the cap, the router forces that key to
the cheap tier and reports "budget exceeded - forced to cheap" in route_reason.

However no endpoint writes that column today. It is only readable via the admin
surface. So for a team rollout today, use daily_spend alerts for visibility and
per-key revocation for enforcement — not per-key hard caps.

  Read only:  GET /admin/keys  → includes daily_budget_usd
  Not writable by any public endpoint today.

A teammate on their own key who exhausts their own provider quota hits the
normal failover chain (frontier → mid → cheap → Gemini), not an error.`,
      },
      {
        label: 'Suggested rollout order',
        code: `1. Add a /compare and /calibrate read on existing traffic.
   See what balanced vs quality would have cost you before you switch.

2. Put kate behind ONE support surface, not all of them.
   Prefer the flow with the most measurable user feedback.

3. Enable the daily_spend alert the same day you enable routing.

4. Read /logs every few days for a fortnight and look for
   cheap + difficulty_score above the policy's cheap cut.
   That is the under-routing signature, and it is exactly what
   "thanks, that fixed it!" style false positives look like.

5. Only then widen to the rest of the support traffic.

Do NOT flip byom_config for a team on day one — it is per-user config and
carries provider keys. Leave the defaults.`,
        lang: 'bash',
      },
    ],
  },

  how: {
    title: 'How routing actually works',
    description:
      'The full pipeline, in the order it runs. Useful when you want to reason about a specific decision instead of just copying a snippet.',
    sections: [
      {
        label: 'The pipeline, in order',
        code: `1. auth              require_api_key  (rw_... key, in-memory cached)
2. validate           query non-empty, ≤1000 chars
                      support_mode ∈ {generic, 2tier, 3tier}
                      override_tier ∈ {cheap, mid, frontier}
                      threshold ∈ [0.0, 2.0]
3. injection check    9 regexes → HTTP 400 on match
4. web search?        ~30 regexes (today/latest/weather/news/price) + Tavily
                      → returns tier="web", cost $0, no LLM called
5. threshold          request value → user setting → default 1.0
6. IN PARALLEL        ┌─ semantic cache lookup  (≥0.95 cosine)
                      └─ difficulty scoring
7. cache hit?         → return stored text, cost $0, done
8. override check     2tier has no mid band, so forcing mid → HTTP 400
9. budget             over daily_budget_usd → force cheap
10. provider call     call_with_failover
11. log               request_logs row
12. cache write       add_to_cache
13. background        LLM-as-judge quality score + LLM-as-labeler difficulty`,
        lang: 'text',
      },
      {
        label: 'What the score is made of',
        code: `emma  — 388 features
  384  MiniLM-L6-v2 sentence embedding (local, in memory)
    4  handcrafted: word count · has-code regex · contains "?" · "N words"
  → ensemble of 2 LightGBM regressors (v18 + v19, averaged), output clipped 0-10
  trained on 8,200 rows of an 8,783-row Claude-verified gold set

lisa / kate — 392 features
  384  the same MiniLM embedding (shared instance, no extra pass)
    4  the same handcrafted features
    4  domain one-hot: account_access · delivery_general ·
                         orders_billing · technical
  → 3 LightGBM regressors (seeds 18/19/20), 17,600 support tickets
  domain chosen by a deterministic keyword vote, no model, no network

lisa and kate run the SAME regressors. They produce identical scores and differ
only in how the score is cut into tiers.`,
        lang: 'text',
      },
      {
        label: 'Score → tier',
        code: `emma:
  t              = (margin * 0.3 - 0.3) / 0.3
  cheap_ceil     = 4.5  - t * 0.75
  frontier_floor = 6.0  - t * 0.75

  margin 0.0 economy   cheap ≤ 5.25   frontier ≥ 6.75
  margin 1.0 balanced  cheap ≤ 4.50   frontier ≥ 6.00
  margin 2.0 quality   cheap ≤ 3.75   frontier ≥ 5.25

  score >= frontier_floor → frontier
  score <= cheap_ceil     → cheap
  otherwise               → mid

lisa (3tier):  cheap ≤ 2.0 · frontier ≥ 4.5 · else mid
kate (2tier):  cheap ≤ 4.0 · else frontier   (no mid band; the stored
                                               frontier_floor of 4.5 is unused)`,
        lang: 'text',
      },
      {
        label: 'The semantic cache',
        code: `threshold      0.95 cosine similarity — deliberately strict, near-exact
                paraphrase only
scan window     most recent 500 rows for your API key
store           the embedding as JSON text alongside the response
on hit          cost $0, logs tokens_saved_usd, no provider call
eviction        30-day expiry, 5,000-row cap

Keyed on the newest message only — see the Support bot tab for why that
matters for multi-turn chat.`,
        lang: 'text',
      },
      {
        label: 'Failover',
        code: `chain          frontier → mid → cheap
               mid      → cheap
               cheap    → internal ollama
               all dead → Gemini (independent provider, cross_provider_fallback)

429             never retried. Retrying a rate limit is pointless for a live
                request, so it skips to the next tier and marks that key
                cooling in the load balancer
timeout / 5xx   retried once after 1s, then falls back
circuit breaker per tier, so a dead provider stops being tried
streaming      no in-place retry — chunks already sent cannot be recalled, so
                it emits a failover event and moves to the next tier
all tiers dead  HTTP 503`,
        lang: 'text',
      },
      {
        label: 'Multi-turn follow-ups',
        code: `The router scores the newest message alone AND together with the last 4
turns, then keeps whichever score is HIGHER.

  "now draw it in python"   alone:  1.61 → cheap
                            with context: 6.86 → frontier

Taking the max means a follow-up can only ever escalate, never de-escalate —
so this cannot make cheap questions accidentally expensive. The second pass is
skipped entirely if the message already routes to frontier.

Single-turn requests build no context string and take the original path
unchanged. Both passes are the same local sklearn model and the same local
embedder, so this costs no extra LLM call and no extra API spend.

This only helps if you send the history — Routewise stores nothing.`,
        lang: 'text',
      },
      {
        label: 'What the models actually cost',
        kind: 'table',
        title: 'Tier prices ascend by design',
        columns: ['tier', 'model', 'in / out per M', 'per request @ 500+500'],
        rows: [
          ['cheap', 'groq · gpt-oss-20b', '$0.075 / $0.30', '$0.000188  (1.0×)'],
          ['mid', 'groq · gpt-oss-120b', '$0.15 / $0.60', '$0.000375  (2.0×)'],
          ['frontier', 'openrouter · deepseek-chat', '$0.27 / $1.10', '$0.000690  (3.7×)'],
        ],
        body: `Tier prices MUST ascend cheap < mid < frontier. They once did not:
deepseek-chat sat in "cheap" while gpt-oss-120b sat in "frontier", so every
downroute cost 1.84× more than calling frontier and the savings claims inverted.
BYOM overrides reprice against the effective model, so swapping in your own
model does not silently inherit the default tier's price.`,
      },
    ],
  },

  policies: {
    title: 'Policies — emma · lisa · kate',
    description:
      'Three routing personalities, each with its own difficulty model and thresholds. Switch per request across every surface.',
    sections: [
      {
        label: 'Pick a policy',
        code: `emma   — generic routing (default): cheap / mid / frontier, slider-movable cuts
lisa   — customer support, 3-tier:  cheap / mid / frontier, fixed cuts ≤ 2.0 / ≥ 4.5
kate   — customer support, 2-tier:  cheap / frontier, single fixed cut ≤ 4.0

Pick by what you route for:
  general chat / agents               → emma
  support tickets, balanced cost       → lisa
  support where a hard ticket is costly → kate

All three cost no extra LLM call. The support policies reuse the MiniLM
embedder already resident in memory.`,
        lang: 'bash',
      },
      {
        label: 'Python SDK',
        code: `from routewise import RouteWiseClient
client = RouteWiseClient(api_key="rw_your_key_here")

client.ask("What is the capital of France?")     # emma (default)
client.ask("I want a refund", model="lisa")      # 3-tier support policy
client.ask("I was charged twice", model="kate")  # 2-tier support policy

client.get_models()    # list all three: tiers, cutoffs, honest eval numbers`,
        lang: 'python',
      },
      {
        label: 'Terminal CLI',
        code: `routewise ask "I want a refund" --model lisa
routewise stream "where is my order?" --model kate
routewise chat --model lisa

routewise models       # browse the policies: tiers, cuts, evals`,
        lang: 'bash',
      },
      {
        label: 'OpenAI-compatible endpoint',
        code: `from openai import OpenAI
client = OpenAI(api_key="...", base_url="${API_BASE}")

resp = client.chat.completions.create(
    model="lisa",          # emma · lisa · kate — mapped server-side
    messages=[{"role": "user", "content": "Refund please"}],
)
print(resp.choices[0].message.content)`,
        lang: 'python',
      },
      {
        label: 'REST',
        code: `curl -X POST ${API_BASE}/route \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${KEY}" \\
  -d '{"query": "Refund please", "support_mode": "3tier"}'

# support_mode: "generic" (emma) | "2tier" (kate) | "3tier" (lisa)`,
        lang: 'bash',
      },
      {
        label: 'Honest eval (shipped artifacts)',
        kind: 'table',
        title: 'Read these as directional signals, not one leaderboard',
        columns: ['policy', 'MAE', 'Spearman', 'frontier recall', 'frontier escape'],
        rows: [
          ['emma (783 general holdout)', '1.018', '0.861', '58.0%', '—'],
          ['lisa (17,600 support tickets)', '0.822', '0.786', '80.4%', '19.6%'],
          ['kate (17,600 support tickets)', '0.822', '0.786', '86.0%', '14.0%'],
        ],
        body: `These are NOT comparable to each other. emma is evaluated on general
Claude-gold queries; lisa and kate are evaluated on support tickets from three
independent batch-level splits (62/13/13 of 88 batches, so tickets from one
conversation cannot leak across train/test).

"Frontier escape" is the share of genuinely-hard queries a policy would have
DOWNGRADED to a cheaper tier. Lower is safer. That is the honest risk metric
and it is why kate is the recommended support default.

Support policies reuse the MiniLM embedder already in memory — support routing
costs no extra embedding pass and no extra LLM call. Same 392-feature LightGBM
regressor (seeds 18/19/20), different cuts.`,
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
        label: 'Pick a routing model',
        code: `# Generic difficulty routing (default)
result = client.ask("What is the capital of France?")

# Customer support — 3-tier policy (lisa)
result = client.ask("I want a refund", model="lisa")

# Customer support — 2-tier policy (kate)
result = client.ask("I was charged twice", model="kate")

# List available models + their cuts and evals
models = client.get_models()
print(models)`,
        lang: 'python',
      },
      {
        label: 'Multi-turn chat',
        code: `# NOTE: ask() and ask_stream() take a single query string and do NOT
# accept messages. For a conversation, use chat() — it forwards the whole
# message list, which is what enables contextual difficulty scoring.

resp = client.chat([
    {"role": "user",      "content": "design a distributed task scheduler"},
    {"role": "assistant", "content": "Use Raft for leader election..."},
    {"role": "user",      "content": "now draw it in python"},
], model="kate")

print(resp["choices"][0]["message"]["content"])`,
        lang: 'python',
      },
      {
        label: 'Streaming',
        code: `for item in client.ask_stream("Explain how transformers work"):
    if isinstance(item, str):
        print(item, end="", flush=True)
    else:
        # final metadata dict
        print(f"\\n\\nTier: {item['tier']}, Cost: $\{item['cost_usd']:.4f}")`,
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
print(f"Savings: {analytics['summary']['savings_pct']}%")

# What emma / lisa / kate would each have done with your real traffic
print(client.get_stats())`,
        lang: 'python',
      },
      {
        label: 'Exceptions',
        code: `from routewise import (
    RouteWiseClient,
    RouteWiseError,      # base class for everything below
    ValidationError,     # 400 — bad request shape, or support_mode typo
    AuthError,           # 401 / 403 / 429 — bad key, revoked key, rate limited
    AllTiersFailedError, # 503 — every provider and fallback failed
)

try:
    client.ask("hello", support_mode="4tier")
except ValidationError as e:
    print(e)   # support_mode must be one of generic/2tier/3tier`,
        lang: 'python',
      },
    ],
  },

  openai: {
    title: 'OpenAI SDK (drop-in)',
    description:
      'Use the OpenAI Python SDK directly — no wrapper needed. Just point it at the Routewise endpoint.',
    sections: [
      {
        label: 'Setup',
        code: `pip install openai

from openai import OpenAI

client = OpenAI(
    api_key="${KEY}",
    base_url="${API_BASE}"
)`,
        lang: 'python',
      },
      {
        label: 'Chat completion',
        code: `response = client.chat.completions.create(
    model="auto",          # "auto" routing, "cheap"/"mid"/"frontier", or emma/lisa/kate
    messages=[
        {"role": "user", "content": "Explain the CAP theorem"}
    ]
)

print(response.choices[0].message.content)
print(f"Tier: {response.headers.get('x-routewise-tier', 'unknown')}")`,
        lang: 'python',
      },
      {
        label: 'Response headers',
        kind: 'table',
        title: 'Every call reports what the router did',
        columns: ['header', 'meaning'],
        rows: [
          ['x-routewise-tier', 'cheap · mid · frontier · web · failed'],
          ['x-routewise-cost', 'USD actually spent on this request'],
          ['x-routewise-cache-hit', '"true" when a cached answer was served'],
          ['x-routewise-difficulty', 'predicted 0-10 difficulty score'],
        ],
        body: `Use these for per-request logging in your own app. They are the
cheapest way to build your own routing dashboard without calling /analytics.`,
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
      {
        label: 'Gotcha — no cache bypass here',
        kind: 'warn',
        title: 'The OpenAI endpoint has no per-request bypass_cache flag',
        body: `POST /route and /route/stream accept bypass_cache. The OpenAI-compatible
POST /v1/chat/completions does not.

If you are sending a real conversation, use /route instead so you can bypass
the semantic cache on follow-up turns — otherwise a short reply like "yes" can
match a stored answer from a different conversation. The Support bot tab shows
the pattern.`,
      },
    ],
  },

  cli: {
    title: 'Terminal CLI',
    description:
      'The `routewise` npm CLI brings routing, streaming chat, analytics, and BYOM straight to your shell.',
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
routewise chat

# pick a routing model: emma (generic, default), lisa (3tier support), kate (2tier support)
routewise ask "I want a refund" --model lisa
routewise stream "Where is my order?" --model kate
routewise chat --model lisa

# raw policy id overrides --model
routewise ask "I was charged twice" --support-mode 2tier`,
        lang: 'bash',
      },
      {
        label: 'Discover models',
        code: `# list all routing models: emma/lisa/kate, their tiers, cuts and evals
routewise models`,
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
        label: 'Useful flags',
        kind: 'table',
        title: 'Flags available on ask / stream / chat',
        columns: ['flag', 'effect'],
        rows: [
          ['--model emma|lisa|kate', 'pick the routing policy'],
          ['--support-mode <id>', 'raw policy id, overrides --model'],
          ['--tier cheap|mid|frontier', 'skip scoring, force a tier'],
          ['--threshold <0..2>', 'override the routing sensitivity for this call'],
          ['--bypass-cache', 'skip the semantic cache'],
          ['--no-byom', 'ignore saved bring-your-own-model settings'],
          ['--stream / --json / --quiet', 'output mode'],
          ['--base-url / --key', 'per-call endpoint and key override'],
        ],
      },
      {
        label: 'Bring your own model',
        code: `# save a custom model for any tier, once — set just one, two, or all three tiers
routewise byom set cheap --provider openrouter --model deepseek/deepseek-v4-flash --key sk-or-v1-...
routewise byom set frontier --provider openrouter --model claude-3.7-sonnet --key sk-or-v1-...

routewise byom list      # see saved config
routewise ask "..."      # auto-applies your saved models; unset tiers keep defaults`,
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
  -H "Authorization: Bearer ${KEY}" \\
  -d '{
    "query": "Explain the difference between TCP and UDP",
    "messages": [{"role": "user", "content": "Explain the difference between TCP and UDP"}],
    "override_tier": "auto",
    "bypass_cache": false,
    "support_mode": "generic"
  }'

# Response — exactly these 20 fields:
# {
#   "response":              "TCP is connection-oriented...",
#   "routed_to":            "cheap",      # what actually served it
#   "intended_tier":        "cheap",      # what the router aimed for
#   "predicted_tier":        "cheap",      # what the score alone wanted
#   "override_used":        false,        # did the caller force a tier?
#   "budget_capped":        false,        # did a spend cap force it to cheap?
#   "fallback_used":        false,        # did a lower tier serve it?
#   "cross_provider_fallback": false,     # did it end up on Gemini?
#   "cache_hit":            false,
#   "difficulty_score":     1.09,         # 0-10
#   "cost_usd":             0.000012,
#   "latency_ms":           342.1,
#   "quality_score":        null,         # filled in later by the judge
#   "cheap_ceil":           4.5,          # the cuts actually used
#   "frontier_floor":       6.0,
#   "support_mode":         "generic",
#   "available_tiers":      ["cheap", "mid", "frontier"],
#   "model_id":             "openai/gpt-oss-20b",
#   "route_reason":         "score 1.09 <= cheap ceiling 4.5",
#   "request_log_id":       4821          # pass this to /route/feedback
# }
#
# intended_tier != routed_to means a failover happened, and route_reason
# then ends with "(fallback to <tier>)".`,
        lang: 'bash',
      },
      {
        label: 'Errors',
        kind: 'table',
        title: 'What comes back when it goes wrong',
        columns: ['status', 'when', 'fix'],
        rows: [
          ['400', 'prompt injection matched', 'reword — the router blocks 9 jailbreak patterns'],
          ['400', 'query empty or over 1000 chars', 'shorten it'],
          ['400', 'support_mode not generic/2tier/3tier', 'use a valid policy id'],
['400', 'override_tier mid under 2tier', 'kate has no mid band'],
          ['400', 'override_tier not cheap/mid/frontier', 'use one of the three'],
          ['401', 'missing or revoked key', 'check the Bearer header'],
          ['429', 'over the per-key request rate limit', 'back off — the limit is requests/minute per key'],
          ['503', 'every tier AND Gemini failed', 'check provider keys'],
        ],
        body: `The router prefers a degraded answer over an error. Provider failures
walk the fallback chain (frontier → mid → cheap → Gemini) and only surface a
503 once everything is genuinely unavailable.`,
      },
      {
        label: 'Feedback loop',
        code: `curl -X POST ${API_BASE}/route/feedback \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${KEY}" \\
  -d '{
    "request_log_id": 4821,
    "feedback": "down",
    "reason": "cheap tier could not explain Raft"
  }'

# feedback is "up" or "down". This is what feeds the policy-quality review
# loop — pair it with the background LLM-as-labeler to catch under-routing.`,
        lang: 'bash',
      },
      {
        label: 'Analytics, compare, calibrate',
        code: `# what your traffic actually cost
curl ${API_BASE}/analytics -H "Authorization: Bearer ${KEY}"

# what balanced / economy / quality would have done with the same traffic
curl ${API_BASE}/compare -H "Authorization: Bearer ${KEY}"

# the difficulty scores that would change tier at each threshold
curl ${API_BASE}/calibrate -H "Authorization: Bearer ${KEY}"

# replay your last 500 logged scores through emma, lisa and kate
curl ${API_BASE}/policy-analytics -H "Authorization: Bearer ${KEY}"`,
        lang: 'bash',
      },
      {
        label: 'JavaScript (fetch)',
        code: `const res = await fetch("${API_BASE}/route", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${KEY}"
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
  -H "Authorization: Bearer ${KEY}" \\
  -d '{"query": "Hello world"}'

# SSE event types, in the order they arrive:
# data: {"type":"meta","routed_to":"cheap","cache_hit":false,"cost_usd":0.0,
#        "latency_ms":342,"model_id":"openai/gpt-oss-20b","request_log_id":4821}
# data: {"type":"chunk","text":"Hello"}
# data: {"type":"chunk","text":"!"}
# data: {"type":"failover","from_tier":"frontier","detail":"429 rate limited"}
# data: {"type":"done","routed_to":"cheap","cost_usd":0.00001,"latency_ms":...}

# Handle all five:
#   meta      exactly once, before any tokens — show the tier early
#   chunk     0..n times, the answer itself
#   failover  a tier died mid-stream. NOT fatal: an answer is still coming,
#             so render it as a continuity notice, not an error
#   error     no tokens produced at all (e.g. "No response from model")
#   done      terminal event, carries the final cost

# Two paths bypass scoring entirely and still emit meta + chunk + done:
#   routed_to "web"   model_id tavily/search, cost_usd 0
#   cache_hit true     the stored answer, cost_usd 0, plus tokens_saved_usd`,
        lang: 'bash',
      },
    ],
  },

  byom: {
    title: 'Bring Your Own Model',
    description:
      'Override any tier with your own provider and API key. Keys are sent per-request and never stored.',
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
  -H "Authorization: Bearer ${KEY}" \\
  -d '{
    "query": "Hello",
    "user_api_keys": {
      "frontier": "sk-your-openai-key",
      "mid": "gsk-your-groq-key"
    }
  }'`,
        lang: 'bash',
      },
      {
        label: 'BYOM reprices your model',
        kind: 'note',
        title: 'Costs are recomputed against your model, not the tier default',
        body: `Prices merged in from the default config belong to the tier's default
model. When you override a model, the router resolves that model's own rates —
and if you supply price_per_m_input / price_per_m_output in byom_config, those
win outright.

That matters because tier prices must ascend cheap < mid < frontier. Swap in a
model whose price breaks that order and your savings numbers will be wrong in
both directions. Check routewise pricing after any BYOM change.`,
      },
    ],
  },

  mcp: {
    title: 'MCP Gateway — Agent Tool Use',
    description:
      'Run Routewise as a local MCP server so agents (Claude Desktop, Cursor, etc.) can call it as a tool. The full routing pipeline runs in-process — no HTTP round-trip.',
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
  query          string   required  — the question or task
  override_tier  enum     optional  — "cheap" | "mid" | "frontier"
  threshold      number   optional  — 0.0 (economy) → 1.0 (balanced) → 2.0 (quality)

returns:
  [tier score=X.XX $0.00123]
  <response text>

  or [cache:mid] <cached response>
  or [web] <live search result>

Note: the tool takes a single query string, so there is no conversation
history to pass. Each agent call is scored and routed independently.`,
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

/* ============================ components ============================ */

function useCopy(resetMs = COPY_RESET_MS) {
  const [copied, setCopied] = useState(false)
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), [])

  function copy(text) {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), resetMs)
    })
  }

  return [copied, copy]
}

function CodeBlock({ code, lang, label }) {
  const [copied, copy] = useCopy()
  const lines = code.split('\n').length

  return (
    <div className="relative group rounded-2xl border border-line bg-surface overflow-hidden shadow-card">
      <div className="flex items-center justify-between bg-panel px-4 py-2.5 border-b border-line">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex gap-1.5 shrink-0">
            <span className="w-2.5 h-2.5 rounded-full bg-danger" />
            <span className="w-2.5 h-2.5 rounded-full bg-signal" />
            <span className="w-2.5 h-2.5 rounded-full bg-cool" />
          </div>
          <span className="font-mono text-[10px] text-primary truncate">
            routewise.{lang}
          </span>
          {label && (
            <span className="hidden sm:inline font-mono text-[9px] text-muted truncate">
              · {label}
            </span>
          )}
        </div>
        <button
          onClick={() => copy(code)}
          aria-label="Copy code"
          className="flex items-center gap-1.5 font-mono text-[10px] px-3 py-1 rounded-full border transition shrink-0"
          style={
            copied
              ? {
                  borderColor: tint('cool', 40),
                  background: tint('cool', 12),
                  color: 'var(--color-cool)',
                }
              : undefined
          }
        >
          {copied ? (
            <span style={{ color: 'var(--color-cool)' }}>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </span>
          ) : null}
          <span style={copied ? { color: 'var(--color-cool)' } : undefined}>
            {copied ? 'copied' : 'copy'}
          </span>
        </button>
      </div>
      <pre className="px-5 py-4 overflow-x-auto text-xs font-mono text-primary leading-relaxed max-h-[32rem]">
        <code>{code}</code>
      </pre>
      {lines > 24 && (
        <div className="px-5 py-2 border-t border-line bg-panel">
          <span className="font-mono text-[9px] text-muted">{lines} lines · scroll for more</span>
        </div>
      )}
    </div>
  )
}

const CALLOUT = {
  note: { label: 'Note', color: 'cool' },
  warn: { label: 'Read this', color: 'danger' },
  tip: { label: 'Tip', color: 'signal' },
}

function Callout({ kind = 'note', title, children }) {
  const c = CALLOUT[kind] || CALLOUT.note
  return (
    <div
      className="rounded-2xl border p-5 shadow-card"
      style={{ background: tint(c.color, 6), borderColor: tint(c.color, 28) }}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: `var(--color-${c.color})` }} />
        <span className="font-mono text-[9px] uppercase tracking-wide" style={{ color: `var(--color-${c.color})` }}>
          {c.label}
        </span>
        {title && <span className="text-sm font-semibold text-primary">{title}</span>}
      </div>
      <div className="text-xs text-muted leading-relaxed font-body whitespace-pre-line">{children}</div>
    </div>
  )
}

function DataTable({ columns, rows }) {
  return (
    <div className="rounded-2xl border border-line bg-surface overflow-hidden shadow-card">
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="bg-panel border-b border-line">
              {columns.map((col, i) => (
                <th
                  key={i}
                  className={`text-left px-4 py-2.5 font-mono text-[10px] uppercase tracking-wide text-muted font-normal ${i > 0 ? 'border-l border-line' : ''}`}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri} className="border-b border-line last:border-b-0 hover:bg-[color-mix(in_srgb,var(--color-panel)_45%,transparent)] transition">
                {row.map((cell, ci) => (
                  <td
                    key={ci}
                    className={`px-4 py-2.5 ${ci === 0 ? 'text-muted' : 'text-primary border-l border-line'}`}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function SectionBlock({ section }) {
  const id = section.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  const isCode = section.kind === 'code' || typeof section.code === 'string'

  return (
    <section id={id} className="scroll-mt-28">
      <h3 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-2 flex items-center gap-2">
        <span
          className="w-1 h-1 rounded-full"
          style={{ background: `var(--color-${section.kind === 'warn' ? 'danger' : 'signal'})` }}
        />
        {section.label}
        <a href={`#${id}`} className="text-muted opacity-50 hover:text-signal transition" aria-label={`Link to ${section.label}`}>
          #
        </a>
      </h3>

      {isCode ? (
        <CodeBlock code={section.code} lang={section.lang || 'text'} label={section.label} />
      ) : section.kind === 'table' ? (
        <div className="space-y-3">
          {section.title && (
            <p className="text-xs text-primary font-medium">{section.title}</p>
          )}
          <DataTable columns={section.columns} rows={section.rows} />
          {section.body && <Callout kind="note">{section.body}</Callout>}
        </div>
      ) : (
        <div className="space-y-3">
          {section.title && <Callout kind={section.kind} title={section.title}>{section.body}</Callout>}
          {!section.title && <Callout kind={section.kind}>{section.body}</Callout>}
        </div>
      )}
    </section>
  )
}

function PillTabBar({ tabs, active, onSelect }) {
  const groups = useMemo(() => {
    const out = []
    for (const t of tabs) {
      const last = out[out.length - 1]
      if (last && last.name === t.group) last.items.push(t)
      else out.push({ name: t.group, items: [t] })
    }
    return out
  }, [tabs])

  return (
    <div className="space-y-3">
      {groups.map((g) => (
        <div key={g.name} className="flex items-start gap-3">
          <span className="font-mono text-[9px] uppercase tracking-wide text-muted opacity-60 w-16 shrink-0 pt-2">
            {g.name}
          </span>
          <div className="flex gap-1.5 flex-wrap">
            {g.items.map((tab) => {
              const on = active === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => onSelect(tab.id)}
                  aria-current={on ? 'page' : undefined}
                  className="px-3.5 py-1.5 font-mono text-xs rounded-full border transition-all flex items-center gap-1.5"
                  style={
                    on
                      ? {
                          borderColor: 'var(--color-signal)',
                          background: tint('signal', 12),
                          color: 'var(--color-signal)',
                        }
                      : undefined
                  }
                >
                  {tab.label}
                  {tab.badge && (
                    <span
                      className="font-mono text-[8px] px-1.5 py-px rounded-full uppercase"
                      style={{
                        background: tint(on ? 'signal' : 'cool', on ? 22 : 16),
                        color: `var(--color-${on ? 'signal' : 'cool'})`,
                      }}
                    >
                      {tab.badge}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

function EndpointBadge({ method, path }) {
  const color = { GET: 'cool', POST: 'signal', DELETE: 'danger', PUT: 'cool', PATCH: 'signal' }[method] || 'muted'
  return (
    <span
      className="inline-flex items-center gap-1.5 font-mono text-[10px] px-2 py-0.5 rounded border shrink-0"
      style={{
        color: `var(--color-${color})`,
        background: tint(color, 10),
        borderColor: tint(color, 28),
      }}
    >
      <span className="font-semibold">{method}</span>
      <span style={{ color: 'var(--color-primary)' }}>{path}</span>
    </span>
  )
}

const ENDPOINT_GROUPS = [
  {
    label: 'Routing',
    dot: 'signal',
    items: [
      { method: 'POST', path: '/route', desc: 'Standard routing — ML picks the tier' },
      { method: 'POST', path: '/route/stream', desc: 'Streaming routing — SSE chunks' },
      { method: 'POST', path: '/v1/chat/completions', desc: 'OpenAI-compatible chat endpoint' },
      { method: 'GET', path: '/route/policies', desc: 'Routing policies, tiers and cutoffs' },
      { method: 'POST', path: '/route/feedback', desc: 'Thumbs up/down on a logged request' },
    ],
  },
  {
    label: 'Observability',
    dot: 'cool',
    items: [
      { method: 'GET', path: '/stats', desc: 'Aggregate stats for your key' },
      { method: 'GET', path: '/analytics', desc: 'Cost analytics and daily breakdown' },
      { method: 'GET', path: '/logs', desc: 'Recent request logs' },
      { method: 'GET', path: '/logs/{log_id}', desc: 'Full detail of one log' },
      { method: 'GET', path: '/compare', desc: 'Economy vs balanced vs quality replay' },
      { method: 'GET', path: '/calibrate', desc: 'Which logs change tier per threshold' },
      { method: 'GET', path: '/policy-analytics', desc: 'Replay logged traffic through emma/lisa/kate' },
    ],
  },
  {
    label: 'Evaluation',
    dot: 'signal',
    items: [
      { method: 'POST', path: '/evaluate', desc: 'Score a batch of labelled queries' },
    ],
  },
  {
    label: 'Keys & settings',
    dot: 'cool',
    items: [
      { method: 'GET', path: '/keys', desc: 'List your API keys' },
      { method: 'POST', path: '/keys', desc: 'Issue a new key' },
      { method: 'DELETE', path: '/keys/{key_id}', desc: 'Revoke a key' },
      { method: 'GET', path: '/settings', desc: 'Your routing threshold' },
      { method: 'POST', path: '/settings', desc: 'Set your routing threshold (0–2)' },
    ],
  },
  {
    label: 'Alerts',
    dot: 'danger',
    items: [
      { method: 'GET', path: '/alerts', desc: 'List your alert rules' },
      { method: 'POST', path: '/alerts', desc: 'daily_spend · error_rate · latency' },
      { method: 'DELETE', path: '/alerts/{alert_id}', desc: 'Delete an alert rule' },
    ],
  },
{
    label: 'Planning & pricing',
    dot: 'cool',
    items: [
      { method: 'GET', path: '/catalog', desc: 'Live per-model prices for the savings picker' },
      { method: 'GET', path: '/tiers', desc: 'The tier ladder as /route actually resolves it' },
      { method: 'POST', path: '/project', desc: 'Project monthly cost + savings for your workload' },
      { method: 'GET', path: '/news/headlines', desc: 'Live headlines for the demo suggestion chip' },
    ],
  },
  {
    label: 'System',
    dot: 'muted',
    items: [
      { method: 'GET', path: '/pricing', desc: 'All model pricing' },
      { method: 'GET', path: '/providers', desc: 'Supported providers' },
      { method: 'GET', path: '/config', desc: 'Current BYOM config' },
      { method: 'POST', path: '/config', desc: 'Save BYOM config' },
      { method: 'DELETE', path: '/config', desc: 'Reset BYOM to defaults' },
      { method: 'GET', path: '/health', desc: 'Health check (no auth)' },
      { method: 'GET', path: '/metrics', desc: 'Prometheus metrics (no auth)' },
    ],
  },
]

const ENDPOINT_COUNT = ENDPOINT_GROUPS.reduce((n, g) => n + g.items.length, 0)

function CopyCurlButton({ method, path }) {
  const [copied, copy] = useCopy()
  return (
    <button
      onClick={() =>
        copy(
          `curl -X ${method} ${API_BASE}${path} \\\n  -H "Authorization: Bearer <your-key>"`
        )
      }
      className="font-mono text-[10px] px-2 py-0.5 rounded-full border transition shrink-0"
      style={
        copied
          ? { borderColor: tint('cool', 40), background: tint('cool', 12), color: 'var(--color-cool)' }
          : undefined
      }
    >
      {copied ? 'copied' : 'curl'}
    </button>
  )
}

function ApiReference() {
  const [copied, copy] = useCopy()
  const everything = ENDPOINT_GROUPS.flatMap((g) =>
    g.items.map((e) => `curl -X ${e.method} ${API_BASE}${e.path} \\\n  -H "Authorization: Bearer <your-key>"`)
  ).join('\n\n')

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-end">
        <button
          onClick={() => copy(everything)}
          className="font-mono text-[10px] px-3 py-1.5 rounded-full border transition"
          style={
            copied
              ? { borderColor: tint('cool', 40), background: tint('cool', 12), color: 'var(--color-cool)' }
              : undefined
          }
        >
          {copied ? `copied all ${ENDPOINT_COUNT}` : 'copy all as curl'}
        </button>
      </div>
      {ENDPOINT_GROUPS.map((group) => (
        <div key={group.label}>
          <h3 className="font-mono text-[10px] text-muted uppercase tracking-wide mb-3 flex items-center gap-2">
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: `var(--color-${group.dot === 'muted' ? 'muted' : group.dot})` }}
            />
            {group.label}
            <span className="font-mono text-[9px] text-muted opacity-50 ml-1">({group.items.length})</span>
          </h3>
          <div className="space-y-2">
            {group.items.map((ep) => (
              <div
                key={`${ep.method}-${ep.path}`}
                className="flex flex-wrap sm:flex-nowrap items-center gap-3 py-3 px-4 bg-surface rounded-xl border border-line shadow-card hover:shadow-card-hover hover:-translate-y-0.5 transition-all duration-200"
              >
                <EndpointBadge method={ep.method} path={ep.path} />
                <span className="flex-1 min-w-[12rem] font-body text-xs text-muted">{ep.desc}</span>
                <CopyCurlButton method={ep.method} path={ep.path} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/* ============================== page ============================== */

export default function GuidePage() {
  const [activeTab, setActiveTab] = useState(() => {
    const hash = window.location.hash.replace('#', '')
    return TABS.some((t) => t.id === hash) ? hash : 'quickstart'
  })
  const [query, setQuery] = useState('')
  const [audience, setAudience] = useState(null)
  const [showApiRef, setShowApiRef] = useState(true)
  const searchRef = useRef(null)

  const current = EXAMPLES[activeTab]
  const tabIndex = TABS.findIndex((t) => t.id === activeTab)

  useEffect(() => {
    const onHash = () => {
      const hash = window.location.hash.replace('#', '')
      if (TABS.some((t) => t.id === hash)) setActiveTab(hash)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    function onKey(e) {
      if (e.key === '/' && document.activeElement !== searchRef.current) {
        e.preventDefault()
        searchRef.current?.focus()
      }
      if (e.key === 'Escape' && document.activeElement === searchRef.current) {
        setQuery('')
        searchRef.current?.blur()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function switchTo(tab, opts = {}) {
    setActiveTab(tab)
    setAudience(opts.audience ?? null)
    if (!opts.silent) {
      window.history.replaceState(null, '', `#${tab}`)
      document.getElementById('guide-tabs')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  const searchHits = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (q.length < 2) return []
    const hits = []
    for (const [tabId, ex] of Object.entries(EXAMPLES)) {
      if (ex.title.toLowerCase().includes(q) || ex.description.toLowerCase().includes(q)) {
        hits.push({ tabId, label: ex.title, where: 'overview' })
      }
      for (const s of ex.sections) {
        const hay = [s.label, s.title, s.body, s.code].filter(Boolean).join(' ').toLowerCase()
        if (hay.includes(q)) hits.push({ tabId, label: s.label, where: ex.title })
      }
    }
    return hits.slice(0, 12)
  }, [query])

  return (
    <div className="relative max-w-5xl mx-auto px-6 py-20">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 dot-grid opacity-30 [mask-image:radial-gradient(ellipse_70%_40%_at_50%_0%,black,transparent)]"
      />

      {/* Hero */}
      <p className="font-mono text-xs text-signal tracking-wide uppercase mb-4">Documentation</p>
      <h1 className="font-display text-3xl font-semibold mb-2">Developer Guide</h1>
      <p className="text-muted text-sm mb-6 max-w-2xl">
        Integration recipes, the full request pipeline, and the exact policy rules — via the Python
        SDK, the terminal CLI, the OpenAI-compatible endpoint, or the REST API directly.
      </p>

      <div className="flex flex-wrap items-center gap-3 mb-8">
        <div className="relative flex-1 min-w-[16rem] max-w-md">
          <input
            ref={searchRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search the guide…  (press / )"
            aria-label="Search the guide"
            className="w-full bg-surface border border-line rounded-full pl-4 pr-10 py-2.5 text-xs font-mono text-primary placeholder:text-muted placeholder-opacity-60 focus:border-signal focus:outline-none transition"
          />
          {query ? (
            <button
              onClick={() => { setQuery(''); searchRef.current?.focus() }}
              aria-label="Clear search"
              className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] text-muted hover:text-danger"
            >
              clear
            </button>
          ) : (
            <kbd className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] text-muted opacity-60 border border-line rounded px-1.5 py-0.5">
              /
            </kbd>
          )}
        </div>
        <span className="font-mono text-[10px] text-muted opacity-70">
          {ENDPOINT_COUNT} endpoints · 13 tabs · 6 paths
        </span>
      </div>

      {query.trim().length >= 2 && (
        <div className="mb-8 rounded-2xl border border-line bg-surface shadow-card overflow-hidden">
          <div className="px-4 py-2.5 bg-panel border-b border-line flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-cool" />
            <span className="font-mono text-[10px] uppercase tracking-wide text-muted">
              {searchHits.length} result{searchHits.length === 1 ? '' : 's'} for “{query.trim()}”
            </span>
          </div>
          {searchHits.length === 0 ? (
            <p className="px-4 py-6 text-xs text-muted font-mono text-center">
              nothing matched — try “kate”, “cache”, “alert”, or “threshold”
            </p>
          ) : (
            <div className="divide-y divide-line">
              {searchHits.map((hit, i) => (
                <button
                  key={`${hit.tabId}-${hit.label}-${i}`}
                  onClick={() => { switchTo(hit.tabId); setQuery('') }}
                  className="w-full text-left px-4 py-2.5 flex items-center gap-3 hover:bg-panel transition"
                >
                  <span className="font-mono text-[10px] text-signal shrink-0">{hit.label}</span>
                  <span className="font-mono text-[9px] text-muted opacity-60 truncate">{hit.where}</span>
                  <span className="ml-auto font-mono text-[10px] text-muted opacity-60">→</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Pick your path */}
      <div className="mb-8">
        <p className="font-mono text-[10px] text-muted uppercase tracking-wide mb-3 flex items-center gap-2">
          <span className="w-1 h-1 rounded-full bg-cool" />
          Pick your path
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {AUDIENCES.map((a) => {
            const on = audience === a.id
            const accent = a.accent || 'signal'
            return (
              <button
                key={a.id}
                onClick={() => switchTo(a.tab, { audience: a.id })}
                className="group relative text-left rounded-xl border bg-surface p-4 shadow-card transition-all duration-200 hover:-translate-y-0.5"
                style={{
                  borderColor: on ? `var(--color-${accent})` : undefined,
                  background: on ? tint(accent, 6) : undefined,
                }}
              >
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: `var(--color-${accent})` }} />
                  <span className="text-sm font-semibold text-primary">{a.title}</span>
                  {a.badge && (
                    <span
                      className="font-mono text-[8px] uppercase px-1.5 py-px rounded-full"
                      style={{ background: tint(accent, 18), color: `var(--color-${accent})` }}
                    >
                      {a.badge}
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted leading-relaxed mb-3">{a.desc}</p>
                <span className="font-mono text-[10px]" style={{ color: `var(--color-${accent})` }}>
                  Start here →
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Tabs */}
      <div id="guide-tabs" className="sticky top-16 z-20 -mx-6 px-6 py-3 mb-8 bg-[color-mix(in_srgb,var(--color-base)_88%,transparent)] backdrop-blur border-y border-line scroll-mt-16">
        <PillTabBar tabs={TABS} active={activeTab} onSelect={(id) => switchTo(id, { silent: true })} />
      </div>

      {/* Content */}
      <div key={activeTab} className="space-y-6 animate-[page-fade-in_0.2s_ease-out]">
        <div>
          <h2 className="font-display text-xl font-semibold mb-1">{current.title}</h2>
          <p className="text-muted text-sm">{current.description}</p>
        </div>

        <div className="space-y-4">
          {current.sections.map((section) => (
            <SectionBlock key={section.label} section={section} />
          ))}
        </div>

        {/* prev / next */}
        <div className="flex items-center justify-between gap-3 pt-6 border-t border-line">
          {tabIndex > 0 ? (
            <button
              onClick={() => switchTo(TABS[tabIndex - 1].id, { silent: true })}
              className="font-mono text-[11px] text-muted hover:text-signal transition px-3 py-2 rounded-full border border-line hover:border-signal"
            >
              ← {TABS[tabIndex - 1].label}
            </button>
          ) : (
            <span />
          )}
          {tabIndex < TABS.length - 1 && (
            <button
              onClick={() => switchTo(TABS[tabIndex + 1].id, { silent: true })}
              className="font-mono text-[11px] text-muted hover:text-signal transition px-3 py-2 rounded-full border border-line hover:border-signal"
            >
              {TABS[tabIndex + 1].label} →
            </button>
          )}
        </div>
      </div>

      {/* API Reference */}
      <div className="mt-16 border-t border-line pt-10">
        <button
          onClick={() => setShowApiRef((v) => !v)}
          className="w-full flex items-center justify-between flex-wrap gap-2 mb-6 text-left"
        >
          <span className="flex items-center gap-3">
            <span
              className="w-1.5 h-1.5 rounded-full transition-transform"
              style={{
                background: 'var(--color-signal)',
                transform: showApiRef ? 'rotate(90deg)' : 'none',
              }}
            />
            <h2 className="font-display text-xl font-semibold">API Reference</h2>
          </span>
          <span className="font-mono text-[9px] uppercase tracking-wide text-muted px-2.5 py-1 rounded-full border border-line">
            {ENDPOINT_COUNT} endpoints · Bearer auth
          </span>
        </button>
        {showApiRef && (
          <>
<p className="text-muted text-sm mb-6">
              All {ENDPOINT_COUNT} non-admin endpoints. Anything touching routing, logs,
              analytics, keys, alerts or settings requires{' '}
              <code className="font-mono text-[10px] bg-panel px-1 py-0.5 rounded">
                Authorization: Bearer &lt;key&gt;
              </code>
              . Unauthenticated: <code className="font-mono text-[10px] bg-panel px-1 py-0.5 rounded">/health</code>,{' '}
              <code className="font-mono text-[10px] bg-panel px-1 py-0.5 rounded">/metrics</code>,{' '}
              <code className="font-mono text-[10px] bg-panel px-1 py-0.5 rounded">/pricing</code>,{' '}
              <code className="font-mono text-[10px] bg-panel px-1 py-0.5 rounded">/providers</code>,{' '}
              <code className="font-mono text-[10px] bg-panel px-1 py-0.5 rounded">GET /config</code>,{' '}
              <code className="font-mono text-[10px] bg-panel px-1 py-0.5 rounded">/evaluate</code> and the
              planning group. Admin (<code className="font-mono text-[10px]">/admin/*</code>) and demo (
              <code className="font-mono text-[10px]">/demo/*</code>) routes are excluded.
            </p>
            <ApiReference />
          </>
        )}
      </div>

      {/* Closing CTA */}
      <div className="relative mt-16 rounded-2xl border border-line bg-surface overflow-hidden shadow-card">
        <div aria-hidden className="pointer-events-none absolute inset-0">
          <div className="absolute -top-20 -left-16 w-64 h-64 rounded-full blur-3xl" style={{ background: tint('cool', 10) }} />
          <div className="absolute -bottom-24 -right-16 w-64 h-64 rounded-full blur-3xl" style={{ background: tint('signal', 10) }} />
        </div>
        <div className="relative px-8 py-10 text-center">
          <p className="font-mono text-[10px] text-signal uppercase tracking-wide mb-3">Ready when you are</p>
          <h2 className="font-display text-2xl font-semibold mb-2">Start routing in 30 seconds</h2>
          <p className="text-sm text-muted mb-7 max-w-md mx-auto">
            Grab your API key and send your first query — the router picks the cheapest tier that
            gets it right.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              to="/get-started"
              className="bg-signal text-white font-semibold text-sm px-7 py-3 rounded-full shadow-card hover:brightness-110 transition"
            >
              Get your API key
            </Link>
            <Link
              to="/policies"
              className="font-mono text-sm text-muted border border-line px-7 py-3 rounded-full hover:text-primary hover:shadow-card transition"
            >
              Compare policies
            </Link>
            <Link
              to="/"
              className="font-mono text-sm text-muted border border-line px-7 py-3 rounded-full hover:text-primary hover:shadow-card transition"
            >
              ← Back to live demo
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}