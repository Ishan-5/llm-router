# Model card — RouteWise difficulty scorer (`emma`)

The model behind RouteWise's default routing policy. It predicts how **hard** a
request is on a 0–10 scale so the router can send easy work to a cheap model and
reserve the frontier tier for the queries that actually need it.

| | |
|---|---|
| **Artifact** | `backend/models/difficulty_regressor.joblib` |
| **Bundle name** | `v20_ensemble_v18_v19` |
| **Status** | deployed (v20), supersedes v15 |
| **Owner** | RouteWise — [`Ishan-5/llm-router`](https://github.com/Ishan-5/llm-router) |
| **Scope** | general chat / generation traffic (`emma`). The support-domain policies `lisa` and `kate` **share one support-trained regressor** and differ only in their tier cutoffs — see `customer-support/docs/`. |

## Overview

- **Architecture** — ensemble of two LightGBM regressors (v18 tuned + v19
  frontier-weighted 2.5×), predictions averaged and clipped to 0–10.
- **Features (388)** — a 384-dim `all-MiniLM-L6-v2` sentence embedding plus four
  handcrafted signals: word count, contains-code, question mark, requested length.
- **Output** — a difficulty score, mapped to `cheap` / `mid` / `frontier` by
  `score_to_tier` (features and serving path are shared with training, so the two
  cannot drift).
- **Scoring latency** — ~16.5 ms per query on CPU (advertised as `<20 ms`); no API
  call is made just to decide routing.
- **License** — proprietary (see [`LICENSE`](../LICENSE)); the code and model are
  not open source.

## Intended use

- Score a single request, then route it to the cheapest tier that can handle it.
- Drive the sensitivity slider (economy / balanced / quality), which moves both
  tier boundaries.
- Choose the policy per request: `emma` (this model), `lisa`, or `kate`.

**Out of scope**

- **Multi-turn intent.** Only the newest message is scored; the router is
  stateless and forwards `messages` verbatim.
- **Answer quality.** This model scores difficulty, not correctness. Quality is
  measured separately by the blind cheap-vs-frontier A/B
  (`backend/scripts/quality_ab_test.py`).
- **Support tickets.** They have their own label distribution — use `lisa`/`kate`.

## Training data

- **Gold set** — `backend/dataset_pipeline/datasets/labeled_dataset/gold_labeled_queries.csv`
  (8,783 rows; columns `query`, `gold_score`, `source`, `label_source`).
- **Labels** — Claude-verified in two waves (v6 + v7). The earlier 8B auto-labels
  over-scored by ~1.4 and were replaced.
- **Training rows** — 8,200. Provenance (`source`, `label_source`) is preserved
  per row.

## Evaluation

Head-to-head on the same **783 held-out Claude-gold rows** (queries neither model
trained on), each at its balanced thresholds:

| Metric | v15 | v20 (deployed) |
|---|---|---|
| MAE | 1.069 | **1.018** |
| Spearman rank correlation | 0.850 | **0.861** |
| Exact-tier accuracy | 70.6% | **77.5%** |
| Cheap recall | 88% | **94%** |
| Mid recall | 68% | 40% |
| Frontier recall | 41% | **58%** |
| Under-routed frontier (of 261 gold) | 154 | **110** |

The 5× jump in Claude-verified labels (1,703 → 8,200) bought a deliberate shift:
v20 is more decisive at both boundaries. It catches far more under-routed hard
queries (frontier recall 41% → 58%) and sends easy queries to cheap more reliably
(88% → 94%), at the cost of a thinner mid band (mid recall 68% → 40%). Exact-tier
accuracy still improves overall.

### Tier boundaries (`score_to_tier`)

| Slider | cheap ≤ | frontier ≥ |
|---|---|---|
| Economy | 5.25 | 6.75 |
| **Balanced (default)** | **4.5** | **6.0** |
| Quality | 3.75 | 5.25 |

## Regression gate

`backend/tests/test_difficulty_model_gate.py` runs in CI and raises a warning —
without failing the build — if the deployed bundle regresses past these floors:

| Metric | Floor | Deployed |
|---|---|---|
| MAE | ≤ **1.05** | 1.018 |
| Spearman | ≥ **0.84** | 0.861 |
| Exact-tier accuracy | ≥ **74%** | 77.5% |

The floor check is advisory on purpose: a regression is surfaced loudly, but it
does not block a merge. The same test *does* hard-fail if this card or the
experiment tracker (`backend/mlops/model_metrics.csv`) disagree with the bundle's
recorded metrics, so the number in the artifact, this document and the tracker
cannot silently drift apart. It reads the bundle's own recorded metrics and needs
no model download, so it runs offline in CI (no MiniLM, no network).

## Limitations

- Evaluated against Claude-verified **labels**, not human quality ratings;
  difficulty is a proxy for "which tier can answer this", not a quality score.
- The held-out slice shares the gold set's composition — it is not a random
  sample of all possible traffic.
- Frontier recall of 58% means ~42% of gold-frontier queries are still routed
  below frontier. This is the metric the project watches most, because that is
  the failure mode that costs answer quality.
- English-centric; the gold set is predominantly English.

## Retraining

```bash
cd backend
python mlops/retrain.py --deploy --version vNN   # deploys only if it beats the live model
```

Every run appends a row to `backend/mlops/model_metrics.csv`. A deploy backs up
the previous model to `*.bak_<version>`, so rollback is a file copy.

---

_Last updated: 2026-10-14 · describes bundle `v20_ensemble_v18_v19`._
