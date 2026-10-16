"""Gera uma imagem de gráfico de velas realista para testar/demonstrar o coletor.

Uso:
  python scripts/make_sample_screenshot.py --out data/sample_screen.png

Desenha velas (corpo + pavios) com as cores típicas da IQ Option sobre fundo
escuro, com eixos simples, para validar a leitura de tela sem depender da
plataforma. Não acessa rede nem a plataforma.
"""
from __future__ import annotations

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover
    raise SystemExit("Pillow é necessário: python -m pip install pillow")

GREEN = (38, 166, 154)
RED = (239, 83, 80)
BG = (15, 20, 32)
GRID = (30, 40, 60)


def build(out_path: str, n: int = 60, width: int = 8, gap: int = 6,
          top: int = 40, height: int = 420, seed: int = 7,
          price_top: float = 1.2000, price_bottom: float = 1.0000) -> dict:
    rng = random.Random(seed)
    chart_left = 20
    img_w = chart_left + n * (width + gap) + gap + 90   # +90 reserva p/ eixo de preço
    img_h = top + height + 40
    img = Image.new("RGB", (img_w, img_h), BG)
    d = ImageDraw.Draw(img)

    # grade horizontal simples
    for gy in range(top, top + height, 60):
        d.line([(chart_left, gy), (chart_left + n * (width + gap), gy)], fill=GRID)

    # eixo de preço (rótulos) — liga y a preço linear
    def price_at(y: float) -> float:
        frac = (y - top) / height
        return price_top + frac * (price_bottom - price_top)

    truth = []
    price = (price_top + price_bottom) / 2 + (price_top - price_bottom) * rng.uniform(-0.25, 0.25)
    band_lo = price_bottom + (price_top - price_bottom) * 0.08
    band_hi = price_top - (price_top - price_bottom) * 0.08
    vol = (price_top - price_bottom) * 0.012
    for i in range(n):
        x = chart_left + i * (width + gap)
        cx = x + width // 2
        o = price
        c = o + rng.gauss(0, vol)
        # leve reversão à média para não sair da faixa
        c += ((price_top + price_bottom) / 2 - o) * 0.05
        c = max(band_lo, min(band_hi, c))
        hi = min(band_hi, max(o, c) + abs(rng.gauss(0, vol * 0.6)))
        lo = max(band_lo, min(o, c) - abs(rng.gauss(0, vol * 0.6)))
        price = c

        def y_of(p: float) -> float:
            return top + (p - price_top) / (price_bottom - price_top) * height

        y_hi, y_lo = int(y_of(hi)), int(y_of(lo))
        y_bt, y_bb = int(y_of(max(o, c))), int(y_of(min(o, c)))
        color = GREEN if c >= o else RED
        d.rectangle([cx - 1, y_hi, cx, y_lo], fill=color)          # pavio
        d.rectangle([x, y_bt, x + width - 1, max(y_bb, y_bt + 1)], fill=color)  # corpo
        truth.append({"open": o, "high": hi, "low": lo, "close": c, "x": x})

    d.text((img_w - 78, top - 2), f"{price_top:.4f}", fill=(150, 165, 190))
    d.text((img_w - 78, top + height - 12), f"{price_bottom:.4f}", fill=(150, 165, 190))

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return {
        "region": (chart_left, top, chart_left + n * (width + gap), top + height),
        "price_top": price_top, "pixel_top": top,
        "price_bottom": price_bottom, "pixel_bottom": top + height,
        "candles": truth,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/sample_screen.png")
    ap.add_argument("--n", type=int, default=60)
    args = ap.parse_args()
    info = build(args.out, n=args.n)
    print(f"imagem salva em {args.out}")
    print(f"calibração sugerida: {info}")


if __name__ == "__main__":
    main()
