#!/usr/bin/env python
"""IQ Analyzer — linha de comando.

Uso:
  python run.py sample                 # gera data/sample.csv (sintético, para testes)
  python run.py fetch --symbol BTCUSDT --interval 1m --limit 5000
                                       # baixa dados reais públicos (Binance) para data/
  python run.py analyze --csv data/BTCUSDT_1m.csv --index 1200
  python run.py backtest --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1
  python run.py walkforward --csv data/BTCUSDT_1m.csv --payout 0.80 --expiry 1
  python run.py serve                  # abre o dashboard web
  python run.py capture --shot print.png --auto-region \\
        --price-top 1.20 --pixel-top 100 --price-bottom 1.00 --pixel-bottom 500 \\
        --out data/captura.csv         # lê velas de um PNG da tela
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from app.core.candles import CandleSeries, synthetic_series
from app.analysis.context import AnalysisContext, IndicatorCache
from app.signal import generate_signal
from app.backtest import run_backtest, walk_forward
from app.config import load_config, DEFAULT_CONFIG
from app.logging_config import setup_logging

DATA = os.path.join(os.path.dirname(__file__), "data")


def _load(args) -> CandleSeries:
    if getattr(args, "csv", None):
        s = CandleSeries.from_csv(args.csv)
        if not s.symbol:
            base = os.path.basename(args.csv)
            s.symbol = os.path.splitext(base)[0]
        return s
    raise SystemExit("Informe --csv com um arquivo de candles.")


def cmd_sample(args):
    os.makedirs(DATA, exist_ok=True)
    s = synthetic_series(args.n, seed=args.seed, volatility=args.vol)
    path = os.path.join(DATA, "sample.csv")
    s.save_csv(path)
    print(f"[sample] {len(s)} candles sintéticos salvos em {path}")
    print("ATENÇÃO: dados SINTÉTICOS. Use apenas para testar o software.")


def cmd_fetch(args):
    from scripts.fetch_binance import fetch_klines
    os.makedirs(DATA, exist_ok=True)
    s = fetch_klines(args.symbol, args.interval, args.limit)
    path = os.path.join(DATA, f"{args.symbol}_{args.interval}.csv")
    s.save_csv(path)
    print(f"[fetch] {len(s)} candles de {args.symbol} {args.interval} salvos em {path}")


def cmd_analyze(args):
    s = _load(args)
    cache = IndicatorCache(s)
    idx = min(args.index if args.index is not None else len(s) - 1, len(s) - 1)
    ctx = AnalysisContext.build(s, idx + 1, cache=cache)
    ctx.asset = s.symbol
    rep = generate_signal(ctx, payout=args.payout)
    print(rep.explain())


def cmd_backtest(args):
    s = _load(args)
    r = run_backtest(s, payout=args.payout, expiry=args.expiry, start=args.start)
    print(r.summary())
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({
                "total": r.total, "wins": r.wins, "losses": r.losses,
                "win_rate": r.win_rate, "ci_low": r.ci_low, "ci_high": r.ci_high,
                "break_even_rate": r.break_even_rate, "net_profit": r.net_profit,
                "expectancy": r.expectancy, "max_drawdown": r.max_drawdown,
                "max_loss_streak": r.max_loss_streak, "by_strategy": r.by_strategy,
                "by_hour": r.by_hour, "note": r.note,
            }, fh, ensure_ascii=False, indent=2)
        print(f"[backtest] relatório salvo em {args.json}")


def cmd_walkforward(args):
    s = _load(args)
    print("Executando walk-forward (treino -> validação -> teste por fold)…")
    report, agg, folds = walk_forward(s, n_folds=args.folds,
                                      payout=args.payout, expiry=args.expiry)
    if report is not None:
        print("\n== Modelo probabilístico ==")
        print(f"  calibração: {report.calibrator}")
        print(f"  Brier validação: {report.brier_val:.4f} | baseline val: {report.baseline_val:.4f}")
        print(f"  Brier teste:     {report.brier_test:.4f} | baseline teste: {report.baseline_test:.4f}")
        print(f"  nota: {report.note}")
    print("\n== Folds (somente bloco de teste) ==")
    for k, f in enumerate(folds):
        print(f"  fold {k}: treino={f.train_slice} val={f.val_slice} teste={f.test_slice} "
              f"| teste n={f.metrics_test['n_signals']} acerto={f.metrics_test['win_rate']:.1%}")
    print("\n== Agregado (fora da amostra) ==")
    print(agg.summary())


def cmd_serve(args):
    from app.ui.server import run
    print(f"Abrindo dashboard em http://{args.host}:{args.port}  (modo simulação)")
    run(host=args.host, port=args.port, debug=False)


def cmd_scan(args):
    """Scanner multi-ativos sobre CSVs disponíveis em data/."""
    from app.scanner import Scanner
    cfg = load_config()
    cfg.scanner.assets = args.assets
    cfg.scanner.payout = args.payout
    cfg.scanner.min_candles = args.min_candles
    cfg.validate()
    log = setup_logging(cfg.log_dir, console=False)
    sc = Scanner(cfg.scanner, data_dir=DATA, logger=log)
    results = sc.scan(now=args.now)
    print(f"== Scanner ({len(results)} ativo(s)) ==")
    for r in results:
        tag = {"sinal_detectado": "SINAL", "aguardar": "AGUARDAR",
               "sem_sinal": "SEM SINAL", "erro": "ERRO",
               "dados_insuficientes": "DADOS INSUF."}.get(r.status, r.status)
        d = {1: "CALL", -1: "PUT", 0: "-"}[r.direction]
        print(f"  [{r.asset}] {tag:10s} {d:4s} qual={r.quality:.2f} "
              f"estrategia={r.strategy_id or '-'}")
        if r.status == "sinal_detectado":
            for c in r.confirmations[:3]:
                print(f"      + {c}")
            print(f"      prob: {r.probability_note}")
        if r.error:
            print(f"      ! {r.error}")
    if args.json:
        import json as _json
        with open(args.json, "w", encoding="utf-8") as fh:
            _json.dump([{
                "asset": r.asset, "status": r.status, "direction": r.direction,
                "decision": r.decision, "strategy_id": r.strategy_id,
                "quality": r.quality, "ts": r.ts, "entry_price": r.entry_price,
                "probability": r.probability, "probability_note": r.probability_note,
                "confirmations": r.confirmations, "risks": r.risks,
                "error": r.error,
                "data_quality": (r.data_quality.__dict__ if r.data_quality else None),
            } for r in results], fh, ensure_ascii=False, indent=2)
        print(f"[scan] relatório salvo em {args.json}")


def cmd_simulate(args):
    """Simulação de operações (expiração de 60s) sobre um CSV — sem ordens reais."""
    from app.simulation import SimulationEngine
    s = _load(args)
    cfg = load_config()
    log = setup_logging(cfg.log_dir, console=False)
    cfg.simulation.payout = args.payout
    eng = SimulationEngine(sim_cfg=cfg.simulation, risk_cfg=cfg.risk,
                           store_path=args.store, logger=log)
    cache = IndicatorCache(s)
    opened = 0
    for i in range(250, len(s) - 1):
        ctx = AnalysisContext.build(s, i + 1, cache=cache)
        ctx.asset = s.symbol
        rep = generate_signal(ctx, payout=args.payout)
        if rep.status != "sinal_detectado":
            continue
        # entrada hipotética = abertura do candle seguinte (não o close do sinal)
        ts_signal = s[i].ts
        entry = s[i + 1].open
        op = eng.open_simulation(symbol=s.symbol, strategy_id=rep.strategy_id,
                                 direction=rep.direction, ts_signal=ts_signal,
                                 entry_price=entry, reason="; ".join(rep.confirmations[:2]),
                                 payout=args.payout, probability=rep.probability)
        if op is None:
            if eng.state == "SUSPENSO_POR_RISCO":
                print(f"[simulate] interrompido por risco: {eng.risk.state.suspend_reason}")
                break
            continue
        opened += 1
        j = i + cfg.simulation.expiry_candles
        if j < len(s):
            eng.resolve(exit_price=s[j].close, ts_expiry=s[j].ts,
                        condition=f"fechamento do candle {j}")
    st = eng.stats()
    print("== Simulação (modo VIRTUAL — nenhuma ordem real) ==")
    print(f"  operações registradas: {st['operations']}  (abertas nesta execução: {opened})")
    print(f"  resolvidas: {st['resolved']}  vitórias={st['wins']} derrotas={st['losses']}")
    if st['win_rate'] is not None:
        print(f"  taxa de acerto simulada: {st['win_rate']:.2%}")
    print(f"  PnL da sessão: {st['session_pnl']:+.2f} stakes  | saldo virtual: {st['balance']:.2f}")
    print(f"  histórico: {args.store}")


def _capture_calibration(args):
    """Monta a calibração a partir de --calib (JSON) ou de --region + dois pontos."""
    from app.data.capture import ScreenCalibration, load_calibration
    if args.calib:
        return load_calibration(args.calib)
    # com --shot --auto-region a região é descoberta na imagem, então é opcional
    auto = args.auto_region and args.shot
    need = [args.price_top, args.pixel_top, args.price_bottom, args.pixel_bottom]
    if any(v is None for v in need) or (args.region is None and not auto):
        raise SystemExit(
            "Informe --calib arquivo.json OU "
            "--region L,T,R,B --price-top P --pixel-top Y --price-bottom P --pixel-bottom Y")
    if args.region is None:
        region = (0, 0, 0, 0)   # será substituída pela região detectada
    else:
        region = tuple(int(v) for v in args.region.split(","))
        if len(region) != 4:
            raise SystemExit("--region deve ter 4 valores: L,T,R,B")
    return ScreenCalibration(region=region, price_top=args.price_top,
                             pixel_top=args.pixel_top, price_bottom=args.price_bottom,
                             pixel_bottom=args.pixel_bottom)


def cmd_capture(args):
    """Coleta velas por leitura de tela (ou de um PNG) e salva em CSV."""
    import time as _time
    from app.data.capture import (detect_candles_from_image, capture_snapshot,
                                  chart_region_from_image, grab_region,
                                  save_calibration)
    from PIL import Image

    calib = _capture_calibration(args)
    now = args.now

    if args.shot:
        img = Image.open(args.shot)
        if args.auto_region:
            reg = chart_region_from_image(img)
            if reg is None:
                raise SystemExit("Nenhuma vela encontrada na imagem (região não detectada).")
            calib.region = reg
            print(f"[capture] região detectada automaticamente: {reg}")
        candles = detect_candles_from_image(img, calib, timeframe_s=args.timeframe,
                                            now=now, split_merged=not args.no_split)
    else:
        if args.auto_region:
            print("[capture] --auto-region só é válido com --shot (imagem).")
        print(f"[capture] capturando região {calib.region} …")
        candles = detect_candles_from_image(
            grab_region(calib.region), calib, timeframe_s=args.timeframe,
            now=now, split_merged=not args.no_split)

    if args.calib_out:
        save_calibration(calib, args.calib_out)
        print(f"[capture] calibração salva em {args.calib_out}")

    if not candles:
        raise SystemExit("Nenhuma vela detectada — verifique região, calibração e cores.")

    from app.core.candles import CandleSeries
    series = CandleSeries(candles, symbol=args.symbol, timeframe_s=args.timeframe)
    first, last = series[0], series[-1]
    print(f"[capture] {len(series)} velas detectadas | ativo={args.symbol} "
          f"tf={args.timeframe}s")
    print(f"  primeira: ts={first.ts} O={first.open:.5f} H={first.high:.5f} "
          f"L={first.low:.5f} C={first.close:.5f}")
    print(f"  última:   ts={last.ts} O={last.open:.5f} H={last.high:.5f} "
          f"L={last.low:.5f} C={last.close:.5f}")
    if args.out:
        series.save_csv(args.out)
        print(f"[capture] salvo em {args.out}")
    if args.watch and not args.shot:
        end = _time.time() + args.watch
        n = 0
        while _time.time() < end:
            _time.sleep(args.interval)
            try:
                s = capture_snapshot(calib, timeframe_s=args.timeframe)
                if args.out:
                    s.save_csv(args.out)
                n += 1
                print(f"  [{n}] recapturado: {len(s)} velas (último C={s[-1].close:.5f})")
            except Exception as exc:
                print(f"  [{n}] falha na captura: {exc}")


def build_parser():
    p = argparse.ArgumentParser(description="IQ Analyzer (modo análise/simulação)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("sample", help="gera dados sintéticos de exemplo")
    sp.add_argument("--n", type=int, default=1500)
    sp.add_argument("--seed", type=int, default=17)
    sp.add_argument("--vol", type=float, default=0.0006)
    sp.set_defaults(func=cmd_sample)

    sp = sub.add_parser("fetch", help="baixa dados reais públicos (Binance)")
    sp.add_argument("--symbol", default="BTCUSDT")
    sp.add_argument("--interval", default="1m")
    sp.add_argument("--limit", type=int, default=5000)
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("analyze", help="analisa um instante")
    sp.add_argument("--csv", required=True)
    sp.add_argument("--index", type=int, default=None)
    sp.add_argument("--payout", type=float, default=0.80)
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("backtest", help="backtest com métricas estatísticas")
    sp.add_argument("--csv", required=True)
    sp.add_argument("--payout", type=float, default=0.80)
    sp.add_argument("--expiry", type=int, default=1)
    sp.add_argument("--start", type=int, default=250)
    sp.add_argument("--json", default=None)
    sp.set_defaults(func=cmd_backtest)

    sp = sub.add_parser("walkforward", help="walk-forward com validação temporal")
    sp.add_argument("--csv", required=True)
    sp.add_argument("--payout", type=float, default=0.80)
    sp.add_argument("--expiry", type=int, default=1)
    sp.add_argument("--folds", type=int, default=2)
    sp.set_defaults(func=cmd_walkforward)

    sp = sub.add_parser("serve", help="dashboard web")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8765)
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("scan", help="scanner multi-ativos (CSVs em data/)")
    sp.add_argument("--assets", nargs="+", required=True,
                    help="lista de ativos (nomes de arquivo em data/ ou caminhos)")
    sp.add_argument("--payout", type=float, default=0.80)
    sp.add_argument("--min-candles", type=int, default=250)
    sp.add_argument("--now", type=int, default=None, help="epoch p/ checar atualidade")
    sp.add_argument("--json", default=None, help="salva resultado em JSON")
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("simulate", help="simulação virtual (expiração 60s, sem ordens reais)")
    sp.add_argument("--csv", required=True)
    sp.add_argument("--payout", type=float, default=0.80)
    sp.add_argument("--store", default=os.path.join("data", "simulation.jsonl"),
                    help="histórico de operações")
    sp.set_defaults(func=cmd_simulate)

    sp = sub.add_parser("capture", help="coleta velas por leitura de tela (ou de um PNG)")
    sp.add_argument("--shot", default=None,
                    help="lê um arquivo de imagem (PNG/JPG) em vez de capturar a tela")
    sp.add_argument("--calib", default=None, help="arquivo JSON de calibração")
    sp.add_argument("--calib-out", default=None, help="salva a calibração usada em JSON")
    sp.add_argument("--region", default=None, help="região da tela: L,T,R,B")
    sp.add_argument("--price-top", type=float, default=None)
    sp.add_argument("--pixel-top", type=float, default=None)
    sp.add_argument("--price-bottom", type=float, default=None)
    sp.add_argument("--pixel-bottom", type=float, default=None)
    sp.add_argument("--auto-region", action="store_true",
                    help="descobre a região pela imagem (só com --shot)")
    sp.add_argument("--timeframe", type=int, default=60, help="segundos por vela")
    sp.add_argument("--now", type=int, default=None, help="epoch p/ timestamps (reprodutível)")
    sp.add_argument("--symbol", default="SCREEN_CAPTURE")
    sp.add_argument("--out", default=None, help="CSV de saída")
    sp.add_argument("--no-split", action="store_true",
                    help="não separar velas coladas da mesma cor")
    sp.add_argument("--watch", type=float, default=0.0,
                    help="reenviar capturas ao vivo por N segundos (só captura de tela)")
    sp.add_argument("--interval", type=float, default=5.0)
    sp.set_defaults(func=cmd_capture)

    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
