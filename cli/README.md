<h1 align="center">🛣️ routewise — the terminal CLI</h1>

<p align="center">
  The <b>cost-aware LLM router</b> in your terminal.
  Every query gets scored for difficulty, then routed to the <b>cheapest model tier</b>
  that can handle it — with web search, semantic caching, and cross-provider failover
  handled automatically.
</p>

Zero runtime dependencies. Talks to the hosted RouteWise API (or your own backend).

```bash
npm install -g routewise
```

## Quick start

```bash
# route one query — answer on stdout, routing metadata on stderr
routewise ask "what is the capital of france"

# force a tier, or change routing sensitivity (0 economy · 1 balanced · 2 quality)
routewise ask "design a distributed rate limiter" --tier frontier
routewise ask "explain a linked list" --threshold 2

# stream tokens as they arrive
routewise stream "write a haiku about routing"

# pipe queries from a shell workflow
cat questions.txt | routewise ask --json

# interactive multi-turn chat
routewise chat

# see who you are + how much you've spent
routewise whoami

# end-to-end self-check (config, backend, providers, live ask)
routewise doctor

# score difficulty + see what each routing mode picks (no key needed)
routewise evaluate "implement a red-black tree"
```

## Getting a key

```bash
# opens the dashboard + saves your key (paste is hidden, never in shell history)
routewise login
# or, non-interactive:
routewise login rw_your-key
```

## What you get per call

```bash
$ routewise ask "what is the capital of france"
Paris
[cheap score=3.11 $0.00008 · 812ms]        # <- stderr, so stdout stays pipeable
```

Metadata on **stderr** keeps stdout clean for `grep`, pipelines, and `> file`.
Add `--json` for the full structured response (tier, score, cost, latency,
cache hit, model, route reason, request log id):

```bash
$ routewise ask "convert 5 miles to km" --json
{
  "response": "5 miles is approximately 8.05 kilometers.",
  "routed_to": "cheap",
  "cache_hit": true,
  "cost_usd": 0,
  ...
}
```

## Commands

| Command | What it does |
|---|---|
| `routewise ask "<q>"` | Route one query. Flags: `--tier`, `--threshold`, `--bypass-cache`, `--no-byom`, `--json`, `--quiet`, `--stream` |
| `routewise stream "<q>"` | Stream tokens as they arrive |
| `routewise chat` | Multi-turn REPL. `/tier cheap`, `/json on`, `/reset`, `/exit` |
| `routewise stats` | Usage, cost, savings, cache rate, tier split |
| `routewise logs [--limit N]` | Recent request log lines |
| `routewise log <id>` | Full detail (incl. response) for one log entry |
| `routewise analytics` | Cost analytics + per-day breakdown |
| `routewise compare` / `calibrate` | Threshold-vs-cost recommendations (JSON) |
| `routewise feedback <id> <up\|down> [reason]` | Submit thumbs up/down on an answer |
| `routewise pricing` | Model price list |
| `routewise providers` | Supported providers + models |
| `routewise byom` | Bring your own model — set/remove/list per-tier overrides |
| `routewise login` | Open the dashboard, save your API key (hidden paste) |
| `routewise whoami` | Identity + account usage snapshot (key valid?, spend, tiers) |
| `routewise doctor` | End-to-end self-check: config, backend, providers, live ask |
| `routewise evaluate "<q>"` | Difficulty score + routing per mode (public, no key) |
| `routewise config` | Show current config / save API key / set base URL |
| `routewise version` | Print version |

## Configuration

Settings are read in this order:

1. CLI flag: `--key <key>` / `--base-url <url>`
2. Environment: `ROUTEWISE_API_KEY`, `ROUTEWISE_BASE_URL` (or `ROUTEWISE_API_BASE`)
3. Config file: `~/.config/routewise/config.json` (⭐ `%APPDATA%\routewise\config.json` on Windows)

```bash
routewise config set rw_xxxxxxxx       # save your key
routewise config set-base https://your-backend.example.com
routewise config                        # view current effective config
routewise config unset key              # clear the saved key
```

## Bring your own model

Force a specific provider/model (and optionally **your own API key**) for a tier.
Set it once — it is saved locally and attached to every `ask`/`stream`
automatically. No re-entry per call. Keys are stored only in your local config
file and sent per-request; they are never stored on the RouteWise server.

```bash
# use openai/gpt-5 with your own key for tricky queries
routewise byom set frontier --provider openai --model gpt-5 --key sk-…

# pick a groq model but bill it through RouteWise's own server keys
routewise byom set cheap --provider groq --model openai/gpt-oss-20b

routewise byom list                   # view overrides (keys masked)
routewise byom remove frontier        # drop one tier
routewise byom remove --all           # drop everything
routewise ask "…" --no-byom           # one call without the overrides
```

Saved overrides are applied only when the server routes to that tier; if no
override is saved for a tier, it uses the router's defaults.

## Using it in scripts

Exit codes: `0` success, `1` on any error (auth, rate limit, all tiers failed, network).

| Shell | Pattern |
|---|---|
| Pipeline | `routewise ask "$Q" --json \| jq -r .response` |
| Loop | `for q in $(cat qs.txt); do routewise ask "$q" --quiet; done` |

The answer is written to stdout even for errors-free responses, so piping and
substitution behave the way any Unix tool would.

## Building from source

```bash
cd cli
npm install
npm run build        # tsc -> dist/src
npm test             # 35 unit tests, mock-fetch (no network)
node dist/src/cli.js --help
```

## Using the client as a library

The same HTTP client backs the CLI and is importable:

```ts
import { RouteWiseClient } from "routewise";

const client = new RouteWiseClient({ apiKey: "rw_…" });
const res = await client.ask({ query: "hello" });
console.log(res.routed_to, res.cost_usd);
```

## Notes

- Requires an API key (`rw_…`) created through the RouteWise dashboard or
  `scripts/create_api_key.py`. Unauthenticated endpoints like `pricing` and
  `providers` work without one.
- This CLI hits the hosted RouteWise API over HTTP — it does not run any
  model locally. For a fully offline path, run the backend + Ollama and point
  `routewise config set-base` at it.
- The MCP server (`routewise mcp`) that reuses this client for IDE integration
  is planned next.