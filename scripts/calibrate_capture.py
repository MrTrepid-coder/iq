"""Assistente de calibração do coletor por leitura de tela.

Objetivo: produzir um arquivo JSON de calibração (região + dois pontos de preço)
para o comando `run.py capture`.

Fluxo sugerido:
  1) Tire um print da janela do IQ Option (o gráfico visível).
  2) Rode com --ruler para gerar uma cópia com uma régua de pixels sobreposta:
       python scripts/calibrate_capture.py --shot print.png --ruler data/regua.png
  3) Abra data/regua.png, escolha DUAS linhas de preço conhecidas do eixo
     (ex.: 1.2000 e 1.1000) e anote o Y (em pixels) de cada uma.
  4) Gere a calibração:
       python scripts/calibrate_capture.py --shot print.png \
         --price-top 1.2000 --pixel-top 120 --price-bottom 1.1000 --pixel-bottom 520 \
         --out data/calib.json
  5) Use:
       python run.py capture --calib data/calib.json --out data/captura.csv

Não acessa rede nem a plataforma.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.capture import (ScreenCalibration, chart_region_from_image,
                              save_calibration)

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover
    raise SystemExit("Pillow é necessário: python -m pip install pillow")


def draw_ruler(src: str, out: str, step: int = 50) -> None:
    with Image.open(src) as im:
        img = im.convert("RGB").copy()
    d = ImageDraw.Draw(img)
    w, h = img.size
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=(255, 215, 0))
        d.text((4, y + 1), str(y), fill=(255, 215, 0))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    img.save(out)


def main():
    ap = argparse.ArgumentParser(description="Assistente de calibração (leitura de tela)")
    ap.add_argument("--shot", required=True, help="print do gráfico (PNG/JPG)")
    ap.add_argument("--ruler", default=None, help="gera uma cópia com régua de pixels")
    ap.add_argument("--region", default=None, help="L,T,R,B (default: auto-região)")
    ap.add_argument("--price-top", type=float, default=None)
    ap.add_argument("--pixel-top", type=float, default=None)
    ap.add_argument("--price-bottom", type=float, default=None)
    ap.add_argument("--pixel-bottom", type=float, default=None)
    ap.add_argument("--out", default=None, help="JSON de calibração de saída")
    args = ap.parse_args()

    with Image.open(args.shot) as im:
        img = im.convert("RGB")
        size = img.size

    # região: informada ou descoberta pela posição das velas
    if args.region:
        region = tuple(int(v) for v in args.region.split(","))
    else:
        region = chart_region_from_image(img)
        if region is None:
            print("AVISO: não encontrei velas na imagem; informe --region manualmente.")
            region = (0, 0, size[0], size[1])
    print(f"imagem: {args.shot} ({size[0]}x{size[1]})")
    print(f"região do gráfico: {region}")

    if args.ruler:
        draw_ruler(args.shot, args.ruler)
        print(f"régua gerada em {args.ruler} — abra e anote o Y de dois preços.")

    need = [args.price_top, args.pixel_top, args.price_bottom, args.pixel_bottom]
    if any(v is None for v in need):
        print("\nPara gerar o JSON, informe dois pontos de preço:")
        print("  --price-top P --pixel-top Y --price-bottom P --pixel-bottom Y")
        return

    calib = ScreenCalibration(region=region, price_top=args.price_top,
                              pixel_top=args.pixel_top, price_bottom=args.price_bottom,
                              pixel_bottom=args.pixel_bottom)
    if calib.pixel_top == calib.pixel_bottom:
        raise SystemExit("pixel-top e pixel-bottom não podem ser iguais.")
    if calib.price_top == calib.price_bottom:
        raise SystemExit("price-top e price-bottom não podem ser iguais.")

    if args.out:
        save_calibration(calib, args.out)
        print(f"\ncalibração salva em {args.out}")
    else:
        print("\ncalibração (use --out para salvar):")
        print(calib.to_dict())


if __name__ == "__main__":
    main()
