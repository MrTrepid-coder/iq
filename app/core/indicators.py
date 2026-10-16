"""Indicadores técnicos calculados sem vazamento de dados futuros.

Todos os arrays de entrada são históricos; a função `rolling` (implementada
via índices) garante que o valor no índice i usa apenas dados [0..i].
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _as_array(values: Sequence[float]) -> np.ndarray:
    return np.asarray(values, dtype=float)


def _nan_array(n: int) -> np.ndarray:
    return np.full(n, np.nan)


# --------------------------------------------------------------------------- #
# Médias móveis
# --------------------------------------------------------------------------- #
def sma(values: Sequence[float], period: int) -> np.ndarray:
    """Média simples móvel. `out[i]` usa values[i-period+1..i]."""
    arr = _as_array(values)
    n = len(arr)
    if period <= 0:
        raise ValueError("period deve ser > 0")
    out = _nan_array(n)
    if n < period:
        return out
    csum = np.cumsum(np.insert(arr, 0, 0.0))
    out[period - 1:] = (csum[period:] - csum[:-period]) / period
    return out


def ema(values: Sequence[float], period: int) -> np.ndarray:
    """Exponential Moving Average (alpha = 2/(period+1))."""
    arr = _as_array(values)
    n = len(arr)
    if period <= 0:
        raise ValueError("period deve ser > 0")
    out = _nan_array(n)
    if n < period:
        return out
    alpha = 2.0 / (period + 1.0)
    # seed com SMA do primeiro bloco (evita depender de dados prévios inexistentes)
    prev = float(np.mean(arr[:period]))
    out[period - 1] = prev
    for i in range(period, n):
        prev = alpha * arr[i] + (1 - alpha) * prev
        out[i] = prev
    return out


# --------------------------------------------------------------------------- #
# RSI
# --------------------------------------------------------------------------- #
def rsi(values: Sequence[float], period: int = 14) -> np.ndarray:
    """RSI de Wilder (suavização 1/period)."""
    arr = _as_array(values)
    n = len(arr)
    out = _nan_array(n)
    if n < period + 1:
        return out
    delta = np.diff(arr)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    # médias iniciais = médias simples dos primeiros `period` deltas
    avg_gain = float(np.mean(gain[:period]))
    avg_loss = float(np.mean(loss[:period]))
    rsi_vals = _nan_array(n)
    if avg_loss == 0:
        rsi_vals[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_vals[period] = 100.0 - 100.0 / (1.0 + rs)
    for i in range(period, n - 1):
        avg_gain = (avg_gain * (period - 1) + gain[i]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i]) / period
        if avg_loss == 0:
            rsi_vals[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_vals[i + 1] = 100.0 - 100.0 / (1.0 + rs)
    out[period:] = rsi_vals[period:]
    return out


# --------------------------------------------------------------------------- #
# MACD
# --------------------------------------------------------------------------- #
def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """Retorna (macd_line, signal_line, histogram)."""
    arr = _as_array(values)
    n = len(arr)
    ema_fast = ema(arr, fast)
    ema_slow = ema(arr, slow)
    line = _nan_array(n)
    valid = ~np.isnan(ema_fast) & ~np.isnan(ema_slow)
    line[valid] = ema_fast[valid] - ema_slow[valid]
    # signal = EMA da linha MACD a partir do primeiro valor válido
    sig = _nan_array(n)
    idx_valid = np.where(valid)[0]
    if len(idx_valid) >= signal:
        start = idx_valid[0]
        seg = line[start:]
        seg_ema = ema(seg, signal)
        sig[start:] = seg_ema
    hist = _nan_array(n)
    both = ~np.isnan(line) & ~np.isnan(sig)
    hist[both] = line[both] - sig[both]
    return line, sig, hist


# --------------------------------------------------------------------------- #
# Bandas de Bollinger
# --------------------------------------------------------------------------- #
def bollinger(values: Sequence[float], period: int = 20, mult: float = 2.0):
    """Retorna (middle, upper, lower, bandwidth, %B)."""
    arr = _as_array(values)
    n = len(arr)
    mid = sma(arr, period)
    upper = _nan_array(n)
    lower = _nan_array(n)
    bw = _nan_array(n)
    pctb = _nan_array(n)
    for i in range(period - 1, n):
        window = arr[i - period + 1:i + 1]
        sd = float(np.std(window, ddof=0))
        m = float(mid[i])
        upper[i] = m + mult * sd
        lower[i] = m - mult * sd
        width = upper[i] - lower[i]
        bw[i] = (width / m * 100.0) if m else float("nan")
        if width > 0:
            pctb[i] = (arr[i] - lower[i]) / width
    return mid, upper, lower, bw, pctb


# --------------------------------------------------------------------------- #
# ATR
# --------------------------------------------------------------------------- #
def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
        period: int = 14) -> np.ndarray:
    """Average True Range com suavização de Wilder."""
    h = _as_array(highs)
    l = _as_array(lows)
    c = _as_array(closes)
    n = len(h)
    out = _nan_array(n)
    if n < period + 1:
        return out
    prev_close = c[:-1]
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(np.abs(h[1:] - prev_close), np.abs(l[1:] - prev_close)))
    # TR[0] definido como high-low do primeiro candle
    tr_full = np.empty(n)
    tr_full[0] = h[0] - l[0]
    tr_full[1:] = tr
    prev = float(np.mean(tr_full[1:period + 1]))
    out[period] = prev
    for i in range(period, n):
        prev = (prev * (period - 1) + tr_full[i]) / period
        out[i] = prev
    return out


# --------------------------------------------------------------------------- #
# ADX
# --------------------------------------------------------------------------- #
def adx(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
        period: int = 14):
    """Retorna (ADX, +DI, -DI) com suavização de Wilder."""
    h = _as_array(highs)
    l = _as_array(lows)
    c = _as_array(closes)
    n = len(h)
    out_adx = _nan_array(n)
    out_pdi = _nan_array(n)
    out_ndi = _nan_array(n)
    if n < 2 * period + 1:
        return out_adx, out_pdi, out_ndi
    up_move = np.zeros(n)
    down_move = np.zeros(n)
    up_move[1:] = np.maximum(h[1:] - h[:-1], 0.0)
    down_move[1:] = np.maximum(l[:-1] - l[1:], 0.0)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:],
                        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    smoothed_tr = float(np.sum(tr[1:period + 1]))
    smoothed_up = float(np.sum(up_move[1:period + 1]))
    smoothed_down = float(np.sum(down_move[1:period + 1]))
    dx = np.full(n, np.nan)
    for i in range(period, n):
        if i > period:
            smoothed_tr = smoothed_tr - smoothed_tr / period + tr[i]
            smoothed_up = smoothed_up - smoothed_up / period + up_move[i]
            smoothed_down = smoothed_down - smoothed_down / period + down_move[i]
        pdi = 100.0 * smoothed_up / smoothed_tr if smoothed_tr > 0 else 0.0
        ndi = 100.0 * smoothed_down / smoothed_tr if smoothed_tr > 0 else 0.0
        out_pdi[i] = pdi
        out_ndi[i] = ndi
        denom = pdi + ndi
        dx[i] = 100.0 * abs(pdi - ndi) / denom if denom > 0 else 0.0
    # ADX = EMA do DX (período `period`), iniciando no índice 2*period
    start = 2 * period
    if start < n:
        first_seg = dx[period:start + 1]
        first_seg = first_seg[~np.isnan(first_seg)]
        if len(first_seg) >= period:
            prev = float(np.mean(first_seg[:period]))
            out_adx[start] = prev
            for i in range(start + 1, n):
                prev = (prev * (period - 1) + dx[i]) / period
                out_adx[i] = prev
    return out_adx, out_pdi, out_ndi


# --------------------------------------------------------------------------- #
# VWAP (sessão — requer reset diário quando há datas)
# --------------------------------------------------------------------------- #
def vwap(highs, lows, closes, volumes, timestamps=None) -> np.ndarray:
    """VWAP cumulativo; reinicia quando o dia (UTC) masha, se timestamps fornecidos.

    Sem timestamps, calcula cumulativo sobre a série inteira.
    Só retorna valor quando volume > 0 é confiável; caso contrário NaN.
    """
    h = _as_array(highs)
    l = _as_array(lows)
    c = _as_array(closes)
    v = _as_array(volumes)
    n = len(h)
    out = _nan_array(n)
    if n == 0:
        return out
    if float(np.nansum(v)) <= 0:
        return out  # volume sem significado => NaN, não forçar cálculo
    typical = (h + l + c) / 3.0
    cum_pv = 0.0
    cum_v = 0.0
    prev_day = None
    from datetime import datetime, timezone
    for i in range(n):
        day = None
        if timestamps is not None:
            day = datetime.fromtimestamp(int(timestamps[i]), tz=timezone.utc).date()
        if day is not None and prev_day is not None and day != prev_day:
            cum_pv = 0.0
            cum_v = 0.0
        cum_pv += typical[i] * v[i]
        cum_v += v[i]
        out[i] = cum_pv / cum_v if cum_v > 0 else float("nan")
        prev_day = day
    return out


# --------------------------------------------------------------------------- #
# Derivados úteis
# --------------------------------------------------------------------------- #
def rolling_volatility(closes: Sequence[float], period: int = 20) -> np.ndarray:
    """Volatilidade (desvio-padrão dos retornos log, anualizado por candle base)."""
    arr = _as_array(closes)
    n = len(arr)
    out = _nan_array(n)
    if n < period + 1:
        return out
    logret = np.log(arr[1:] / arr[:-1])
    for i in range(period, n):
        out[i] = float(np.std(logret[i - period:i], ddof=1))
    return out


def slope(values: Sequence[float], period: int = 5) -> np.ndarray:
    """Inclinação linear normalizada (em fração do valor médio) dos últimos `period` pontos."""
    arr = _as_array(values)
    n = len(arr)
    out = _nan_array(n)
    if n < period:
        return out
    x = np.arange(period, dtype=float)
    xm = x.mean()
    denom = float(((x - xm) ** 2).sum())
    for i in range(period - 1, n):
        y = arr[i - period + 1:i + 1]
        ym = y.mean()
        if abs(ym) < 1e-12:
            continue
        beta = float(((x - xm) * (y - ym)).sum() / denom)
        out[i] = beta / ym  # inclinação relativa
    return out
