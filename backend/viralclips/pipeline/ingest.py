"""Entrada de material: fichero subido o URL (YouTube, Vimeo, etc.)."""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .ffmpeg import MediaInfo, extract_audio, probe

ProgressFn = Callable[[float, str], None]

_SAFE = re.compile(r"[^\w\s.-]", re.UNICODE)


def safe_filename(name: str, fallback: str = "video") -> str:
    base = _SAFE.sub("", name).strip().replace(" ", "_")
    return (base or fallback)[:120]


@dataclass
class IngestResult:
    video_path: Path
    audio_path: Path
    info: MediaInfo
    title: str


def download_url(url: str, dest_dir: Path, *, on_progress: ProgressFn | None = None) -> tuple[Path, str]:
    """Descarga un vídeo con yt-dlp. Devuelve (ruta, título)."""
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - dependencia declarada
        raise RuntimeError("yt-dlp no está instalado; no se pueden usar URLs.") from exc

    dest_dir.mkdir(parents=True, exist_ok=True)

    def hook(d: dict) -> None:
        if not on_progress:
            return
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            got = d.get("downloaded_bytes") or 0
            frac = (got / total) if total else 0.0
            on_progress(min(frac, 0.99), "Descargando vídeo")
        elif d.get("status") == "finished":
            on_progress(1.0, "Descarga completada")

    opts = {
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        # Preferimos un mp4 ya mezclado; si no existe, el mejor vídeo+audio.
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "retries": 3,
        "socket_timeout": 30,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise RuntimeError("yt-dlp no devolvió información del vídeo.")
        title = info.get("title") or "Vídeo"
        path = Path(ydl.prepare_filename(info))

    if not path.exists():
        candidates = sorted(dest_dir.glob("source.*"), key=lambda p: p.stat().st_size, reverse=True)
        if not candidates:
            raise RuntimeError("La descarga terminó pero no se encontró el archivo.")
        path = candidates[0]

    return path, title


def ingest_upload(temp_path: Path, dest_dir: Path, filename: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix or ".mp4"
    dest = dest_dir / f"source{suffix}"
    shutil.move(str(temp_path), dest)
    return dest


def prepare(
    *,
    video_path: Path,
    work_dir: Path,
    title: str,
    on_progress: ProgressFn | None = None,
) -> IngestResult:
    """Sondea el vídeo y extrae el audio que usará el ASR."""
    if on_progress:
        on_progress(0.55, "Analizando el archivo")
    info = probe(video_path)

    if info.duration < 5:
        raise RuntimeError("El vídeo dura menos de 5 segundos: no hay material para clips.")
    if not info.has_audio:
        raise RuntimeError(
            "El vídeo no tiene audio. ViralClips necesita la voz para encontrar los momentos."
        )

    if on_progress:
        on_progress(0.75, "Extrayendo audio")
    audio_path = extract_audio(video_path, work_dir / "audio.wav")

    if on_progress:
        on_progress(1.0, "Material preparado")

    return IngestResult(video_path=video_path, audio_path=audio_path, info=info, title=title)
