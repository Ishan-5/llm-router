from predict_difficulty import score_to_tier


def test_low_score_is_cheap():
    assert score_to_tier(1.0) == "cheap"


def test_mid_range_score_is_mid():
    assert score_to_tier(5.0) == "mid"


def test_high_score_is_frontier():
    assert score_to_tier(9.0) == "frontier"


def test_margin_bumps_borderline_score_to_frontier():
    # default margin=1.0 means score>=6 counts as frontier, not just score>7
    assert score_to_tier(6.5, margin=1.0) == "frontier"
    assert score_to_tier(5.9, margin=1.0) == "mid"


def test_margin_zero_uses_hard_cutoff_at_seven():
    assert score_to_tier(6.5, margin=0.0) == "mid"
    assert score_to_tier(7.1, margin=0.0) == "frontier"


def test_cheap_mid_boundary_has_no_margin():
    # margin only applies at the mid/frontier boundary -- see reasoning in
    # predict_difficulty.py. A score of 3.0 should always be cheap regardless
    # of margin, since erring cheap-side is a cost problem, not a safety one.
    assert score_to_tier(3.0, margin=1.0) == "cheap"
    assert score_to_tier(3.1, margin=1.0) == "mid"