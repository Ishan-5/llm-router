"""Regression gate for the deployed difficulty model (`emma`).

The model is a shipped product artifact: the README, the frontend copy and this
repo all state its metrics. This test makes those claims enforceable instead of
trusted:

  * the deployed joblib must meet the metric floors below, so a worse model
    cannot be merged without the floors being moved deliberately;
  * docs/MODEL_CARD.md must state the bundle's recorded metrics;
  * backend/mlops/model_metrics.csv must carry a matching deployed row;
  * the gold dataset the card cites must be present and well formed;
  * the tier boundaries the card documents must match `score_to_tier`.

It is deliberately offline: it reads the metrics recorded in the bundle at
training time (measured on the 783-row held-out slice), so it needs no MiniLM
download and makes no model call, and runs the same on a laptop and in CI.
"""
from __future__ import annotations

import csv
from pathlib import Path

import joblib
import pytest

from predict_difficulty import EnsembleRegressor, score_to_tier

REPO = Path(__file__).resolve().parents[2]
BUNDLE_PATH = REPO / "backend" / "models" / "difficulty_regressor.joblib"
CARD_PATH = REPO / "docs" / "MODEL_CARD.md"
METRICS_CSV = REPO / "backend" / "mlops" / "model_metrics.csv"
GOLD_CSV = (
    REPO
    / "backend"
    / "dataset_pipeline"
    / "datasets"
    / "labeled_dataset"
    / "gold_labeled_queries.csv"
)

EXPECTED_BUNDLE_NAME = "v20_ensemble_v18_v19"

# Floors sit a little below the deployed model (1.018 / 0.861 / 0.775) so ordinary
# re-evaluation jitter cannot fail CI, but a real regression can.
MAE_FLOOR = 1.05
SPEARMAN_FLOOR = 0.84
TIER_ACC_FLOOR = 0.74


@pytest.fixture(scope="module")
def bundle() -> dict:
    assert BUNDLE_PATH.exists(), f"deployed model missing: {BUNDLE_PATH}"
    return joblib.load(BUNDLE_PATH)


def test_deployed_bundle_is_the_documented_model(bundle: dict):
    assert bundle.get("model_name") == EXPECTED_BUNDLE_NAME
    assert isinstance(bundle.get("model"), EnsembleRegressor)
    for key in ("test_mae", "test_spearman", "test_tier_acc"):
        assert key in bundle, f"bundle is missing recorded metric {key!r}"


def test_deployed_metrics_meet_regression_floors(bundle: dict):
    mae = bundle["test_mae"]
    spearman = bundle["test_spearman"]
    tier_acc = bundle["test_tier_acc"]
    assert mae <= MAE_FLOOR, f"MAE regressed to {mae:.3f} (floor {MAE_FLOOR})"
    assert spearman >= SPEARMAN_FLOOR, (
        f"Spearman regressed to {spearman:.3f} (floor {SPEARMAN_FLOOR})"
    )
    assert tier_acc >= TIER_ACC_FLOOR, (
        f"exact-tier accuracy regressed to {tier_acc:.3f} (floor {TIER_ACC_FLOOR})"
    )


def test_model_card_documents_the_deployed_metrics(bundle: dict):
    assert CARD_PATH.exists(), "docs/MODEL_CARD.md is missing"
    card = CARD_PATH.read_text(encoding="utf-8")
    assert EXPECTED_BUNDLE_NAME in card, "model card must name the deployed bundle"
    assert f"{bundle['test_mae']:.3f}" in card, "card MAE does not match the bundle"
    assert f"{bundle['test_spearman']:.3f}" in card, "card Spearman does not match the bundle"
    assert f"{bundle['test_tier_acc'] * 100:.1f}" in card, "card tier accuracy does not match"


def test_experiment_tracker_matches_the_deployed_bundle(bundle: dict):
    assert METRICS_CSV.exists(), "model_metrics.csv is missing"
    with METRICS_CSV.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    deployed = [r for r in rows if (r.get("deployed") or "").strip() == "yes"]
    assert deployed, "no row in model_metrics.csv is marked deployed"
    live = deployed[-1]
    assert abs(float(live["mae"]) - bundle["test_mae"]) < 1e-6, "tracker MAE != bundle"
    assert abs(float(live["spearman"]) - bundle["test_spearman"]) < 1e-6, "tracker Spearman != bundle"
    assert abs(float(live["tier_acc"]) - bundle["test_tier_acc"]) < 1e-6, "tracker tier_acc != bundle"


def test_gold_dataset_is_present_and_well_formed():
    assert GOLD_CSV.exists(), f"gold dataset missing: {GOLD_CSV}"
    with GOLD_CSV.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        columns = set(reader.fieldnames or [])
        rows = list(reader)
    assert {"query", "gold_score"} <= columns, f"unexpected gold schema: {sorted(columns)}"
    assert len(rows) >= 8000, f"gold set shrank to {len(rows)} rows"
    scores = [float(r["gold_score"]) for r in rows if r.get("gold_score")]
    assert scores, "gold set has no gold_score values"
    assert all(0.0 <= s <= 10.0 for s in scores), "gold_score outside the 0-10 range"


@pytest.mark.parametrize(
    "margin,cheap_ceil,frontier_floor",
    [(0.0, 5.25, 6.75), (1.0, 4.5, 6.0), (2.0, 3.75, 5.25)],
)
def test_tier_boundaries_are_the_documented_ones(margin: float, cheap_ceil: float, frontier_floor: float):
    _tier, got_cheap, got_frontier = score_to_tier(0.0, margin=margin)
    assert got_cheap == cheap_ceil, f"economy/balanced/quality cheap cut moved at margin={margin}"
    assert got_frontier == frontier_floor, f"frontier cut moved at margin={margin}"
    assert got_cheap < got_frontier
