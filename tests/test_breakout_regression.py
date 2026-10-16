"""Regressão: detecção de rompimento e falso rompimento.

Bug corrigido: `detect_breakout` avaliava `false_breakout` num intervalo sempre
vazio (`range(last + 1, len)`), então falsos rompimentos NUNCA eram detectados.
Correção secundária: respeitar o tipo do nível (resistência rompe para cima,
suporte para baixo), evitando que o candle de RETORNO seja lido como rompimento.
"""
from app.core.candles import Candle
from app.core.structure import Level, detect_breakout


def _c(o, h, l, cl, ts):
    return Candle(ts, o, h, l, cl)


def test_confirmed_breakout_up():
    lvl = Level(100.0, "resistance", 3, 0.75)
    candles = [
        _c(99, 99.5, 98, 99.0, 0),
        _c(99, 99.5, 98, 99.2, 60),
        _c(99.2, 99.6, 98.8, 99.4, 120),
        _c(99.4, 103, 99, 102.5, 180),   # fecha bem acima do nível
    ]
    brk = detect_breakout(candles, [lvl], atr_val=1.0)
    assert brk is not None
    assert brk.direction == 1
    assert brk.confirmed is True
    assert brk.false_breakout is False


def test_false_breakout_detected():
    lvl = Level(100.0, "resistance", 3, 0.75)
    candles = [
        _c(99, 99.5, 98, 99.0, 0),
        _c(99, 100.0, 98.5, 99.5, 60),
        _c(99.5, 102, 99, 101.2, 120),   # rompe (fecha > 100)
        _c(101, 101, 99, 99.0, 180),     # FECHA de volta abaixo do nível => falso
    ]
    brk = detect_breakout(candles, [lvl], atr_val=1.0)
    assert brk is not None
    assert brk.direction == 1
    assert brk.false_breakout is True


def test_retest_detected():
    lvl = Level(100.0, "resistance", 3, 0.75)
    candles = [
        _c(99, 99.5, 98, 99.0, 0),
        _c(99, 100.0, 98.5, 99.6, 60),
        _c(99.8, 103, 99.6, 102.2, 120),  # rompe confirmado
        _c(102, 102, 100.2, 101.4, 180),  # volta perto (low<=100.5) e fecha acima
    ]
    brk = detect_breakout(candles, [lvl], atr_val=1.0)
    assert brk is not None
    assert brk.retest is True
    assert brk.false_breakout is False


def test_breakout_down_false():
    lvl = Level(100.0, "support", 3, 0.75)
    candles = [
        _c(101, 102, 100.5, 101.0, 0),
        _c(101, 101.5, 100.0, 100.5, 60),
        _c(100.5, 101, 98.5, 99.0, 120),   # rompe abaixo (fecha < 99.75)
        _c(99, 101, 99, 100.8, 180),        # fecha de volta acima => falso
    ]
    brk = detect_breakout(candles, [lvl], atr_val=1.0)
    assert brk is not None
    assert brk.direction == -1
    assert brk.false_breakout is True


def test_no_breakout_returns_none():
    lvl = Level(100.0, "resistance", 3, 0.75)
    candles = [_c(99, 99.5, 98, 99.0, i * 60) for i in range(5)]
    assert detect_breakout(candles, [lvl], atr_val=1.0) is None


def test_false_breakout_can_be_true_regression_for_dead_loop():
    """Garante que o bug do loop morto não volte: false_breakout DEVE poder ser True."""
    lvl = Level(100.0, "resistance", 3, 0.75)
    candles = [
        _c(99, 99.5, 98, 99.0, 0),
        _c(99, 100.0, 98.5, 99.4, 60),
        _c(99.4, 101.5, 99, 101.0, 120),
        _c(101, 101, 98, 98.5, 180),
    ]
    brk = detect_breakout(candles, [lvl], atr_val=1.0)
    assert brk is not None and brk.false_breakout is True


# --------------------------------------------------------------------------- #
# Regressão da TAUTOLOGIA de falso rompimento
#
# `Level.kind` era derivado da posição do preço atual
# (`"resistance" if price > last_close else "support"`). Com isso, um nível
# classificado como resistência estava SEMPRE acima do último fechamento e um
# rompimento de alta detectado em candles anteriores acabava sempre classificado
# como falso (o fechamento atual nunca poderia estar acima). O resultado era
# `false_breakout=True` em 100% dos casos e a Estratégia C zerada.
#
# Correção: o tipo do nível vem da NATUREZA dos swings que o formam
# (topos => resistência; fundos => suporte).
# --------------------------------------------------------------------------- #
def test_level_kind_from_swing_nature_not_price_position():
    """Cluster de TOPOS deve ser resistência mesmo estando abaixo do preço atual."""
    import numpy as np
    from app.core.structure import support_resistance, SwingPoint

    candles = [_c(99, 100, 98, 99, i * 60) for i in range(5)]
    candles.append(_c(199, 201, 198, 200, 5 * 60))  # último fechamento MUITO acima
    atr = np.full(len(candles), 2.0)                # tol = 0.5 * 2.0 = 1.0
    swings = [SwingPoint(1, 100.0, "high", True), SwingPoint(3, 100.2, "high", True)]

    levels = support_resistance(candles, atr_series=atr, swings=swings)
    assert levels, "deveria produzir ao menos um nível"
    # posição diria 'support' (100 < 200); natureza do swing diz 'resistance'
    assert levels[0].kind == "resistance"


def test_level_kind_support_from_swing_lows_below_position():
    """Cluster de FUNDOS deve ser suporte mesmo estando acima do preço atual."""
    import numpy as np
    from app.core.structure import support_resistance, SwingPoint

    candles = [_c(199, 201, 198, 200, i * 60) for i in range(5)]
    candles.append(_c(101, 102, 99, 100, 5 * 60))   # último fechamento MUITO abaixo
    atr = np.full(len(candles), 2.0)
    swings = [SwingPoint(1, 300.0, "low", True), SwingPoint(3, 300.3, "low", True)]

    levels = support_resistance(candles, atr_series=atr, swings=swings)
    assert levels, "deveria produzir ao menos um nível"
    # posição diria 'resistance' (300 > 100); natureza do swing diz 'support'
    assert levels[0].kind == "support"


def test_breakouts_are_not_tautologically_false():
    """Em série realista, NEM todo rompimento pode ser falso.

    Guarda contra a regressão em que `kind` relativo ao preço fazia
    `false_breakout` ser sempre True.
    """
    from app.core.candles import synthetic_series
    from app.analysis.context import AnalysisContext, IndicatorCache
    from app.core import structure as st

    s = synthetic_series(n=500, seed=11)
    cache = IndicatorCache(s)
    total = 0
    false = 0
    for i in range(250, len(s)):
        ctx = AnalysisContext.build(s, i + 1, cache=cache)
        brk = st.detect_breakout(ctx.candles, ctx.levels, ctx.atr_val)
        if brk is None:
            continue
        total += 1
        false += 1 if brk.false_breakout else 0
    assert total > 0, "a série de teste deveria gerar rompimentos"
    assert false < total, (
        "todos os rompimentos foram classificados como falsos — tautologia "
        "de `Level.kind` (regressão)"
    )

