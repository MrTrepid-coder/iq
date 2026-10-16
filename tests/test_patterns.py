"""Testes de padrões e estrutura de mercado."""
from app.core.candles import Candle, CandleSeries
from app.core import patterns as pat
from app.core import structure as st


def _c(o, h, l, cl, ts=0):
    return Candle(ts, o, h, l, cl)


def test_engulfing_bull():
    candles = [_c(10, 10.5, 9.5, 9.6),      # bear
               _c(9.5, 10.6, 9.4, 10.5)]    # corpo engole o anterior
    m = pat.engulfing(candles, 1)
    assert m is not None and m.direction == 1


def test_engulfing_requires_direction_change():
    candles = [_c(10, 11, 9.5, 10.8),       # bull
               _c(10.8, 12, 10.5, 11.9)]    # bull maior, mesma direção => não é engolfo
    assert pat.engulfing(candles, 1) is None


def test_pin_bar_bull():
    candles = [_c(10, 10.2, 9.9, 10.1),
               _c(10.1, 10.2, 9.0, 10.05)]  # sombra inferior longa
    m = pat.pin_bar(candles, 1)
    assert m is not None and m.direction == 1


def test_doji():
    candles = [_c(10, 10.5, 9.5, 10.01)]
    m = pat.doji(candles, 0)
    assert m is not None


def test_hammer_requires_fall_context():
    uptrend = [_c(10 + i * 0.1, 10.2 + i * 0.1, 9.9 + i * 0.1, 10.15 + i * 0.1) for i in range(6)]
    hammer_c = _c(10.6, 10.65, 9.8, 10.55)
    assert pat.hammer(uptrend + [hammer_c], 6) is None   # sem queda recente
    downtrend = [_c(10 - i * 0.1, 10.1 - i * 0.1, 9.8 - i * 0.1, 9.9 - i * 0.1) for i in range(6)]
    m = pat.hammer(downtrend + [_c(9.2, 9.3, 8.5, 9.25)], 6)
    assert m is not None and m.direction == 1


def test_strength_sequence():
    candles = [_c(10, 10.4, 9.95, 10.35) for _ in range(3)]
    m = pat.strength_sequence(candles, 2)
    assert m is not None and m.direction == 1


def test_detect_all_returns_list():
    candles = [_c(10, 10.5, 9.5, 9.6), _c(9.5, 10.6, 9.4, 10.5)]
    out = pat.detect_all(candles, 1)
    assert isinstance(out, list)
    assert any(m.name == "engulfing_bull" for m in out)


def test_swings_confirm():
    # zigzag com 3 picos
    prices = [1, 2, 3, 2, 3, 4, 3, 4, 5, 4]
    candles = [Candle(i, p, p + 0.1, p - 0.1, p) for i, p in enumerate(prices)]
    swings = st.find_swings(candles, 1, 1)
    highs = [s for s in swings if s.kind == "high" and s.confirmed]
    assert len(highs) >= 2


def test_trend_up_structure():
    prices = [100, 101, 102, 101, 103, 104, 103, 105, 106, 105,
              107, 108, 107, 109, 110, 109, 111, 112, 111, 113,
              114, 113, 115, 116, 115, 117, 118, 117, 119, 120,
              119, 121, 122, 121, 123, 124, 123, 125, 126, 125,
              127, 128, 127, 129, 130, 129, 131, 132, 131, 133,
              134, 133, 135, 136, 135, 137, 138, 137, 139, 140]
    candles = [Candle(i, p, p + 0.2, p - 0.2, p + 0.1) for i, p in enumerate(prices)]
    ts = st.trend_state(candles)
    assert ts.direction == 1


def test_support_resistance_levels():
    from app.core import indicators as ind
    prices = []
    for i in range(120):
        base = 100 if i % 20 < 10 else 105     # oscila entre 100 e 105
        prices.append(base + (i % 3) * 0.1)
    candles = [Candle(i, p, p + 0.4, p - 0.4, p) for i, p in enumerate(prices)]
    atr = ind.atr([c.high for c in candles], [c.low for c in candles],
                  [c.close for c in candles], 14)
    levels = st.support_resistance(candles, atr_series=atr)
    assert len(levels) >= 2


def test_consolidation_detect():
    candles = [Candle(i, 10.0, 10.1, 9.9, 10.02) for i in range(40)]
    from app.core import indicators as ind
    atr = ind.atr([c.high for c in candles], [c.low for c in candles],
                  [c.close for c in candles], 14)
    zone = st.consolidation_zone(candles, 20, atr_series=atr)
    assert zone is not None
