import numpy as np
from router.cache import _cosine_sim


def test_identical_vectors_have_similarity_one():
    v = np.array([1.0, 2.0, 3.0])
    assert abs(_cosine_sim(v, v) - 1.0) < 1e-6


def test_orthogonal_vectors_have_similarity_zero():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert abs(_cosine_sim(a, b)) < 1e-6


def test_opposite_vectors_have_similarity_negative_one():
    a = np.array([1.0, 0.0])
    b = np.array([-1.0, 0.0])
    assert abs(_cosine_sim(a, b) - (-1.0)) < 1e-6