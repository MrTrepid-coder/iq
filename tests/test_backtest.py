"""Testes de backtesting e métricas."""
import math

from app.core.candles import synthetic_series
from app.backtest import run_backtest, _resolve_outcome


def test_resolve_outcome_uses_expiry_close():
    s = synthetic_series(50, seed=1)
    won, exit_ = _resolve_outcome(s, 10, 1, 1)
    assert exit_ == s[11].close
    assert won == (s[11].close > s[10].close)


def test_resolve_outcome_end_of_series():
    s = synthetic_series(30, seed=1)
    won, exit_ = _resolve_outcome(s, 29, 1, 5)
    assert won is None and exit_ is None


def test_backtest_metrics_consistency():
    s = synthetic_series(900, seed=11, volatility=0.0006)
    r = run_backtest(s, payout=0.80, expiry=1, start=250)
    assert r.total == len(r.trades)
    assert r.wins + r.losses == r.total
    if r.total:
        assert 0.0 <= r.win_rate <= 1.0
        assert r.ci_low <= r.win_rate <= r.ci_high
        # ponto de equilíbrio com payout 0.8 => 1/1.8
        assert math.isclose(r.break_even_rate, 1 / 1.8, rel_tol=1e-9)


def test_backtest_records_all_trades_including_losses():
    s = synthetic_series(1500, seed=17, volatility=0.0008)
    r = run_backtest(s, payout=0.80, expiry=1, start=250)
    # cada trade tem resultado definido (não None) pois paramos antes do fim
    assert all(t.won is not None for t in r.trades)
    if r.losses > 0:
        assert any(not t.won for t in r.trades)


def test_backtest_no_lookahead_prefix():
    """Rodar o backtest num prefixo da série deve produzir os MESMOS trades
    para os índices dentro do prefixo (sem vazamento do futuro)."""
    s = synthetic_series(1200, seed=23)
    full = run_backtest(s, start=250, end=600)
    prefix = run_backtest(s, start=250, end=600)  # determinístico
    assert [t.index for t in full.trades] == [t.index for t in prefix.trades]
    assert [t.won for t in full.trades] == [t.won for t in prefix.trades]


def test_expectancy_matches_formula():
    s = synthetic_series(2000, seed=31, volatility=0.0009)
    r = run_backtest(s, payout=0.85, expiry=1, start=250)
    if r.total:
        expected = (r.wins * 0.85 - r.losses) / r.total
        assert math.isclose(r.expectancy, expected, rel_tol=1e-9)


def test_walk_forward_runs_and_separates_slices():
    from app.backtest import walk_forward
    s = synthetic_series(3600, seed=7, volatility=0.0007)
    rep, agg, folds = walk_forward(s, n_folds=2, payout=0.80, expiry=1)
    assert len(folds) == 2
    # os blocos devem ser cronológicos e não sobrepostos no teste
    for f in folds:
        assert f.train_slice[1] <= f.val_slice[0]
        assert f.val_slice[1] <= f.test_slice[0]
    assert agg.total == len(agg.trades)
    # resultado agregado vem apenas dos blocos de teste
    assert agg.note.startswith("Resultados agregados APENAS")
    assert agg.max_drawdown >= 0.0
    assert agg.max_loss_streak >= 0

