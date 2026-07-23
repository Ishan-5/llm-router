from predict_difficulty import score_to_tier


def test_low_score_is_cheap():
    assert score_to_tier(1.0)[0] == "cheap"


def test_mid_range_score_is_mid():
    assert score_to_tier(4.0, margin=1.0)[0] == "mid"


def test_high_score_is_frontier():
    assert score_to_tier(9.0)[0] == "frontier"


def test_margin_bumps_borderline_score_to_frontier():
    assert score_to_tier(4.5, margin=2.0)[0] == "frontier"
    assert score_to_tier(4.5, margin=0.0)[0] == "mid"


def test_margin_zero_uses_hard_cutoff():
    assert score_to_tier(4.8, margin=0.0)[0] == "mid"
    assert score_to_tier(5.0, margin=0.0)[0] == "frontier"


def test_cheap_boundary_moves_with_margin():
    assert score_to_tier(3.4, margin=0.0)[0] == "cheap"
    assert score_to_tier(3.4, margin=1.0)[0] == "cheap"
    assert score_to_tier(3.5, margin=1.0)[0] == "mid"


def test_score_to_tier_returns_thresholds():
    tier, cheap_ceil, frontier_floor = score_to_tier(4.0, margin=1.0)
    assert cheap_ceil == 3.4
    assert frontier_floor == 4.6