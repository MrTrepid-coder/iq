"""Coletor de dados reais públicos (Binance) — fonte autorizada e gratuita.

A API pública de klines da Binance é documentada e liberada para consulta
pública (sem chave, sem login). Usada aqui como FONTE DE VALIDAÇÃO do motor
de análise. Não é a IQ Option e não substitui dados da plataforma; serve para
testar o software com dados de mercado reais de um ativo de referência.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

from app.core.candles import Candle, CandleSeries

BASE = "https://api.binance.com/api/v3/klines"


def fetch_klines(symbol: str = "BTCUSDT", interval: str = "1m",
                 limit: int = 5000) -> CandleSeries:
    limit = max(1, min(limit, 5000))
    all_rows: list[list] = []
    end_time = None
    remaining = limit
    while remaining > 0:
        batch = min(1000, remaining)
        params = {"symbol": symbol, "interval": interval, "limit": batch}
        if end_time is not None:
            params["endTime"] = end_time
        url = BASE + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "iq-analyzer/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        if not rows:
            break
        all_rows = rows + all_rows
        end_time = rows[0][0] - 1
        remaining -= batch
        if len(rows) < batch:
            break

    candles: list[Candle] = []
    for r in all_rows:
        # r = [openTime, open, high, low, close, volume, closeTime, ...]
        candles.append(Candle(
            ts=int(r[0] // 1000),
            open=float(r[1]), high=float(r[2]), low=float(r[3]),
            close=float(r[4]), volume=float(r[5]),
        ))
    # dedup por ts e ordena
    seen = {}
    for c in candles:
        seen[c.ts] = c
    candles = [seen[k] for k in sorted(seen)]
    return CandleSeries(candles, symbol=symbol, timeframe_s=_interval_seconds(interval))


def _interval_seconds(interval: str) -> int:
    unit = interval[-1]
    num = int(interval[:-1])
    return num * {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit, 60)


if __name__ == "__main__":
    s = fetch_klines("BTCUSDT", "1m", 3000)
    s.save_csv("data/BTCUSDT_1m.csv")
    print(f"{len(s)} candles salvos.")
