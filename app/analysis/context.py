"""Contexto de análise: computa uma única vez todos os indicadores visíveis
no índice `end_exclusive` e o expõe às estratégias.

Garante a propriedade anti-lookahead: `AnalysisContext.build(series, i)`
usa somente candles[0..i].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..core.candles import Candle, CandleSeries
from ..core import indicators as ind
from ..core import patterns as pat
from ..core import structure as st


@dataclass
class AnalysisContext:
    index: int
    candles: list[Candle]
    closes: list[float]
    cur: Candle

    ema9: np.ndarray
    ema21: np.ndarray
    ema50: np.ndarray
    rsi14: np.ndarray
    macd_line: np.ndarray
    macd_signal: np.ndarray
    macd_hist: np.ndarray
    bb_mid: np.ndarray
    bb_upper: np.ndarray
    bb_lower: np.ndarray
    bb_bw: np.ndarray
    bb_pctb: np.ndarray
    atr14: np.ndarray
    adx14: np.ndarray
    pdi: np.ndarray
    ndi: np.ndarray
    vol20: np.ndarray

    trend: st.TrendState
    levels: list[st.Level]
    zone: Optional[tuple]
    regime: str
    pattern_matches: list[pat.PatternMatch]
    atr_val: float
    tf5m: Optional[dict] = field(default=None)   # contexto de timeframe maior

    @classmethod
    def build(cls, series: CandleSeries, end_exclusive: int,
              cache: Optional["IndicatorCache"] = None) -> "AnalysisContext":
        if end_exclusive < 60:
            raise ValueError("Contexto requer ao menos 60 candles visíveis "
                             "(end_exclusive >= 60).")
        candles = series.candles[:end_exclusive]
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        if cache is not None and cache.matches(series):
            # indicadores são causais: o valor no índice i não depende de dados
            # futuros, logo arrays pré-calculados no total podem ser fatiados.
            sl = slice(0, end_exclusive)
            ema9 = cache.ema9[sl]
            ema21 = cache.ema21[sl]
            ema50 = cache.ema50[sl]
            rsi14 = cache.rsi14[sl]
            m_line = cache.macd_line[sl]
            m_sig = cache.macd_signal[sl]
            m_hist = cache.macd_hist[sl]
            bb_mid = cache.bb_mid[sl]
            bb_up = cache.bb_upper[sl]
            bb_lo = cache.bb_lower[sl]
            bb_bw = cache.bb_bw[sl]
            bb_pctb = cache.bb_pctb[sl]
            atr14 = cache.atr14[sl]
            adx14 = cache.adx14[sl]
            pdi = cache.pdi[sl]
            ndi = cache.ndi[sl]
            vol20 = cache.vol20[sl]
        else:
            ema9 = ind.ema(closes, 9)
            ema21 = ind.ema(closes, 21)
            ema50 = ind.ema(closes, 50)
            rsi14 = ind.rsi(closes, 14)
            m_line, m_sig, m_hist = ind.macd(closes)
            bb_mid, bb_up, bb_lo, bb_bw, bb_pctb = ind.bollinger(closes, 20, 2.0)
            atr14 = ind.atr(highs, lows, closes, 14)
            adx14, pdi, ndi = ind.adx(highs, lows, closes, 14)
            vol20 = ind.rolling_volatility(closes, 20)

        if cache is not None and cache.matches(series):
            swings = cache.swings_until(end_exclusive)
            trend = st.trend_state(candles, adx14, swings=swings,
                                   ema9_arr=ema9, ema21_arr=ema21, ema50_arr=ema50,
                                   slope_arr=cache.slope10[sl])
        else:
            swings = st.find_swings(candles)
            trend = st.trend_state(candles, adx14, swings=swings)
        # limita S/R aos swing points das últimas ~300 velas (relevância + desempenho)
        recent_cut = end_exclusive - 300
        sr_swings = [s for s in swings if s.index >= recent_cut]
        levels = st.support_resistance(candles, atr_series=atr14, swings=sr_swings)
        zone = st.consolidation_zone(candles, atr_series=atr14)
        last = len(candles) - 1
        atr_val = float(atr14[last]) if not np.isnan(atr14[last]) else candles[last].range_
        regime = st.volatility_regime(list(atr14))
        matches = pat.detect_all(candles, last)

        ctx = cls(
            index=end_exclusive - 1,
            candles=candles,
            closes=closes,
            cur=candles[-1],
            ema9=ema9, ema21=ema21, ema50=ema50,
            rsi14=rsi14,
            macd_line=m_line, macd_signal=m_sig, macd_hist=m_hist,
            bb_mid=bb_mid, bb_upper=bb_up, bb_lower=bb_lo,
            bb_bw=bb_bw, bb_pctb=bb_pctb,
            atr14=atr14, adx14=adx14, pdi=pdi, ndi=ndi,
            vol20=vol20,
            trend=trend, levels=levels, zone=zone, regime=regime,
            pattern_matches=matches, atr_val=atr_val,
        )
        # contexto de 5m (quando há dados suficientes: >= 250 candles de 1m => 50 de 5m)
        if len(candles) >= 250:
            m5_trend_dir, m5_desc, m5_ema21 = _tf5_context(candles, end_exclusive, cache)
            if m5_trend_dir is not None:
                ctx.tf5m = {
                    "ema21": m5_ema21,
                    "trend_dir": m5_trend_dir,
                    "trend_desc": m5_desc,
                }
        return ctx

    # helpers de conveniência ------------------------------------------- #
    def v(self, arr: np.ndarray) -> float:
        """Valor atual (último) de um array de indicador, NaN-safe."""
        val = arr[-1]
        return float(val)

    def pattern(self, name: str) -> Optional[pat.PatternMatch]:
        for m in self.pattern_matches:
            if m.name == name:
                return m
        return None

    def patterns_with_direction(self, direction: int) -> list[pat.PatternMatch]:
        return [m for m in self.pattern_matches if m.direction == direction]

    def nearest_level(self, direction: int) -> Optional[st.Level]:
        """Nível mais próximo a favor do cenário: resistência acima (+1) ou
        suporte abaixo (-1)."""
        price = self.cur.close
        cands = [l for l in self.levels
                 if (direction == 1 and l.price > price) or (direction == -1 and l.price < price)]
        if not cands:
            return None
        return min(cands, key=lambda l: abs(l.price - price))

    def distance_to_level(self, direction: int) -> Optional[float]:
        lvl = self.nearest_level(direction)
        if lvl is None or self.atr_val <= 0:
            return None
        return (lvl.price - self.cur.close) / self.atr_val  # em unidades de ATR


class IndicatorCache:
    """Pré-calcula todos os indicadores causais uma única vez para a série
    completa. Como cada indicador no índice i depende apenas de dados[0..i],
    os arrays podem ser fatiados até qualquer `end_exclusive` sem vazamento
    (lookahead). Elimina o custo O(n²) do backtesting.
    """

    def __init__(self, series: CandleSeries):
        self._id = id(series)
        self._len = len(series)
        closes = [c.close for c in series.candles]
        highs = [c.high for c in series.candles]
        lows = [c.low for c in series.candles]
        self.ema9 = ind.ema(closes, 9)
        self.ema21 = ind.ema(closes, 21)
        self.ema50 = ind.ema(closes, 50)
        self.rsi14 = ind.rsi(closes, 14)
        self.macd_line, self.macd_signal, self.macd_hist = ind.macd(closes)
        (self.bb_mid, self.bb_upper, self.bb_lower,
         self.bb_bw, self.bb_pctb) = ind.bollinger(closes, 20, 2.0)
        self.atr14 = ind.atr(highs, lows, closes, 14)
        self.adx14, self.pdi, self.ndi = ind.adx(highs, lows, closes, 14)
        self.vol20 = ind.rolling_volatility(closes, 20)
        self.slope10 = ind.slope(closes, 10)
        # swing points confirmados calculados uma vez; para um prefixo ending em
        # `end_exclusive`, os swings confirmados são aqueles com índice <= end-1-right.
        self.swings_confirmed = [s for s in st.find_swings(series.candles) if s.confirmed]
        self._right = 2
        # arrays de 5m pré-calculados (causal em blocos de 5)
        from ..core.candles import _resample_list
        m5 = _resample_list(series.candles, 5)
        self.m5_closes = [c.close for c in m5]
        self.m5_ema9 = ind.ema(self.m5_closes, 9)
        self.m5_ema21 = ind.ema(self.m5_closes, 21)
        self.m5_ema50 = ind.ema(self.m5_closes, 50)
        self.m5_slope = ind.slope(self.m5_closes, 10)

    def swings_until(self, end_exclusive: int) -> list:
        limit = end_exclusive - 1 - self._right
        return [s for s in self.swings_confirmed if s.index <= limit]

    def matches(self, series: CandleSeries) -> bool:
        return self._id == id(series) and self._len == len(series)


def _tf5_context(candles, end_exclusive: int, cache):
    """Contexto de 5m (direção, descrição, ema21) usando apenas grupos COMPLETOS
    de 5 candles e arrays causais. Sem lookahead."""
    n_groups = end_exclusive // 5
    if n_groups < 52:
        return None, None, None
    i = n_groups - 1
    if cache is not None and getattr(cache, "m5_closes", None):
        e9, e21, e50 = cache.m5_ema9[i], cache.m5_ema21[i], cache.m5_ema50[i]
        sl = cache.m5_slope[i]
    else:
        # mesma matemática do cache, calculada apenas nos grupos COMPLETOS do prefixo
        m5_closes = [candles[k * 5 + 4].close for k in range(n_groups)]
        e9 = ind.ema(m5_closes, 9)[i]
        e21 = ind.ema(m5_closes, 21)[i]
        e50 = ind.ema(m5_closes, 50)[i]
        sl = ind.slope(m5_closes, 10)[i]
    ema21_val = float(e21) if not np.isnan(e21) else None
    direction = 0
    if not any(np.isnan(v) for v in (e9, e21, e50)):
        if e9 > e21 > e50 and (np.isnan(sl) or sl > 0):
            direction = 1
        elif e9 < e21 < e50 and (np.isnan(sl) or sl < 0):
            direction = -1
    desc = {1: "tendência de alta (5m)", -1: "tendência de baixa (5m)",
            0: "lateralização (5m)"}[direction]
    return direction, desc, ema21_val
