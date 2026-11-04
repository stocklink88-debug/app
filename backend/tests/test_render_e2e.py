"""Prueba de extremo a extremo con ffmpeg real.

Genera un vídeo sintético, lo pasa por el pipeline completo y comprueba que
salen MP4 verticales reproducibles. Es lenta (decodifica y recodifica vídeo),
así que va marcada como `slow`:

    pytest -m slow            # sólo estas
    pytest -m "not slow"      # el resto
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from viralclips.config import get_settings
from viralclips.models import CaptionStyle, Layout, Word
from viralclips.pipeline.ffmpeg import probe
from viralclips.pipeline.render import RenderRequest, output_size, render_clip

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory) -> Path:
    """Vídeo 1920x1080 de 14 s con un sujeto que se desplaza y audio variable."""
    out = tmp_path_factory.mktemp("media") / "source.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=0x14202e:size=1920x1080:rate=25:duration=14",
            "-f", "lavfi", "-i", "color=c=0xffd27f:size=240x240:rate=25:duration=14",
            "-f", "lavfi", "-i", "sine=frequency=220:duration=14:sample_rate=48000",
            "-filter_complex",
            "[1:v]format=yuva420p,geq=lum='p(X,Y)':"
            "a='if(lt((X-120)*(X-120)+(Y-120)*(Y-120),14400),255,0)'[head];"
            "[0:v][head]overlay=x='200+1200*(0.5+0.5*sin(t*0.6))':y='380+100*sin(t)'[v];"
            "[2:a]volume='0.2+0.7*abs(sin(t*0.7))':eval=frame[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out),
        ],
        check=True, capture_output=True,
    )
    return out


@pytest.fixture
def words() -> list[Word]:
    text = "Este es el error que comete casi todo el mundo cuando empieza a invertir su dinero"
    out, t = [], 2.0
    for token in text.split():
        out.append(Word(token, t, t + 0.38))
        t += 0.44
    return out


def _request(sample_video, words, tmp_path, **overrides) -> RenderRequest:
    settings = get_settings()
    defaults = dict(
        source=sample_video,
        out_video=tmp_path / "clip.mp4",
        out_thumb=tmp_path / "clip.jpg",
        work_dir=tmp_path / "work",
        start=2.0, end=10.0,
        source_w=1920, source_h=1080,
        layout=Layout.FILL, caption_style=CaptionStyle.POP, aspect="9:16",
        words=words, hook="EL ERROR QUE TODOS COMETEN",
        resolution=720, normalize_audio=True, model_path=settings.yunet_path,
    )
    defaults.update(overrides)
    return RenderRequest(**defaults)


@pytest.mark.parametrize("layout", [Layout.FILL, Layout.BLUR, Layout.SPLIT])
def test_every_layout_renders_a_valid_vertical_clip(sample_video, words, tmp_path, layout):
    req = _request(
        sample_video, words, tmp_path,
        layout=layout, out_video=tmp_path / f"{layout.value}.mp4",
        out_thumb=tmp_path / f"{layout.value}.jpg",
    )
    result = render_clip(req)

    assert result.video.exists() and result.video.stat().st_size > 20_000
    assert result.thumb.exists()

    info = probe(result.video)
    assert (info.width, info.height) == (720, 1280)
    assert info.has_audio
    assert info.video_codec == "h264"
    assert info.duration == pytest.approx(8.0, abs=0.4)


@pytest.mark.parametrize("style", [CaptionStyle.POP, CaptionStyle.KARAOKE,
                                   CaptionStyle.BOXED, CaptionStyle.MINIMAL,
                                   CaptionStyle.NONE])
def test_every_caption_style_renders(sample_video, words, tmp_path, style):
    req = _request(
        sample_video, words, tmp_path,
        caption_style=style, out_video=tmp_path / f"{style.value}.mp4",
        out_thumb=tmp_path / f"{style.value}.jpg", end=6.0,
    )
    result = render_clip(req)
    assert probe(result.video).duration == pytest.approx(4.0, abs=0.4)


@pytest.mark.parametrize("aspect,expected", [
    ("9:16", (720, 1280)), ("1:1", (720, 720)), ("4:5", (720, 900)),
])
def test_aspect_ratios(sample_video, words, tmp_path, aspect, expected):
    req = _request(
        sample_video, words, tmp_path, aspect=aspect, end=5.0,
        out_video=tmp_path / f"{aspect.replace(':', '_')}.mp4",
        out_thumb=tmp_path / f"{aspect.replace(':', '_')}.jpg",
    )
    result = render_clip(req)
    info = probe(result.video)
    assert (info.width, info.height) == expected
    assert output_size(aspect, 720) == expected


def test_render_without_words_still_produces_video(sample_video, tmp_path):
    req = _request(sample_video, [], tmp_path, hook=None,
                   caption_style=CaptionStyle.NONE, end=5.0)
    result = render_clip(req)
    assert probe(result.video).duration == pytest.approx(3.0, abs=0.4)


def test_tracking_produces_a_moving_crop(sample_video, tmp_path):
    """El sujeto se mueve, así que el recorte no debe quedarse quieto."""
    from viralclips.pipeline.tracking import compute_track

    settings = get_settings()
    track = compute_track(
        sample_video, start=0.0, duration=12.0,
        source_w=1920, source_h=1080, target_ratio=9 / 16,
        model_path=settings.yunet_path, work_dir=tmp_path / "track",
    )
    assert track.crop_w == 608 and track.crop_h == 1080
    assert track.samples > 0
    xs = [x for _, x in track.keyframes_x]
    assert len(xs) >= 2
    assert max(xs) - min(xs) > 40          # la cámara ha seguido al sujeto
    assert all(0 <= x <= 1920 - 608 for x in xs)
