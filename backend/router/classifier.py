import sys
import os

# Append src/ directory to system path to import predict_difficulty
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from predict_difficulty import predict_difficulty, score_to_tier


def score_difficulty(query: str) -> float:
    return predict_difficulty(query)


def get_tier(query: str, margin: float = 0.3) -> tuple[float, str, float, float]:
    score = predict_difficulty(query)
    tier, cheap_ceil, frontier_floor = score_to_tier(score, margin=margin)
    return score, tier, cheap_ceil, frontier_floor