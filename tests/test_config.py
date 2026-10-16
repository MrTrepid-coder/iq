"""Testes de configuração e bloqueio de execução real."""
import pytest

from app.config import (AppConfig, RiskConfig, ScannerConfig, SimulationConfig,
                        load_config, ensure_real_execution_blocked,
                        RealExecutionBlocked, DEFAULT_CONFIG)


def test_default_config_is_valid_and_simulation():
    cfg = load_config()
    assert cfg.simulation_mode is True
    assert DEFAULT_CONFIG.simulation_mode is True


def test_config_rejects_disabling_simulation():
    cfg = AppConfig()
    cfg.simulation_mode = False
    with pytest.raises(ValueError):
        cfg.validate()


def test_risk_config_invalid_values():
    with pytest.raises(ValueError):
        RiskConfig(max_operations_per_session=0).validate()
    with pytest.raises(ValueError):
        RiskConfig(max_session_loss=-1).validate()
    with pytest.raises(ValueError):
        RiskConfig(max_consecutive_losses=0).validate()
    with pytest.raises(ValueError):
        RiskConfig(max_stake=0).validate()


def test_scan_config_requires_warmup():
    with pytest.raises(ValueError):
        ScannerConfig(min_candles=10).validate()
    with pytest.raises(ValueError):
        ScannerConfig(assets=["a", "b"], max_assets=1).validate()


def test_config_rejects_stake_above_max():
    cfg = AppConfig()
    cfg.simulation.stake = 5.0
    cfg.risk.max_stake = 2.0
    with pytest.raises(ValueError):
        cfg.validate()


def test_unknown_override_rejected():
    with pytest.raises(ValueError):
        load_config(nao_existe=1)


def test_real_execution_always_blocked():
    with pytest.raises(RealExecutionBlocked):
        ensure_real_execution_blocked("teste")
