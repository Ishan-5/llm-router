"""
Two jobs:

predict_difficulty(query) — takes raw text, returns a 0–10 float. Does this by combining a 384-dim semantic embedding from MiniLM with 4 handcrafted features, feeding all 388 into LightGBM

score_to_tier(score) — maps that float to "cheap", "mid", or "frontier" with an asymmetric safety margin at the frontier boundary

The lazy loading pattern means the ~400MB of model weights 
load once at first request and stay in memory for the lifetime
of the server process. get_embedder() exposes the MiniLM instance
so cache.py can reuse it without loading it a second time.
"""

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
    if _bundle is None:  # only loads if not already loaded. First call loads everything, every subsequent call just returns the already-loaded objects instantly
        _bundle = joblib.load(MODEL_PATH)
        _embedder = SentenceTransformer(_EMBEDDER_NAME)
    return _bundle, _embedder
#This pattern is called lazy loading — load on first use, cache forever. 
# In a web server context this means the first request after startup is slow (model loading), every request after that is fast.

def get_embedder():  #Expose the shared embedder so other modules (e.g. semantic cache) reuse it instead of loading MiniLM a second time.
    _load()
    return _embedder


def predict_difficulty(query: str) -> float:
    bundle, embedder = _load()
    embed = embedder.encode([query]) #converts the query string into a 384-dimensional vector

    word_count = len(query.split())
    has_code = int(bool(re.search(r"(?:def |function|class |import |SELECT |for\(|while\()", query)))
    question_mark = int("?" in query)
    length_match = re.search(r"(\d+)[\s-]*word", query)
    requested_length = float(length_match.group(1)) if length_match else 0.0
    extra = np.array([[word_count, has_code, question_mark, requested_length]])

    X = np.hstack([embed, extra])
    score = bundle["model"].predict(X)[0]
    return float(np.clip(score, 0, 10)) # the final feature vector is 388 numbers: 384 semantic + 4 handcrafted


def score_to_tier(score: float, margin: float = 1.0) -> str:
    if score >= (7 - margin):
        return "frontier"
    elif score <= 3:
        return "cheap"
    else:
        return "mid"

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