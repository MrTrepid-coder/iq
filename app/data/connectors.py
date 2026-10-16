"""Adaptadores de fonte de dados (arquitetura desacoplada).

Classificação honesta das fontes (exigida pelo briefing):

A. Integração OFICIAL documentada e validada .......... NÃO EXISTE
   — a IQ Option não publica API oficial de execução/mercado para o público.
B. Biblioteca de terceiros sem autorização comprovada ... PROIBIDA
   — intercepta canal interno; fere os termos; não implementada aqui.
C. Fonte histórica/importada ........................... SUPORTADA (CSV)
D. Adaptador simulado (só testes) ...................... SUPORTADA (sintético)

Portanto, o adaptador "real" existe apenas como interface NÃO implementada que
falha de forma segura. O restante do sistema opera com dados históricos,
importados e o coletor por leitura de tela (não é rede/login).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..core.candles import CandleSeries


class DataSource(ABC):
    """Interface comum de fonte de candles."""

    name: str = "base"
    official: bool = False
    kind: str = "desconhecido"   # "historico" | "importado" | "captura" | "simulado" | "indisponivel"

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def load(self, symbol: str) -> CandleSeries: ...


class CsvSource(DataSource):
    """Candles históricos/importados de um arquivo CSV local. (categoria C)"""
    name = "csv"
    kind = "historico"

    def __init__(self, path: str):
        self.path = path

    def is_available(self) -> bool:
        import os
        return os.path.exists(self.path)

    def load(self, symbol: str = "") -> CandleSeries:
        s = CandleSeries.from_csv(self.path, symbol=symbol)
        return s


class ScreenCaptureSource(DataSource):
    """Coletor por leitura de tela (digitaliza o que já está visível). (categoria C)"""
    name = "screen_capture"
    kind = "captura"

    def __init__(self, calibration):
        self.calibration = calibration

    def is_available(self) -> bool:
        try:
            from .capture import ImageGrab  # type: ignore
            return ImageGrab is not None
        except Exception:
            return False

    def load(self, symbol: str = "SCREEN_CAPTURE") -> CandleSeries:
        from .capture import capture_snapshot
        return capture_snapshot(self.calibration)


class RealBrokerAdapter(DataSource):
    """Adaptador de EXECUÇÃO/MERCADO real da IQ Option — NÃO IMPLEMENTADO.

    Não há endpoint, protocolo ou método autorizado comprovado. Qualquer tentativa
    de uso falha de forma segura (fail-safe), nunca simulando sucesso.
    """
    name = "iq_option_real"
    official = False
    kind = "indisponivel"

    def is_available(self) -> bool:
        return False

    def load(self, symbol: str = "") -> CandleSeries:  # pragma: no cover - sempre falha
        raise RuntimeError(
            "Fonte real indisponível: não existe integração autorizada com a "
            "IQ Option. Use CSV, dados importados ou o coletor por leitura de tela."
        )

    def submit_real_operation(self, *args, **kwargs):  # pragma: no cover - bloqueio explícito
        from ..config import ensure_real_execution_blocked
        ensure_real_execution_blocked("tentativa de operação real no adaptador indisponível")


# Registro documental das fontes conhecidas e do seu estado
KNOWN_SOURCES = {
    "csv": {"kind": "historico", "available": True,
            "note": "CSV exportado/fornecido pelo usuário."},
    "screen_capture": {"kind": "captura", "available": True,
                       "note": "Lê apenas a tela local; sem rede/login."},
    "synthetic": {"kind": "simulado", "available": True,
                  "note": "Apenas para testes; NÃO é dado de mercado."},
    "iq_option_real": {"kind": "indisponivel", "available": False,
                       "note": "Sem API oficial; execução real bloqueada."},
}
