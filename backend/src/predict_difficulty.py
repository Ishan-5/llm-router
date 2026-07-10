import os
import joblib
import numpy as np
import re
from sentence_transformers import SentenceTransformer

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "difficulty_regressor.joblib")


_bundle = None
_embedder = None


def _load():
    global _bundle, _embedder
    if _bundle is None:
        _bundle = joblib.load(MODEL_PATH)
        _embedder = SentenceTransformer(_bundle["embedder_name"])
    return _bundle, _embedder


def get_embedder():
    """Expose the shared embedder so other modules (e.g. semantic cache) reuse it
    instead of loading MiniLM a second time."""
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


def score_to_tier(score: float, margin: float = 1.0) -> str:
    if score >= (7 - margin):
        return "frontier"
    elif score <= 3:
        return "cheap"
    else:
        return "mid"


if __name__ == "__main__":
    tests = [
        "What is the capital of France?",
        "Design a caching layer for a distributed rate limiter",
        "Write a 1000-word short story with a twist ending",
    ]
    for q in tests:
        s = predict_difficulty(q)
        print(f"{s:.2f} -> {score_to_tier(s):8s} | {q}")