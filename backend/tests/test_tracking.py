import pytest

from viralclips.pipeline.tracking import (
    _rdp, _smooth, build_crop_expression, crop_size, parse_aspect,
)


@pytest.mark.parametrize(
    "src_w,src_h,ratio,expected",
    [
        (1920, 1080, 9 / 16, (608, 1080)),   # horizontal -> vertical
        (1080, 1920, 9 / 16, (1080, 1920)),  # ya es vertical: sin recorte
        (1920, 1080, 1.0, (1080, 1080)),     # cuadrado
        (1280, 720, 4 / 5, (576, 720)),
    ],
)
def test_crop_size(src_w, src_h, ratio, expected):
    assert crop_size(src_w, src_h, ratio) == expected


def test_crop_size_is_always_even():
    for w, h in [(1921, 1081), (999, 555), (1337, 777)]:
        cw, ch = crop_size(w, h, 9 / 16)
        assert cw % 2 == 0 and ch % 2 == 0
        assert cw <= w and ch <= h


def test_parse_aspect():
    assert parse_aspect("9:16") == pytest.approx(0.5625)
    assert parse_aspect("16:9") == pytest.approx(1.7778, abs=1e-3)
    assert parse_aspect("basura") == pytest.approx(0.5625)   # valor por defecto


def test_crop_expression_is_constant_for_single_keyframe():
    assert build_crop_expression([(0.0, 420.0)], fallback=0) == "420.0"


def test_crop_expression_interpolates_linearly():
    expr = build_crop_expression([(0.0, 0.0), (2.0, 200.0)], fallback=0)
    assert "if(lt(t,2.000)" in expr
    assert "100.0000" in expr        # pendiente = 200 px / 2 s


def test_crop_expression_has_no_escaped_commas():
    # Las comas van protegidas por las comillas simples del filtro, no por barras.
    expr = build_crop_expression([(0.0, 0.0), (1.0, 50.0), (2.0, 10.0)], fallback=0)
    assert "\\," not in expr


def test_smooth_fills_leading_gaps():
    series = [(0.0, None, False), (0.2, None, False), (0.4, 100.0, False)]
    out = _smooth(series, width=320, default=160.0)
    assert len(out) == 3
    assert all(v is not None for _, v in out)


def test_smooth_snaps_on_scene_cut():
    series = [(0.0, 10.0, False), (0.2, 10.0, False), (0.4, 300.0, True)]
    out = _smooth(series, width=320, default=160.0)
    assert out[-1][1] == pytest.approx(300.0)   # el corte permite el salto


def test_smooth_limits_speed_without_a_cut():
    series = [(0.0, 10.0, False)] + [(i * 0.2, 300.0, False) for i in range(1, 6)]
    out = _smooth(series, width=320, default=160.0)
    steps = [abs(b[1] - a[1]) for a, b in zip(out, out[1:])]
    # 0.22 * 320 px/s * 0.2 s = 14.08 px por muestra como máximo.
    assert max(steps) <= 320 * 0.22 * 0.2 + 1e-6


def test_rdp_keeps_endpoints_and_reduces_points():
    points = [(i * 0.1, 100.0) for i in range(40)]   # recta: debe quedar en 2 puntos
    simplified = _rdp(points, tolerance=1.0)
    assert simplified[0] == points[0]
    assert simplified[-1] == points[-1]
    assert len(simplified) == 2
