"""Scanner de múltiplos ativos.

Responsabilidades:
- aceitar uma lista configurável de ativos (arquivos CSV em data/);
- consultar apenas fontes disponíveis (arquivos locais — nenhuma cotação inventada);
- detectar dados ausentes, duplicados, incompletos e desatualizados;
- normalizar timestamps e ordenar candles;
- calcular indicadores independentemente por ativo;
- gerar sinais CALL / PUT / SEM SINAL com MOTIVOS objetivos;
- ordenar por qualidade estatística da configuração;
- excluir ativos sem histórico suficiente;
- evitar repetir sinal para o mesmo candle/ativo;
- isolar falhas: um ativo indisponível não derruba o scanner.

A "qualidade" NÃO é probabilidade de acerto: é uma coerência interna da
estratégia (0..1). Probabilidade de acerto só seria exibida com calibração
estatística validada (que o modelo atual não atingiu).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from ..core.candles import Candle, CandleSeries
from ..analysis.context import AnalysisContext, IndicatorCache
from ..signal import generate_signal, SignalReport


@dataclass
class DataQuality:
    n_candles: int = 0
    n_duplicates: int = 0
    n_gaps: int = 0
    n_invalid: int = 0
    last_ts: Optional[int] = None
    missing_seconds: int = 0
    ok: bool = True
    issues: list = field(default_factory=list)


@dataclass
class ScanResult:
    asset: str
    status: str                    # "sinal_detectado" | "aguardar" | "sem_sinal" | "erro" | "dados_insuficientes"
    direction: int = 0
    decision: str = "AGUARDAR"
    strategy_id: str = ""
    strategy_name: str = ""
    quality: float = 0.0
    ts: Optional[int] = None
    entry_price: Optional[float] = None
    probability: Optional[float] = None
    probability_note: str = "dados insuficientes"
    confirmations: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    data_quality: Optional[DataQuality] = None
    error: str = ""
    report: Optional[SignalReport] = None


def inspect_quality(series: CandleSeries, timeframe_s: int = 60,
                    now: Optional[int] = None,
                    stale_after_s: int = 300) -> DataQuality:
    """Avalia a qualidade dos dados SEM alterar a origem."""
    q = DataQuality(n_candles=len(series))
    seen = set()
    prev_ts = None
    for c in series.candles:
        if not c.is_valid():
            q.n_invalid += 1
        if c.ts in seen:
            q.n_duplicates += 1
        seen.add(c.ts)
        if prev_ts is not None:
            step = c.ts - prev_ts
            if step > timeframe_s:
                q.n_gaps += 1
                q.missing_seconds += (step - timeframe_s)
        prev_ts = c.ts
    if series.candles:
        q.last_ts = series.candles[-1].ts
    ref = int(now) if now is not None else q.last_ts
    if ref is not None and q.last_ts is not None and ref - q.last_ts > stale_after_s:
        q.issues.append(f"dados desatualizados ({(ref - q.last_ts)}s sem atualização)")
        q.ok = False
    if q.n_duplicates:
        q.issues.append(f"{q.n_duplicates} timestamp(s) duplicado(s)")
    if q.n_gaps:
        q.issues.append(f"{q.n_gaps} lacuna(s) temporal(is)")
    if q.n_invalid:
        q.issues.append(f"{q.n_invalid} candle(s) inválido(s)")
        q.ok = False
    return q


def sanitize_series(candles: Sequence[Candle], symbol: str,
                    timeframe_s: int = 60) -> tuple:
    """Remove duplicados/inválidos e ordena por timestamp. Retorna (série, qualidade).

    Não inventa candles ausentes — apenas normaliza o que existe.
    """
    raw = list(candles)
    q = DataQuality(n_candles=len(raw))
    valid = [c for c in raw if c.is_valid()]
    q.n_invalid = len(raw) - len(valid)
    # ordena por ts e remove duplicados mantendo o primeiro
    valid.sort(key=lambda c: c.ts)
    dedup: list[Candle] = []
    seen = set()
    for c in valid:
        if c.ts in seen:
            q.n_duplicates += 1
            continue
        seen.add(c.ts)
        dedup.append(c)
    order = [c.ts for c in dedup]
    for i in range(1, len(order)):
        if order[i] - order[i - 1] > timeframe_s:
            q.n_gaps += 1
    q.last_ts = dedup[-1].ts if dedup else None
    q.ok = bool(dedup) and q.n_invalid == 0
    return CandleSeries(dedup, symbol=symbol, timeframe_s=timeframe_s), q


class Scanner:
    """Varre uma lista de ativos locais e devolve sinais ordenados."""

    def __init__(self, cfg, data_dir: str = "data", logger=None,
                 model=None):
        self.cfg = cfg
        self.data_dir = data_dir
        self.log = logger
        self.model = model
        self._last_signal_key: dict[str, str] = {}   # ativo -> última chave emitida

    def _path_for(self, asset: str) -> Optional[str]:
        candidates = [asset]
        if not asset.lower().endswith(".csv"):
            candidates.append(f"{asset}.csv")
        for name in candidates:
            p = name if os.path.isabs(name) else os.path.join(self.data_dir, name)
            if os.path.exists(p):
                return p
        return None

    def _signal_key(self, series: CandleSeries) -> str:
        return f"{series.symbol}|{series[-1].ts}"

    def scan_asset(self, asset: str, now: Optional[int] = None) -> ScanResult:
        """Analisa um único ativo. Nunca lança: erros viram ScanResult(status='erro')."""
        path = self._path_for(asset)
        if path is None:
            return ScanResult(asset=asset, status="erro",
                              error=f"arquivo não encontrado para '{asset}'")
        try:
            series = CandleSeries.from_csv(path)
        except Exception as exc:
            return ScanResult(asset=asset, status="erro",
                              error=f"falha ao ler CSV: {type(exc).__name__}: {exc}")
        if not series.symbol:
            series.symbol = os.path.splitext(os.path.basename(path))[0]

        series, quality = sanitize_series(series.candles, series.symbol,
                                          series.timeframe_s or self.cfg.timeframe_s)
        if len(series) < self.cfg.min_candles:
            return ScanResult(asset=series.symbol, status="dados_insuficientes",
                              data_quality=quality,
                              error=f"{len(series)} candles < mínimo {self.cfg.min_candles}")
        q_live = inspect_quality(series, series.timeframe_s, now=now,
                                 stale_after_s=self.cfg.stale_after_s)
        if not q_live.ok:
            # dados ruins => não inventa sinal; reporta problema
            q = quality
            q.issues.extend(q_live.issues)
            q.ok = False

        try:
            cache = IndicatorCache(series)
            ctx = AnalysisContext.build(series, len(series), cache=cache)
            ctx.asset = series.symbol
            rep = generate_signal(ctx, payout=self.cfg.payout, model=self.model)
        except Exception as exc:
            return ScanResult(asset=series.symbol, status="erro", data_quality=quality,
                              error=f"{type(exc).__name__}: {exc}")

        res = ScanResult(
            asset=series.symbol, status=rep.status, direction=rep.direction,
            decision=rep.decision, strategy_id=rep.strategy_id,
            strategy_name=rep.strategy_name,
            quality=self._quality_of(rep), ts=series[-1].ts,
            entry_price=series[-1].close, probability=rep.probability,
            probability_note=rep.probability_note,
            confirmations=list(rep.confirmations), risks=list(rep.risks),
            data_quality=quality, report=rep,
        )
        # dados desatualizados/inválidos NÃO viram sinal: bloqueia e reporta
        if not q_live.ok:
            res.status = "aguardar"
            res.decision = "AGUARDAR"
            res.direction = 0
            res.quality = 0.0
            res.risks = list(res.risks) + list(q_live.issues)
        # deduplicação: não repete sinal para o mesmo candle/ativo
        key = self._signal_key(series)
        if res.status == "sinal_detectado":
            if self._last_signal_key.get(series.symbol) == key:
                res.risks.append("Sinal já emitido para este candle — ignorado.")
                res.status = "aguardar"
                res.decision = "AGUARDAR"
            else:
                self._last_signal_key[series.symbol] = key
        return res

    @staticmethod
    def _quality_of(rep: SignalReport) -> float:
        """Qualidade interna = coerência da estratégia (NÃO probabilidade de acerto)."""
        if rep.status != "sinal_detectado":
            return 0.0
        crit = rep.criteria or {}
        n_ok = sum(1 for v in crit.values() if v is True)
        n_eval = sum(1 for v in crit.values() if v is not None)
        base = (n_ok / n_eval) if n_eval else 0.0
        conf = min(1.0, len(rep.confirmations) / 5.0)
        return round(0.6 * base + 0.4 * conf, 3)

    def scan(self, assets: Optional[Sequence[str]] = None,
             now: Optional[int] = None) -> list[ScanResult]:
        """Varre todos os ativos com isolamento de falhas. Ordena por qualidade."""
        assets = list(assets if assets is not None else self.cfg.assets)
        if len(assets) > self.cfg.max_assets:
            assets = assets[:self.cfg.max_assets]
        results: list[ScanResult] = []
        for asset in assets:
            try:
                results.append(self.scan_asset(asset, now=now))
            except Exception as exc:  # blindagem extra: nunca derruba o scanner
                results.append(ScanResult(asset=asset, status="erro",
                                          error=f"{type(exc).__name__}: {exc}"))
                if self.log is not None:
                    self.log.error(f"falha isolada no ativo {asset}: {exc}")
        # ordena: sinais primeiro (por qualidade desc); depois aguardar/sem_sinal
        def _rank(r: ScanResult):
            prio = 0 if r.status == "sinal_detectado" else 1
            return (prio, -r.quality, r.asset)
        results.sort(key=_rank)
        return results
