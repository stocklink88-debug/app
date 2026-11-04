"""Montaje final de cada clip: recorte vertical, subtítulos y audio."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..models import AudioMode, CaptionStyle, Layout, Word
from .ffmpeg import escape_filter_path, extract_thumbnail, run_ffmpeg
from .subtitles import build_ass
from .tracking import Track, build_crop_expression, compute_track, parse_aspect

log = logging.getLogger(__name__)
ProgressFn = Callable[[float], None]

# Perfiles de salida habituales en vertical.
ASPECT_HEIGHTS = {"9:16": 16 / 9, "4:5": 5 / 4, "1:1": 1.0, "16:9": 9 / 16}


@dataclass
class RenderRequest:
    source: Path
    out_video: Path
    out_thumb: Path
    work_dir: Path
    start: float
    end: float
    source_w: int
    source_h: int
    layout: Layout
    caption_style: CaptionStyle
    aspect: str
    words: list[Word]
    hook: str | None
    resolution: int
    normalize_audio: bool
    model_path: Path
    font: str | None = None
    audio_mode: AudioMode = AudioMode.ORIGINAL
    # Locución ya generada (ElevenLabs) para audio_mode == VOICEOVER.
    voiceover_path: Path | None = None
    # Volumen del audio original bajo la locución: 0 lo elimina del todo.
    background_volume: float = 0.0

    @property
    def duration(self) -> float:
        return max(self.end - self.start, 0.1)


@dataclass
class RenderResult:
    video: Path
    thumb: Path
    track_found_subject: bool
    width: int
    height: int


def output_size(aspect: str, resolution: int) -> tuple[int, int]:
    ratio = parse_aspect(aspect)
    if ratio <= 1:          # vertical o cuadrado: `resolution` es el ancho
        w = resolution
        h = int(round(w / ratio))
    else:                   # horizontal: `resolution` es la altura
        h = resolution
        w = int(round(h * ratio))
    return w - (w % 2), h - (h % 2)


def render_clip(req: RenderRequest, *, on_progress: ProgressFn | None = None) -> RenderResult:
    req.work_dir.mkdir(parents=True, exist_ok=True)
    req.out_video.parent.mkdir(parents=True, exist_ok=True)

    out_w, out_h = output_size(req.aspect, req.resolution)
    ratio = parse_aspect(req.aspect)

    track = compute_track(
        req.source,
        start=req.start,
        duration=req.duration,
        source_w=req.source_w,
        source_h=req.source_h,
        target_ratio=ratio,
        model_path=req.model_path,
        work_dir=req.work_dir,
    )

    ass_path = req.work_dir / f"{req.out_video.stem}.ass"
    ass_path.write_text(
        build_ass(
            req.words,
            style=req.caption_style,
            width=out_w,
            height=out_h,
            clip_start=req.start,
            clip_end=req.end,
            hook=req.hook,
            font=req.font,
        ),
        encoding="utf-8",
    )

    filtergraph = _build_filtergraph(
        req, track, out_w=out_w, out_h=out_h, ass_path=ass_path
    )

    args = [
        "-ss", f"{req.start:.3f}",
        "-i", str(req.source),
    ]
    if req.audio_mode == AudioMode.VOICEOVER and req.voiceover_path:
        args += ["-i", str(req.voiceover_path)]
    args += [
        "-t", f"{req.duration:.3f}",
        "-filter_complex", filtergraph,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
        "-g", "60", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        str(req.out_video),
    ]
    run_ffmpeg(args, total_duration=req.duration, on_progress=on_progress)

    extract_thumbnail(
        req.out_video, req.out_thumb, at=req.duration * 0.12, width=min(out_w, 540)
    )

    return RenderResult(
        video=req.out_video,
        thumb=req.out_thumb,
        track_found_subject=track.found_subject,
        width=out_w,
        height=out_h,
    )


def _build_filtergraph(
    req: RenderRequest,
    track: Track,
    *,
    out_w: int,
    out_h: int,
    ass_path: Path,
) -> str:
    ass = f"ass='{escape_filter_path(ass_path)}'"
    has_subs = req.caption_style != CaptionStyle.NONE or bool(req.hook)

    if req.layout == Layout.BLUR:
        video = _blur_graph(out_w, out_h)
    elif req.layout == Layout.SPLIT:
        video = _split_graph(req, track, out_w, out_h)
    else:
        video = _fill_graph(track, out_w, out_h)

    if has_subs:
        video += f",{ass}"
    video += ",format=yuv420p[vout]"

    return f"{video};{_audio_graph(req)}"


def _audio_graph(req: RenderRequest) -> str:
    """Cadena de audio según el modo elegido."""
    normalize = ",loudnorm=I=-14:TP=-1.5:LRA=11" if req.normalize_audio else ""

    if req.audio_mode == AudioMode.MUTE:
        # Pista silenciosa en lugar de ninguna: algunas plataformas rechazan
        # los vídeos sin stream de audio. `-t` la recorta a la duración del clip.
        return "anullsrc=channel_layout=stereo:sample_rate=48000[aout]"

    if req.audio_mode == AudioMode.VOICEOVER and req.voiceover_path:
        # La locución nunca dura exactamente lo que el clip: se rellena con
        # silencio si falta y se recorta si sobra.
        voice = (
            f"[1:a]aresample=48000,asetpts=PTS-STARTPTS,"
            f"apad,atrim=duration={req.duration:.3f}"
        )
        if req.background_volume > 0:
            return (
                f"{voice}[voice];"
                f"[0:a]asetpts=PTS-STARTPTS,aresample=48000,"
                f"volume={req.background_volume:.3f}[bgaudio];"
                f"[bgaudio][voice]amix=inputs=2:duration=first:dropout_transition=0,"
                f"aresample=48000{normalize}[aout]"
            )
        return f"{voice}{normalize}[aout]"

    return f"[0:a]asetpts=PTS-STARTPTS{normalize},aresample=48000[aout]"


def _fill_graph(track: Track, out_w: int, out_h: int) -> str:
    """Recorte dinámico que sigue al sujeto."""
    base = "[0:v]setpts=PTS-STARTPTS"
    if track.crop_w >= track.source_w and track.crop_h >= track.source_h:
        # El origen ya es más estrecho: escalamos y rellenamos con desenfoque.
        return _blur_graph(out_w, out_h)

    x = build_crop_expression(
        track.keyframes_x, fallback=max((track.source_w - track.crop_w) / 2, 0)
    )
    y = build_crop_expression(
        track.keyframes_y, fallback=max((track.source_h - track.crop_h) / 2, 0)
    )
    return (
        f"{base},crop=w={track.crop_w}:h={track.crop_h}:x='{x}':y='{y}',"
        f"scale={out_w}:{out_h}:flags=bicubic"
    )


def _blur_graph(out_w: int, out_h: int) -> str:
    """Vídeo completo centrado sobre una versión ampliada y desenfocada."""
    return (
        f"[0:v]setpts=PTS-STARTPTS,split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h},gblur=sigma={max(out_w // 38, 8)},"
        f"eq=brightness=-0.10:saturation=1.15[bg];"
        f"[fgsrc]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )


def _split_graph(req: RenderRequest, track: Track, out_w: int, out_h: int) -> str:
    """Arriba el sujeto en primer plano, abajo el plano general."""
    top_h = int(out_h * 0.58)
    top_h -= top_h % 2
    bottom_h = out_h - top_h

    if track.crop_w >= track.source_w:
        top = f"[topsrc]scale={out_w}:{top_h}:force_original_aspect_ratio=increase,crop={out_w}:{top_h}[top]"
    else:
        # Para la mitad superior usamos un recorte más ancho que el 9:16 puro.
        tw = track.crop_w
        wide_w = min(int(tw * 1.25), track.source_w)
        wide_w -= wide_w % 2
        wide_h = min(int(wide_w * top_h / out_w), track.source_h)
        wide_h -= wide_h % 2
        x = build_crop_expression(
            [(t, max(0.0, min(v - (wide_w - tw) / 2, track.source_w - wide_w)))
             for t, v in track.keyframes_x],
            fallback=max((track.source_w - wide_w) / 2, 0),
        )
        y = build_crop_expression(
            [(t, max(0.0, min(v, track.source_h - wide_h))) for t, v in track.keyframes_y],
            fallback=max((track.source_h - wide_h) / 2, 0),
        )
        top = (
            f"[topsrc]crop=w={wide_w}:h={wide_h}:x='{x}':y='{y}',"
            f"scale={out_w}:{top_h}:flags=bicubic[top]"
        )

    return (
        f"[0:v]setpts=PTS-STARTPTS,split=2[topsrc][botsrc];"
        f"{top};"
        f"[botsrc]scale={out_w}:{bottom_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{bottom_h}:(ow-iw)/2:(oh-ih)/2:color=0x0B0E13[bot];"
        f"[top][bot]vstack=inputs=2"
    )
