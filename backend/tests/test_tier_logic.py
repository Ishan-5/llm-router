from predict_difficulty import score_to_tier


def test_low_score_is_cheap():
    assert score_to_tier(1.0) == "cheap"


def test_mid_range_score_is_mid():
    # balanced margin=1.0: cheap<=3.4, frontier>=3.9, so 3.7 is mid
    assert score_to_tier(3.7, margin=1.0) == "mid"


def test_high_score_is_frontier():
    assert score_to_tier(9.0) == "frontier"


def test_margin_bumps_borderline_score_to_frontier():
    # quality margin=2.0: frontier>=2.9, so 3.0 is frontier
    assert score_to_tier(3.0, margin=2.0) == "frontier"
    # economy margin=0.0: frontier>=4.9, so 4.5 is mid
    assert score_to_tier(4.5, margin=0.0) == "mid"


def test_margin_zero_uses_hard_cutoff():
    # economy margin=0.0: frontier>=4.9
    assert score_to_tier(4.8, margin=0.0) == "mid"
    assert score_to_tier(5.0, margin=0.0) == "frontier"


def test_cheap_boundary_moves_with_margin():
    # economy margin=0.0: cheap<=3.65, so 3.5 is cheap
    assert score_to_tier(3.5, margin=0.0) == "cheap"
    # quality margin=2.0: frontier>=2.9, cheap<=3.15, so 3.5 is frontier
    assert score_to_tier(3.5, margin=2.0) == "frontier"
    # to test cheap ceiling lowering: use balanced margin=1.0 where frontier>=3.9
    # score 3.3 is cheap at economy (<=3.65) but mid at balanced (<=3.4 ceiling)
    assert score_to_tier(3.3, margin=0.0) == "cheap"
    assert score_to_tier(3.5, margin=1.0) == "mid"