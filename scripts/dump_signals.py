"""Exporta TODOS os sinais de um backtest (inclusive os perdedores) para CSV.

Uso:
  python scripts/dump_signals.py --csv data/BTCUSDT_1m.csv --out data/signals.csv

Cada linha contém timestamp, direção, estratégia, preço de entrada/saída,
resultado e probabilidade (quando disponível). Serve para auditoria e para
alimentar o aprendizado contínuo (recalibração com validação temporal).
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.candles import CandleSeries
from app.backtest import run_backtest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--payout", type=float, default=0.80)
    ap.add_argument("--expiry", type=int, default=1)
    ap.add_argument("--start", type=int, default=250)
    ap.add_argument("--out", default="data/signals.csv")
    args = ap.parse_args()

    s = CandleSeries.from_csv(args.csv)
    s.symbol = os.path.splitext(os.path.basename(args.csv))[0]
    r = run_backtest(s, payout=args.payout, expiry=args.expiry, start=args.start)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp_utc", "index", "symbol", "direction", "strategy",
                    "entry", "exit", "expiry", "payout", "probability", "resultado"])
        for t in r.trades:
            w.writerow([
                datetime.fromtimestamp(t.ts, tz=timezone.utc).isoformat(timespec="seconds"),
                t.index, s.symbol,
                "CALL" if t.direction == 1 else "PUT",
                t.strategy_id, f"{t.entry_price:.6f}",
                f"{t.exit_price:.6f}" if t.exit_price is not None else "",
                t.expiry, t.payout,
                f"{t.probability:.4f}" if t.probability is not None else "",
                "VITORIA" if t.won else "DERROTA",
            ])
    print(f"{len(r.trades)} sinais exportados para {args.out}")
    print(r.summary())


if __name__ == "__main__":
    main()
