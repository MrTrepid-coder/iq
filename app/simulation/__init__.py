"""Simulação automática de operações (expiração de 60 segundos).

Máquina de estados explícita:

    INICIALIZACAO -> AGUARDANDO_DADOS -> ANALISANDO -> SINAL_DISPONIVEL
        -> OPERACAO_ABERTA -> OPERACAO_ENCERRADA -> (AGUARDANDO_DADOS ...)
    SUSPENSO_POR_RISCO, ERRO_INTEGRACAO e ENCERRAMENTO a partir de qualquer estado.

Regras temporais (expiração de 1 minuto):
- instante do sinal = timestamp do candle de decisão (ts_signal);
- instante de entrada hipotético = ts_signal + timeframe (abertura do candle seguinte);
- instante de expiração = ts_entry + expiry_s (60s);
- o preço de entrada NÃO é o fechamento do candle de decisão (não era executável
  no instante do sinal); usamos a ABERTURA do candle seguinte quando disponível;
- o resultado é o fechamento do candle no índice de expiração.

Garantias:
- NÃO envia ordens reais: só registra operações simuladas;
- idempotência por `dedup_key = symbol|strategy|ts_signal|direction`;
- persistência em JSONL com recuperação de histórico ao reiniciar.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from ..config import SimulationConfig, RiskConfig
from ..risk import RiskManager


class SimState:
    INICIALIZACAO = "INICIALIZACAO"
    AGUARDANDO_DADOS = "AGUARDANDO_DADOS"
    ANALISANDO = "ANALISANDO"
    SINAL_DISPONIVEL = "SINAL_DISPONIVEL"
    OPERACAO_ABERTA = "OPERACAO_ABERTA"
    OPERACAO_ENCERRADA = "OPERACAO_ENCERRADA"
    SUSPENSO_POR_RISCO = "SUSPENSO_POR_RISCO"
    ERRO_INTEGRACAO = "ERRO_INTEGRACAO"
    ENCERRAMENTO = "ENCERRAMENTO"

    ALL = (INICIALIZACAO, AGUARDANDO_DADOS, ANALISANDO, SINAL_DISPONIVEL,
           OPERACAO_ABERTA, OPERACAO_ENCERRADA, SUSPENSO_POR_RISCO,
           ERRO_INTEGRACAO, ENCERRAMENTO)

    # transições permitidas (validação da máquina)
    TRANSITIONS = {
        INICIALIZACAO: {AGUARDANDO_DADOS, ENCERRAMENTO},
        AGUARDANDO_DADOS: {ANALISANDO, ERRO_INTEGRACAO, SUSPENSO_POR_RISCO, ENCERRAMENTO},
        ANALISANDO: {SINAL_DISPONIVEL, AGUARDANDO_DADOS, ERRO_INTEGRACAO,
                     SUSPENSO_POR_RISCO, ENCERRAMENTO},
        SINAL_DISPONIVEL: {OPERACAO_ABERTA, AGUARDANDO_DADOS, SUSPENSO_POR_RISCO,
                           ENCERRAMENTO},
        OPERACAO_ABERTA: {OPERACAO_ENCERRADA, ENCERRAMENTO},
        OPERACAO_ENCERRADA: {AGUARDANDO_DADOS, ENCERRAMENTO},
        SUSPENSO_POR_RISCO: {AGUARDANDO_DADOS, ENCERRAMENTO},
        ERRO_INTEGRACAO: {AGUARDANDO_DADOS, ENCERRAMENTO},
        ENCERRAMENTO: set(),
    }


STRATEGY_VERSION = "1.0.0"


@dataclass
class SimOperation:
    op_id: str
    symbol: str
    strategy_id: str
    direction: int                 # +1 CALL, -1 PUT
    ts_signal: int                 # instante de geração do sinal
    ts_entry: int                  # instante hipotético de entrada
    ts_expiry: int                 # instante de expiração
    entry_price: float             # preço hipotético de entrada (não o close do sinal)
    expiry_s: int = 60             # expiração em segundos
    payout: float = 0.80
    stake: float = 1.0
    exit_price: Optional[float] = None
    exit_condition: str = ""
    result: Optional[str] = None   # "WIN" | "LOSS" | "NAO_RESOLVIDO"
    reason: str = ""
    strategy_version: str = STRATEGY_VERSION
    config_snapshot: dict = field(default_factory=dict)
    probability: Optional[float] = None

    @property
    def dedup_key(self) -> str:
        return f"{self.symbol}|{self.strategy_id}|{self.ts_signal}|{self.direction}"

    def to_dict(self) -> dict:
        return asdict(self)


class SimulationEngine:
    """Orquestra a simulação: estados, risco, idempotência e persistência."""

    def __init__(self, sim_cfg: Optional[SimulationConfig] = None,
                 risk_cfg: Optional[RiskConfig] = None,
                 store_path: str = "simulation.jsonl",
                 logger=None):
        self.sim_cfg = sim_cfg or SimulationConfig()
        self.risk = RiskManager(risk_cfg, initial_balance=self.sim_cfg.initial_virtual_balance,
                                stake=self.sim_cfg.stake)
        self.store_path = store_path
        self.log = logger
        self.state = SimState.INICIALIZACAO
        self.operations: list[SimOperation] = []
        self._seen: set[str] = set()
        self._open: Optional[SimOperation] = None
        self._load_history()
        self._transition(SimState.AGUARDANDO_DADOS)

    # ------------------------------------------------------------------ #
    # Máquina de estados
    # ------------------------------------------------------------------ #
    def _transition(self, new_state: str) -> None:
        allowed = SimState.TRANSITIONS.get(self.state, set())
        if new_state not in allowed and new_state != self.state:
            raise ValueError(f"transição inválida: {self.state} -> {new_state}")
        self.state = new_state
        self._log("info", f"estado -> {new_state}")

    def _log(self, level: str, msg: str) -> None:
        if self.log is not None:
            getattr(self.log, level, self.log.info)(msg)

    # ------------------------------------------------------------------ #
    # Persistência / idempotência
    # ------------------------------------------------------------------ #
    def _load_history(self) -> None:
        if not os.path.exists(self.store_path):
            return
        # Log append-only: cada mudança de estado grava uma nova linha com o MESMO
        # op_id. Ao recarregar, mantém-se a ÚLTIMA versão por op_id (idempotência
        # e recuperação consistente após reinício).
        latest: dict = {}
        order: list = []
        with open(self.store_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    op = SimOperation(**{k: v for k, v in d.items()
                                         if k in SimOperation.__dataclass_fields__})
                except TypeError:
                    continue
                if op.op_id not in latest:
                    order.append(op.op_id)
                latest[op.op_id] = op
        self.operations = [latest[i] for i in order]
        for op in self.operations:
            self._seen.add(op.dedup_key)
            # reconstrói saldo/pnl a partir do histórico resolvido
            if op.result in ("WIN", "LOSS"):
                self.risk.register_open(op.ts_signal, "")
                self.risk.register_result(op.result == "WIN", op.stake, op.payout)

    def _append(self, op: SimOperation) -> None:
        os.makedirs(os.path.dirname(self.store_path) or ".", exist_ok=True)
        with open(self.store_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(op.to_dict(), ensure_ascii=False) + "\n")

    def is_duplicate(self, symbol: str, strategy_id: str, ts_signal: int,
                     direction: int) -> bool:
        key = f"{symbol}|{strategy_id}|{ts_signal}|{direction}"
        return key in self._seen

    # ------------------------------------------------------------------ #
    # Fluxo principal
    # ------------------------------------------------------------------ #
    def open_simulation(self, *, symbol: str, strategy_id: str, direction: int,
                        ts_signal: int, entry_price: float, reason: str = "",
                        payout: Optional[float] = None,
                        probability: Optional[float] = None,
                        data_stale: bool = False) -> Optional[SimOperation]:
        """Abre uma operação SIMULADA respeitando risco e idempotência."""
        payout = self.sim_cfg.payout if payout is None else payout
        tf = self.sim_cfg.timeframe_s
        expiry_s = self.sim_cfg.expiry_candles * tf
        key = f"{symbol}|{strategy_id}|{ts_signal}|{direction}"

        if self.is_duplicate(symbol, strategy_id, ts_signal, direction):
            self._log("info", f"operação duplicada ignorada ({key})")
            return None

        decision = self.risk.can_open(ts_signal, fetch_key=key, data_stale=data_stale)
        if not decision.allowed:
            self._log("warning", f"bloqueio de risco: {decision.reason}")
            self.risk.suspend(decision.reason)
            self._transition(SimState.SUSPENSO_POR_RISCO)
            return None

        expiry_ts = ts_signal + tf
        op = SimOperation(
            op_id=f"{symbol}-{strategy_id}-{ts_signal}-{direction}",
            symbol=symbol, strategy_id=strategy_id, direction=direction,
            ts_signal=ts_signal, ts_entry=expiry_ts, ts_expiry=expiry_ts + expiry_s,
            entry_price=float(entry_price), expiry_s=expiry_s, payout=payout,
            stake=self.risk.next_stake(), reason=reason, probability=probability,
            config_snapshot={"payout": payout, "expiry_candles": self.sim_cfg.expiry_candles,
                             "timeframe_s": tf, "stake": self.sim_cfg.stake},
        )
        self.operations.append(op)
        self._seen.add(op.dedup_key)
        self.risk.register_open(ts_signal, key)
        self._transition(SimState.ANALISANDO)
        self._transition(SimState.SINAL_DISPONIVEL)
        self._transition(SimState.OPERACAO_ABERTA)
        self._open = op
        self._append(op)
        self._log("info", f"operação simulada aberta {op.op_id} "
                          f"{'CALL' if direction == 1 else 'PUT'} @ {entry_price}")
        return op

    def resolve(self, exit_price: float, ts_expiry: int,
                condition: str = "") -> Optional[SimOperation]:
        """Resolve a operação aberta contra o preço de expiração."""
        op = self._open
        if op is None:
            return None
        if op.direction == 1:
            won = exit_price > op.entry_price
        else:
            won = exit_price < op.entry_price
        op.exit_price = float(exit_price)
        op.exit_condition = condition or f"fechamento em {ts_expiry}"
        op.result = "WIN" if won else "LOSS"
        self.risk.register_result(won, op.stake, op.payout)
        self._transition(SimState.OPERACAO_ENCERRADA)
        self._append(op)
        self._open = None
        self._transition(SimState.AGUARDANDO_DADOS)
        self._log("info", f"operação simulada encerrada {op.op_id}: {op.result}")
        return op

    def mark_data_failure(self, reason: str = "") -> None:
        d = self.risk.register_data_failure(reason)
        if not d.allowed:
            self._transition(SimState.SUSPENSO_POR_RISCO)
        else:
            self._transition(SimState.ERRO_INTEGRACAO)

    # ------------------------------------------------------------------ #
    # Métricas
    # ------------------------------------------------------------------ #
    def stats(self) -> dict:
        resolved = [o for o in self.operations if o.result in ("WIN", "LOSS")]
        wins = sum(1 for o in resolved if o.result == "WIN")
        n = len(resolved)
        return {
            "state": self.state,
            "operations": len(self.operations),
            "resolved": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate": (wins / n) if n else None,
            "session_pnl": self.risk.state.session_pnl,
            "balance": self.risk.state.balance,
            "suspended": self.risk.state.suspended,
            "suspend_reason": self.risk.state.suspend_reason,
            "simulation_mode": True,
        }

    def shutdown(self) -> None:
        self._transition(SimState.ENCERRAMENTO)
