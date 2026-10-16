"""Estrutura de mercado: tendência, swing points, suporte/resistência,
consolidação, rompimentos e regime de volatilidade.

Princípio anti-lookahead: todas as funções recebem uma lista visível
(janela histórica) e retornam resultado válido apenas para o último candle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from .candles import Candle
from . import indicators as ind


@dataclass(frozen=True)
class SwingPoint:
    index: int
    price: float
    kind: str          # "high" | "low"
    confirmed: bool    # confirmado => ponto já não pode ser repintado


@dataclass(frozen=True)
class TrendState:
    direction: int          # +1 alta, -1 baixa, 0 lateral
    strength: float         # 0..1
    hh_hl: bool             # highs e lows ascendentes
    lh_ll: bool             # highs e lows descendentes
    ema_aligned: bool       # EMA9 > EMA21 > EMA50 (ou inverso)
    adx: float              # NaN se indisponível
    losing_force: bool      # tendência perdeu força (divergência de slope)
    description: str


@dataclass(frozen=True)
class Level:
    price: float
    kind: str               # "support" | "resistance"
    touches: int
    strength: float         # 0..1


@dataclass(frozen=True)
class Breakout:
    index: int
    direction: int          # +1 rompimento para cima
    level: float
    confirmed: bool         # fechamento além do nível (não apenas toque)
    retest: bool            # houve reteste posterior dentro da janela
    false_breakout: bool    # rompimento seguido de retorno ao interior


# --------------------------------------------------------------------------- #
# Swing points
# --------------------------------------------------------------------------- #
def find_swings(candles: Sequence[Candle], left: int = 2, right: int = 2) -> list[SwingPoint]:
    """Swing highs/lows fractais: candle é máximo/mínimo local com `left` e `right`
    candles ao redor. `confirmed=True` quando os `right` candles posteriores existem."""
    out: list[SwingPoint] = []
    n = len(candles)
    for i in range(left, n - right):
        c = candles[i]
        ch, cl = c.high, c.low
        is_high = True
        is_low = True
        for j in range(i - left, i + right + 1):
            if j == i:
                continue
            w = candles[j]
            if w.high > ch:
                is_high = False
            if w.low < cl:
                is_low = False
            if not is_high and not is_low:
                break
        if is_high:
            out.append(SwingPoint(i, ch, "high", True))
        if is_low:
            out.append(SwingPoint(i, cl, "low", True))
    # ponto no fim ainda não confirmado (right candles não existem) — marcado como não confirmado
    if n > left:
        i = n - 1
        c = candles[i]
        is_high = True
        is_low = True
        for j in range(max(0, i - left), i):
            w = candles[j]
            if w.high > c.high:
                is_high = False
            if w.low < c.low:
                is_low = False
        if is_high:
            out.append(SwingPoint(i, c.high, "high", False))
        if is_low:
            out.append(SwingPoint(i, c.low, "low", False))
    out.sort(key=lambda s: s.index)
    return out


# --------------------------------------------------------------------------- #
# Tendência
# --------------------------------------------------------------------------- #
def trend_state(candles: Sequence[Candle], adx_series: Optional[np.ndarray] = None,
                swings: Optional[Sequence[SwingPoint]] = None,
                ema9_arr: Optional[np.ndarray] = None,
                ema21_arr: Optional[np.ndarray] = None,
                ema50_arr: Optional[np.ndarray] = None,
                slope_arr: Optional[np.ndarray] = None) -> TrendState:
    """Classifica tendência por estrutura (HH/HL vs LH/LL), alinhamento de EMAs,
    slope e força (ADX quando disponível).

    `ema9_arr/ema21_arr/ema50_arr/slope_arr` permitem injetar arrays causais
    pré-calculados (evita recomputar em loop de backtest).
    """
    closes = [c.close for c in candles]
    n = len(closes)
    if n < 30:
        return TrendState(0, 0.0, False, False, False, float("nan"), False,
                          "Dados insuficientes para classificar tendência.")

    if swings is None:
        swings = find_swings(candles)
    swings = [s for s in swings if s.confirmed]
    highs = [s.price for s in swings if s.kind == "high"]
    lows = [s.price for s in swings if s.kind == "low"]

    hh_hl = _is_asc(highs, min_pts=2) and _is_asc(lows, min_pts=2)
    lh_ll = _is_desc(highs, min_pts=2) and _is_desc(lows, min_pts=2)

    ema9 = ema9_arr if ema9_arr is not None else ind.ema(closes, 9)
    ema21 = ema21_arr if ema21_arr is not None else ind.ema(closes, 21)
    ema50 = ema50_arr if ema50_arr is not None else ind.ema(closes, 50)
    last = n - 1
    up_aligned = (not np.isnan(ema9[last]) and not np.isnan(ema21[last])
                  and not np.isnan(ema50[last])
                  and ema9[last] > ema21[last] > ema50[last])
    down_aligned = (not np.isnan(ema9[last]) and not np.isnan(ema21[last])
                    and not np.isnan(ema50[last])
                    and ema9[last] < ema21[last] < ema50[last])

    sl = slope_arr if slope_arr is not None else ind.slope(closes, 10)
    sl_last = float(sl[last]) if not np.isnan(sl[last]) else 0.0
    sl_prev = float(sl[last - 5]) if last >= 5 and not np.isnan(sl[last - 5]) else None

    adx_val = float("nan")
    strong_adx = False
    if adx_series is not None and len(adx_series) == n and not np.isnan(adx_series[last]):
        adx_val = float(adx_series[last])
        strong_adx = adx_val >= 20.0

    # perda de força: ADX caindo enquanto preço ainda em tendência, ou slope
    # reduzindo de forma relevante
    losing_force = False
    if adx_series is not None and len(adx_series) == n and last >= 5:
        if (not np.isnan(adx_series[last]) and not np.isnan(adx_series[last - 5])
                and adx_series[last] < adx_series[last - 5] - 3.0):
            losing_force = True
    if sl_prev is not None and abs(sl_last) < 0.3 * abs(sl_prev):
        losing_force = True

    direction = 0
    if hh_hl and (up_aligned or sl_last > 0):
        direction = 1
    elif lh_ll and (down_aligned or sl_last < 0):
        direction = -1
    elif up_aligned and sl_last > 0:
        direction = 1
    elif down_aligned and sl_last < 0:
        direction = -1

    score = 0.0
    if hh_hl or lh_ll:
        score += 0.35
    if up_aligned or down_aligned:
        score += 0.30
    if strong_adx:
        score += 0.20
    if abs(sl_last) > 0.0005:
        score += 0.15
    if losing_force:
        score *= 0.6
    score = float(min(1.0, score))
    if direction == 0:
        score *= 0.5

    desc_map = {1: "tendência de alta", -1: "tendência de baixa", 0: "lateralização"}
    return TrendState(direction, score, hh_hl, lh_ll, bool(up_aligned or down_aligned),
                      adx_val, losing_force,
                      f"{desc_map[direction]} (força {score:.2f})"
                      + ("; perda de força detectada" if losing_force else ""))


def _is_asc(vals: Sequence[float], min_pts: int = 2) -> bool:
    if len(vals) < min_pts:
        return False
    recent = vals[-min_pts:]
    return all(recent[i] < recent[i + 1] for i in range(len(recent) - 1))


def _is_desc(vals: Sequence[float], min_pts: int = 2) -> bool:
    if len(vals) < min_pts:
        return False
    recent = vals[-min_pts:]
    return all(recent[i] > recent[i + 1] for i in range(len(recent) - 1))


# --------------------------------------------------------------------------- #
# Suporte e resistência
# --------------------------------------------------------------------------- #
def support_resistance(candles: Sequence[Candle], max_levels: int = 4,
                       cluster_tol_atr: float = 0.5,
                       atr_series: Optional[np.ndarray] = None,
                       swings: Optional[Sequence[SwingPoint]] = None) -> list[Level]:
    """Suportes/ resistências por clusterização de swing points.

    Toleraância de agrupamento = cluster_tol_atr * ATR recente.
    """
    closes = [c.close for c in candles]
    last = len(closes) - 1
    if atr_series is not None and len(atr_series) == last + 1 and not np.isnan(atr_series[last]):
        tol = cluster_tol_atr * float(atr_series[last])
    else:
        rng = np.asarray(closes[-50:], dtype=float)
        tol = cluster_tol_atr * float(np.std(rng)) if len(rng) > 2 else 0.0
    if tol <= 0:
        return []

    swings = [s for s in (swings if swings is not None else find_swings(candles)) if s.confirmed]
    if not swings:
        return []
    # clusterização em passada única sobre swings ordenados por preço (O(s log s))
    ordered = sorted(swings, key=lambda x: x.price)
    clusters: list[list] = []
    for s in ordered:
        if clusters and s.price - clusters[-1][-1].price <= tol:
            clusters[-1].append(s)
        else:
            clusters.append([s])
    levels: list[Level] = []
    for cluster in clusters:
        price = float(np.mean([c.price for c in cluster]))
        touches = len(cluster)
        strength = min(1.0, touches / 4.0)
        # O tipo do nível vem da NATUREZA dos swing points que o formam
        # (topos => resistência; fundos => suporte) — e NÃO da posição do preço
        # atual em relação ao último fechamento.
        #
        # Definir o tipo pela posição relativa ao último fechamento tornava o
        # rompimento impossível de validar (tautologia): se `kind` é "resistance"
        # então price > last_close, logo o fechamento atual está SEMPRE abaixo do
        # nível e qualquer rompimento de alta detectado em candles anteriores
        # apareceria como falso; simetricamente para "support". O resultado era
        # todo rompimento classificado como falso e a Estratégia C zerada.
        n_high = sum(1 for s in cluster if s.kind == "high")
        n_low = len(cluster) - n_high
        kind = "resistance" if n_high >= n_low else "support"
        levels.append(Level(price, kind, touches, strength))

    levels.sort(key=lambda l: -l.strength)
    levels = levels[:max_levels]
    levels.sort(key=lambda l: l.price)
    return levels


def consolidation_zone(candles: Sequence[Candle], lookback: int = 20,
                       atr_mult: float = 1.5,
                       atr_series: Optional[np.ndarray] = None) -> Optional[tuple]:
    """Zona de consolidação: range das últimas `lookback` barras estreito
    (largura <= atr_mult * ATR). Retorna (low, high) ou None."""
    if len(candles) < lookback:
        return None
    recent = candles[-lookback:]
    hi = max(c.high for c in recent)
    lo = min(c.low for c in recent)
    width = hi - lo
    last = len(candles) - 1
    if atr_series is not None and len(atr_series) == last + 1 and not np.isnan(atr_series[last]):
        atr_val = float(atr_series[last])
    else:
        atr_val = float(np.mean([c.range_ for c in recent]))
    if atr_val <= 0:
        return None
    if width <= atr_mult * atr_val:
        return (lo, hi)
    return None


# --------------------------------------------------------------------------- #
# Rompimento e reteste
# --------------------------------------------------------------------------- #
def detect_breakout(candles: Sequence[Candle], levels: Sequence[Level],
                    atr_val: float, lookback: int = 3) -> Optional[Breakout]:
    """Detecta o rompimento mais recente (até `lookback` candles atrás) de um nível.

    Classifica corretamente:
    - `confirmed`: fechamento além do nível por >= 0.25*ATR no candle do rompimento;
    - `retest`: após o rompimento, o preço voltou perto do nível (<= 0.5*ATR) e
      fechou ainda do lado rompido (defesa do nível);
    - `false_breakout`: após o rompimento, algum candle FECHOU de volta para o
      interior do nível (rompimento falhou).

    Correção de bug: a versão anterior avaliava `false_breakout` num intervalo
    `range(last+1, len(candles))` sempre vazio (o rompimento era detectado no
    último candle), então falsos rompimentos nunca eram identificados.
    """
    if not levels or atr_val <= 0 or len(candles) < 4:
        return None
    last = len(candles) - 1
    start = max(1, last - lookback + 1)
    for j in range(last, start - 1, -1):
        cur = candles[j]
        prev = candles[j - 1]
        for lvl in levels:
            direction = 0
            if cur.close > lvl.price and prev.close <= lvl.price:
                direction = 1
            elif cur.close < lvl.price and prev.close >= lvl.price:
                direction = -1
            if direction == 0:
                continue
            # Respeita o TIPO do nível: resistência rompe para cima, suporte para
            # baixo. Sem isso, o candle de RETORNO ao interior seria lido como um
            # rompimento no sentido oposto.
            if lvl.kind == "resistance" and direction != 1:
                continue
            if lvl.kind == "support" and direction != -1:
                continue
            if direction == 1:
                confirmed = cur.close > lvl.price + 0.25 * atr_val
            else:
                confirmed = cur.close < lvl.price - 0.25 * atr_val
            false_break = False
            retest = False
            for k in range(j + 1, last + 1):        # candles POSTERIORES ao rompimento
                c = candles[k]
                if direction == 1:
                    if c.close < lvl.price:
                        false_break = True
                    if abs(c.low - lvl.price) <= 0.5 * atr_val and c.close > lvl.price:
                        retest = True
                else:
                    if c.close > lvl.price:
                        false_break = True
                    if abs(c.high - lvl.price) <= 0.5 * atr_val and c.close < lvl.price:
                        retest = True
            return Breakout(j, direction, lvl.price, confirmed, retest, false_break)
    return None


# --------------------------------------------------------------------------- #
# Regime de volatilidade
# --------------------------------------------------------------------------- #
def volatility_regime(atr_series: Sequence[float], lookback: int = 50) -> str:
    """Classifica regime: 'baixa', 'normal', 'alta', 'anormal' (ATR extremo)."""
    vals = [v for v in atr_series if not np.isnan(v)]
    if len(vals) < lookback // 2:
        return "indisponível"
    recent = vals[-lookback:]
    med = float(np.median(recent))
    if med <= 0:
        return "indisponível"
    cur = vals[-1]
    ratio = cur / med
    if ratio < 0.6:
        return "baixa"
    if ratio > 2.5:
        return "anormal"
    if ratio > 1.6:
        return "alta"
    return "normal"
