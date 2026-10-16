"""Filtro de qualidade e geração de sinais.

Aplica os 10 critérios do briefing antes de indicar CALL/PUT.
Produz SignalReport com estado explícito:
  - "sem_sinal"      : nenhuma estratégia produziu cenário
  - "aguardar"       : há cenário, mas o filtro reprovou
  - "sinal_detectado": filtro aprovou (modo análise)
  - "invalidado"     : sinal anterior que perdeu a condição de validade
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..analysis.context import AnalysisContext
from ..strategies import StrategyResult, ALL_STRATEGIES


@dataclass
class SignalReport:
    status: str                        # sem_sinal | aguardar | sinal_detectado
    direction: int                     # +1 CALL, -1 PUT, 0 indefinido
    strategy_id: str
    strategy_name: str
    asset: str
    timeframe_s: int
    context: str
    probability: Optional[float]       # None => "não calibrado"
    probability_note: str
    confidence_interval: Optional[tuple] = None
    confirmations: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    criteria: dict = field(default_factory=dict)
    invalidation: str = ""
    decision: str = ""                 # AVALIAR CALL | AVALIAR PUT | AGUARDAR
    expected_value: Optional[float] = None
    payout: Optional[float] = None

    def explain(self) -> str:
        lines = [
            f"ATIVO: {self.asset}",
            f"PERÍODO: {self.timeframe_s // 60} minuto(s)",
            f"CONTEXTO: {self.context}",
            f"ESTADO: {self.status.upper()}",
            f"CENÁRIO: {'CALL' if self.direction == 1 else 'PUT' if self.direction == -1 else 'NENHUM'}",
        ]
        if self.probability is None:
            lines.append(f"PROBABILIDADE ESTIMADA: {self.probability_note}")
        else:
            ci = (f" (IC95%: {self.confidence_interval[0]:.2f}–{self.confidence_interval[1]:.2f})"
                  if self.confidence_interval else "")
            lines.append(f"PROBABILIDADE ESTIMADA: {self.probability:.2f}{ci}")
        lines.append(f"ESTRATÉGIA: [{self.strategy_id}] {self.strategy_name}")
        if self.confirmations:
            lines.append("CONFIRMAÇÕES:")
            lines += [f"  + {c}" for c in self.confirmations]
        if self.risks:
            lines.append("RISCOS:")
            lines += [f"  - {r}" for r in self.risks]
        if self.invalidation:
            lines.append(f"VALIDADE DO SINAL: {self.invalidation}")
        lines.append(f"DECISÃO: {self.decision}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Critérios de qualidade
# --------------------------------------------------------------------------- #
def evaluate_criteria(ctx: AnalysisContext, res: StrategyResult,
                      min_data: int = 120) -> dict:
    """Os 10 critérios do briefing. True = aprovado, False = reprovado,
    None = não avaliável (dado ausente)."""
    c: dict[str, Optional[bool]] = {}
    c["1_dados_suficientes"] = len(ctx.candles) >= min_data
    c["2_tendencia_identificada"] = (ctx.trend.direction != 0 and ctx.trend.strength >= 0.3) \
        or res.strategy_id in ("B", "C", "D", "E")  # reversões podem operar em lateral, mas exige contexto
    dist_r = ctx.distance_to_level(-1)
    dist_a = ctx.distance_to_level(1)
    near = (dist_r is not None and abs(dist_r) <= 2.0) or (dist_a is not None and abs(dist_a) <= 2.0)
    c["3_srp_proximo"] = near
    c["4_volatilidade_adequada"] = ctx.regime in ("normal", "baixa")
    # 5: coerência dos indicadores com o cenário (MACD hist na direção)
    hist = ctx.v(ctx.macd_hist)
    if np.isnan(hist):
        c["5_indicadores_coerentes"] = None
    else:
        c["5_indicadores_coerentes"] = (hist > 0) == (res.direction == 1)
    c["6_confirmacao_objetiva"] = len(res.confirmations) >= 2 and res.direction != 0
    # 7 e 8 (validação da estratégia e calibração) são preenchidos pelo chamador
    # com dados do backtester; por padrão None.
    c["7_estrategia_validada"] = None
    c["8_probabilidade_calibrada"] = None
    c["9_expectativa_favoravel"] = None
    c["10_payout_considerado"] = None
    return c


def apply_payout(c: dict, direction: int, ctx: AnalysisContext,
                 payout: float, entry_price: float,
                 calibrated_prob: Optional[float]) -> dict:
    """Avalia critérios 7-10 quando payout e probabilidade calibrada existem."""
    c = dict(c)
    c["10_payout_considerado"] = True
    if calibrated_prob is not None:
        ev = calibrated_prob * payout - (1 - calibrated_prob)
        c["9_expectativa_favoravel"] = ev > 0
        c["8_probabilidade_calibrada"] = True
    else:
        c["9_expectativa_favoravel"] = None
        c["8_probabilidade_calibrada"] = False
    return c


# --------------------------------------------------------------------------- #
# Filtro principal
# --------------------------------------------------------------------------- #
def generate_signal(ctx: AnalysisContext, payout: float = 0.80,
                    model=None) -> SignalReport:
    """Executa todas as estratégias, aplica o filtro e monta o relatório.

    `model` (opcional): objeto com .predict_prob(features) -> float, usado
    apenas se estiver calibrado (model.calibrated == True).
    """
    results: list[StrategyResult] = [fn(ctx) for fn in ALL_STRATEGIES]
    with_dir = [r for r in results if r.direction != 0]

    asset = getattr(ctx, "asset", "") or "—"
    base = dict(status="sem_sinal", direction=0, strategy_id="", strategy_name="",
                asset=asset, timeframe_s=60, context=ctx.trend.description,
                probability=None, probability_note="dados insuficientes / sem cenário",
                decision="AGUARDAR")

    if not with_dir:
        rep = SignalReport(**base)
        rep.criteria = evaluate_criteria(ctx, results[0])
        rep.risks = [f"[{r.strategy_id}] {risk}" for r in results for risk in r.risks[:1]]
        rep.decision = "AGUARDAR"
        return rep

    # melhor cenário: maior qualidade; empate => confluência (E) > A > C > B > D
    prio = {"E": 5, "A": 4, "C": 3, "B": 2, "D": 1}
    best = max(with_dir, key=lambda r: (r.quality, prio.get(r.strategy_id, 0)))

    # conflito: estratégia melhor posicionada com direção oposta => aguardar
    conflicting = [r for r in with_dir if r.direction != best.direction and
                   prio.get(r.strategy_id, 0) >= prio.get(best.strategy_id, 0)]
    if conflicting:
        rep = SignalReport(**{**base, "status": "aguardar", "strategy_id": best.strategy_id,
                              "strategy_name": best.name, "direction": best.direction})
        rep.confirmations = best.confirmations
        rep.risks = [f"Conflito: [{r.strategy_id}] {r.name} indica direção oposta."
                     for r in conflicting] + best.risks
        rep.criteria = evaluate_criteria(ctx, best)
        rep.decision = "AGUARDAR"
        return rep

    rep = SignalReport(**{**base, "status": "sinal_detectado", "direction": best.direction,
                          "strategy_id": best.strategy_id, "strategy_name": best.name,
                          "context": ctx.trend.description})
    rep.confirmations = best.confirmations
    rep.risks = list(best.risks)
    rep.invalidation = best.invalidation
    rep.payout = payout
    rep.criteria = evaluate_criteria(ctx, best)

    # probabilidade: apenas de modelo calibrado; nunca score arbitrário
    if model is not None and getattr(model, "calibrated", False):
        try:
            p = model.predict_prob(ctx, best)
            rep.probability = p
            rep.probability_note = "modelo calibrado"
            ev = p * payout - (1 - p)
            rep.expected_value = ev
            rep.criteria = apply_payout(rep.criteria, best.direction, ctx, payout,
                                        ctx.cur.close, p)
        except Exception as exc:  # modelo indisponível => sem probabilidade
            rep.probability = None
            rep.probability_note = f"modelo indisponível ({type(exc).__name__})"
    else:
        rep.probability_note = "sem modelo calibrado — probabilidade não estimada"
        rep.criteria = apply_payout(rep.criteria, best.direction, ctx, payout,
                                    ctx.cur.close, None)

    # critérios 7-10 sem backtester => None; filtro final:
    hard_fail = any(rep.criteria[k] is False for k in
                    ("1_dados_suficientes", "4_volatilidade_adequada",
                     "6_confirmacao_objetiva"))
    ev_fail = rep.criteria.get("9_expectativa_favoravel") is False

    if hard_fail or ev_fail:
        rep.status = "aguardar"
        rep.decision = "AGUARDAR"
        if ev_fail:
            rep.risks.append("Expectativa matemática desfavorável com o payout configurado.")
    else:
        rep.decision = "AVALIAR CALL" if rep.direction == 1 else "AVALIAR PUT"
    return rep
