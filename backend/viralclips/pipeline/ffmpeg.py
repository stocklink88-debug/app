"""Envoltorios sobre ffmpeg / ffprobe."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence


class FFmpegError(RuntimeError):
    pass


def _binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise FFmpegError(
            f"No se encuentra '{name}'. Instala ffmpeg (apt install ffmpeg / brew install ffmpeg)."
        )
    return path


@dataclass
class MediaInfo:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    video_codec: str | None = None
    audio_codec: str | None = None

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 16 / 9


def probe(path: Path | str) -> MediaInfo:
    """Lee metadatos del contenedor con ffprobe."""
    out = subprocess.run(
        [
            _binary("ffprobe"), "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise FFmpegError(f"ffprobe falló: {out.stderr.strip()[:500]}")

    data = json.loads(out.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise FFmpegError("El archivo no contiene pista de vídeo.")

    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0.0)
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)

    # La rotación en metadatos intercambia ancho/alto visibles (móviles).
    rotation = 0
    for side in (video.get("side_data_list") or []):
        if "rotation" in side:
            rotation = int(abs(float(side["rotation"]))) % 360
    if rotation in (90, 270):
        width, height = height, width

    fps = 30.0
    raw_fps = video.get("avg_frame_rate") or video.get("r_frame_rate") or "30/1"
    try:
        num, _, den = raw_fps.partition("/")
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    if not fps or fps <= 0 or fps > 480:
        fps = 30.0

    return MediaInfo(
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        has_audio=audio is not None,
        video_codec=video.get("codec_name"),
        audio_codec=(audio or {}).get("codec_name"),
    )


_TIME_RE = re.compile(r"out_time_ms=(\d+)")


def run_ffmpeg(
    args: Sequence[str],
    *,
    total_duration: float | None = None,
    on_progress: Callable[[float], None] | None = None,
    timeout: float | None = None,
) -> None:
    """Ejecuta ffmpeg informando del progreso (0..1) si se conoce la duración."""
    cmd = [_binary("ffmpeg"), "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    if on_progress and total_duration:
        cmd += ["-progress", "pipe:1", "-stats_period", "0.4"]
    cmd += list(args)

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
    )
    try:
        if on_progress and total_duration and proc.stdout:
            for line in proc.stdout:
                m = _TIME_RE.search(line)
                if m:
                    done = int(m.group(1)) / 1_000_000 / max(total_duration, 0.001)
                    on_progress(max(0.0, min(1.0, done)))
        stderr = proc.communicate(timeout=timeout)[1]
    except subprocess.TimeoutExpired:
        proc.kill()
        raise FFmpegError("ffmpeg excedió el tiempo máximo.")

    if proc.returncode != 0:
        tail = "\n".join((stderr or "").strip().splitlines()[-12:])
        raise FFmpegError(f"ffmpeg falló (código {proc.returncode}):\n{tail}")
    if on_progress:
        on_progress(1.0)


def extract_audio(src: Path, dst: Path, *, sample_rate: int = 16000) -> Path:
    """Extrae audio mono PCM, el formato que esperan los ASR."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-i", str(src), "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-c:a", "pcm_s16le", str(dst),
    ])
    return dst


def extract_thumbnail(src: Path, dst: Path, *, at: float = 0.0, width: int = 540) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-ss", f"{max(at, 0):.3f}", "-i", str(src), "-frames:v", "1",
        "-vf", f"scale={width}:-2:flags=bicubic", "-q:v", "3", str(dst),
    ])
    return dst


def compress_audio_for_api(src: Path, dst: Path, *, bitrate: str = "48k") -> Path:
    """Los ASR cobran/limitan por tamaño: mandamos opus mono de baja tasa."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "libopus", "-b:a", bitrate, str(dst),
    ])
    return dst


def split_audio(src: Path, out_dir: Path, *, chunk_seconds: float = 600.0) -> list[tuple[Path, float]]:
    """Divide el audio en trozos; devuelve (ruta, offset_en_segundos)."""
    info = probe(src)
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[tuple[Path, float]] = []
    offset = 0.0
    idx = 0
    while offset < info.duration:
        dst = out_dir / f"chunk_{idx:03d}.ogg"
        run_ffmpeg([
            "-ss", f"{offset:.3f}", "-t", f"{chunk_seconds:.3f}", "-i", str(src),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "48k", str(dst),
        ])
        chunks.append((dst, offset))
        offset += chunk_seconds
        idx += 1
    return chunks


def escape_filter_path(path: Path | str) -> str:
    """Escapa una ruta para usarla dentro de un filtro de ffmpeg."""
    s = str(path)
    s = s.replace("\\", "/")
    s = s.replace(":", r"\:")
    s = s.replace("'", r"\'")
    s = s.replace("[", r"\[").replace("]", r"\]")
    s = s.replace(",", r"\,")
    return s


def build_filter_chain(parts: Iterable[str]) -> str:
    return ",".join(p for p in parts if p)
