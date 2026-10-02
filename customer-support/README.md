# Customer-Support Routing — Integration Guide

Route your support traffic through RouteWise's support policies: **lisa** (3-tier)
and **kate** (2-tier). Plain numbers, no marketing. Last updated 2026-10-02.

> If you are integrating rather than evaluating, you only need the first four
> sections. The model forensics start at [Model forensics](#model-forensics).

---

## TL;DR

- Keep your chatbot, your memory, and your UX. Swap only the model call.
- Default to **`kate`**. It has the safer cut for support traffic.
- **You must send the full conversation every turn.** RouteWise stores nothing.
- **Turn the cache off on follow-ups.** See
  [You own the memory](#2-you-own-the-memory-and-the-cache).

---

## 1. The integration

Point the OpenAI SDK at RouteWise and send your existing message list. Nothing
else about your bot changes.

```python
from openai import OpenAI

router = OpenAI(api_key="rw_...", base_url="https://llm-router-…onrender.com")

def ask_router(turns):                 # turns = the list your bot already builds
    resp = router.chat.completions.create(model="kate", messages=turns)
    return resp.choices[0].message.content

answer = ask_router([
    {"role": "user",      "content": "my app keeps crashing when I sync"},
    {"role": "assistant", "content": "Sorry about that — can you send the error code?"},
    {"role": "user",      "content": "it says 500 every time"},
])

print(answer)
print(resp.headers.get("x-routewise-tier"))   # cheap | mid | frontier
print(resp.headers.get("x-routewise-cost"))   # USD actually spent
```

That is the whole change. Your prompt, your retrieval, your handoff logic, your
conversation store — all untouched.

### Prefer `/route` for a real conversation

`/v1/chat/completions` has no per-request `bypass_cache` flag. `/route` does, and
it also returns `request_log_id` so you can attach thumbs up/down feedback to the
exact turn.

```python
import requests

BASE = "https://llm-router-…onrender.com"
HEADERS = {"Authorization": "Bearer rw_..."}

def route_turn(turns):
    r = requests.post(f"{BASE}/route", headers={**HEADERS, "Content-Type": "application/json"}, json={
        "query":        turns[-1]["content"],   # newest message drives the score
        "messages":     turns,                   # full context — this is what fixes follow-ups
        "support_mode": "2tier",                 # kate  ("3tier" = lisa, omit = emma)
        "bypass_cache": len(turns) > 1,          # never serve a stored answer to a follow-up
    }, timeout=30)
    r.raise_for_status()
    d = r.json()
    return {
        "reply":      d["response"],
        "tier":       d["routed_to"],
        "difficulty": d["difficulty_score"],
        "cost_usd":   d["cost_usd"],
        "log_id":     d["request_log_id"],
    }
```

---

## 2. You own the memory and the cache

**RouteWise is stateless.** It stores no sessions, holds no conversation memory,
and never reads your history back. It scores the newest message to choose a
model, then forwards whatever `messages` array you gave it.

So if you send only the latest turn, a follow-up gets judged with no context:

| message sent | scored alone | scored with context | routed |
|---|---|---|---|
| `"now draw it in python"` | 1.61 | 6.86 | cheap → **frontier** |

RouteWise scores the last 4 turns as context too and keeps whichever score is
higher, so a follow-up can only ever escalate. **But it can only do that if you
send the history.** Sending one message means paying cheap-tier prices for a
hard question.

```python
# wrong — no context reaches the scorer
client.chat.completions.create(model="kate", messages=[{"role":"user","content":"now draw it in python"}])

# right
client.chat.completions.create(model="kate", messages=[*full_turn_history, {"role":"user","content":"now draw it in python"}])
```

### The cache does not know which conversation it belongs to

The semantic cache matches on the **newest message only**, scoped to your API
key, at 0.95 cosine similarity. On a hit it returns the stored answer verbatim —
no model call, no history replayed.

A follow-up like `"yes"` or `"draw it"` sits very close to someone else's `"yes"`
or `"draw it"` from a completely different conversation, and a hit will serve
that unrelated answer.

**Bypass the cache on every turn after the first.** `bypass_cache` is supported on
`/route` and `/route/stream`; it is not available on the OpenAI-compatible
endpoint.

---

## 3. kate or lisa?

Both policies run the **same regressors** on the **same 17,600 tickets**. They
produce identical scores and differ only in how a score is cut into tiers.

| | **kate** (2-tier) | **lisa** (3-tier) |
|---|---|---|
| cheap when | score ≤ 4.0 | score ≤ 2.0 |
| mid | *no mid band* | 2.0 < score < 4.5 |
| frontier when | anything above 4.0 | score ≥ 4.5 |
| frontier recall | **86.0%** | 80.4% |
| frontier escape | **14.0%** | 19.6% |
| traffic (cheap/mid/frontier) | 66 / 0 / 34 | 46 / 24 / 29 |

**"Frontier escape"** is the share of genuinely-hard tickets the policy would
have downgraded to a cheaper tier. Lower is safer.

Choose **kate** when a wrong answer costs more than the extra spend — a bot that
answers "I can't log in" with the cheap model is a bad experience, and kate's 4.0
cut keeps far more of those on a capable tier.

Choose **lisa** only if mid-tier answers are genuinely good enough for your
product and you want the cheaper mix. Dropping the mid band is not free: it costs
5 more points of traffic on the expensive tier.

Use **emma** (the default, no `support_mode`) for anything that is not a support
ticket — see the domain warning below.

---

## 4. Before you ship

### Measure it on your own traffic

```python
# replay your last 500 logged scores through each policy's own rule
stats = requests.get(f"{BASE}/policy-analytics", headers=HEADERS).json()
for m in stats["models"]:
    if m["available"]:
        print(m["id"], m["traffic"], f"{m['savings_pct']}% saved")

for log in requests.get(f"{BASE}/logs?limit=20", headers=HEADERS).json():
    print(f"{log['tier']:9s} score={log['difficulty_score']:.2f}  {log['query'][:60]}")
```

### Four things to know before a paying customer does

- **The score is length-sensitive.** `"Prove the halting problem is undecidable"`
  scores 3.60 and routes cheap; the same question spelled out at length scores
  8.35 and routes frontier. Short-but-hard tickets can be under-routed. If your
  tickets are terse, prefer kate, and read `/logs` weekly.

- **The models are domain-specific.** They were trained on support tickets across
  `account_access`, `orders_billing`, `technical` and `delivery_general`. Point
  kate at a general or coding question and it will under-route, because that is
  out of distribution. Use emma for anything that is not a support ticket.

- **Short conversational turns land in mid under lisa.** `"thanks, that fixed it!"`
  scores 2.17 against a 2.0 cut, so lisa routes a no-op acknowledgment to the mid
  tier. Harmless, but do not read it as a bug.

- **The top of the scale compresses.** On the hardest tickets (gold 8–9) the model
  under-predicts, typically 5.6–7.1. Score 9–10 is 18 rows out of 17,600, so the
  top band is effectively unevidenced and is not claimed.

### Recommended rollout

1. Put kate behind **one** support surface — the one with the most measurable
   user feedback.
2. Enable the `daily_spend` alert the same day you enable routing.
3. Read `/logs` every few days for a fortnight. Look for
   `cheap` + a `difficulty_score` above the policy's cheap cut: that is the
   under-routing signature.
4. Widen to the rest of the traffic once the numbers look boring.

---

---

# Model forensics

Everything below is evaluation evidence. It is not needed to integrate.

## What the models are

A difficulty regressor for **customer-support mode only**, separate from the
generic router, loaded only when a request carries `support_mode`. It never
scores coding, writing, or general reasoning queries.

Both shipped policies use MiniLM-L6-v2 (384-dim) + 4 handcrafted features +
4 domain indicators = 392, then an ensemble of three LightGBM regressors
(seeds 18, 19, 20), predictions averaged and clipped to 0–10.

Support mode is opt-in and additive. The live RouteWise router is the default and
its behavior is unchanged; a request only touches these models if it carries
`support_mode`.

```
POST /route            {"query": "...", "support_mode": "2tier"}   # or "3tier"
GET  /route/policies                                          # what is servable
```

```python
from predict_difficulty import get_embedder
import feature_builder as fb

policy = fb.load_policy("2tier")                    # validates the manifest
embed  = get_embedder().encode([query])             # shared, already resident
X      = fb.build_support_features(embed, [query], [fb.classify_domain(query)])
score  = float(policy.predict(X)[0])
tier   = policy.tier_for(score)                     # rule comes from the artifact
```

Each request runs the embedder **once** and makes **one** LLM call, exactly as
the generic path does. Selecting a policy adds no model call and no latency.

Two guards worth knowing about:

- `load_policy()` validates `feature_count`, `feature_order`, `domain_order`
  and `tier_rule` against the builder. A mismatch between a retrained artifact
  and the inference code raises at load time rather than silently mis-scoring.
- The domain one-hot is derived from query text with a deterministic keyword
  vote (`classify_domain`), because the public request carries no domain
  field. It falls back to `delivery_general` rather than emitting an all-zero
  block the regressors never saw in training.

## Training data: 17,600 rows

All 17,600 are `(support query, difficulty score 0-10)` pairs, every score
labeled by Claude using the support-specific rubric. No other labeler
contributed to the training set.

| source | rows | what it is |
|---|---|---|
| DS3 (Tobi Bueck) | 9,229 | real enterprise support tickets, actual customer emails |
| DS2 (Bitext) | 8,371 | synthetic customer-support Q/A pairs |

| category | rows |
|---|---|
| technical | 5,817 |
| orders & billing | 4,941 |
| delivery & general | 4,750 |
| account access | 2,092 |

The 238 generated batches were shuffled across all four categories, so no
category is over-represented within a batch. The labeled set is deduplicated:
51,838 raw rows → 50,063 after category mapping → 47,599 after
exact-normalized dedup → 17,600 currently labeled (90 of 238 batches done).
The remaining 148 batches are deliberately unfinished, not failed.

## Model selection

Two shipped policies, both sharing one regressor. Same architecture, same
training rows, same seeds — the only difference between them is how a score
maps to a tier. That isolates the tier policy as the thing being compared.

| artifact | tiers | tier rule | training rows |
|---|---|---|---|
| `support_final_3tier.joblib` | 3 | `tier3_two_cuts` — cheap ≤ 2.0, mid, frontier ≥ 4.5 | 17,600 |
| `support_final_2tier.joblib` | 2 | `tier2_single_cut` — cheap ≤ 4.0, else frontier | 17,600 |

Regressor in both: 3 × LightGBM, `regression_l1`, 1,200 trees, lr 0.02,
seeds 18/19/20, 392 features (MiniLM 384 + 4 handcrafted + 4 domain).

Ensemble size barely mattered — 2, 3, and 4 seeds scored within noise. L1 beat
L2 clearly. Adding the domain block changed MAE by ~0.003, so it is kept for
schema consistency rather than accuracy.

### Honest metrics — mean of 3 independent batch-level splits

Seeds 42 / 7 / 2024, each 62/13/13 of the 88 batches. **Quote the mean and the
worst split, never a single split.** Seed 42 alone is flattering by ~0.14 MAE.

| | 3-tier | 2-tier |
|---|---|---|
| MAE (mean) | 0.822 | 0.822 |
| MAE (worst split) | 0.919 | 0.919 |
| Spearman | 0.786 | 0.786 |
| cheap recall | 79.9% | 87.7% |
| mid recall | 70.9% | n/a |
| frontier recall | 80.4% | **86.0%** |
| frontier escape rate | 19.6% | **14.0%** |
| traffic | 46 / 24 / 29 | 66 / 0 / 34 |

2-tier is not simply "3-tier with the middle removed." Dropping the mid band
pushes borderline tickets onto the frontier model, which **raises** frontier
recall by 5.6 points and cuts escapes by a quarter. The cost is 5 more points of
traffic on the expensive tier. Same MAE, because the regressor is identical —
MAE measures the score, not the routing.

Balanced accuracy is **not** comparable across the two: 2-tier averages two
tiers, 3-tier averages three. Frontier recall, escape rate, cheap recall and
traffic are computed on the same gold rows and do compare directly.

## How the evaluation split works

The 17,600 labeled rows were split **by batch, not by row**, because
near-duplicate tickets survive exact-normalized dedup and a random row split
lets siblings leak across the boundary. Batches are the unit.

Each of the 3 evaluation splits holds out 13 batches (2,600 rows) for testing.
The shipped artifacts are then retrained on all 17,600. Fit-set MAE for the
shipped models is ~0.627 — that is memorization, not quality, and is not
reportable as an accuracy claim.

## Thresholds

Support models have their own cuts. They are **not** the generic 4.5 / 6.0,
which were tuned on general-purpose labels.

- 3-tier: cheap ≤ 2.0, mid 2.0–4.5, frontier ≥ 4.5
- 2-tier: cheap ≤ 4.0, frontier above it

The 3-tier frontier floor was chosen by measurement, not preference. Moving it
4.5 → 5.0 costs 7.9 points of frontier recall (80.4% → 72.5%) and 80 more
escapes, to move 4.2 points of traffic. 4.5 is the safer default.

The 2-tier model was originally mislabelled: `tier3` was used to score it, so
the dead (4.0, 4.5) band routed to a `mid` tier that a 2-tier artifact is not
supposed to have. Those tickets were going to a middle model instead of the
frontier one, which is why fixing it improved frontier recall. `two_tier_model.py`
now asserts 0% mid traffic before writing, and both artifacts carry an explicit
`tier_rule` so the loader never has to infer it from `n_tiers`.

## Known weakness: the top of the scale compresses

On the hardest support tickets (gold 8–9: data-breach escalations, service
outages, security incidents) the model under-predicts, typically 5.6–7.1
against a gold of 8–9. This compression is in the model, not the thresholds.

Score 9–10 is very sparse — 18 rows in 17,600 — so the top band is effectively
unevidenced and should not be claimed. Any UI threshold slider should cap the
frontier floor at 8 for the same reason.

## Ceiling on accuracy

Label noise sets the floor. An independent second labeler disagreed with
Claude on 68% of a 1,000-ticket overlap sample, with a mean absolute
difference of 1.34 points. On that evidence, MAE below roughly 1.0 is not
attainable on this data and is not a target. The reported 0.822 mean MAE is
partly a measure of agreement with one labeler's specific judgments.

## Data provenance and honesty notes

- The 4 domain splits (`account_access`, `orders_billing`, `technical`,
  `delivery_general`) were built and saved. A one-model-versus-four-model
  comparison was considered and not run. The shipped model is a single model
  over all four categories.
- Human agent priority exists in the DS3 source but was found to have a
  correlation of 0.091 with Claude's difficulty score. It is **not** used as
  validation for difficulty, and no claim should rest on it.
- Datasets rejected for this use, and why:
  - DS1 — 100% unfilled placeholders and gibberish resolutions
  - DS4 — post-resolution CSAT comments, far too short to score difficulty
  - DS5 — same upstream source as DS3, so including it would double-count

## Files

Paths are relative to `D:\llm-router-cs-upgrade\` (outside the git repo, so no
data is versioned).

| path | what |
|---|---|
`labeled_support.csv` | 17,600 merged labels with domain, source, batch, serial |
`merge_report.txt` | validation log and score distribution per merge run |
`support_eval_report.md` | full evaluation output, per-tier recall, hardest tickets |
`models\support_final_3tier.joblib` | shipped 3-tier policy (cuts 2.0 / 4.5) |
`models\support_final_2tier.joblib` | shipped 2-tier policy (cut 4.0, single rule) |
`models\support_all.joblib`, `support_ds3.joblib`, `support_final.joblib` | earlier candidates, superseded, kept as evidence |
`routing\feature_builder.py` | shared 392-feature builder + policy loader |
`claude_batches\` | 238 prompt batches, 200 tickets each |
`claude_replies\` | 90 Claude reply files |

Scripts live in the repo under `customer-support\scripts\` and are the only
trackable part:

| script | what |
|---|---|
`merge_support_labels.py` | validates reply files against `row_index.csv`, merges to CSV |
`build_domain_splits.py` | maps DS2/DS3 into the four categories |
`make_support_batches.py` | builds the 238 Claude batches with the rubric |
`extract_ds3_english.py` | extracts + deduplicates the English DS3 tickets |
`fetch_ds2_bitext.py` | reproducible DS2 download |
`eval_support_model.py` | batch-level split, calibration, metrics, report |

`train_support_models.py` is kept for the record but its headline comparison
was against generic-domain gold and is **not** the evaluation described here.
`eval_support_model.py` supersedes it.

## Known data gap

2 of the 90 reply files were rejected by the merge validator and need to be
re-run: `batch_225` returned 209 lines for 200 tickets, and `batch_238`
returned 199. 400 of 18,000 potential labels are therefore missing. The merge
script rejects rather than silently misaligning, so these are dropped cleanly
rather than corrupting the set.