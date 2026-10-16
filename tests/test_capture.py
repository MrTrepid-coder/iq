"""Testes do coletor por leitura de tela.

Não acessa rede nem a plataforma: desenha gráficos sintéticos realistas
(corpo + pavios, cores da IQ Option) e verifica que o detector reconstrói
corretamente o número de velas, OHLC, cores e timestamps.
"""
import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw

from app.core.candles import CandleSeries
from app.data.capture import (
    ScreenCalibration,
    chart_region_from_image,
    detect_candles_from_image,
    load_calibration,
    save_calibration,
)

GREEN = (38, 166, 154)   # verde/teal típico da IQ Option
RED = (239, 83, 80)      # vermelho típico
BG = (15, 20, 32)


def _calib(size=(0, 0, 400, 200)):
    # preço 1.20 no topo (y=0) e 1.00 na base (y=200): price = 1.20 - 0.001*y
    return ScreenCalibration(region=size, price_top=1.20, pixel_top=0.0,
                             price_bottom=1.00, pixel_bottom=200.0)


def _draw_candle(d, x, color, y_high, y_low, y_bt, y_bb, width=8):
    """Desenha uma vela: pavio (2px) + corpo (width px)."""
    cx = x + width // 2
    d.rectangle([cx - 1, y_high, cx, y_low], fill=color)         # pavio
    d.rectangle([x, y_bt, x + width - 1, y_bb], fill=color)      # corpo


def _chart(specs, width=8, gap=6, start_x=8, height=200):
    total_w = start_x + len(specs) * (width + gap) + gap
    img = Image.new("RGB", (total_w, height), BG)
    d = ImageDraw.Draw(img)
    for i, s in enumerate(specs):
        x = start_x + i * (width + gap)
        _draw_candle(d, x, GREEN if s["color"] == "green" else RED,
                     s["y_high"], s["y_low"], s["y_bt"], s["y_bb"], width)
    return img


def test_price_at_calibration():
    c = _calib()
    assert c.price_at(0) == pytest.approx(1.20)
    assert c.price_at(200) == pytest.approx(1.00)
    assert c.price_at(100) == pytest.approx(1.10)


def test_calibration_roundtrip(tmp_path):
    c = _calib((1, 2, 3, 4))
    p = str(tmp_path / "calib.json")
    save_calibration(c, p)
    d = load_calibration(p)
    assert tuple(d.region) == (1, 2, 3, 4)
    assert d.price_top == pytest.approx(1.20)
    assert d.pixel_bottom == pytest.approx(200.0)


def test_single_candle_is_one_candle():
    """Regressão: UMA vela desenhada deve virar UMA vela detectada."""
    img = _chart([{"color": "green", "y_high": 20, "y_low": 120,
                   "y_bt": 40, "y_bb": 100}])
    candles = detect_candles_from_image(img, _calib(), now=1_700_000_010)
    assert len(candles) == 1


def test_count_and_directions():
    specs = [
        {"color": "green", "y_high": 20, "y_low": 120, "y_bt": 40, "y_bb": 100},
        {"color": "red",   "y_high": 30, "y_low": 130, "y_bt": 50, "y_bb": 110},
        {"color": "green", "y_high": 10, "y_low": 90,  "y_bt": 30, "y_bb": 80},
        {"color": "red",   "y_high": 40, "y_low": 140, "y_bt": 60, "y_bb": 120},
        {"color": "green", "y_high": 25, "y_low": 135, "y_bt": 45, "y_bb": 115},
    ]
    img = _chart(specs)
    candles = detect_candles_from_image(img, _calib(), now=1_700_000_010)
    assert len(candles) == 5
    dirs = [c.direction for c in candles]
    assert dirs == [1, -1, 1, -1, 1]


def test_ohlc_matches_drawing():
    cal = _calib()
    specs = [{"color": "green", "y_high": 20, "y_low": 120, "y_bt": 40, "y_bb": 100}]
    img = _chart(specs)
    c = detect_candles_from_image(img, cal, now=0)[0]
    # altas: high = extremo superior (y=20), low = inferior (y=120)
    assert c.high == pytest.approx(cal.price_at(20), abs=1e-6)
    assert c.low == pytest.approx(cal.price_at(120), abs=1e-6)
    # corpo: abre embaixo (y=100), fecha em cima (y=40)
    assert c.open == pytest.approx(cal.price_at(100), abs=1e-6)
    assert c.close == pytest.approx(cal.price_at(40), abs=1e-6)
    assert c.is_valid()


def test_red_candle_ohlc():
    cal = _calib()
    specs = [{"color": "red", "y_high": 20, "y_low": 120, "y_bt": 40, "y_bb": 100}]
    img = _chart(specs)
    c = detect_candles_from_image(img, cal, now=0)[0]
    # baixa: abre em cima (y=40), fecha embaixo (y=100)
    assert c.open == pytest.approx(cal.price_at(40), abs=1e-6)
    assert c.close == pytest.approx(cal.price_at(100), abs=1e-6)
    assert c.close < c.open


def test_timestamps_are_minute_aligned_and_increasing():
    img = _chart([{"color": "green", "y_high": 20, "y_low": 120, "y_bt": 40, "y_bb": 100},
                  {"color": "red", "y_high": 30, "y_low": 130, "y_bt": 50, "y_bb": 110},
                  {"color": "green", "y_high": 20, "y_low": 120, "y_bt": 40, "y_bb": 100}])
    now = 1_700_000_010  # não é múltiplo de 60
    candles = detect_candles_from_image(img, _calib(), timeframe_s=60, now=now)
    ts = [c.ts for c in candles]
    assert ts == sorted(ts) and len(set(ts)) == 3
    assert all(t % 60 == 0 for t in ts)
    assert ts[-1] == (now // 60) * 60          # última vela = minuto atual
    assert ts[1] - ts[0] == 60 and ts[2] - ts[1] == 60


def test_empty_image_returns_no_candles():
    img = Image.new("RGB", (80, 80), BG)
    assert detect_candles_from_image(img, _calib()) == []


def test_wick_does_not_create_extra_candle():
    # vela com pavio longo: pavio é da mesma cor e toca o corpo => 1 vela
    img = _chart([{"color": "green", "y_high": 5, "y_low": 160, "y_bt": 40, "y_bb": 120}])
    candles = detect_candles_from_image(img, _calib(), now=0)
    assert len(candles) == 1


def test_two_same_color_touching_candles_are_split_by_wicks():
    """Duas velas verdes coladas (sem gap) viram 2, pelos picos de pavio."""
    width = 8
    img = Image.new("RGB", (120, 200), BG)
    d = ImageDraw.Draw(img)
    # vela 1: x 8..15, vela 2: x 16..23 (coladas)
    _draw_candle(d, 8, GREEN, 20, 120, 40, 100, width)
    _draw_candle(d, 16, GREEN, 30, 140, 50, 110, width)
    candles = detect_candles_from_image(img, _calib(), now=0, split_merged=True)
    assert len(candles) == 2


def test_chart_region_helper():
    img = _chart([{"color": "green", "y_high": 20, "y_low": 120, "y_bt": 40, "y_bb": 100},
                  {"color": "red", "y_high": 30, "y_low": 130, "y_bt": 50, "y_bb": 110}],
                 start_x=12)
    region = chart_region_from_image(img)
    assert region is not None
    left, top, right, bottom = region
    assert left == 12 and right > left and top <= 20 and bottom >= 130


def test_generated_chart_matches_truth(tmp_path):
    """Validação ponta a ponta: velas detectadas == velas desenhadas (com tolerância de pixel)."""
    from scripts.make_sample_screenshot import build
    out = str(tmp_path / "s.png")
    info = build(out, n=40, seed=3)
    img = Image.open(out)
    calib = ScreenCalibration(
        region=info["region"], price_top=info["price_top"], pixel_top=info["pixel_top"],
        price_bottom=info["price_bottom"], pixel_bottom=info["pixel_bottom"])
    candles = detect_candles_from_image(img, calib, now=1_700_000_000)
    truth = info["candles"]
    assert len(candles) == len(truth) == 40

    px_price = abs(info["price_top"] - info["price_bottom"]) / abs(
        info["pixel_bottom"] - info["pixel_top"])
    tol = px_price * 2.5   # ~2,5 px de folga

    for got, exp in zip(candles, truth):
        assert got.high == pytest.approx(exp["high"], abs=tol)
        assert got.low == pytest.approx(exp["low"], abs=tol)
        assert got.open == pytest.approx(exp["open"], abs=tol)
        assert got.close == pytest.approx(exp["close"], abs=tol)
        # direção coerente com a cor desenhada (verde=alta, vermelho=baixa)
        if exp["close"] > exp["open"]:
            assert got.direction == 1
        elif exp["close"] < exp["open"]:
            assert got.direction == -1


def test_builds_valid_candle_series():
    specs = [{"color": "green", "y_high": 20, "y_low": 120, "y_bt": 40, "y_bb": 100},
             {"color": "red", "y_high": 30, "y_low": 130, "y_bt": 50, "y_bb": 110}]
    img = _chart(specs)
    candles = detect_candles_from_image(img, _calib(), now=1_700_000_010)
    series = CandleSeries(candles, symbol="TEST", timeframe_s=60)
    assert len(series) == 2              # _validate() passou (ordem + OHLC)
