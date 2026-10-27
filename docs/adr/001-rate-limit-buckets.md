# ADR 001 - Two rate-limit budgets, split by path

- **Status:** accepted
- **Date:** 2026-10-27
- **Code:** `backend/router/auth.py`, `backend/tests/test_auth.py`

## Context

Every authenticated endpoint used to share one sliding window of 20 requests
per minute, keyed on the API key.

That was wrong in two independent ways.

1. **Free traffic competed with paid traffic.** The dashboard polls `/stats`
   every 12-15 s (`LiveTicker`, `LiveStatsStrip`, `MetricsDashboard`) and calls
   `/route/explain` on a 450 ms debounce while the user types. None of those
   requests reach a provider, but all of them spent the same 20/min budget that
   `/route` needs. Two open browser tabs could exhaust the budget without a
   single genuine question being asked, and every real request then came back
   `429 Too Many Requests`.

2. **The bucket was global, not per user.** The public demo's key is compiled
   into the Vercel bundle, so every visitor presented the same key to the
   limiter. One visitor's polling degraded everyone else.

The failure mode was visible in the logs and reproducible: 19 successful
requests followed by 429s from a single idle dashboard.

## Decision

Split the limiter into two buckets, classified by request path:

- **read** - 240 req/min. Endpoints that never spend provider money:
  `/route/explain`, `/stats`, `/logs`, `/analytics`, `/policy-analytics`,
  `/calibrate`, `/compare`, `/config`, `/settings`, `/keys`, `/admin`,
  `/alerts`, `/catalog`, `/tiers`, `/pricing`, `/providers`, `/project`,
  `/evaluate`, `/demo/chaos`.
- **call** - 60 req/min. Everything else.

Classification is a **prefix test against an allowlist of cheap paths**
(`rate_limit_bucket(path)`), not a list of expensive ones. A route added later
is therefore treated as expensive until someone deliberately classifies it:
the default is the safe direction, because guessing "free" costs money and
guessing "costly" costs a retry.

The two budgets are independent: draining the read bucket cannot produce a 429
on `/route`, which is the actual bug that was reported.

Both windows are in-memory (`dict[(bucket, key)] -> timestamps`), pruned on
every check, and the tracking map is capped at 10,000 keys with stale entries
evicted, so a key-spraying client cannot grow memory without bound.

## Consequences

- The dashboard can poll as much as it likes (within 240/min) without ever
  starving a routing request.
- The 60/min call budget is still shared by all demo visitors, because they
  all present the same bundled key. The limit is now survivable rather than
  punishing, but it is not isolation. Follow-up: server-issued guest keys.
- `/evaluate` is in the read bucket even though it runs a local embedding plus
  a forward pass per query (up to 50 queries per call). It costs no provider
  money, so the classification matches the stated rule, but it does cost CPU:
  240 calls/min x 50 queries is far more local inference than the instance can
  absorb. Either move it to the call bucket or add a separate compute budget.
- In-memory state is per process. A second Render instance, or a restart, has
  its own counters. Documented in the README roadmap as "distributed rate
  limiting (Redis)"; not worth the cost and complexity for a single instance.
- Authenticated users on real accounts are limited by their own key, so the
  split mainly protects the shared demo. That is the intended audience.

## Alternatives rejected

- **Per-IP limiting.** The frontend calls the backend directly from the
  browser, so the only IP the server sees is the visitor's - good - but
  Render sits behind a proxy and IPs are shared by schools, offices and
  carriers, so one NAT would starve everyone behind it while a trivial
  header-spoofing client bypasses it. Key-based limiting is the honest unit
  here until guest keys exist.
- **A single higher limit.** Raising 20 to, say, 200 keeps the coupling: the
  polling still eats the routing budget, it just takes longer. The failure
  returns under any real demo traffic.
- **Endpoint-by-endpoint limits with no default.** Every new route silently
  inherits "unlimited" until someone remembers to add it. The allowlist
  inverts that failure.
