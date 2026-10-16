"""Backtesting realista sem vazamento de dados.

Propriedades:
- Decisão no candle i usa somente candles[0..i] (via AnalysisContext.build).
- Resultado da operação é avaliado no candle i + expiração (expiração em nº
  de candles do timeframe base).
- Separação cronológica: treino -> validação -> teste, com walk-forward.
- Registra todos os sinais, inclusive perdedores.
- Ponto de equilíbrio calculado pelo payout.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from ..core.candles import CandleSeries
from ..analysis.context import AnalysisContext, IndicatorCache
from ..signal import generate_signal, SignalReport
from ..probability import ProbabilityModel, wilson_interval, extract_features


@dataclass
class Trade:
    index: int                 # candle de decisão
    ts: int
    direction: int             # +1 CALL, -1 PUT
    strategy_id: str
    entry_price: float
    expiry: int                # em candles
    payout: float
    won: Optional[bool]        # None = sem resultado (fim da série)
    exit_price: Optional[float]
    probability: Optional[float]
    confirmations: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass
class BacktestResult:
    trades: list[Trade]
    payout: float
    expiry: int
    total: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = float("nan")
    ci_low: float = float("nan")
    ci_high: float = float("nan")
    net_profit: float = 0.0       # em unidade de stake (1.0 = 100% da stake)
    expectancy: float = 0.0       # ganho médio por operação (fração da stake)
    break_even_rate: float = float("nan")
    max_drawdown: float = 0.0
    max_loss_streak: int = 0
    by_strategy: dict = field(default_factory=dict)
    by_hour: dict = field(default_factory=dict)
    note: str = ""

    def summary(self) -> str:
        lines = [
            f"Operações: {self.total}",
            f"Vitórias/Derrotas: {self.wins}/{self.losses}",
            f"Taxa de acerto: {self.win_rate:.2%}" if self.total else "Taxa de acerto: N/A",
            f"IC95% (Wilson): [{self.ci_low:.2%}, {self.ci_high:.2%}]" if self.total else "IC95%: N/A",
            f"Ponto de equilíbrio (payout {self.payout:.0%}): {self.break_even_rate:.2%}",
            f"Resultado líquido simulado: {self.net_profit:+.2f} stakes",
            f"Esperança por operação: {self.expectancy:+.4f} stakes",
            f"Drawdown máximo: {self.max_drawdown:.2f} stakes",
            f"Máxima sequência de perdas: {self.max_loss_streak}",
        ]
        if self.by_strategy:
            lines.append("Por estratégia:")
            for sid, stats in sorted(self.by_strategy.items()):
                lines.append(f"  [{sid}] n={stats['n']} acerto={stats['win_rate']:.1%} "
                             f"IC=[{stats['ci_low']:.1%},{stats['ci_high']:.1%}]")
        if self.note:
            lines.append(f"Nota: {self.note}")
        return "\n".join(lines)


def _resolve_outcome(series: CandleSeries, decision_idx: int, direction: int,
                     expiry: int) -> tuple:
    """Resultado real da operação: compara preço de entrada (fechamento do candle
    de decisão) com o fechamento do candle i+expiry. Se a série termina antes,
    retorna (None, None)."""
    j = decision_idx + expiry
    if j >= len(series):
        return None, None
    entry = series[decision_idx].close
    exit_ = series[j].close
    won = exit_ > entry if direction == 1 else exit_ < entry
    return won, exit_


def run_backtest(series: CandleSeries, payout: float = 0.80, expiry: int = 1,
                 start: int = 250, end: Optional[int] = None,
                 step: int = 1, min_interval: int = 1,
                 model: Optional[ProbabilityModel] = None,
                 collect_features: bool = False,
                 on_signal: Optional[Callable] = None) -> BacktestResult:
    """Percorre a série decidindo em cada candle (a partir de `start`).

    - `min_interval`: nº mínimo de candles entre um sinal e o próximo.
    - `collect_features`: retorna (X, y) junto, para treinar o modelo.
    """
    trades: list[Trade] = []
    end = end if end is not None else len(series)
    last_signal_idx = -10**9
    X_list: list[np.ndarray] = []
    y_list: list[int] = []
    decisions_log: list[tuple[int, str, int]] = []  # (idx, status, direction)
    cache = IndicatorCache(series)

    for i in range(start, end - expiry):
        if i - last_signal_idx < min_interval:
            continue
        try:
            ctx = AnalysisContext.build(series, i + 1, cache=cache)
            ctx.asset = series.symbol
        except ValueError:
            continue
        rep: SignalReport = generate_signal(ctx, payout=payout, model=model)
        decisions_log.append((i, rep.status, rep.direction))
        if collect_features:
            # rotula APENAS os sinais detectados (não os ignorados), pois o modelo
            # estima P(sucesso | sinal), não P(preço subir|mercado).
            if rep.status == "sinal_detectado":
                won, _ = _resolve_outcome(series, i, rep.direction, expiry)
                if won is not None:
                    X_list.append(extract_features(ctx))
                    y_list.append(1 if won else 0)
        if rep.status != "sinal_detectado":
            continue
        won, exit_ = _resolve_outcome(series, i, rep.direction, expiry)
        if won is None:
            continue
        trades.append(Trade(
            index=i, ts=series[i].ts, direction=rep.direction,
            strategy_id=rep.strategy_id, entry_price=series[i].close,
            expiry=expiry, payout=payout, won=won, exit_price=exit_,
            probability=rep.probability,
            confirmations=list(rep.confirmations), risks=list(rep.risks),
        ))
        last_signal_idx = i
        if on_signal is not None:
            on_signal(rep, trades[-1])

    res = BacktestResult(trades=trades, payout=payout, expiry=expiry)
    res.break_even_rate = 1.0 / (1.0 + payout)
    n = len(trades)
    res.total = n
    if n:
        wins = sum(1 for t in trades if t.won)
        res.wins = wins
        res.losses = n - wins
        res.win_rate = wins / n
        lo, hi = wilson_interval(wins, n)
        res.ci_low, res.ci_high = lo, hi
        # lucro: +payout por vitória, -1 por derrota (stake normalizada)
        results = [(t.payout if t.won else -1.0) for t in trades]
        res.net_profit = float(sum(results))
        res.expectancy = float(np.mean(results))
        # drawdown e sequência
        equity = np.cumsum(results)
        peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))
        dd = peak[1:] - equity
        res.max_drawdown = float(dd.max()) if len(dd) else 0.0
        streak = best_streak = 0
        for r in results:
            if r < 0:
                streak += 1
                best_streak = max(best_streak, streak)
            else:
                streak = 0
        res.max_loss_streak = best_streak
        # por estratégia
        by_s: dict[str, list[bool]] = {}
        for t in trades:
            by_s.setdefault(t.strategy_id, []).append(t.won)
        for sid, ws in by_s.items():
            w = sum(ws)
            l, h = wilson_interval(w, len(ws))
            res.by_strategy[sid] = {"n": len(ws), "wins": w,
                                    "win_rate": w / len(ws), "ci_low": l, "ci_high": h}
        # por hora (UTC)
        from datetime import datetime, timezone
        by_h: dict[int, list[bool]] = {}
        for t in trades:
            h = datetime.fromtimestamp(t.ts, tz=timezone.utc).hour
            by_h.setdefault(h, []).append(t.won)
        for h, ws in by_h.items():
            res.by_hour[h] = {"n": len(ws), "win_rate": sum(ws) / len(ws)}
        if res.win_rate <= res.break_even_rate:
            res.note = ("Taxa de acerto ATÉ o ponto de equilíbrio — "
                        "resultado líquido negativo esperado neste cenário.")
    else:
        res.note = "Nenhuma operação gerada — mercado sem condições objetivas."
    from ..probability import FEATURE_NAMES as _FN
    res._features = (np.vstack(X_list) if X_list else np.empty((0, len(_FN))), y_list)
    return res


# --------------------------------------------------------------------------- #
# Walk-forward
# --------------------------------------------------------------------------- #
@dataclass
class WalkForwardFold:
    train_slice: tuple
    val_slice: tuple
    test_slice: tuple
    metrics_train: dict
    metrics_val: dict
    metrics_test: dict


def walk_forward(series: CandleSeries, n_folds: int = 3, payout: float = 0.80,
                 expiry: int = 1) -> tuple:
    """Divide a série em n_folds blocos cronológicos; para cada fold:
    treino = blocos anteriores, validação = bloco seguinte, teste = bloco seguinte.
    Retorna (model_report, aggregated_test_result, folds).
    """
    n = len(series)
    if n < 3000:
        raise ValueError(f"Série muito pequena para walk-forward ({n} candles); "
                         f"mínimo 3000 para 3 folds com margem.")
    fold_size = n // (n_folds + 2)
    slices = [(k * fold_size, (k + 1) * fold_size) for k in range(n_folds + 2)]

    all_test_trades: list[Trade] = []
    folds: list[WalkForwardFold] = []
    model = ProbabilityModel()
    first_report = None

    for f in range(n_folds):
        tr = slices[f]
        va = slices[f + 1]
        te = slices[f + 2]
        # uma única passada por bloco: coleta features/rótulos E as métricas cruas
        # (modelo=None => não filtra por EV; reaproveitamos o resultado)
        X_tr, y_tr, bt_train = _collect(series, tr, payout, expiry, model=None)
        X_va, y_va, bt_val = _collect(series, va, payout, expiry, model=None)
        X_te, y_te, bt_test_raw = _collect(series, te, payout, expiry, model=None)
        # treina em treino, CALIBRA na validação, avalia no teste (fora da amostra)
        model = ProbabilityModel()
        rep = model.fit(X_tr, y_tr, X_va, y_va, X_te, y_te) if len(X_tr) else None
        if first_report is None and rep is not None:
            first_report = rep
        # se o modelo estiver calibrado, refaz o teste filtrando por EV;
        # caso contrário reaproveita a passada crua (evita trabalho redundante)
        if model.calibrated:
            bt_test = run_backtest(series, payout, expiry, start=te[0], end=te[1],
                                   model=model)
        else:
            bt_test = bt_test_raw
        all_test_trades.extend(bt_test.trades)
        folds.append(WalkForwardFold(
            train_slice=tr, val_slice=va, test_slice=te,
            metrics_train={"n_signals": len(bt_train.trades),
                           "win_rate": bt_train.win_rate,
                           "model_calibrated": bool(model.calibrated)},
            metrics_val={"n_signals": len(bt_val.trades),
                         "win_rate": bt_val.win_rate},
            metrics_test={"n_signals": len(bt_test.trades),
                          "win_rate": bt_test.win_rate,
                          "model_used": bool(model.calibrated)},
        ))

    agg = BacktestResult(trades=all_test_trades, payout=payout, expiry=expiry)
    agg.break_even_rate = 1.0 / (1.0 + payout)
    n_t = len(all_test_trades)
    agg.total = n_t
    if n_t:
        wins = sum(1 for t in all_test_trades if t.won)
        agg.wins, agg.losses = wins, n_t - wins
        agg.win_rate = wins / n_t
        agg.ci_low, agg.ci_high = wilson_interval(wins, n_t)
        results = [(t.payout if t.won else -1.0) for t in all_test_trades]
        agg.net_profit = float(sum(results))
        agg.expectancy = float(np.mean(results))
        # drawdown e sequência de perdas sobre a curva de capital dos folds
        equity = np.cumsum(results)
        peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))
        dd = peak[1:] - equity
        agg.max_drawdown = float(dd.max()) if len(dd) else 0.0
        streak = best = 0
        for r in results:
            if r < 0:
                streak += 1
                best = max(best, streak)
            else:
                streak = 0
        agg.max_loss_streak = best
        # por estratégia (para relatório de fora da amostra)
        by_s: dict[str, list[bool]] = {}
        for t in all_test_trades:
            by_s.setdefault(t.strategy_id, []).append(t.won)
        for sid, ws in by_s.items():
            w = sum(ws)
            lo, hi = wilson_interval(w, len(ws))
            agg.by_strategy[sid] = {"n": len(ws), "wins": w,
                                    "win_rate": w / len(ws), "ci_low": lo, "ci_high": hi}
    agg.note = ("Resultados agregados APENAS do bloco de teste de cada fold "
                "(fora da amostra de treino/calibração).")
    return (first_report, agg, folds)


def _collect(series: CandleSeries, sl: tuple, payout: float, expiry: int,
             model):
    """Uma passada sobre o bloco [sl[0], sl[1]) que devolve
    (X, y, resultado_do_backtest) — features/rótulos e métricas cruas juntos."""
    r = run_backtest(series, payout, expiry, start=max(sl[0], 250), end=sl[1],
                     collect_features=True, model=model)
    X, y = r._features
    return X, np.asarray(y), r
