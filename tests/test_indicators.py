"""Testes do motor de candles e indicadores."""
import math
import pytest

from app.core.candles import Candle, CandleSeries, synthetic_series
from app.core import indicators as ind


def test_candle_validation():
    c = Candle(0, 10, 12, 9, 11)
    assert c.is_valid()
    bad = Candle(0, 10, 11, 10.5, 12)  # high < close
    assert not bad.is_valid()


def test_series_ordering():
    cs = [Candle(100, 1, 2, 0.5, 1.5), Candle(50, 1, 2, 0.5, 1.5)]
    with pytest.raises(ValueError):
        CandleSeries(cs)


def test_sma_basic():
    out = ind.sma([1, 2, 3, 4, 5], 3)
    assert math.isnan(out[0]) and math.isnan(out[1])
    assert out[2] == pytest.approx(2.0)
    assert out[4] == pytest.approx(4.0)


def test_ema_uses_only_past():
    a = ind.ema([1, 2, 3, 4, 5], 3)
    b = ind.ema([1, 2, 3, 4, 999], 3)
    # valores antes do índice final não mudam quando o futuro muda
    assert a[3] == pytest.approx(b[3])


def test_rsi_range_and_extremes():
    up = list(range(1, 40))
    r = ind.rsi(up, 14)
    assert r[-1] == pytest.approx(100.0)
    down = list(range(40, 1, -1))
    r2 = ind.rsi(down, 14)
    assert r2[-1] == pytest.approx(0.0, abs=1e-9)


def test_macd_no_lookahead():
    vals = [1 + 0.01 * i for i in range(80)]
    a = ind.macd(vals)
    vals2 = vals[:60] + [100.0] * 20
    b = ind.macd(vals2)
    assert a[0][50] == pytest.approx(b[0][50])


def test_bollinger_shape():
    vals = [1.0 + 0.001 * ((i % 7) - 3) for i in range(100)]
    mid, up, lo, bw, pctb = ind.bollinger(vals, 20, 2.0)
    i = 50
    assert up[i] > mid[i] > lo[i]
    assert 0 <= pctb[i] <= 1


def test_atr_positive():
    n = 60
    highs = [10 + (i % 5) + 1 for i in range(n)]
    lows = [10 + (i % 5) - 1 for i in range(n)]
    closes = [10 + (i % 5) for i in range(n)]
    a = ind.atr(highs, lows, closes, 14)
    assert not math.isnan(a[-1])
    assert a[-1] > 0


def test_adx_trending_market():
    n = 80
    closes = [100 + i * 0.5 for i in range(n)]       # forte tendência de alta
    highs = [c + 0.3 for c in closes]
    lows = [c - 0.3 for c in closes]
    adx, pdi, ndi = ind.adx(highs, lows, closes, 14)
    assert not math.isnan(adx[-1])
    assert pdi[-1] > ndi[-1]      # DI+ domina em alta


def test_vwap_zero_volume_is_nan():
    n = 10
    out = ind.vwap([1] * n, [1] * n, [1] * n, [0] * n)
    assert all(math.isnan(v) for v in out)


def test_window_no_lookahead():
    s = synthetic_series(300)
    w1 = s.window(100)
    assert len(w1) == 100
    assert w1[99].ts == s[99].ts


def test_resample_ohlc():
    s = synthetic_series(100, timeframe_s=60)
    r = s.resample(5)
    assert len(r) == 20
    assert r[0].high == max(c.high for c in s.candles[0:5])
    assert r[0].close == s[4].close
    assert r.timeframe_s == 300
