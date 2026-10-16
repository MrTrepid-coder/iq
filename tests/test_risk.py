"""Testes da gestão de risco (ambiente virtual)."""
from app.config import RiskConfig
from app.risk import RiskManager


def _rm(**kw):
    kw.setdefault("max_open_positions", 99)
    cfg = RiskConfig(**kw)
    return RiskManager(cfg, initial_balance=100.0, stake=1.0)


def test_blocks_after_max_operations():
    rm = _rm(max_operations_per_session=2, min_seconds_between_operations=0,
             max_consecutive_losses=99, max_session_loss=99)
    assert rm.can_open(0).allowed
    rm.register_open(0)
    assert rm.can_open(1).allowed
    rm.register_open(1)
    d = rm.can_open(2)
    assert not d.allowed
    assert "operações" in d.reason


def test_blocks_after_consecutive_losses():
    rm = _rm(max_consecutive_losses=3, min_seconds_between_operations=0,
             max_operations_per_session=99, max_session_loss=99)
    for i in range(3):
        rm.register_open(i)
        rm.register_result(False, 1.0, 0.8)
    d = rm.can_open(10)
    assert not d.allowed
    assert "consecutivas" in d.reason


def test_blocks_after_session_loss_limit():
    rm = _rm(max_session_loss=2.0, min_seconds_between_operations=0,
             max_operations_per_session=99, max_consecutive_losses=99)
    for i in range(2):
        rm.register_open(i)
        rm.register_result(False, 1.0, 0.8)
    d = rm.can_open(10)
    assert not d.allowed
    assert "perda" in d.reason


def test_min_interval_between_operations():
    rm = _rm(min_seconds_between_operations=60, max_operations_per_session=99,
             max_consecutive_losses=99, max_session_loss=99)
    rm.register_open(1000)
    d = rm.can_open(1030)
    assert not d.allowed
    assert "intervalo" in d.reason
    assert rm.can_open(1060).allowed


def test_duplicate_blocked():
    rm = _rm(min_seconds_between_operations=0, max_operations_per_session=99,
             max_consecutive_losses=99, max_session_loss=99)
    rm.register_open(1000, fetch_key="A|s1|1000|1")
    d = rm.can_open(1010, fetch_key="A|s1|1000|1")
    assert not d.allowed
    assert "duplicada" in d.reason


def test_max_open_positions_blocks_exposure():
    rm = _rm(max_open_positions=1, min_seconds_between_operations=0,
             max_operations_per_session=99, max_consecutive_losses=99,
             max_session_loss=99)
    rm.register_open(1000, "k")
    d = rm.can_open(1100)
    assert not d.allowed
    assert "exposição" in d.reason


def test_no_martingale_stake_constant():
    rm = _rm()
    s0 = rm.next_stake()
    rm.register_open(0)
    rm.register_result(False, s0, 0.8)
    assert rm.next_stake() == s0   # não aumenta após derrota


def test_suspend_after_data_failures():
    rm = _rm(pause_after_data_failures=2)
    assert rm.register_data_failure("x").allowed
    d = rm.register_data_failure("y")
    assert not d.allowed
    assert rm.state.suspended
    assert not rm.can_open(9999).allowed


def test_data_success_resets_failures():
    rm = _rm(pause_after_data_failures=3)
    rm.register_data_failure("a")
    rm.register_data_success()
    assert rm.state.data_failures == 0


def test_stale_data_blocks():
    rm = _rm()
    d = rm.can_open(0, data_stale=True)
    assert not d.allowed
    assert "desatualizados" in d.reason


def test_insufficient_balance_blocks():
    cfg = RiskConfig()
    rm = RiskManager(cfg, initial_balance=0.5, stake=1.0)
    d = rm.can_open(0)
    assert not d.allowed
    assert "saldo" in d.reason


def test_reset_session_preserves_balance():
    rm = _rm(min_seconds_between_operations=0)
    rm.register_open(0)
    rm.register_result(True, 1.0, 0.8)
    bal = rm.state.balance
    rm.reset_session()
    assert rm.state.operations == 0
    assert rm.state.balance == bal
