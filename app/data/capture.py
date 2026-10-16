"""Coletor por leitura de tela da janela do IQ Option (ou de qualquer gráfico de velas).

Como funciona (versão funcional):

1. Captura um retângulo da tela (ou lê um PNG já salvo em disco).
2. Classifica cada pixel como vela de ALTA (verde) ou de BAIXA (vermelha).
3. Agrupa pixels conectados em **cada vela** por componentes conexos: o corpo e
   o(s) pavio(s) têm a mesma cor e se tocam, então formam **um único** componente
   — pavio NÃO vira vela separada, e uma vela larga NÃO vira várias.
4. Separa corpo de pavio pelas larguras linha a linha: as linhas "gordas" são o
   corpo (open/close); o extremo superior/inferior do componente é high/low.
5. Converte pixels em preço por calibração linear de dois pontos.
6. Assina timestamps REAIS em minutos: a última vela = minuto atual (truncado).

Limitações honestas:
- Sensível a tema/zoom/anti-aliasing; exige calibração por ativo.
- Duas velas da MESMA cor sem nenhum espaço entre elas podem ser lidas como uma
  só. Mitigue com mais zoom na plataforma ou use ``split_merged=True``.
- Não faz OCR do eixo de preço: a calibração de dois pontos é informada (ou via
  JSON). O eixo de tempo é aproximado (última vela = minuto atual).
- Só lê o que está visível; velas fora do painel não entram.
- É uma aproximação: valide com CSV/fonte nativa quando possível.

Este módulo NÃO acessa a rede, NÃO faz login e NÃO usa API interna.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Optional

from ..core.candles import Candle, CandleSeries

try:  # captura ao vivo (Windows)
    from PIL import ImageGrab  # type: ignore
except Exception:  # pragma: no cover
    ImageGrab = None

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None


__all__ = [
    "ScreenCalibration",
    "detect_candles_from_image",
    "detect_candles_from_file",
    "chart_region_from_image",
    "grab_region",
    "capture_snapshot",
    "collect_loop",
    "save_calibration",
    "load_calibration",
]


@dataclass
class ScreenCalibration:
    """Calibração preço<->pixel (linear, dois pontos).

    region: (left, top, right, bottom) do painel do gráfico em pixels da tela.
    price_top/pixel_top: preço e coordenada Y da linha SUPERIOR da escala.
    price_bottom/pixel_bottom: idem para a linha INFERIOR.
    """

    region: tuple
    price_top: float
    pixel_top: float
    price_bottom: float
    pixel_bottom: float

    def price_at(self, y: float) -> float:
        if self.pixel_top == self.pixel_bottom:
            raise ValueError("Calibração inválida: pixels coincidentes.")
        frac = (y - self.pixel_top) / (self.pixel_bottom - self.pixel_top)
        return self.price_top + frac * (self.price_bottom - self.price_top)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["region"] = list(self.region)
        return d


def save_calibration(calib: ScreenCalibration, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(calib.to_dict(), fh, ensure_ascii=False, indent=2)


def load_calibration(path: str) -> ScreenCalibration:
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return ScreenCalibration(
        region=tuple(d["region"]),
        price_top=float(d["price_top"]), pixel_top=float(d["pixel_top"]),
        price_bottom=float(d["price_bottom"]), pixel_bottom=float(d["pixel_bottom"]),
    )


# --------------------------------------------------------------------------- #
# Captura bruta
# --------------------------------------------------------------------------- #
def grab_region(region: tuple) -> "object":
    """Captura um retângulo da tela (left, top, right, bottom)."""
    if ImageGrab is None:
        raise RuntimeError("Pillow/ImageGrab indisponível neste ambiente.")
    return ImageGrab.grab(bbox=tuple(int(v) for v in region))


# --------------------------------------------------------------------------- #
# Classificação de cor e segmentação por componentes conexos
# --------------------------------------------------------------------------- #
def _is_green(px) -> bool:
    r, g, b = px[0], px[1], px[2]
    return g > 110 and g > r + 40 and g >= b - 5


def _is_red(px) -> bool:
    r, g, b = px[0], px[1], px[2]
    return r > 110 and r > g + 40 and r > b + 40


def _masks(img):
    """Devolve (green_mask, red_mask) como arrays numpy booleanos HxW."""
    if np is None:
        raise RuntimeError("numpy é necessário para a detecção de velas.")
    arr = np.asarray(img.convert("RGB"), dtype=np.int16)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    green = (g > 110) & (g > r + 40) & (g >= b - 5)
    red = (r > 110) & (r > g + 40) & (r > b + 40)
    return green, red


def _components(mask) -> list:
    """Componentes conexos (8-vizinhos) por linhas de pixels — rápido e sem scipy."""
    if not mask.any():
        return []
    H = mask.shape[0]
    parent: list[int] = []

    def find(a: int) -> int:
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    prev: list[tuple] = []
    runs_by_row: list[tuple] = []
    for y in range(H):
        idx = np.flatnonzero(mask[y])
        cur: list[tuple] = []
        if idx.size:
            breaks = np.flatnonzero(np.diff(idx) > 1)
            starts = np.concatenate(([0], breaks + 1))
            ends = np.concatenate((breaks, [idx.size - 1]))
            for s, e in zip(starts, ends):
                xs, xe = int(idx[s]), int(idx[e])
                lab = len(parent)
                parent.append(lab)
                for pxs, pxe, plab in prev:          # toca alguma run da linha anterior?
                    if xs <= pxe + 1 and pxs <= xe + 1:
                        union(lab, plab)
                cur.append((xs, xe, lab))
        runs_by_row.append((y, cur))
        prev = cur

    groups: dict[int, list] = {}
    for y, cur in runs_by_row:
        for xs, xe, lab in cur:
            groups.setdefault(find(lab), []).append((y, xs, xe))

    comps = []
    for runs in groups.values():
        ys = [y for y, _, _ in runs]
        comps.append({
            "y0": min(ys), "y1": max(ys),
            "x0": min(xs for _, xs, _ in runs),
            "x1": max(xe for _, _, xe in runs),
        })
    return comps


def _measure(mask, bbox: dict) -> dict:
    """Mede um componente: extremos (high/low) e corpo (open/close)."""
    y0, y1, x0, x1 = bbox["y0"], bbox["y1"], bbox["x0"], bbox["x1"]
    sub = mask[y0:y1 + 1, x0:x1 + 1]
    counts = sub.sum(axis=1)
    rows = np.flatnonzero(counts)
    maxw = int(counts.max())
    body_thresh = max(2, int(round(maxw * 0.5)))
    body_rows = rows[counts[rows] >= body_thresh]
    if body_rows.size == 0:
        body_rows = rows
    return {
        "npix": int(sub.sum()),
        "y_top": int(y0 + rows[0]),
        "y_bot": int(y0 + rows[-1]),
        "body_top": int(y0 + body_rows[0]),
        "body_bot": int(y0 + body_rows[-1]),
        "width": int(x1 - x0 + 1),
    }


def _split_by_wicks(mask, bbox: dict, min_pixels: int = 4) -> list:
    """Separa um componente que contenha VÁRIAS velas coladas da mesma cor.

    Usa os 'picos' verticais (colunas de pavio): cada vela tem no máximo um
    pavio, então N picos distintos ⇒ N velas. Sem picos múltiplos, não separa.
    """
    from collections import Counter
    y0, y1, x0, x1 = bbox["y0"], bbox["y1"], bbox["x0"], bbox["x1"]
    heights = []
    for x in range(x0, x1 + 1):
        rows = np.flatnonzero(mask[y0:y1 + 1, x])
        heights.append(int(rows[-1] - rows[0] + 1) if rows.size else 0)
    pos = [h for h in heights if h > 0]
    if not pos:
        return [bbox]
    # a altura mais frequente é a do CORPO; colunas bem mais altas são PAVIOS
    body_h = Counter(pos).most_common(1)[0][0]
    thresh = body_h + 2
    n = len(heights)
    peaks = []
    for i, h in enumerate(heights):
        if h < thresh:
            continue
        left = heights[i - 1] if i > 0 else -1
        right = heights[i + 1] if i < n - 1 else -1
        if h >= left and h >= right and (h > left or h > right):
            peaks.append(x0 + i)
    clusters: list[list[int]] = []
    for x in peaks:
        if clusters and x - clusters[-1][-1] <= 2:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    if len(clusters) < 2:
        return [bbox]
    centers = [sum(c) / len(c) for c in clusters]
    bounds = [x0] + [int(round((centers[i] + centers[i + 1]) / 2))
                     for i in range(len(centers) - 1)] + [x1 + 1]
    out = []
    for i in range(len(bounds) - 1):
        sa, sb = bounds[i], bounds[i + 1] - 1
        if sb < sa:
            continue
        if mask[y0:y1 + 1, sa:sb + 1].sum() < min_pixels:
            continue
        out.append({"y0": y0, "y1": y1, "x0": sa, "x1": sb})
    return out if len(out) >= 2 else [bbox]


def chart_region_from_image(img, min_pixels: int = 4) -> Optional[tuple]:
    """Descobre a região do gráfico = bounding box dos pixels coloridos (verde/vermelho).

    Útil como assistente de calibração: evita ter que acertar a região na mão.
    Retorna (left, top, right, bottom) ou None se nenhuma vela for encontrada.
    """
    green, red = _masks(img)
    mask = green | red
    ys, xs = np.nonzero(mask)
    if xs.size < min_pixels:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


# --------------------------------------------------------------------------- #
# Detecção principal
# --------------------------------------------------------------------------- #
def detect_candles_from_image(img, calib: ScreenCalibration,
                              timeframe_s: int = 60, now: Optional[int] = None,
                              min_pixels: int = 4,
                              split_merged: bool = True) -> list:
    """Detecta velas numa imagem (screenshot) de gráfico.

    - corpo/pavio agrupados por componente conexo (uma vela = um componente);
    - preço por calibração de dois pontos;
    - timestamps reais em minutos (última vela = minuto atual).

    split_merged=True separa componentes que contenham várias velas coladas da
    mesma cor, pelos picos de pavio (cada vela tem no máximo um pavio).
    """
    green, red = _masks(img)
    comps: list[tuple] = []
    for color, mask in (("green", green), ("red", red)):
        for bbox in _components(mask):
            m = _measure(mask, bbox)
            if m["npix"] < min_pixels:
                continue
            comps.append({"bbox": bbox, "m": m, "color": color, "mask": mask})

    if split_merged:
        split: list[tuple] = []
        for c in comps:
            for nb in _split_by_wicks(c["mask"], c["bbox"], min_pixels):
                split.append({"bbox": nb, "m": _measure(c["mask"], nb),
                              "color": c["color"], "mask": c["mask"]})
        comps = split

    comps.sort(key=lambda c: (c["bbox"]["x0"] + c["bbox"]["x1"]) / 2)

    now = int(now if now is not None else time.time())
    base = (now // timeframe_s) * timeframe_s
    n = len(comps)
    candles: list = []
    for i, c in enumerate(comps):
        m = c["m"]
        p_hi = calib.price_at(m["y_top"])
        p_lo = calib.price_at(m["y_bot"])
        high, low = max(p_hi, p_lo), min(p_hi, p_lo)
        p_bt = calib.price_at(m["body_top"])   # y menor -> preço maior
        p_bb = calib.price_at(m["body_bot"])
        if c["color"] == "green":              # alta: abre embaixo, fecha em cima
            o, cl = p_bb, p_bt
        else:                                  # baixa: abre em cima, fecha embaixo
            o, cl = p_bt, p_bb
        o = min(max(o, low), high)
        cl = min(max(cl, low), high)
        ts = base - (n - 1 - i) * timeframe_s
        candles.append(Candle(ts=ts, open=o, high=high, low=low, close=cl, volume=0.0))
    return candles


def detect_candles_from_file(path: str, calib: ScreenCalibration,
                             timeframe_s: int = 60, now: Optional[int] = None,
                             **kwargs) -> list:
    """Detecta velas a partir de um arquivo de imagem (PNG/JPG) salvo em disco."""
    from PIL import Image
    with Image.open(path) as img:
        return detect_candles_from_image(img, calib, timeframe_s=timeframe_s,
                                         now=now, **kwargs)


# --------------------------------------------------------------------------- #
# Captura ao vivo
# --------------------------------------------------------------------------- #
def capture_snapshot(calib: ScreenCalibration, timeframe_s: int = 60,
                     now: Optional[int] = None) -> CandleSeries:
    img = grab_region(calib.region)
    candles = detect_candles_from_image(img, calib, timeframe_s=timeframe_s, now=now)
    if not candles:
        raise RuntimeError("Nenhuma vela detectada — verifique região e calibração.")
    return CandleSeries(candles, symbol="SCREEN_CAPTURE", timeframe_s=timeframe_s)


def collect_loop(calib: ScreenCalibration, interval_s: float = 5.0,
                 duration_s: float = 60.0, timeframe_s: int = 60, on_update=None):
    """Loop de coleta: captura snapshots periodicamente e chama on_update(series).

    Encerra após `duration_s`. Não faz nada além de ler a tela do usuário.
    `on_update` recebe a CandleSeries em caso de sucesso ou a exceção em erro.
    """
    t_end = time.time() + duration_s
    last = None
    while time.time() < t_end:
        try:
            last = capture_snapshot(calib, timeframe_s=timeframe_s)
            if on_update is not None:
                on_update(last)
        except Exception as exc:  # pragma: no cover
            if on_update is not None:
                on_update(exc)
        time.sleep(interval_s)
    return last
