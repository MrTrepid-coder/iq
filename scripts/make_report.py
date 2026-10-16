"""Gera o relatório final em Markdown a partir de um backtest + walk-forward.

Uso:
  python scripts/make_report.py --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.candles import CandleSeries
from app.backtest import run_backtest, walk_forward


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--payout", type=float, default=0.80)
    ap.add_argument("--expiry", type=int, default=1)
    ap.add_argument("--folds", type=int, default=2)
    ap.add_argument("--out", default="data/REPORT.md")
    args = ap.parse_args()

    s = CandleSeries.from_csv(args.csv)
    symbol = os.path.splitext(os.path.basename(args.csv))[0]
    s.symbol = symbol

    full = run_backtest(s, payout=args.payout, expiry=args.expiry, start=250)
    lines = [
        f"# Relatório de Backtest — {symbol}",
        "",
        f"- Gerado em (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Candles: {len(s)} | timeframe: {s.timeframe_s}s",
        f"- Payout: {args.payout:.0%} | Expiração: {args.expiry} candle(s)",
        f"- Ponto de equilíbrio: {full.break_even_rate:.2%}",
        "",
        "## Backtest completo (in-sample, todas as operações)",
        "",
        "```",
        full.summary(),
        "```",
        "",
        "### Por estratégia",
        "",
        "| Estratégia | n | Acerto | IC95% |",
        "|---|---|---|---|",
    ]
    for sid, st in sorted(full.by_strategy.items()):
        lines.append(f"| {sid} | {st['n']} | {st['win_rate']:.1%} | "
                     f"[{st['ci_low']:.1%}, {st['ci_high']:.1%}] |")
    lines += ["", "### Por hora (UTC)", ""]
    for h in sorted(full.by_hour):
        st = full.by_hour[h]
        lines.append(f"- {h:02d}h: n={st['n']} acerto={st['win_rate']:.1%}")

    try:
        report, agg, folds = walk_forward(s, n_folds=args.folds,
                                          payout=args.payout, expiry=args.expiry)
        lines += ["", "## Walk-forward (resultados FORA da amostra)", ""]
        if report is not None:
            lines += [
                f"- Calibração: {report.calibrator}",
                f"- Brier validação: {report.brier_val:.4f} (baseline {report.baseline_val:.4f})",
                f"- Brier teste: {report.brier_test:.4f} (baseline {report.baseline_test:.4f})",
                f"- Nota: {report.note}",
                "",
            ]
        lines += ["| Fold | Treino | Validação | Teste | n teste | Acerto teste |",
                  "|---|---|---|---|---|---|"]
        for k, f in enumerate(folds):
            lines.append(f"| {k} | {f.train_slice} | {f.val_slice} | {f.test_slice} | "
                         f"{f.metrics_test['n_signals']} | {f.metrics_test['win_rate']:.1%} |")
        lines += ["", "```", agg.summary(), "```"]
    except ValueError as exc:
        lines += ["", f"> Walk-forward não executado: {exc}"]

    lines += [
        "",
        "## Interpretação",
        "",
        "- Taxa de acerto **abaixo** do ponto de equilíbrio indica ausência de vantagem",
        "  estatística demonstrada para este ativo/expiração/payout.",
        "- Intervalos de confiança largos indicam amostra pequena — não tirar conclusões.",
        "- Resultados in-sample não valem como prova de desempenho futuro; use o walk-forward.",
        "",
        "> Este relatório é uma medição, não uma promessa de rentabilidade.",
    ]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"Relatório salvo em {args.out}")


if __name__ == "__main__":
    main()
