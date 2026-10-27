# ADR 003 - Route on a continuous difficulty score, with prices that ascend

- **Status:** accepted
- **Date:** 2026-10-27
- **Code:** `backend/src/predict_difficulty.py`, `backend/router/config.py`,
  `backend/router/support_policy.py`, `frontend/src/productMetrics.js`

## Context

The product claim is "answer easy questions cheaply and hard questions well".
That needs two things that are easy to get wrong:

1. A way to decide *before* answering how hard a question is.
2. A guarantee that "cheaper" really is cheaper.

The second one was broken at some point in the project's history. `deepseek-chat`
sat in the `cheap` tier at $0.28/$1.10 per million tokens while `gpt-oss-120b`
sat in `frontier` at $0.15/$0.60. Every "downgrade" to cheap cost 1.84x more
than staying on frontier, so the savings percentages on the site inverted the
moment a user pushed the slider down.

## Decision

**A continuous score, then thresholds.** A lightweight difficulty model
(embeddings + LightGBM/logistic head) scores each query 0-10. Two thresholds on
that score pick the tier:

```
cheap_ceil     = 4.5    # balanced default
frontier_floor = 6.0
score <= cheap_ceil        -> cheap
score >= frontier_floor    -> frontier
otherwise                  -> mid
```

The thresholds move with the user's sensitivity slider (`margin` 0.0 / 1.0 /
2.0 for economy / balanced / quality), each step shifting both boundaries by
0.75 points:

| Mode | cheap_ceil | frontier_floor |
|---|---|---|
| economy | 5.25 | 6.75 |
| balanced | 4.50 | 6.00 |
| quality | 3.75 | 5.25 |

The returned thresholds are sent with every routing decision, so the frontend
diagram draws tick marks at the same numbers the backend used instead of
recomputing them and drifting.

**Prices must ascend.** `cheap < mid < frontier` is an invariant asserted by
the config comments and by a test, not a coincidence. At the 1,000-in / 300-out
assumption used by the backend's cost model:

| Tier | Model | $/M in | $/M out | Cost / request | Multiple |
|---|---|---|---|---|---|
| cheap | `openai/gpt-oss-20b` (Groq) | 0.075 | 0.30 | $0.000165 | 1.0x |
| mid | `openai/gpt-oss-120b` (Groq) | 0.15 | 0.60 | $0.000330 | 2.0x |
| frontier | `deepseek/deepseek-chat` (OpenRouter) | 0.27 | 1.10 | $0.000600 | 3.6x |

Any routing decision is therefore monotone in cost: moving down the ladder can
only save money.

**Two routing modes on top.** The score thresholds are shared, but the support
policies (`emma`, `lisa`, `kate` in `support_policy.py`) reinterpret the middle
band, which is why `/evaluate` reports a tier per policy rather than one answer.

## Consequences

- A single number decides quality and cost, so a mis-scored query is a
  mis-priced query. Calibration is therefore a first-class metric, not a nice
  to have: `GET /stats/reliability` compares the predicted score against the
  independent LLM-as-labeler score and reports MAE, expected calibration error,
  and the share of requests landing within 0.25 of a boundary.
- Boundary traffic is inherently a coin flip. A query scored 4.49 and one
  scored 4.51 get different models and a 2x cost difference for no semantic
  reason. The `borderline_share` number exists to make that visible instead of
  hiding it.
- Cost figures are only comparable at a fixed token assumption. The site quotes
  everything at 1,000 in / 300 out; real traffic has a different mix, which is
  why `/stats` reports measured cost rather than the projected figure.
- Quality after routing is unverified. Cheap is chosen because a query *looks*
  easy, not because the answer turned out to be good. Follow-up:
  verify-then-escalate, using the existing judge.

## Alternatives rejected

- **Route on provider price alone.** Ignores difficulty entirely; that is a
  price floor, not a router, and it cannot justify a `frontier` tier at all.
- **Always answer with the cheapest model.** Maximises savings and destroys the
  quality claim on exactly the queries the product is supposed to handle well.
- **Run an LLM judge on every request before answering.** Doubles latency and
  spend on every call, including the cheap ones, which deletes the savings the
  router exists to produce. Judging after the fact on a sample is affordable
  and is what the project does.
