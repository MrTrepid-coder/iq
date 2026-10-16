"""Gestão de risco (somente ambiente virtual/simulado).

Controles implementados:
- limite de operações por sessão;
- limite de perda simulada por sessão;
- limite de perdas consecutivas;
- intervalo mínimo entre operações;
- bloqueio de operações duplicadas (mesmo ativo/direção/janela);
- validação de saldo virtual e stake;
- limite de exposição simultânea;
- pausa após falhas de dados/integração;
- interrupção automática e registro do motivo de cada bloqueio.

NÃO usa martingale, recuperação de perdas nem aumento de stake após derrota —
`next_stake()` devolve sempre a stake fixa configurada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..config import RiskConfig


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:  # permite `if decision:`
        return self.allowed


@dataclass
class RiskState:
    operations: int = 0
    session_pnl: float = 0.0          # em unidades de stake
    consecutive_losses: int = 0
    last_operation_ts: Optional[int] = None
    data_failures: int = 0
    suspended: bool = False
    suspend_reason: str = ""
    open_positions: int = 0
    balance: float = 0.0
    recent_keys: list = field(default_factory=list)   # (key, ts) p/ deduplicação


class RiskManager:
    """Aplica os limites do RiskConfig a cada operação simulada."""

    def __init__(self, config: Optional[RiskConfig] = None,
                 initial_balance: float = 100.0, stake: float = 1.0):
        self.cfg = config or RiskConfig()
        self.cfg.validate()
        self.state = RiskState(balance=initial_balance)
        self.stake = stake
        if stake > self.cfg.max_stake:
            raise ValueError("stake inicial excede max_stake")

    # ------------------------------------------------------------------ #
    # Consultas
    # ------------------------------------------------------------------ #
    def can_open(self, ts: int, fetch_key: str = "",
                 data_stale: bool = False) -> RiskDecision:
        st = self.state
        if data_stale:
            return RiskDecision(False, "dados desatualizados — operação bloqueada")
        if st.suspended:
            return RiskDecision(False, f"sessão suspensa: {st.suspend_reason}")
        if st.operations >= self.cfg.max_operations_per_session:
            return RiskDecision(False, "limite de operações por sessão atingido")
        if st.session_pnl <= -abs(self.cfg.max_session_loss):
            return RiskDecision(False, "limite de perda por sessão atingido")
        if st.consecutive_losses >= self.cfg.max_consecutive_losses:
            return RiskDecision(False, "limite de perdas consecutivas atingido")
        if st.open_positions >= self.cfg.max_open_positions:
            return RiskDecision(False, "limite de exposição simultânea atingido")
        if self.stake > st.balance:
            return RiskDecision(False, "saldo virtual insuficiente para a stake")
        if st.last_operation_ts is not None:
            gap = ts - st.last_operation_ts
            if 0 <= gap < self.cfg.min_seconds_between_operations:
                return RiskDecision(
                    False, f"intervalo mínimo entre operações ({gap}s < "
                           f"{self.cfg.min_seconds_between_operations}s)")
        if fetch_key and self._is_duplicate(fetch_key, ts):
            return RiskDecision(False, "operação duplicada bloqueada")
        return RiskDecision(True, "")

    def _is_duplicate(self, key: str, ts: int) -> bool:
        for k, t in self.state.recent_keys:
            if k == key and abs(ts - t) <= self.cfg.duplicate_window_s:
                return True
        return False

    # ------------------------------------------------------------------ #
    # Registro de eventos
    # ------------------------------------------------------------------ #
    def register_open(self, ts: int, fetch_key: str = "") -> None:
        st = self.state
        st.operations += 1
        st.open_positions += 1
        st.last_operation_ts = ts
        if fetch_key:
            st.recent_keys.append((fetch_key, ts))
            # poda janela de deduplicação
            cutoff = ts - self.cfg.duplicate_window_s
            st.recent_keys = [(k, t) for k, t in st.recent_keys if t >= cutoff]
            st.recent_keys = st.recent_keys[-200:]

    def register_result(self, won: bool, stake: float, payout: float) -> None:
        """Atualiza PnL e sequência de perdas. Sem martingale."""
        st = self.state
        st.open_positions = max(0, st.open_positions - 1)
        delta = (stake * payout) if won else (-stake)
        st.session_pnl += delta
        st.balance += delta
        if won:
            st.consecutive_losses = 0
        else:
            st.consecutive_losses += 1

    def register_data_failure(self, reason: str = "") -> RiskDecision:
        """Contabiliza falha de dados; suspende ao ultrapassar o limite."""
        st = self.state
        st.data_failures += 1
        if st.data_failures >= self.cfg.pause_after_data_failures:
            st.suspended = True
            st.suspend_reason = ("falhas de dados/integração consecutivas"
                                 + (f": {reason}" if reason else ""))
            return RiskDecision(False, st.suspend_reason)
        return RiskDecision(True, "falha registrada")

    def register_data_success(self) -> None:
        self.state.data_failures = 0

    def suspend(self, reason: str) -> None:
        self.state.suspended = True
        self.state.suspend_reason = reason

    def reset_session(self) -> None:
        """Reinicia limites. Regra documentada: reinício MANUAL e explícito.

        Zera contadores de sessão; preserva saldo virtual acumulado.
        """
        self.state = RiskState(balance=self.state.balance)

    def next_stake(self) -> float:
        """Stake fixa. Nunca aumenta após derrota (proibido martingale)."""
        return self.stake
