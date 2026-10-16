"""Testes do modelo probabilístico e calibração."""
import numpy as np

from app.probability import ProbabilityModel, wilson_interval, FEATURE_NAMES


def _fake_data(n=2000, seed=0, signal_strength=1.0):
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 1, size=(n, len(FEATURE_NAMES)))
    logit = signal_strength * X[:, 0] - 0.5 * X[:, 1]
    p = 1 / (1 + np.exp(-logit))
    y = (rng.random(n) < p).astype(float)
    return X, y


def test_model_uncalibrated_without_fit():
    m = ProbabilityModel()
    assert not m.calibrated
    try:
        m.predict_array(np.zeros((1, len(FEATURE_NAMES))))
        assert False
    except RuntimeError:
        pass


def test_model_rejects_small_sample():
    X, y = _fake_data(100)
    m = ProbabilityModel()
    rep = m.fit(X, y)
    assert not m.calibrated
    assert "insuficiente" in rep.note


def test_model_calibrates_with_signal():
    X, y = _fake_data(4000, seed=1, signal_strength=1.5)
    Xtr, ytr = X[:2000], y[:2000]
    Xva, yva = X[2000:3000], y[2000:3000]
    Xte, yte = X[3000:], y[3000:]
    m = ProbabilityModel()
    rep = m.fit(Xtr, ytr, Xva, yva, Xte, yte)
    assert m.calibrated
    assert rep.brier_test < rep.baseline_test


def test_model_rejects_pure_noise():
    rng = np.random.default_rng(7)
    X = rng.normal(0, 1, size=(4000, len(FEATURE_NAMES)))
    y = (rng.random(4000) < 0.55).astype(float)   # sem relação com X
    m = ProbabilityModel()
    rep = m.fit(X[:2000], y[:2000], X[2000:3000], y[2000:3000], X[3000:], y[3000:])
    # sem sinal, não deve ser considerado calibrado/aprovado
    assert not m.calibrated


def test_wilson_interval_bounds():
    lo, hi = wilson_interval(80, 100)
    assert 0 <= lo <= 0.8 <= hi <= 1
    lo0, hi0 = wilson_interval(0, 0)
    assert np.isnan(lo0) and np.isnan(hi0)
