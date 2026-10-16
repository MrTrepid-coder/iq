"""Detecção de padrões de velas com regras objetivas (sem semântica visual).

Cada detector opera sobre um índice i e usa apenas candles visíveis até i.
Retorna PatternMatch | None.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .candles import Candle


@dataclass(frozen=True)
class PatternMatch:
    name: str            # identificador canônico
    direction: int       # +1 bullish, -1 bearish, 0 neutro
    index: int           # índice do candle de confirmação
    strength: float      # 0..1 (quão representativo é o padrão)
    description: str


def _rng(c: Candle) -> float:
    return c.range_ if c.range_ > 0 else 1e-12


# --------------------------------------------------------------------------- #
# Engolfo
# --------------------------------------------------------------------------- #
def engulfing(candles: Sequence[Candle], i: int) -> Optional[PatternMatch]:
    """Engolfo de alta/baixa: corpo do candle i engole o corpo do candle i-1,
    com direções opostas e corpo mínimo razoável (>= 50% do range)."""
    if i < 1:
        return None
    prev, cur = candles[i - 1], candles[i]
    if prev.direction == 0 or cur.direction == 0 or prev.direction == cur.direction:
        return None
    if cur.body < 0.5 * cur.range_:
        return None
    if cur.body <= prev.body:
        return None
    cur_top, cur_bot = max(cur.open, cur.close), min(cur.open, cur.close)
    prev_top, prev_bot = max(prev.open, prev.close), min(prev.open, prev.close)
    if cur_top <= prev_top or cur_bot >= prev_bot:
        return None
    strength = min(1.0, cur.body / _rng(prev))
    if cur.direction == 1:
        return PatternMatch("engulfing_bull", 1, i, strength,
                            "Engolfo de alta: corpo atual engole o corpo anterior (direção oposta).")
    return PatternMatch("engulfing_bear", -1, i, strength,
                        "Engolfo de baixa: corpo atual engole o corpo anterior (direção oposta).")


# --------------------------------------------------------------------------- #
# Pin bar / rejeição
# --------------------------------------------------------------------------- #
def pin_bar(candles: Sequence[Candle], i: int) -> Optional[PatternMatch]:
    """Pin bar: sombra >= 2x o corpo e >= 60% do range; corpo na extremidade oposta.
    Sombra inferior longa => rejeição de baixa (bullish); superior longa => bearish."""
    c = candles[i]
    if c.range_ <= 0 or c.body > 0.5 * c.range_:
        return None
    if c.lower_shadow >= 2.0 * c.body and c.lower_shadow >= 0.6 * c.range_ and c.upper_shadow < c.lower_shadow:
        strength = min(1.0, c.lower_shadow / (2.0 * _rng(c)))
        return PatternMatch("pin_bar_bull", 1, i, strength,
                            "Pin bar com rejeição de baixa: sombra inferior longa em relação ao corpo.")
    if c.upper_shadow >= 2.0 * c.body and c.upper_shadow >= 0.6 * c.range_ and c.upper_shadow > c.lower_shadow:
        strength = min(1.0, c.upper_shadow / (2.0 * _rng(c)))
        return PatternMatch("pin_bar_bear", -1, i, strength,
                            "Pin bar com rejeição de alta: sombra superior longa em relação ao corpo.")
    return None


# --------------------------------------------------------------------------- #
# Doji
# --------------------------------------------------------------------------- #
def doji(candles: Sequence[Candle], i: int) -> Optional[PatternMatch]:
    """Doji: corpo <= 10% do range e range > 0 (mercado em equilíbrio/indecisão)."""
    c = candles[i]
    if c.range_ <= 0:
        return None
    if c.body <= 0.10 * c.range_:
        return PatternMatch("doji", 0, i, 1.0 - (c.body / _rng(c)),
                            "Doji: corpo mínimo em relação ao range — indecisão.")
    return None


# --------------------------------------------------------------------------- #
# Martelo / martelo invertido
# --------------------------------------------------------------------------- #
def hammer(candles: Sequence[Candle], i: int) -> Optional[PatternMatch]:
    """Martelo: sombra inferior >= 2x corpo, sombra superior <= 30% do range,
    corpo na parte superior. Relevante apenas após queda recente (contexto).
    Martelo invertido: espelhado, relevante após alta recente."""
    c = candles[i]
    if c.range_ <= 0 or c.body == 0:
        return None
    if (c.lower_shadow >= 2.0 * c.body and c.upper_shadow <= 0.3 * c.range_
            and min(c.open, c.close) >= c.low + 0.65 * c.range_):
        if _recent_fall(candles, i):
            return PatternMatch("hammer", 1, i, min(1.0, c.lower_shadow / (2.0 * _rng(c))),
                                "Martelo: rejeição de baixa após sequência de quedas.")
        return None
    if (c.upper_shadow >= 2.0 * c.body and c.lower_shadow <= 0.3 * c.range_
            and max(c.open, c.close) <= c.high - 0.65 * c.range_):
        if _recent_rise(candles, i):
            return PatternMatch("inverted_hammer", -1, i, min(1.0, c.upper_shadow / (2.0 * _rng(c))),
                                "Martelo invertido: rejeição de alta após sequência de altas.")
        return None
    return None


# --------------------------------------------------------------------------- #
# Estrela cadente (shooting star / falling star)
# --------------------------------------------------------------------------- #
def shooting_star(candles: Sequence[Candle], i: int) -> Optional[PatternMatch]:
    """Estrela cadente: corpo pequeno no baixo, sombra superior >= 2x corpo,
    após alta recente. Estrela da manhã (reversão de baixa) é o oposto, após queda."""
    c = candles[i]
    if c.range_ <= 0 or c.body == 0:
        return None
    if (c.upper_shadow >= 2.0 * c.body and c.upper_shadow >= 0.6 * c.range_
            and c.lower_shadow <= 0.2 * c.range_):
        if _recent_rise(candles, i):
            return PatternMatch("shooting_star", -1, i, min(1.0, c.upper_shadow / (2.0 * _rng(c))),
                                "Estrela cadente: rejeição de alta após movimento ascendente.")
        return None
    if (c.lower_shadow >= 2.0 * c.body and c.lower_shadow >= 0.6 * c.range_
            and c.upper_shadow <= 0.2 * c.range_):
        if _recent_fall(candles, i):
            return PatternMatch("morning_star_doji", 1, i, min(1.0, c.lower_shadow / (2.0 * _rng(c))),
                                "Estrela da manhã (doji): rejeição de baixa após movimento descendente.")
        return None
    return None


# --------------------------------------------------------------------------- #
# Harami
# --------------------------------------------------------------------------- #
def harami(candles: Sequence[Candle], i: int) -> Optional[PatternMatch]:
    """Harami: corpo do candle i contido no corpo do candle i-1, corpo i menor,
    direções opostas."""
    if i < 1:
        return None
    prev, cur = candles[i - 1], candles[i]
    if prev.direction == 0 or cur.direction == 0 or prev.direction == cur.direction:
        return None
    if cur.body >= prev.body:
        return None
    cur_top, cur_bot = max(cur.open, cur.close), min(cur.open, cur.close)
    prev_top, prev_bot = max(prev.open, prev.close), min(prev.open, prev.close)
    if cur_top < prev_top and cur_bot > prev_bot:
        strength = 1.0 - (cur.body / _rng(prev))
        d = 1 if prev.direction == -1 else -1
        name = "harami_bull" if d == 1 else "harami_bear"
        desc = ("Harami de alta: corpo pequeno dentro do corpo anterior de baixa."
                if d == 1 else
                "Harami de baixa: corpo pequeno dentro do corpo anterior de alta.")
        return PatternMatch(name, d, i, strength, desc)
    return None


# --------------------------------------------------------------------------- #
# Sequência de força
# --------------------------------------------------------------------------- #
def strength_sequence(candles: Sequence[Candle], i: int, min_len: int = 3,
                      body_ratio: float = 0.5) -> Optional[PatternMatch]:
    """Sequência de candles de força: >= min_len candles consecutivos na mesma
    direção, cada corpo >= body_ratio do próprio range."""
    if i + 1 < min_len:
        return None
    seq = [candles[j] for j in range(i - min_len + 1, i + 1)]
    dirs = {c.direction for c in seq}
    if len(dirs) != 1 or 0 in dirs:
        return None
    if not all(c.body >= body_ratio * c.range_ for c in seq if c.range_ > 0):
        return None
    d = seq[0].direction
    total = sum(c.body for c in seq)
    avg_rng = sum(c.range_ for c in seq) / min_len
    strength = min(1.0, total / (min_len * avg_rng)) if avg_rng > 0 else 0.0
    name = "strength_up" if d == 1 else "strength_down"
    desc = (f"Sequência de {min_len} candles de força de alta (corpos dominantes)."
            if d == 1 else
            f"Sequência de {min_len} candles de força de baixa (corpos dominantes).")
    return PatternMatch(name, d, i, strength, desc)


# --------------------------------------------------------------------------- #
# Contexto auxiliar
# --------------------------------------------------------------------------- #
def _recent_fall(candles: Sequence[Candle], i: int, lookback: int = 5) -> bool:
    if i < lookback:
        return False
    return candles[i].open < candles[i - lookback].close


def _recent_rise(candles: Sequence[Candle], i: int, lookback: int = 5) -> bool:
    if i < lookback:
        return False
    return candles[i].open > candles[i - lookback].close


ALL_PATTERNS = (engulfing, pin_bar, doji, hammer, shooting_star, harami)


def detect_all(candles: Sequence[Candle], i: int) -> list[PatternMatch]:
    """Aplica todos os detectores no índice i e retorna os matches."""
    out: list[PatternMatch] = []
    for fn in ALL_PATTERNS:
        m = fn(candles, i)
        if m is not None:
            out.append(m)
    seq = strength_sequence(candles, i)
    if seq is not None:
        out.append(seq)
    return out
