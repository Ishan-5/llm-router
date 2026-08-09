import os
import joblib
import numpy as np
import re
from sentence_transformers import SentenceTransformer

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "difficulty_regressor.joblib")
_MINILM_LOCAL = os.path.join(os.path.dirname(__file__), "..", "models", "minilm")
_EMBEDDER_NAME = _MINILM_LOCAL if os.path.isdir(_MINILM_LOCAL) else "sentence-transformers/all-MiniLM-L6-v2"


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


# score_to_tier thresholds are calibrated to this model's actual output range (0-7.9).
# Frontier-gold queries (label 8-10) predict ~6.0, so the frontier floor is set lower
# than 8 to keep the frontier tier reachable. We bias toward over-routing rather than
# under-routing — a frontier model on an easy query wastes money; a cheap model on a
# hard query gives a wrong answer.
def score_to_tier(score: float, margin: float = 0.3) -> tuple[str, float, float]:
    # Both boundaries shift with margin.
    # Economy (low margin) raises cheap ceiling + raises frontier floor → more cheap, less frontier.
    # Quality (high margin) lowers cheap ceiling + lowers frontier floor → less cheap, more frontier.
    # Slider range is 0-2. Scale margin down so balanced (1.0) keeps sensible defaults.
    scaled = margin * 0.3          # 0.0→0.0, 1.0→0.3, 2.0→0.6
    cheap_ceil = 4.0 - (scaled - 0.3) * 0.25   # economy=4.075, balanced=4.0, quality=3.925
    frontier_floor = 6.3 - scaled               # economy=6.3, balanced=6.0, quality=5.7
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