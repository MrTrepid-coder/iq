"""Registro estruturado de sinais e resultados (aprendizado contínuo).

Cada sinal é gravado em JSONL com TODAS as informações usadas na decisão e,
quando o resultado for conhecido, atualizado com o desfecho. O sistema pode
recalibrar modelos com esses dados, sempre com validação temporal e controle
de versão — nunca alterando o modelo por uma sequência curta de vitórias.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np

from .analysis.context import AnalysisContext
from .probability import FEATURE_NAMES


MODEL_VERSION = "0.1.0"


@dataclass
class JournalEntry:
    ts: int
    symbol: str
    timeframe_s: int
    direction: int
    strategy_id: str
    entry_price: float
    expiry: int
    payout: float
    status: str
    probability: Optional[float]
    confirmations: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    features: Optional[list] = None
    outcome: Optional[bool] = None      # None até ser resolvido
    exit_price: Optional[float] = None
    model_version: str = MODEL_VERSION


class Journal:
    def __init__(self, path: str = "journal.jsonl"):
        self.path = path

    def record(self, ctx: AnalysisContext, direction: int, strategy_id: str,
               expiry: int, payout: float, status: str,
               probability: Optional[float], confirmations: list[str],
               risks: list[str]) -> JournalEntry:
        from .probability import extract_features
        entry = JournalEntry(
            ts=ctx.cur.ts, symbol=getattr(ctx, "asset", "") or "—",
            timeframe_s=60, direction=direction, strategy_id=strategy_id,
            entry_price=ctx.cur.close, expiry=expiry, payout=payout,
            status=status, probability=probability,
            confirmations=list(confirmations), risks=list(risks),
            features=[float(v) for v in extract_features(ctx)],
        )
        self._append(entry)
        return entry

    def _append(self, entry: JournalEntry) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def load(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def resolved_dataset(self):
        """Retorna (X, y) apenas dos sinais com resultado conhecido."""
        rows = [r for r in self.load() if r.get("outcome") is not None
                and r.get("features")]
        if not rows:
            return np.empty((0, len(FEATURE_NAMES))), np.array([])
        X = np.array([r["features"] for r in rows], dtype=float)
        y = np.array([1.0 if r["outcome"] else 0.0 for r in rows], dtype=float)
        return X, y
