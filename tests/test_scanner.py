"""Testes do scanner multi-ativos e da qualidade de dados."""
import os

import pytest

from app.config import ScannerConfig
from app.core.candles import synthetic_series
from app.scanner import Scanner, sanitize_series, inspect_quality


def _write_csv(tmp_path, name, series):
    p = os.path.join(str(tmp_path), name)
    series.save_csv(p)
    return p


def _cfg(assets, **kw):
    return ScannerConfig(assets=assets, min_candles=kw.pop("min_candles", 250),
                         max_assets=kw.pop("max_assets", 20),
                         payout=kw.pop("payout", 0.80),
                         stale_after_s=kw.pop("stale_after_s", 10**12), **kw)


def test_scanner_runs_over_multiple_assets(tmp_path):
    a = synthetic_series(600, seed=1, volatility=0.0008)
    b = synthetic_series(600, seed=2, volatility=0.0008)
    _write_csv(tmp_path, "A.csv", a)
    _write_csv(tmp_path, "B.csv", b)
    sc = Scanner(_cfg(["A.csv", "B.csv"]), data_dir=str(tmp_path))
    res = sc.scan()
    assert len(res) == 2
    assert all(r.status in ("sinal_detectado", "aguardar", "sem_sinal",
                            "dados_insuficientes") for r in res)


def test_scanner_isolates_missing_asset(tmp_path):
    a = synthetic_series(600, seed=1, volatility=0.0008)
    _write_csv(tmp_path, "A.csv", a)
    sc = Scanner(_cfg(["A.csv", "NAO_EXISTE.csv"]), data_dir=str(tmp_path))
    res = sc.scan()
    assert len(res) == 2
    err = [r for r in res if r.asset == "NAO_EXISTE.csv"]
    assert err and err[0].status == "erro"
    # o ativo válido continua processado
    assert any(r.asset == "A" for r in res)


def test_scanner_flags_insufficient_history(tmp_path):
    a = synthetic_series(120, seed=3)
    _write_csv(tmp_path, "SHORT.csv", a)
    sc = Scanner(_cfg(["SHORT.csv"], min_candles=250), data_dir=str(tmp_path))
    res = sc.scan()
    assert res[0].status == "dados_insuficientes"


def test_scanner_orders_signals_first(tmp_path):
    a = synthetic_series(800, seed=5, volatility=0.001)
    b = synthetic_series(800, seed=6, volatility=0.001)
    _write_csv(tmp_path, "A.csv", a)
    _write_csv(tmp_path, "B.csv", b)
    sc = Scanner(_cfg(["A.csv", "B.csv"]), data_dir=str(tmp_path))
    res = sc.scan()
    statuses = [r.status for r in res]
    if "sinal_detectado" in statuses:
        assert statuses[0] == "sinal_detectado"


def test_scanner_never_raises_on_corrupt_csv(tmp_path):
    p = os.path.join(str(tmp_path), "BAD.csv")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("lixo,nao,e,csv\n1,2\n")
    sc = Scanner(_cfg(["BAD.csv"]), data_dir=str(tmp_path))
    res = sc.scan()   # não deve lançar
    assert res[0].status == "erro"


def test_sanitize_removes_duplicates_and_sorts():
    from app.core.candles import Candle
    cs = [Candle(200, 1, 2, 0.5, 1.5), Candle(100, 1, 2, 0.5, 1.5),
          Candle(100, 1, 2, 0.5, 1.5)]     # fora de ordem + duplicado
    series, q = sanitize_series(cs, "X")
    assert [c.ts for c in series.candles] == [100, 200]
    assert q.n_duplicates == 1


def test_inspect_quality_flags_stale():
    a = synthetic_series(300, seed=1)
    q = inspect_quality(a, now=a[-1].ts + 100000, stale_after_s=300)
    assert not q.ok
    assert any("desatualiz" in s for s in q.issues)


def test_scan_does_not_emit_without_data(tmp_path):
    # scanner com ativo inexistente não inventa sinal
    sc = Scanner(_cfg(["X.csv"]), data_dir=str(tmp_path))
    res = sc.scan()
    assert res[0].status == "erro"
    assert res[0].direction == 0
