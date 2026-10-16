"""Verifica que o IndicatorCache não altera resultados (equivalência exata)."""
import numpy as np

from app.core.candles import synthetic_series
from app.analysis.context import AnalysisContext, IndicatorCache
from app.signal import generate_signal


def test_cache_matches_uncached():
    s = synthetic_series(700, seed=11)
    cache = IndicatorCache(s)
    for i in (120, 200, 305, 450, 699):
        a = AnalysisContext.build(s, i + 1)
        b = AnalysisContext.build(s, i + 1, cache=cache)
        ra = generate_signal(a)
        rb = generate_signal(b)
        assert ra.status == rb.status
        assert ra.direction == rb.direction
        assert ra.strategy_id == rb.strategy_id


def test_cache_tf5m_matches():
    s = synthetic_series(700, seed=5)
    cache = IndicatorCache(s)
    for i in (300, 500, 699):
        a = AnalysisContext.build(s, i + 1)
        b = AnalysisContext.build(s, i + 1, cache=cache)
        assert (a.tf5m is None) == (b.tf5m is None)
        if a.tf5m and b.tf5m:
            assert a.tf5m["trend_dir"] == b.tf5m["trend_dir"]
