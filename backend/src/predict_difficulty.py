import os
import joblib
import numpy as np
import re
from sentence_transformers import SentenceTransformer

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "difficulty_regressor.joblib")
_MINILM_LOCAL = os.path.join(os.path.dirname(__file__), "..", "models", "minilm")
_EMBEDDER_NAME = _MINILM_LOCAL if os.path.isdir(_MINILM_LOCAL) else "sentence-transformers/all-MiniLM-L6-v2"


class EnsembleRegressor:
    """Deployed difficulty model = average of two LightGBM regressors (v18 + v19).
    Defined in this module so joblib.load() can always resolve it."""

    def __init__(self, models):
        self.models = models

    def predict(self, X):
        preds = [np.clip(m.predict(X), 0, 10) for m in self.models]
        return np.clip(np.mean(preds, axis=0), 0, 10)


_bundle = None
_embedder = None


def _load():
    global _bundle, _embedder
    if _bundle is None:
        _bundle = joblib.load(MODEL_PATH)
        _embedder = SentenceTransformer(_EMBEDDER_NAME)
    return _bundle, _embedder


def preload_models():
    _load()
    return True

def get_embedder():
    # shared embedder — cache.py reuses this instead of loading MiniLM twice
    _load()
    return _embedder


def predict_difficulty(query: str) -> float:
    bundle, embedder = _load()
    embed = embedder.encode([query])

    word_count = len(query.split())
    has_code = int(bool(re.search(r"(?:def |function|class |import |SELECT |for\(|while\()", query)))
    question_mark = int("?" in query)
    length_match = re.search(r"(\d+)[\s-]*word", query)
    requested_length = float(length_match.group(1)) if length_match else 0.0
    extra = np.array([[word_count, has_code, question_mark, requested_length]])

    X = np.hstack([embed, extra])
    score = bundle["model"].predict(X)[0]
    return float(np.clip(score, 0, 10))


# score_to_tier thresholds are calibrated to the v20 ensemble's output range (0-9).
# Frontier-gold queries (label 8-10) predict ~6.0, so the frontier floor is set lower
# than 8 to keep the frontier tier reachable. We bias toward over-routing rather than
# under-routing — a frontier model on an easy query wastes money; a cheap model on a
# hard query gives a wrong answer.
#
# Both boundaries slide continuously with margin:
#   economy (0.0): cheap<=5.25, frontier>=6.75  -> cheapest routing, fewest frontier calls
#   balanced (1.0): cheap<=4.5, frontier>=6.0   -> default, wide mid band
#   quality (2.0): cheap<=3.75, frontier>=5.25  -> strongest models for more queries
def score_to_tier(score: float, margin: float = 0.3) -> tuple[str, float, float]:
    scaled = margin * 0.3          # 0.0→0.0, 1.0→0.3, 2.0→0.6
    t = (scaled - 0.3) / 0.3       # -1.0 (economy) -> 0.0 (balanced) -> +1.0 (quality)
    cheap_ceil = 4.5 - t * 0.75    # economy=5.25, balanced=4.5, quality=3.75
    frontier_floor = 6.0 - t * 0.75  # economy=6.75, balanced=6.0, quality=5.25
    if score >= frontier_floor:
        tier = "frontier"
    elif score <= cheap_ceil:
        tier = "cheap"
    else:
        tier = "mid"
    return tier, round(cheap_ceil, 3), round(frontier_floor, 3)

# Test
if __name__ == "__main__":
    tests = [
        "What is the capital of France?",
        "Design a caching layer for a distributed rate limiter",
        "Write a 1000-word short story with a twist ending",
    ]
    for q in tests:
        s = predict_difficulty(q)
        print(f"{s:.2f} -> {score_to_tier(s):8s} | {q}")