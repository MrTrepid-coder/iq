"""Servidor do dashboard (Flask) — análise, sinais, marcações e replay.

A interface NÃO executa operações reais: é modo análise/simulação.
"""
from __future__ import annotations

import os
from flask import Flask, jsonify, render_template, request

from ..core.candles import CandleSeries, synthetic_series
from ..analysis.context import AnalysisContext, IndicatorCache
from ..signal import generate_signal
from ..backtest import run_backtest, walk_forward

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")

_state = {"series": None, "symbol": "—", "cache": None}


def get_series(source: str = "sample", csv_path: str = None) -> CandleSeries:
    """Obtém a série atual: CSV informado, arquivo em data/ ou série sintética."""
    def _with_symbol(s: CandleSeries, path: str) -> CandleSeries:
        if not s.symbol:
            s.symbol = os.path.splitext(os.path.basename(path))[0]
        return s
    if csv_path and os.path.exists(csv_path):
        return _with_symbol(CandleSeries.from_csv(csv_path), csv_path)
    if source == "sample":
        path = os.path.join(DATA_DIR, "sample.csv")
        if os.path.exists(path):
            return _with_symbol(CandleSeries.from_csv(path), path)
        s = synthetic_series(1500, seed=17, volatility=0.0006)
        return s
    # tenta carregar data/<source>.csv
    path = os.path.join(DATA_DIR, f"{source}.csv")
    if os.path.exists(path):
        return _with_symbol(CandleSeries.from_csv(path), path)
    return synthetic_series(1500, seed=17, volatility=0.0006)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/datasets")
def api_datasets():
    """Lista os CSVs disponíveis em data/ para o seletor de ativo."""
    out = []
    if os.path.isdir(DATA_DIR):
        for name in sorted(os.listdir(DATA_DIR)):
            if name.lower().endswith(".csv"):
                out.append({"value": os.path.splitext(name)[0], "label": name})
    return jsonify({"datasets": out})


@app.route("/api/series")
def api_series():
    source = request.args.get("source", "sample")
    s = get_series(source)
    _state["series"] = s
    _state["cache"] = IndicatorCache(s)
    ctx = AnalysisContext.build(s, len(s), cache=_state["cache"])
    candles = [{"time": c.ts, "open": c.open, "high": c.high,
                "low": c.low, "close": c.close} for c in s.candles]
    ema = {
        "ema9": [None if v != v else round(float(v), 6) for v in ctx.ema9],
        "ema21": [None if v != v else round(float(v), 6) for v in ctx.ema21],
        "ema50": [None if v != v else round(float(v), 6) for v in ctx.ema50],
    }
    levels = [{"price": l.price, "kind": l.kind, "touches": l.touches,
               "strength": round(l.strength, 2)} for l in ctx.levels]
    return jsonify({
        "symbol": s.symbol, "timeframe_s": s.timeframe_s, "n": len(s),
        "candles": candles, "ema": ema, "levels": levels,
        "zone": ctx.zone, "trend": ctx.trend.description,
        "regime": ctx.regime,
    })


@app.route("/api/signal")
def api_signal():
    """Sinal em um índice específico (replay). Sem lookahead: usa candles[:i+1]."""
    s = _state.get("series") or get_series()
    i = int(request.args.get("i", len(s) - 1))
    i = max(60, min(i, len(s) - 1))
    payout = float(request.args.get("payout", 0.80))
    cache = _state.get("cache") or IndicatorCache(s)
    ctx = AnalysisContext.build(s, i + 1, cache=cache)
    ctx.asset = s.symbol
    rep = generate_signal(ctx, payout=payout, model=None)
    return jsonify({
        "index": i,
        "time": s[i].ts,
        "status": rep.status,
        "direction": rep.direction,
        "strategy_id": rep.strategy_id,
        "strategy_name": rep.strategy_name,
        "decision": rep.decision,
        "probability": rep.probability,
        "probability_note": rep.probability_note,
        "confirmations": rep.confirmations,
        "risks": rep.risks,
        "invalidation": rep.invalidation,
        "criteria": rep.criteria,
        "explain": rep.explain(),
    })


@app.route("/api/backtest")
def api_backtest():
    s = _state.get("series") or get_series()
    payout = float(request.args.get("payout", 0.80))
    expiry = int(request.args.get("expiry", 1))
    r = run_backtest(s, payout=payout, expiry=expiry, start=250)
    return jsonify({
        "total": r.total, "wins": r.wins, "losses": r.losses,
        "win_rate": r.win_rate, "ci_low": r.ci_low, "ci_high": r.ci_high,
        "break_even_rate": r.break_even_rate, "net_profit": r.net_profit,
        "expectancy": r.expectancy, "max_drawdown": r.max_drawdown,
        "max_loss_streak": r.max_loss_streak,
        "by_strategy": r.by_strategy, "note": r.note,
        "summary": r.summary(),
    })


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "mode": "simulation", "real_execution": False})


def run(host: str = "127.0.0.1", port: int = 8765, debug: bool = False):
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run()
