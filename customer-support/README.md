# Customer-Support Difficulty Model — Reference

Notes for the README. Plain numbers, no marketing. Last updated 2026-09-28.

## What this is

A difficulty regressor for **customer-support mode only**. It is a separate model
from the generic router, loaded only when a user selects the customer-support
option. It never scores coding, writing, or general reasoning queries.

Same architecture as the generic model: MiniLM-L6-v2 (384-dim) + 4 handcrafted
features = 388, then an ensemble of two LightGBM regressors. Two regressors,
seeds 18 and 19, predictions averaged and clipped to 0–10.

## Training data: 17,600 rows

All 17,600 are `(support query, difficulty score 0-10)` pairs, every score
labeled by Claude using the support-specific rubric. No other labeler
contributed to the training set.

| source | rows | what it is |
|---|---|---|
DS3 (Tobi Bueck) | 9,229 | real enterprise support tickets, actual customer emails |
DS2 (Bitext) | 8,371 | synthetic customer-support Q/A pairs |

| category | rows |
|---|---|
technical | 5,817 |
orders & billing | 4,941 |
delivery & general | 4,750 |
account access | 2,092 |

The 238 generated batches were shuffled across all four categories, so no
category is over-represented within a batch. The labeled set is deduplicated:
51,838 raw rows → 50,063 after category mapping → 47,599 after
exact-normalized dedup → 17,600 currently labeled (90 of 238 batches done).
The remaining 148 batches are deliberately unfinished, not failed.

## Model selection

Three models were trained. `support_all` is the one to ship; the other two
exist for the record.

| model | training rows | test rows | MAE | Spearman | tier accuracy |
|---|---|---|---|---|---|
**support_all** (ship) | 12,000 | 2,800 | **0.740** | **0.861** | **92.5%** |
support_ds3 | 6,256 | 2,800 | 0.911 | 0.728 | 86.4% |
generic (pre-existing) | 8,000 | 2,800 | 1.301 | 0.757 | 68.3% |

- `support_ds3` is the same architecture trained on real tickets only, to test
  whether the synthetic rows dilute the model. They do not — mixing both
  sources scores 0.861 vs 0.728. Kept as evidence, not shipped.
- `generic` is the pre-existing general-purpose model, trained on 8,000
  programming / writing / reasoning labels. It is listed **only** as a
  reference point for "what happens if support queries are routed by the
  generic model." It is not a support model and the two are not otherwise
  comparable.

## How the evaluation split works

The 17,600 labeled rows were split **by batch, not by row**, because
near-duplicate tickets survive exact-normalized dedup and a random row split
lets siblings leak across the boundary. Batches are the unit.

| split | batches | rows | used for |
|---|---|---|---|
train | 60 | 12,000 | fitting the regressors |
calibration | 14 | 2,800 | grid-searching the tier thresholds |
test | 14 | 2,800 | reported metrics, never touched otherwise |

The 12,000 / 2,800 / 2,800 figures describe the *evaluation* run. The shipped
model is retrained on all 17,600.

## Thresholds — different from the generic model

The generic model's 4.5 / 6.0 boundaries were tuned on general-purpose labels.
Support scores sit higher on the same 0–10 scale, so the deployed boundaries
are wrong for this model.

| | cheap | mid | frontier | tier accuracy |
|---|---|---|---|---|
generic boundaries | ≤ 4.5 | 4.5–6.0 | ≥ 6.0 | 79.2% |
**support boundaries** | **≤ 6.5** | **6.5–7.0** | **≥ 7.0** | **92.5%** |

13.3 points of tier accuracy from the thresholds alone, at no model cost.

## Known weakness: the top of the scale compresses

On the hardest support tickets (gold 8–9: data-breach escalations, service
outages, security incidents) the model under-predicts, typically 5.6–7.1
against a gold of 8–9.

Under the generic 4.5 / 6.0 boundaries this is a real problem: a medical
data-breach escalation scores 6.03 and routes to the cheap tier. The
calibrated 6.5 / 7.0 boundaries catch most of these, but the compression is
in the model, not the thresholds, and it is the main thing to fix with more
labels.

Score 9–10 is very sparse — 18 rows in 17,600 — so the top band is effectively
unevidenced and should not be claimed.

## Ceiling on accuracy

Label noise sets the floor. An independent second labeler disagreed with
Claude on 68% of a 1,000-ticket overlap sample, with a mean absolute
difference of 1.34 points. On that evidence, MAE below roughly 1.0 is not
attainable on this data and is not a target. The reported 0.740 is partly a
measure of agreement with one labeler's specific judgments.

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
`models\support_all.joblib` | the shipped model |
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
| `eval_support_model.py` | batch-level split, calibration, metrics, report |

`train_support_models.py` is kept for the record but its headline comparison
was against generic-domain gold and is **not** the evaluation described here.
`eval_support_model.py` supersedes it.

## Known data gap

2 of the 90 reply files were rejected by the merge validator and need to be
re-run: `batch_225` returned 209 lines for 200 tickets, and `batch_238`
returned 199. 400 of 18,000 potential labels are therefore missing. The merge
script rejects rather than silently misaligning, so these are dropped cleanly
rather than corrupting the set.
