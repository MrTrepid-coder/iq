"""Testes das estratégias e do filtro de sinais."""
from app.core.candles import Candle, CandleSeries, synthetic_series
from app.analysis.context import AnalysisContext
from app.strategies import (strategy_trend_continuation, ALL_STRATEGIES)
from app.signal import generate_signal


def _uptrend(n=200, start=100.0, step=0.08):
    candles = []
    p = start
    for i in range(n):
        o = p
        c = p + step
        h = c + 0.05
        l = o - 0.05
        candles.append(Candle(i * 60, o, h, l, c, 1000))
        p = c
    return CandleSeries(candles, symbol="UP")


def test_all_strategies_return_valid_direction():
    s = synthetic_series(400, seed=9)
    ctx = AnalysisContext.build(s, 400)
    for fn in ALL_STRATEGIES:
        r = fn(ctx)
        assert r.direction in (-1, 0, 1)
        assert r.strategy_id in ("A", "B", "C", "D", "E")


def test_trend_follow_fires_in_clean_uptrend():
    s = _uptrend(250)
    ctx = AnalysisContext.build(s, 250)
    r = strategy_trend_continuation(ctx)
    assert r.direction == 1
    assert len(r.confirmations) >= 1


def test_no_forced_signal_in_flat_market():
    # mercado perfeitamente plano => não deve forçar CALL/PUT
    candles = [Candle(i * 60, 10.0, 10.0, 10.0, 10.0, 100) for i in range(300)]
    s = CandleSeries(candles, symbol="FLAT")
    rep = generate_signal(AnalysisContext.build(s, 300))
    assert rep.direction == 0
    assert rep.decision == "AGUARDAR"


def test_signal_report_explain_has_all_fields():
    s = synthetic_series(400, seed=2)
    ctx = AnalysisContext.build(s, 400)
    rep = generate_signal(ctx)
    txt = rep.explain()
    for field in ("ATIVO", "PERÍODO", "CONTEXTO", "CENÁRIO", "DECISÃO"):
        assert field in txt
