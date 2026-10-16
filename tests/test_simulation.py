"""Testes da simulação automática: estados, expiração 60s, idempotência, persistência."""
import os

import pytest

from app.config import SimulationConfig, RiskConfig
from app.simulation import SimulationEngine, SimState


def _engine(tmp_path, name="sim.jsonl", risk_kw=None, **sim_kw):
    sim = SimulationConfig(**sim_kw)
    store = os.path.join(str(tmp_path), name)
    rc = RiskConfig(**(risk_kw or {}))
    return SimulationEngine(sim_cfg=sim, risk_cfg=rc, store_path=store)


# risco permissivo para testar o mecanismo (não os limites)
_OPEN = {"min_seconds_between_operations": 0, "max_operations_per_session": 999,
         "max_consecutive_losses": 999, "max_session_loss": 999,
         "max_open_positions": 99}


def test_starts_in_waiting_data(tmp_path):
    eng = _engine(tmp_path)
    assert eng.state == SimState.AGUARDANDO_DADOS
    assert eng.operations == []


def test_expiry_is_60_seconds(tmp_path):
    eng = _engine(tmp_path, risk_kw=_OPEN)
    op = eng.open_simulation(symbol="BTC", strategy_id="A", direction=1,
                             ts_signal=1_000_000, entry_price=100.0)
    assert op is not None
    assert op.expiry_s == 60
    assert op.ts_entry == 1_000_060
    assert op.ts_expiry == 1_000_120


def test_entry_is_not_signal_close(tmp_path):
    eng = _engine(tmp_path, risk_kw=_OPEN)
    op = eng.open_simulation(symbol="BTC", strategy_id="A", direction=1,
                             ts_signal=1000, entry_price=101.5)
    assert op.entry_price == 101.5


def test_win_resolution(tmp_path):
    eng = _engine(tmp_path, risk_kw=_OPEN)
    eng.open_simulation(symbol="BTC", strategy_id="A", direction=1,
                        ts_signal=1000, entry_price=100.0)
    res = eng.resolve(exit_price=100.5, ts_expiry=1060)
    assert res.result == "WIN"
    assert eng.state == SimState.AGUARDANDO_DADOS


def test_loss_resolution(tmp_path):
    eng = _engine(tmp_path, risk_kw=_OPEN)
    eng.open_simulation(symbol="BTC", strategy_id="A", direction=1,
                        ts_signal=1000, entry_price=100.0)
    res = eng.resolve(exit_price=99.5, ts_expiry=1060)
    assert res.result == "LOSS"


def test_put_resolution(tmp_path):
    eng = _engine(tmp_path, risk_kw=_OPEN)
    eng.open_simulation(symbol="BTC", strategy_id="B", direction=-1,
                        ts_signal=1000, entry_price=100.0)
    res = eng.resolve(exit_price=99.0, ts_expiry=1060)
    assert res.result == "WIN"


def test_idempotency_same_signal_ignored(tmp_path):
    eng = _engine(tmp_path, risk_kw=_OPEN)
    a = eng.open_simulation(symbol="BTC", strategy_id="A", direction=1,
                            ts_signal=1000, entry_price=100.0)
    b = eng.open_simulation(symbol="BTC", strategy_id="A", direction=1,
                            ts_signal=1000, entry_price=100.0)
    assert a is not None
    assert b is None
    assert len(eng.operations) == 1


def test_history_persisted_and_reloaded(tmp_path):
    eng = _engine(tmp_path, risk_kw=_OPEN)
    eng.open_simulation(symbol="BTC", strategy_id="A", direction=1,
                        ts_signal=1000, entry_price=100.0)
    eng.resolve(exit_price=101.0, ts_expiry=1060)
    # novo engine no mesmo arquivo recupera histórico
    eng2 = _engine(tmp_path, risk_kw=_OPEN)
    assert len(eng2.operations) == 1
    # e o mesmo sinal continua sendo considerado duplicado
    dup = eng2.open_simulation(symbol="BTC", strategy_id="A", direction=1,
                               ts_signal=1000, entry_price=100.0)
    assert dup is None


def test_risk_suspension_blocks(tmp_path):
    sim = SimulationConfig()
    risk = RiskConfig(max_operations_per_session=1, min_seconds_between_operations=0)
    store = os.path.join(str(tmp_path), "r.jsonl")
    eng = SimulationEngine(sim_cfg=sim, risk_cfg=risk, store_path=store)
    assert eng.open_simulation(symbol="A", strategy_id="A", direction=1,
                               ts_signal=1000, entry_price=1.0) is not None
    eng.resolve(exit_price=2.0, ts_expiry=1060)
    blocked = eng.open_simulation(symbol="A", strategy_id="A", direction=1,
                                  ts_signal=2000, entry_price=1.0)
    assert blocked is None
    assert eng.state == SimState.SUSPENSO_POR_RISCO


def test_stats_and_shutdown(tmp_path):
    eng = _engine(tmp_path, risk_kw=_OPEN)
    eng.open_simulation(symbol="A", strategy_id="A", direction=1,
                        ts_signal=1000, entry_price=1.0)
    eng.resolve(exit_price=2.0, ts_expiry=1060)
    st = eng.stats()
    assert st["resolved"] == 1
    assert st["wins"] == 1
    assert st["win_rate"] == 1.0
    assert st["simulation_mode"] is True
    eng.shutdown()
    assert eng.state == SimState.ENCERRAMENTO


def test_invalid_transition_raises(tmp_path):
    eng = _engine(tmp_path)
    with pytest.raises(ValueError):
        eng._transition(SimState.OPERACAO_ABERTA)  # AGUARDANDO_DADOS -> OP_ABERTA inválido


def test_operation_records_all_required_fields(tmp_path):
    eng = _engine(tmp_path, risk_kw=_OPEN)
    op = eng.open_simulation(symbol="BTC", strategy_id="A", direction=1,
                             ts_signal=1000, entry_price=100.0,
                             reason="tendência", payout=0.85, probability=0.6)
    d = op.to_dict()
    for key in ("op_id", "symbol", "strategy_id", "direction", "ts_signal",
                "ts_entry", "ts_expiry", "entry_price", "expiry_s", "payout",
                "stake", "reason", "strategy_version", "config_snapshot"):
        assert key in d
    assert op.strategy_version
    assert d["config_snapshot"]["expiry_candles"] == 1
