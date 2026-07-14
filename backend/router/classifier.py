"""
It's a 17-line adapter. Its only real job is to bridge the path gap
between router/ and src/ and expose a clean get_tier() 
function that returns (score, tier) as a tuple — exactly what main.py needs in one call.
"""

import sys
import os

# adjust this if your src/ folder lives elsewhere relative to router/
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from predict_difficulty import predict_difficulty, score_to_tier


def score_difficulty(query: str) -> float:
    return predict_difficulty(query)


def get_tier(query: str, margin: float = 1.0) -> tuple[float, str]:
    score = predict_difficulty(query)
    tier = score_to_tier(score, margin=margin)
    return score, tier