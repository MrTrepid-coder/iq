"""Estratégias independentes e testáveis (A–E).

Cada estratégia recebe um AnalysisContext (janela visível até o índice de
decisão) e retorna um StrategyResult com:
- direção proposta (+1 CALL, -1 PUT, 0 sem cenário)
- confirmações objetivas (lista de evidências)
- riscos/contradições (lista)
- condição de invalidação (texto objetivo)

Nenhuma estratégia força sinal: sem condições objetivas, retorna direção 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..analysis.context import AnalysisContext


@dataclass
class StrategyResult:
    strategy_id: str
    name: str
    direction: int                 # +1 CALL, -1 PUT, 0 AGUARDAR
    confirmations: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    invalidation: str = ""
    quality: float = 0.0           # 0..1 coerência interna (não é probabilidade)

    def add_conf(self, text: str, weight: float = 1.0) -> None:
        self.confirmations.append(text)

    def add_risk(self, text: str) -> None:
        self.risks.append(text)


def _ema_aligned(ctx: AnalysisContext, direction: int) -> bool:
    e9, e21, e50 = ctx.v(ctx.ema9), ctx.v(ctx.ema21), ctx.v(ctx.ema50)
    if any(np.isnan(x) for x in (e9, e21, e50)):
        return False
    if direction == 1:
        return e9 > e21 > e50
    return e9 < e21 < e50


# --------------------------------------------------------------------------- #
# Estratégia A — Continuação de tendência
# --------------------------------------------------------------------------- #
def strategy_trend_continuation(ctx: AnalysisContext) -> StrategyResult:
    """Regras de entrada (CALL em tendência de alta; PUT simétrico):
    1) tendência direcional com estrutura HH/HL (ou LH/LL) e EMAs alinhadas;
    2) ADX >= 20 quando disponível (força) e tendência sem perda de força;
    3) candle de decisão alinhado com a tendência (fecha do lado certo e
       além da EMA9);
    4) sem padrão de reversão forte no candle atual;
    5) sem consolidação estreita (zona) no momento.
    Invalidação: fechamento contra a direção por >= 1*ATR, ou perda da EMA21.
    """
    res = StrategyResult("A", "Continuação de tendência", 0)
    trend = ctx.trend
    if trend.direction == 0:
        res.add_risk("Sem tendência direcional definida.")
        return res
    if trend.losing_force:
        res.add_risk("Tendência apresentando perda de força.")
        return res
    d = trend.direction
    if not _ema_aligned(ctx, d):
        res.add_risk("EMAs 9/21/50 não alinhadas com a tendência.")
        return res
    res.add_conf(f"Estrutura {trend.description}.")
    if not np.isnan(ctx.v(ctx.adx14)):
        if ctx.v(ctx.adx14) < 20.0:
            res.add_risk(f"ADX baixo ({ctx.v(ctx.adx14):.1f}) — força insuficiente.")
            return res
        res.add_conf(f"ADX {ctx.v(ctx.adx14):.1f} confirma força da tendência.")
    # candle atual alinhado
    if ctx.cur.direction != d:
        res.add_risk("Candle de decisão não está alinhado com a tendência.")
        return res
    e9 = ctx.v(ctx.ema9)
    if not np.isnan(e9):
        if d == 1 and ctx.cur.close < e9:
            res.add_risk("Fechamento abaixo da EMA9 em tendência de alta.")
            return res
        if d == -1 and ctx.cur.close > e9:
            res.add_risk("Fechamento acima da EMA9 em tendência de baixa.")
            return res
        res.add_conf("Fechamento além da EMA9, a favor da tendência.")
    # sem reversão forte
    for m in ctx.patterns_with_direction(-d):
        if m.name in ("engulfing_bear", "engulfing_bull", "shooting_star", "pin_bar_bear", "pin_bar_bull"):
            res.add_risk(f"Padrão de reversão presente: {m.name}.")
            return res
    if ctx.zone is not None:
        res.add_risk("Mercado em zona de consolidação estreita.")
        return res
    if ctx.regime == "anormal":
        res.add_risk("Regime de volatilidade anormal.")
        return res
    res.direction = d
    res.quality = min(1.0, 0.3 * trend.strength + 0.3 + 0.2 * min(1.0, ctx.v(ctx.adx14) / 40 if not np.isnan(ctx.v(ctx.adx14)) else 0) + 0.2)
    res.invalidation = ("Fechamento contra a tendência por 1*ATR ou perda da EMA21 invalida o cenário.")
    return res


# --------------------------------------------------------------------------- #
# Estratégia B — Reversão em suporte/resistência
# --------------------------------------------------------------------------- #
def strategy_sr_reversal(ctx: AnalysisContext) -> StrategyResult:
    """Regras (CALL em suporte; PUT em resistência):
    1) preço tocando/encostando num nível relevante (distância <= 0.35*ATR);
    2) padrão de rejeição no candle atual (pin bar, hammer, engulfing, doji);
    3) perda de força do movimento anterior (RSI saindo de extremo OU MACD
       hist diminuindo OU ADX caindo);
    4) sem rompimento confirmado do nível.
    Invalidação: fechamento além do nível por 0.5*ATR.
    """
    res = StrategyResult("B", "Reversão em suporte/resistência", 0)
    dist_r = ctx.distance_to_level(-1)   # distância ao suporte abaixo (negativa se abaixo)
    dist_a = ctx.distance_to_level(1)    # resistência acima
    lvl_support = ctx.nearest_level(-1)
    lvl_res = ctx.nearest_level(1)

    at_zone = False
    direction = 0
    level_used = None
    if lvl_support is not None and dist_r is not None and 0 <= dist_r <= 0.35:
        at_zone, direction, level_used = True, 1, lvl_support
    if lvl_res is not None and dist_a is not None and 0 <= dist_a <= 0.35:
        at_zone, direction, level_used = True, -1, lvl_res
    if not at_zone or level_used is None:
        res.add_risk("Preço não está em zona relevante de suporte/resistência.")
        return res
    res.add_conf(f"Preço junto ao nível de {'suporte' if direction == 1 else 'resistência'} "
                 f"({level_used.touches} toques, força {level_used.strength:.2f}).")

    patterns_dir = ctx.patterns_with_direction(direction)
    if not patterns_dir:
        res.add_risk("Sem padrão de rejeição de preço no candle atual.")
        return res
    best = max(patterns_dir, key=lambda m: m.strength)
    res.add_conf(f"Padrão de rejeição: {best.description}")

    # perda de força do movimento anterior
    rsi_val = ctx.v(ctx.rsi14)
    losing = ctx.trend.losing_force
    rsi_extreme = (direction == 1 and not np.isnan(rsi_val) and rsi_val < 35) or \
                  (direction == -1 and not np.isnan(rsi_val) and rsi_val > 65)
    hist_now = ctx.v(ctx.macd_hist)
    hist_prev = float(ctx.macd_hist[-3]) if len(ctx.macd_hist) >= 3 and not np.isnan(ctx.macd_hist[-3]) else None
    macd_fading = hist_prev is not None and not np.isnan(hist_now) and \
        ((direction == 1 and hist_now > hist_prev) or (direction == -1 and hist_now < hist_prev))
    if losing:
        res.add_conf("Movimento anterior perdeu força (tendência enfraquecendo).")
    elif rsi_extreme:
        res.add_conf(f"RSI em zona extrema ({rsi_val:.1f}) — atenção à exaustão.")
    elif macd_fading:
        res.add_conf("Histograma MACD enfraquecendo contra o movimento anterior.")
    else:
        res.add_risk("Sem evidência de perda de força do movimento anterior.")
        return res

    # não operar reversão se há rompimento confirmado
    from ..core import structure as st
    if ctx.atr_val > 0:
        brk = st.detect_breakout(ctx.candles, [level_used], ctx.atr_val)
        if brk is not None and brk.confirmed:
            res.add_risk("Rompimento confirmado do nível — reversão invalidada.")
            return res

    if ctx.regime == "anormal":
        res.add_risk("Volatilidade anormal — reversão imprevisível.")
        return res
    res.direction = direction
    res.quality = min(1.0, 0.4 * level_used.strength + 0.3 * best.strength + 0.2 + 0.1 * (1 if losing else 0.5))
    res.invalidation = f"Fechamento além do nível por 0.5*ATR invalida o cenário."
    return res


# --------------------------------------------------------------------------- #
# Estratégia C — Rompimento e reteste
# --------------------------------------------------------------------------- #
def strategy_breakout_retest(ctx: AnalysisContext) -> StrategyResult:
    """Regras (CALL em rompimento de resistência; PUT em suporte):
    1) consolidação prévia identificável (zona ou banda de Bollinger estreita);
    2) rompimento com fechamento além do nível por >= 0.25*ATR (confirmado);
    3) reteste do nível com defesa (sombra no lado do nível, fecha do outro lado)
       OU candle de continuação pós-rompimento;
    4) volume (quando confiável) acima da média no rompimento.
    Invalidação: retorno ao interior da zona por 1 candle fechando dentro.
    """
    res = StrategyResult("C", "Rompimento e reteste", 0)
    from ..core import structure as st
    if ctx.atr_val <= 0 or not ctx.levels:
        res.add_risk("Sem níveis ou volatilidade para avaliar rompimento.")
        return res
    brk = st.detect_breakout(ctx.candles, ctx.levels, ctx.atr_val)
    if brk is None:
        res.add_risk("Sem rompimento recente de nível.")
        return res
    if brk.false_breakout:
        res.add_risk("Rompimento aparente classificado como falso.")
        return res
    d = brk.direction
    res.add_conf(f"Rompimento de {'resistência' if d == 1 else 'suporte'} em {brk.level:.6g}.")
    if not brk.confirmed:
        res.add_risk("Rompimento sem confirmação (fechamento além por 0.25*ATR).")
        return res
    res.add_conf("Fechamento além do nível com margem de 0.25*ATR — rompimento confirmado.")

    # contexto de consolidação prévia: banda de Bollinger estreita nos candles anteriores
    bw_series = ctx.bb_bw
    lookback_bw = [float(bw_series[j]) for j in range(max(0, len(bw_series) - 15), len(bw_series) - 1)
                   if not np.isnan(bw_series[j])]
    if lookback_bw:
        cur_bw = float(bw_series[-1]) if not np.isnan(bw_series[-1]) else None
        if cur_bw is not None and float(np.mean(lookback_bw)) > 0:
            if cur_bw > 1.6 * float(np.mean(lookback_bw)):
                res.add_conf("Abertura de bandas de Bollinger após período de compressão.")

    if brk.retest:
        res.add_conf("Candle atual no reteste do nível rompido (defesa do nível).")
        # defesa: sombra tocando o nível e fechando do lado do rompimento
        lvl_touch = abs(min(ctx.cur.open, ctx.cur.close) - brk.level) <= 0.5 * ctx.atr_val
        close_ok = ctx.cur.close > brk.level if d == 1 else ctx.cur.close < brk.level
        if lvl_touch and close_ok and ctx.cur.direction == d:
            res.add_conf("Defesa do nível no reteste (sombra + fechamento a favor).")
        else:
            res.add_risk("Candle de reteste sem defesa clara do nível.")
            return res
    else:
        # continuação pós-rompimento: candle atual alinhado, fecha além do nível
        if ctx.cur.direction != d:
            res.add_risk("Sem candle de continuação após o rompimento.")
            return res
        beyond = ctx.cur.close > brk.level if d == 1 else ctx.cur.close < brk.level
        if not beyond:
            res.add_risk("Candle atual voltou para dentro do nível rompido.")
            return res
        res.add_conf("Candle de continuação fechando além do nível rompido.")

    if ctx.zone is not None and brk.retest is False:
        # zona ainda presente pode indicar consolidação não resolvida
        pass
    if ctx.regime == "anormal":
        res.add_risk("Volatilidade anormal no momento do rompimento.")
        return res
    res.direction = d
    res.quality = min(1.0, 0.5 + 0.25 * (1 if brk.retest else 0.5) + 0.15 + 0.1)
    res.invalidation = "Fechamento de volta para dentro da zona consolidada invalida o rompimento."
    return res


# --------------------------------------------------------------------------- #
# Estratégia D — Reversão estatística (exaustão)
# --------------------------------------------------------------------------- #
def strategy_statistical_reversal(ctx: AnalysisContext) -> StrategyResult:
    """Regras (CALL em sobrevenda; PUT em sobrecompra):
    1) RSI extremo (< 28 ou > 72);
    2) distância do preço à banda de Bollinger correspondente (%B extremo);
    3) exaustão do impulso: MACD hist contratando OU slope caindo;
    4) NÃO operar em tendência forte direcional (ADX >= 30 com EMAs alinhadas
       e estrutura clara) — RSI extremo em tendência forte não é sinal;
    5) contexto de timeframe maior não contra o cenário.
    O RSI extremo NUNCA é sinal por si só.
    Invalidação: retomada do movimento com candle forte alinhado à tendência.
    """
    res = StrategyResult("D", "Reversão estatística (exaustão)", 0)
    rsi_val = ctx.v(ctx.rsi14)
    if np.isnan(rsi_val):
        res.add_risk("RSI indisponível.")
        return res
    pctb = ctx.v(ctx.bb_pctb)
    if np.isnan(pctb):
        res.add_risk("Bandas de Bollinger indisponíveis.")
        return res
    direction = 0
    if rsi_val < 28 and pctb < 0.05:
        direction = 1
    elif rsi_val > 72 and pctb > 0.95:
        direction = -1
    if direction == 0:
        res.add_risk("Sem exaustão estatística (RSI não extremo em conjunto com banda).")
        return res
    res.add_conf(f"RSI {rsi_val:.1f} com %B {pctb:.2f} — preço estatisticamente esticado.")

    # exaustão do impulso
    hist_now = ctx.v(ctx.macd_hist)
    hist_prev = float(ctx.macd_hist[-3]) if len(ctx.macd_hist) >= 3 and not np.isnan(ctx.macd_hist[-3]) else None
    fading = hist_prev is not None and not np.isnan(hist_now) and \
        ((direction == 1 and hist_now > hist_prev) or (direction == -1 and hist_now < hist_prev))
    if fading:
        res.add_conf("Histograma MACD contratando contra o movimento — exaustão.")
    else:
        sl = ctx.v(ind_np_slope(ctx))
        if not np.isnan(sl) and abs(sl) < 1e-6:
            res.add_conf("Slope do preço praticamente neutro — momentum em exaustão.")
        else:
            res.add_risk("Sem exaustão de momentum — movimento ainda forte.")
            return res

    # filtro de tendência forte
    e_aligned = _ema_aligned(ctx, direction * -1)
    if ctx.trend.direction == -direction and ctx.trend.strength >= 0.6:
        if not np.isnan(ctx.v(ctx.adx14)) and ctx.v(ctx.adx14) >= 30 and e_aligned:
            res.add_risk("Tendência forte contra o cenário — RSI extremo não é sinal aqui.")
            return res
        if e_aligned:
            res.add_risk("EMAs alinhadas contra o cenário — evitar reversão contra tendência.")
            return res

    # contexto de 5m
    if ctx.tf5m and ctx.tf5m.get("trend_dir") is not None:
        if ctx.tf5m["trend_dir"] == -direction:
            res.add_risk("Tendência de 5 minutos contra o cenário de reversão.")
            return res

    if ctx.regime == "anormal":
        res.add_risk("Volatilidade anormal — reversões estatísticas sem confiabilidade.")
        return res
    res.direction = direction
    res.quality = min(1.0, 0.35 + 0.25 * (1 if fading else 0.5) + 0.2 * min(1.0, (50 - abs(rsi_val - 50)) / 22) + 0.1)
    res.invalidation = "Candle forte alinhado à tendência anterior (corpo > 1*ATR) invalida a reversão."
    return res


def ind_np_slope(ctx: AnalysisContext):
    from ..core import indicators as ind
    return ind.slope(ctx.closes, 8)


# --------------------------------------------------------------------------- #
# Estratégia E — Confluência de sinais
# --------------------------------------------------------------------------- #
def strategy_confluence(ctx: AnalysisContext) -> StrategyResult:
    """Combina sinais parcialmente independentes:
    - tendência (estrutura + EMAs) — fonte 1
    - padrão de candle — fonte 2
    - momentum (MACD/RSI) — fonte 3
    - posição relativa a níveis (estrutura de preço) — fonte 4
    - contexto 5m — fonte 5
    Entrada exige >= 3 fontes independentes concordando na mesma direção e
    nenhuma fonte relevante contra. Confluência não substitui validação
    estatística — é filtro de qualidade.
    """
    res = StrategyResult("E", "Confluência de sinais", 0)
    votes = {1: [], -1: []}

    # fonte 1: tendência
    if ctx.trend.direction != 0 and ctx.trend.strength >= 0.45:
        votes[ctx.trend.direction].append(f"Tendência: {ctx.trend.description}")

    # fonte 2: padrões
    for d in (1, -1):
        ms = ctx.patterns_with_direction(d)
        strong = [m for m in ms if m.strength >= 0.6]
        if strong:
            votes[d].append(f"Padrão: {strong[0].description}")

    # fonte 3: momentum (MACD hist + RSI direção implícita)
    hist = ctx.v(ctx.macd_hist)
    if not np.isnan(hist) and abs(hist) > 0:
        votes[1 if hist > 0 else -1].append(f"MACD histogram {'positivo' if hist > 0 else 'negativo'}.")

    # fonte 4: posição em relação a níveis
    dist_r = ctx.distance_to_level(-1)
    dist_a = ctx.distance_to_level(1)
    if dist_r is not None and dist_a is not None:
        if dist_a > 1.0 and dist_r > 0.2:
            votes[1].append("Distância saudável até resistência; suporte próximo defensivo.")
        if dist_r > 1.0 and dist_a > 0.2:
            votes[-1].append("Distância saudável até suporte; resistência próxima.")

    # fonte 5: contexto 5m
    if ctx.tf5m and ctx.tf5m.get("trend_dir") in (1, -1):
        votes[ctx.tf5m["trend_dir"]].append(f"Contexto 5m: {ctx.tf5m['trend_desc']}")

    n_pos = len(votes[1])
    n_neg = len(votes[-1])
    best_dir = 1 if n_pos > n_neg else (-1 if n_neg > n_pos else 0)
    if best_dir == 0:
        res.add_risk("Sinais divididos ou insuficientes entre fontes independentes.")
        return res
    if max(n_pos, n_neg) < 3:
        res.add_risk(f"Apenas {max(n_pos, n_neg)} fonte(s) concordando — mínimo exigido: 3.")
        return res
    for txt in votes[best_dir]:
        res.add_conf(txt)
    other = -best_dir
    for txt in votes[other][:2]:
        res.add_risk(f"Contra: {txt}")
    res.direction = best_dir
    res.quality = min(1.0, 0.3 + 0.175 * max(n_pos, n_neg))
    res.invalidation = "Qualquer fonte que se inverte invalida a confluência."
    return res


ALL_STRATEGIES = (
    strategy_trend_continuation,
    strategy_sr_reversal,
    strategy_breakout_retest,
    strategy_statistical_reversal,
    strategy_confluence,
)
