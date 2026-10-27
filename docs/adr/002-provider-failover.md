# ADR 002 - Degrade the tier instead of failing the request

- **Status:** accepted
- **Date:** 2026-10-27
- **Code:** `backend/router/rate_limiter.py`, `backend/router/circuit_breaker.py`,
  `backend/router/load_balancer.py`, `backend/router/config.py`

## Context

A request is routed to one of three tiers (`cheap`, `mid`, `frontier`) backed by
different models, and mostly by different accounts or providers. Any of those
calls can fail, and the failures are not interchangeable:

| Failure | Retrying the same model | What actually helps |
|---|---|---|
| `429` rate limit | Useless - the provider says wait minutes | Another key, or another tier |
| Timeout / connection reset / `5xx` | Often works once | One quick retry, then another tier |
| `402` out of credit | Never | Another provider |
| Provider outage | Never | Another provider |

A user asking a question does not care which model answers; they care that
something answers. Returning a 500 because the frontier account is empty is a
worse product than returning a mid-tier answer that is flagged as such.

## Decision

Fail **down the price ladder**, then **across providers**, then give up:

1. Try the intended tier.
2. On failure, walk `FALLBACK_CHAIN`: `frontier -> mid -> cheap`, `mid -> cheap`.
3. If the whole chain fails, try Gemini once as an independent last resort.
4. Only then raise `AllTiersFailedError`.

Failure handling is split by kind, not by generic retry:

- **Rate limit** (`429` / `rate_limit` / `too many requests`): do not retry the
  same model. Mark the key as rate-limited in the load balancer so the next
  request picks a different key, and move to the next tier immediately.
- **Everything else:** retry the same tier exactly once after a 1 s pause.
  A second failure falls through the chain.
- **Circuit breaker per tier:** after repeated failures the tier is skipped
  entirely for a cooldown window instead of being probed on every request.
- **Streaming** uses the same chain but cannot retry in place - chunks already
  sent cannot be retracted - so it emits a `{"type": "failover"}` marker and
  continues with the next tier. The UI renders the chip the user sees.

Every response carries `intended_tier` and `fallback_used`, so a degraded
answer is never silently presented as the requested one.

## Consequences

- **This is what the reported "asked for frontier, got mid" incident was.** The
  OpenRouter account was out of credit (`402`), the chain did exactly what it
  was designed to do, and the answer was honestly labelled `fallback`. The
  correct fix was money, not code.
- The `402` case currently burns a full tier attempt before falling back.
  Follow-up: parse the affordable token count out of the 402 body and reissue
  the same call clamped to that budget, so a nearly-empty account still serves
  its top tier.
- Cost is bounded by the ladder: a degraded request can only ever be cheaper
  than the one that was asked for, never more expensive.
- Quality is not verified. A cheap answer to a genuinely hard question is
  marked as cheap, not as inadequate. Follow-up: verify-then-escalate.

## Alternatives rejected

- **Retry the same model on 429 with backoff.** Groq's own error tells the
  client to wait on the order of minutes. A live request cannot hold a
  connection that long, and the user has already paid the latency.
- **Fail fast and return 503.** Simple and honest, but it turns a provider
  outage into a product outage for no benefit. Degrading is strictly better
  when the fallback tiers are real models.
- **Round-robin across providers for every request.** This optimises for
  uptime and destroys the cost story: the whole product is "spend less by
  answering easy questions cheaply".
