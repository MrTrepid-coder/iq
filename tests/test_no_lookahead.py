"""Teste crítico: nenhum sinal pode depender de candles futuros."""
from app.core.candles import synthetic_series
from app.analysis.context import AnalysisContext
from app.signal import generate_signal


def _signal_at(series, i):
    ctx = AnalysisContext.build(series, i + 1)
    return generate_signal(ctx, payout=0.80)


def test_no_lookahead_signals_stable():
    """Alterar os candles FUTUROS não pode mudar o sinal de um índice passado."""
    s = synthetic_series(500, seed=42)
    cut = 300
    a = _signal_at(s, cut)

    # cria uma série alternativa que muda radicalmente tudo APÓS o índice de decisão
    from app.core.candles import Candle, CandleSeries
    mutated = list(s.candles[:cut + 1])
    last = mutated[-1]
    price = last.close
    for k in range(cut + 1, len(s)):
        price *= 1.05          # rally forte artificial no futuro
        mutated.append(Candle(s[k].ts, price, price * 1.001, price * 0.999, price, 1.0))
    s2 = CandleSeries(mutated, symbol=s.symbol)

    b = _signal_at(s2, cut)
    assert a.status == b.status
    assert a.direction == b.direction
    assert a.strategy_id == b.strategy_id
    assert len(a.confirmations) == len(b.confirmations)


def test_context_requires_enough_data():
    s = synthetic_series(50)
    try:
        AnalysisContext.build(s, 50)
        assert False, "deveria exigir >= 60 candles"
    except ValueError:
        pass


def test_signal_always_has_decision():
    s = synthetic_series(400, seed=3)
    for i in (200, 250, 300, 350):
        rep = _signal_at(s, i)
        assert rep.decision in ("AVALIAR CALL", "AVALIAR PUT", "AGUARDAR")
        assert rep.status in ("sem_sinal", "aguardar", "sinal_detectado")


def test_probability_none_when_uncalibrated():
    s = synthetic_series(400, seed=5)
    rep = _signal_at(s, 300)
    # Sem modelo => probabilidade deve ser None (não inventada)
    assert rep.probability is None
