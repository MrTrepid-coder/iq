"""Configuração centralizada, validada na inicialização.

Regras de segurança (inegociáveis):
- SIMULATION_MODE é True por padrão e NÃO pode ser desativado por variável de
  ambiente. A execução real permanece bloqueada nesta versão.
- `ensure_real_execution_blocked()` é o guard chamado pelo fluxo de simulação;
  ele SEMPRE recusa, porque não existe integração autorizada com a IQ Option.

Qualquer valor inválido gera ValueError no carregamento (falha segura), nunca
um default silencioso que possa liberar comportamento perigoso.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional


# --------------------------------------------------------------------------- #
# Bloqueio permanente da execução real
# --------------------------------------------------------------------------- #
class RealExecutionBlocked(RuntimeError):
    """Levantada quando algo tenta habilitar/enviar operação real."""


def ensure_real_execution_blocked(reason: str = "") -> None:
    """Sempre recusa. Nenhuma configuração de ambiente libera execução real.

    Justificativa documental: a IQ Option não expõe API oficial de execução para
    o público. Bibliotecas de terceiros que interceptam o canal interno não têm
    autorização/compatibilidade comprovadas e são proibidas pelo briefing. Enquanto
    não houver uma interface oficial verificável, o sistema recusa qualquer envio.
    """
    raise RealExecutionBlocked(
        "Execução real DESATIVADA e bloqueada por política. "
        "Não existe integração autorizada com a IQ Option. "
        + (f"Motivo: {reason}" if reason else "")
        + " Pré-requisitos para futura avaliação: documentação oficial de execução, "
          "consentimento explícito do usuário, isolamento de credenciais e revisão de termos."
    )


# --------------------------------------------------------------------------- #
# Configuração de simulação/risco (ambiente VIRTUAL)
# --------------------------------------------------------------------------- #
@dataclass
class SimulationConfig:
    """Parâmetros do simulador. Todos aplicados somente ao ambiente virtual."""
    enabled: bool = True
    timeframe_s: int = 60                # expiração base = 1 candle de 1 minuto
    expiry_candles: int = 1              # expiração de 60 segundos
    payout: float = 0.80                 # payout hipotético (não constante na prática)
    initial_virtual_balance: float = 100.0
    stake: float = 1.0                   # stake fixa (NUNCA martingale)


@dataclass
class RiskConfig:
    """Limites de risco conservadores, explícitos e validados."""
    max_operations_per_session: int = 20
    max_session_loss: float = 3.0        # em unidades de stake
    max_consecutive_losses: int = 5
    min_seconds_between_operations: int = 60
    max_stake: float = 2.0
    max_open_positions: int = 1          # exposição simultânea
    pause_after_data_failures: int = 3   # falhas de dados antes de suspender
    duplicate_window_s: int = 300        # janela de bloqueio de sinal duplicado

    def validate(self) -> None:
        if self.max_operations_per_session <= 0:
            raise ValueError("max_operations_per_session deve ser > 0")
        if self.max_session_loss <= 0:
            raise ValueError("max_session_loss deve ser > 0")
        if self.max_consecutive_losses <= 0:
            raise ValueError("max_consecutive_losses deve ser > 0")
        if self.min_seconds_between_operations < 0:
            raise ValueError("min_seconds_between_operations não pode ser negativo")
        if self.max_stake <= 0:
            raise ValueError("max_stake deve ser > 0")
        if self.max_open_positions <= 0:
            raise ValueError("max_open_positions deve ser > 0")
        if not (0.0 <= self.payout_placeholder() <= 2.0):
            raise ValueError("payout fora de faixa")

    def payout_placeholder(self) -> float:
        return 0.80


@dataclass
class ScannerConfig:
    """Configuração do scanner multi-ativos."""
    assets: List[str] = field(default_factory=list)
    timeframe_s: int = 60
    payout: float = 0.80
    min_candles: int = 250               # mínimo para análise confiável
    max_assets: int = 20                 # limite de exposição do scanner
    stale_after_s: int = 300             # dado mais velho que isso = desatualizado

    def validate(self) -> None:
        if self.min_candles < 60:
            raise ValueError("min_candles deve ser >= 60 (aquecimento de indicadores)")
        if self.max_assets <= 0:
            raise ValueError("max_assets deve ser > 0")
        if len(self.assets) > self.max_assets:
            raise ValueError(f"scanner com {len(self.assets)} ativos excede "
                             f"max_assets={self.max_assets}")
        if not (0.0 < self.payout <= 1.5):
            raise ValueError("payout deve estar em (0, 1.5]")


@dataclass
class AppConfig:
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    data_dir: str = "data"
    log_dir: str = "logs"
    journal_path: str = "journal.jsonl"
    simulation_mode: bool = True          # inegociável

    def validate(self) -> "AppConfig":
        if not self.simulation_mode:
            raise ValueError("simulation_mode deve permanecer True nesta versão "
                             "(execução real bloqueada).")
        if not (0.0 < self.simulation.payout <= 1.5):
            raise ValueError("simulation.payout fora de faixa")
        if self.simulation.stake <= 0:
            raise ValueError("simulation.stake deve ser > 0")
        if self.simulation.stake > self.risk.max_stake:
            raise ValueError("simulation.stake maior que risk.max_stake")
        if self.simulation.expiry_candles <= 0:
            raise ValueError("simulation.expiry_candles deve ser > 0")
        self.risk.validate()
        self.scanner.validate()
        return self

    def to_dict(self) -> dict:
        return asdict(self)


def load_config(**overrides) -> AppConfig:
    """Monta e valida a configuração. `overrides` aceita chaves de AppConfig.

    Lê apenas variáveis de ambiente NÃO sensíveis e nunca de .env com segredos.
    A presença de variáveis de ambiente NÃO altera simulation_mode.
    """
    cfg = AppConfig()
    # simulation_mode não é lido do ambiente de propósito (bloqueio estrito)
    for k, v in overrides.items():
        if not hasattr(cfg, k):
            raise ValueError(f"config desconhecida: {k}")
        setattr(cfg, k, v)
    return cfg.validate()


DEFAULT_CONFIG = load_config()
