"""Modelo probabilístico interpretável com calibração e controle de overfitting.

Pipeline:
1. Features de contexto (tendência, RSI, distâncias, padrões...) — interpretáveis.
2. Regressão logística (coeficientes inspecionáveis) como modelo base.
3. Calibração com validação temporal (Platt/Isotonic) e Brier Score medido
   em holdout NÃO usado no treino.
4. Sem dados suficientes => `calibrated=False` e o sistema NÃO exibe
   probabilidade (mostra "dados insuficientes").

A regressão logística é usada como estimadora de probabilidade calibrada —
é um modelo de classificação linear com saída interpretável (log-odds),
diferente de uma "pontuação arbitrária de indicadores".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


FEATURE_NAMES = [
    "trend_dir", "trend_strength", "ema_aligned", "adx_norm", "rsi_centered",
    "macd_hist_norm", "bb_pctb", "atr_norm", "dist_support_atr", "dist_resistance_atr",
    "pattern_dir", "pattern_strength", "body_ratio", "range_norm", "ema9_slope",
]


@dataclass
class FeatureVector:
    values: dict[str, float]

    def as_array(self) -> np.ndarray:
        return np.array([self.values[name] for name in FEATURE_NAMES], dtype=float)


def extract_features(ctx) -> np.ndarray:
    """Extrai o vetor de features do contexto ANTES de conhecer o resultado."""
    from ..core import indicators as ind
    closes = ctx.closes
    last = len(closes) - 1
    ema9 = ctx.ema9
    e9 = float(ema9[last]) if not np.isnan(ema9[last]) else float(ctx.cur.close)
    slope9 = (e9 - float(ema9[last - 3])) / ctx.atr_val if (
        len(ema9) > 3 and not np.isnan(ema9[last - 3]) and ctx.atr_val > 0) else 0.0
    dist_s = ctx.distance_to_level(-1)
    dist_a = ctx.distance_to_level(1)
    hist = float(ctx.macd_hist[last]) if not np.isnan(ctx.macd_hist[last]) else 0.0
    rsi_val = float(ctx.rsi14[last]) if not np.isnan(ctx.rsi14[last]) else 50.0
    pctb = float(ctx.bb_pctb[last]) if not np.isnan(ctx.bb_pctb[last]) else 0.5
    adx_val = float(ctx.adx14[last]) if not np.isnan(ctx.adx14[last]) else 0.0
    strongest = max(ctx.pattern_matches, key=lambda m: m.strength) if ctx.pattern_matches else None
    rng_norm = ctx.cur.range_ / ctx.atr_val if ctx.atr_val > 0 else 1.0

    return np.array([
        float(ctx.trend.direction),
        ctx.trend.strength,
        1.0 if (ctx.trend.hh_hl or ctx.trend.lh_ll) else 0.0,
        min(adx_val, 60.0) / 60.0,
        (rsi_val - 50.0) / 50.0,
        hist / ctx.atr_val if ctx.atr_val > 0 else 0.0,
        pctb,
        min(rng_norm, 3.0) / 3.0,
        dist_s if dist_s is not None else 2.0,
        dist_a if dist_a is not None else 2.0,
        float(strongest.direction) if strongest else 0.0,
        strongest.strength if strongest else 0.0,
        ctx.cur.body / ctx.cur.range_ if ctx.cur.range_ > 0 else 0.0,
        min(rng_norm, 3.0) / 3.0,
        max(min(slope9, 1.0), -1.0),
    ], dtype=float)


@dataclass
class CalibrationReport:
    n_train: int = 0
    n_val: int = 0
    n_test: int = 0
    brier_val: float = float("nan")
    brier_test: float = float("nan")
    baseline_brier: float = float("nan")
    baseline_val: float = float("nan")
    baseline_test: float = float("nan")
    accuracy_val: float = float("nan")
    accuracy_test: float = float("nan")
    calibrator: str = "nenhum"
    intercept: float = 0.0
    coefs: dict = field(default_factory=dict)
    note: str = ""


class ProbabilityModel:
    """Regressão logística + calibração temporal.

    Uso:
        model = ProbabilityModel()
        model.fit(X_train, y_train, X_val, y_val, X_test, y_test)
        model.predict_prob(ctx, strategy_result)
    Sem fit() ou com amostra insuficiente, `calibrated` é False.
    """

    MIN_TRAIN = 300          # amostras mínimas para considerar treino
    MIN_POS_RATE = 0.02      # precisa haver variação nos alvos
    BRIER_MARGIN = 0.02      # deve bater a baseline (previsão da média) por isso

    def __init__(self, calibrator: str = "isotonic"):
        self.calibrator_name = calibrator
        self.calibrated: bool = False
        self.w: Optional[np.ndarray] = None
        self.b: float = 0.0
        self._calibrator = None
        self._mean: Optional[float] = None
        self.report = CalibrationReport()

    # ----------------------------- treino -------------------------------- #
    def fit(self, X_train, y_train, X_val=None, y_val=None, X_test=None, y_test=None,
            lr: float = 0.05, epochs: int = 800, l2: float = 1e-3) -> CalibrationReport:
        X_train = np.asarray(X_train, dtype=float)
        y_train = np.asarray(y_train, dtype=float)
        n = len(y_train)
        rep = CalibrationReport(n_train=n)
        if n < self.MIN_TRAIN:
            rep.note = f"amostra de treino insuficiente ({n} < {self.MIN_TRAIN})"
            self.report = rep
            self.calibrated = False
            return rep
        rate = float(np.mean(y_train))
        if rate < self.MIN_POS_RATE or rate > 1 - self.MIN_POS_RATE:
            rep.note = f"taxa de eventos ({rate:.3f}) sem variação suficiente"
            self.report = rep
            self.calibrated = False
            return rep

        # padronização (fit só no treino)
        self._mean = X_train.mean(axis=0)
        self._std = X_train.std(axis=0)
        self._std[self._std < 1e-9] = 1.0
        Xs = (X_train - self._mean) / self._std

        # gradiente descendente em log-loss + L2 (interpretável e determinístico)
        d = Xs.shape[1]
        w = np.zeros(d)
        b = 0.0
        for _ in range(epochs):
            z = Xs @ w + b
            p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
            err = p - y_train
            grad_w = Xs.T @ err / n + l2 * w
            grad_b = float(err.mean())
            w -= lr * grad_w
            b -= lr * grad_b
        self.w, self.b = w, b

        # baseline: prever sempre a média do treino
        rep.baseline_brier = float(np.mean((y_train - rate) ** 2))

        # calibrador em validação (temporalmente posterior ao treino)
        if X_val is not None and y_val is not None and len(X_val) >= 50:
            p_val_raw = self._raw_prob((np.asarray(X_val, float) - self._mean) / self._std)
            y_val = np.asarray(y_val, dtype=float)
            self._calibrator = self._fit_calibrator(p_val_raw, y_val)
            self.calibrator_name = "isotonic" if isinstance(self._calibrator, tuple) else "platt"
            rep.n_val = len(y_val)
            p_val = self._apply_calibrator(p_val_raw)
            rep.brier_val = float(np.mean((p_val - y_val) ** 2))
            rep.baseline_val = float(np.mean((y_val - np.mean(y_val)) ** 2))
            rep.accuracy_val = float(np.mean((p_val >= 0.5) == (y_val >= 0.5)))
        else:
            self._calibrator = None
            self.calibrator_name = "nenhum"
            rep.note += " | sem validação: calibração não aplicada"

        # teste final (nunca usado no treino/calibração)
        if X_test is not None and y_test is not None and len(X_test) >= 50:
            X_test = np.asarray(X_test, dtype=float)
            y_test = np.asarray(y_test, dtype=float)
            p_test = self.predict_array(X_test)
            rep.n_test = len(y_test)
            rep.brier_test = float(np.mean((p_test - y_test) ** 2))
            rep.baseline_test = float(np.mean((y_test - np.mean(y_test)) ** 2))
            rep.accuracy_test = float(np.mean((p_test >= 0.5) == (y_test >= 0.5)))

        rep.intercept = b
        rep.coefs = {FEATURE_NAMES[i]: float(w[i]) for i in range(d)}

        # critério de aceitação: o modelo precisa MELHORAR sobre a baseline do
        # próprio split (prever a taxa-base). Sem ganho estatístico => rejeitado.
        ok = True
        reasons = []
        if not np.isnan(rep.brier_val) and not np.isnan(rep.baseline_val):
            if rep.brier_val > rep.baseline_val - self.BRIER_MARGIN:
                ok = False
                reasons.append("validação sem ganho sobre a baseline")
        if not np.isnan(rep.brier_test) and not np.isnan(rep.baseline_test):
            if rep.brier_test > rep.baseline_test - self.BRIER_MARGIN:
                ok = False
                reasons.append("teste sem ganho sobre a baseline")
        if self.calibrator_name == "nenhum":
            ok = False
            reasons.append("sem calibração")
        rep.note = (rep.note + " | " if rep.note else "") + ("aprovado" if ok else "; ".join(reasons))
        self.report = rep
        self.calibrated = ok
        return rep

    # --------------------------- predição -------------------------------- #
    def _raw_prob(self, Xs: np.ndarray) -> np.ndarray:
        z = Xs @ self.w + self.b
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))

    def _fit_calibrator(self, p: np.ndarray, y: np.ndarray):
        if self.calibrator_name == "isotonic":
            try:
                from sklearn.isotonic import IsotonicRegression
                iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip")
                iso.fit(p, y)
                return ("isotonic", iso)
            except Exception:
                pass
        # Platt (logistic sobre logit das probabilidades)
        eps = 1e-6
        logit = np.log(np.clip(p, eps, 1 - eps) / np.clip(1 - p, eps, 1 - eps)).reshape(-1, 1)
        from sklearn.linear_model import LogisticRegression
        lr = LogisticRegression(C=1e6)
        lr.fit(logit, (y >= 0.5).astype(int))
        return ("platt", lr)

    def _apply_calibrator(self, p: np.ndarray) -> np.ndarray:
        if self._calibrator is None:
            return p
        kind, obj = self._calibrator
        if kind == "isotonic":
            return np.asarray(obj.predict(p), dtype=float)
        eps = 1e-6
        logit = np.log(np.clip(p, eps, 1 - eps) / np.clip(1 - p, eps, 1 - eps)).reshape(-1, 1)
        return obj.predict_proba(logit)[:, 1]

    def predict_array(self, X: np.ndarray) -> np.ndarray:
        if self.w is None:
            raise RuntimeError("Modelo não treinado")
        Xs = (np.asarray(X, dtype=float) - self._mean) / self._std
        return self._apply_calibrator(self._raw_prob(Xs))

    def predict_prob(self, ctx, strategy_result=None) -> float:
        """Probabilidade calibrada de o resultado ser favorável à direção indicada.

        Nota: o modelo é treinado para a classe 'preço na direção do sinal até
        a expiração', então a probabilidade retornada já é P(sucesso).
        """
        if not self.calibrated or self.w is None:
            raise RuntimeError("Modelo não calibrado — não exibir probabilidade")
        x = extract_features(ctx).reshape(1, -1)
        return float(self.predict_array(x)[0])


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple:
    """IC de Wilson para proporção (mais adequado que normal em amostras pequenas)."""
    if n == 0:
        return (float("nan"), float("nan"))
    phat = wins / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))
