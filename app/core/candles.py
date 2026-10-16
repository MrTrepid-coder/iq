"""Candles OHLCV com validação e reamostragem.

Regras:
- Nunca expõe dados futuros: todo acesso é por índice (i) usando apenas
  candles[0..i] via `window(end_exclusive)`.
- Valida coerência OHLC: high >= max(open, close) e low <= min(open, close).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence
import csv
import math


@dataclass(frozen=True)
class Candle:
    ts: int            # epoch seconds do início do candle
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range_(self) -> float:
        return self.high - self.low

    @property
    def direction(self) -> int:
        """+1 alta, -1 baixa, 0 neutro."""
        if self.close > self.open:
            return 1
        if self.close < self.open:
            return -1
        return 0

    @property
    def upper_shadow(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        return min(self.open, self.close) - self.low

    def is_valid(self) -> bool:
        if self.high < max(self.open, self.close):
            return False
        if self.low > min(self.open, self.close):
            return False
        if self.low > self.high:
            return False
        if any(math.isnan(v) or math.isinf(v) for v in (self.open, self.high, self.low, self.close)):
            return False
        return True


class CandleSeries:
    """Sequência ordenada de candles + metadados do ativo/período."""

    def __init__(self, candles: Sequence[Candle], symbol: str = "", timeframe_s: int = 60):
        self.candles: list[Candle] = list(candles)
        self.symbol = symbol
        self.timeframe_s = timeframe_s
        self._validate()

    def _validate(self) -> None:
        prev_ts = -1
        for i, c in enumerate(self.candles):
            if not c.is_valid():
                raise ValueError(f"Candle inválido no índice {i}: {c}")
            if c.ts <= prev_ts:
                raise ValueError(f"Candles fora de ordem no índice {i}: ts={c.ts} <= {prev_ts}")
            prev_ts = c.ts

    def __len__(self) -> int:
        return len(self.candles)

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            return self.candles[idx]
        return self.candles[idx]

    @property
    def closes(self) -> list[float]:
        return [c.close for c in self.candles]

    @property
    def highs(self) -> list[float]:
        return [c.high for c in self.candles]

    @property
    def lows(self) -> list[float]:
        return [c.low for c in self.candles]

    @property
    def opens(self) -> list[float]:
        return [c.open for c in self.candles]

    @property
    def volumes(self) -> list[float]:
        return [c.volume for c in self.candles]

    def window(self, end_exclusive: int) -> "CandleSeries":
        """Retorna série contendo apenas candles [0, end_exclusive).

        É o único meio legítimo de obter dados para uma decisão no índice i.
        """
        if end_exclusive < 0:
            raise ValueError("end_exclusive negativo")
        return CandleSeries(self.candles[:end_exclusive], self.symbol, self.timeframe_s)

    # ------------------------------------------------------------------ #
    # Carregamento
    # ------------------------------------------------------------------ #
    @classmethod
    def from_csv(cls, path: str, symbol: str = "", timeframe_s: int = 60) -> "CandleSeries":
        """CSV com cabeçalho: ts,open,high,low,close[,volume].

        ts pode ser epoch segundos ou ISO 8601 (YYYY-MM-DD HH:MM:SS).
        """
        candles: list[Candle] = []
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            required = {"ts", "open", "high", "low", "close"}
            if not reader.fieldnames or not required.issubset({f.strip() for f in reader.fieldnames}):
                raise ValueError(f"CSV precisa das colunas {sorted(required)}; obtido {reader.fieldnames}")
            for row_no, row in enumerate(reader, start=2):
                ts_raw = (row.get("ts") or "").strip()
                ts = _parse_ts(ts_raw, row_no)
                vol = (row.get("volume") or "0").strip() or "0"
                c = Candle(
                    ts=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(vol),
                )
                candles.append(c)
        if not candles:
            raise ValueError("CSV vazio")
        return cls(candles, symbol=symbol, timeframe_s=timeframe_s)

    def save_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["ts", "open", "high", "low", "close", "volume"])
            for c in self.candles:
                writer.writerow([c.ts, c.open, c.high, c.low, c.close, c.volume])

    # ------------------------------------------------------------------ #
    # Reamostragem (contexto de timeframe maior)
    # ------------------------------------------------------------------ #
    def resample(self, factor: int) -> "CandleSeries":
        """Agrupa candles consecutivos (`factor` unidades do timeframe base).

        Ex.: base=60s e factor=5 => 5 minutos.
        O candle agregado usa apenas os candles passados (sem lookahead):
        o timestamp é o do primeiro candle do grupo.
        """
        if factor < 1:
            raise ValueError("factor deve ser >= 1")
        out: list[Candle] = []
        cs = self.candles
        for i in range(0, len(cs), factor):
            group = cs[i:i + factor]
            out.append(Candle(
                ts=group[0].ts,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(c.volume for c in group),
            ))
        return CandleSeries(out, symbol=self.symbol, timeframe_s=self.timeframe_s * factor)

    def last_complete_ts(self) -> int:
        """Timestamp do último candle (considerado completo na coleta)."""
        return self.candles[-1].ts


def _resample_list(candles: Sequence[Candle], factor: int) -> list[Candle]:
    """Agrupa candles em blocos de `factor` (mesma semântica de CandleSeries.resample,
    mas sem revalidar a série de origem — evita custo O(n) por construção)."""
    out: list[Candle] = []
    for i in range(0, len(candles), factor):
        group = candles[i:i + factor]
        out.append(Candle(
            ts=group[0].ts, open=group[0].open,
            high=max(c.high for c in group), low=min(c.low for c in group),
            close=group[-1].close, volume=sum(c.volume for c in group),
        ))
    return out


def _parse_ts(raw: str, row_no: int) -> int:
    if not raw:
        raise ValueError(f"Linha {row_no}: ts vazio")
    if raw.isdigit():
        return int(raw)
    from datetime import datetime, timezone
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(raw, fmt)
            return int(dt.replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
    raise ValueError(f"Linha {row_no}: ts não reconhecido: {raw!r}")


def synthetic_series(n: int, seed: int = 7, start_price: float = 1.1000,
                     start_ts: int = 1_700_000_000, volatility: float = 0.0004,
                     timeframe_s: int = 60) -> CandleSeries:
    """Série sintética para testes (random walk com drift por regime).

    Usada apenas para testes unitários e demonstração — NÃO é dado real de mercado.
    """
    import random
    rng = random.Random(seed)
    candles: list[Candle] = []
    price = start_price
    drift = 0.0
    for i in range(n):
        if i % 60 == 0:
            drift = rng.choice([-1, 0, 1]) * volatility * 0.15
        o = price
        ret = rng.gauss(drift, volatility)
        c = o * (1 + ret)
        h = max(o, c) * (1 + abs(rng.gauss(0, volatility * 0.5)))
        l = min(o, c) * (1 - abs(rng.gauss(0, volatility * 0.5)))
        v = float(rng.randint(800, 4000))
        candles.append(Candle(ts=start_ts + i * timeframe_s, open=o, high=h, low=l, close=c, volume=v))
        price = c
    return CandleSeries(candles, symbol="SYNTH", timeframe_s=timeframe_s)
