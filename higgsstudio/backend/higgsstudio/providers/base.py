"""Interfaz común de los proveedores de generación.

Un proveedor recibe una `GenRequest` (ya normalizada por el pipeline) y
devuelve una `GenResult` con los ficheros producidos. El pipeline no sabe si
detrás hay fal.ai, Replicate o el motor local.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

ProgressFn = Callable[[float, str], None]


class ProviderError(RuntimeError):
    """Fallo recuperable del proveedor (se muestra al usuario)."""


class ProviderUnavailable(ProviderError):
    """El proveedor no puede atender esta petición (falta clave o soporte)."""


@dataclass
class GenRequest:
    job_id: str
    type: str                      # video | image | speak | audio | tool
    mode: str                      # t2v, i2v, frames, t2i, edit, speak, tts...
    model: dict[str, Any]          # entrada del catálogo
    workdir: Path
    prompt: str = ""
    negative_prompt: str = ""
    duration: float = 5.0
    aspect: str = "16:9"
    resolution: str = "720p"
    fps: int = 24
    seed: int | None = None
    count: int = 1
    images: list[Path] = field(default_factory=list)
    end_image: Path | None = None
    video: Path | None = None
    audio: Path | None = None
    preset: dict[str, Any] | None = None
    style: dict[str, Any] | None = None
    voice: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    progress: ProgressFn = lambda pct, msg: None

    @property
    def motion(self) -> str:
        if self.preset:
            return str(self.preset.get("motion") or "static")
        return str(self.extra.get("motion") or "static")

    def provider_model(self, provider: str) -> str | None:
        """Endpoint del proveedor para este modo.

        En fal (y en Replicate) texto→vídeo e imagen→vídeo son rutas
        distintas, así que `providers` puede ser un diccionario por modo.
        Se admite también una cadena suelta o la clave "*" para los modelos
        que usan un único endpoint para todo.
        """
        from ..config import get_settings

        overrides = get_settings().endpoint_overrides()
        entry = overrides.get(self.model["id"], {}).get(provider)
        if entry is None:
            entry = self.model.get("providers", {}).get(provider)
        if entry is None:
            return None
        if isinstance(entry, str):
            return entry
        return entry.get(self.mode) or entry.get("*")

    def full_prompt(self) -> str:
        parts = [self.prompt.strip()]
        if self.style and self.style.get("prompt"):
            parts.append(self.style["prompt"])
        if self.preset and self.preset.get("prompt"):
            parts.append(self.preset["prompt"])
        if camera := self.extra.get("camera_prompt"):
            parts.append(str(camera))
        return ", ".join(p for p in parts if p)


@dataclass
class Output:
    path: Path
    kind: str                      # video | image | audio | model3d
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenResult:
    outputs: list[Output]
    provider: str
    meta: dict[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    name: str

    def available(self) -> bool: ...

    def supports(self, req: GenRequest) -> bool: ...

    def run(self, req: GenRequest) -> GenResult: ...


# ------------------------- utilidades de medios -------------------------

ASPECT_SIZES: dict[str, tuple[int, int]] = {
    "16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:3": (4, 3),
    "3:4": (3, 4), "4:5": (4, 5), "21:9": (21, 9), "2:3": (2, 3), "3:2": (3, 2),
}

RES_HEIGHT = {
    "480p": 480, "540p": 540, "720p": 720, "768p": 768,
    "1080p": 1080, "1k": 1024, "2k": 1440, "4k": 2160,
}


def dimensions(aspect: str, resolution: str) -> tuple[int, int]:
    """Calcula ancho y alto pares a partir del formato y la resolución."""
    aw, ah = ASPECT_SIZES.get(aspect, (16, 9))
    short = RES_HEIGHT.get(resolution, 720)
    if aw >= ah:                     # horizontal o cuadrado: la altura manda
        height = short
        width = round(height * aw / ah)
    else:                            # vertical: la anchura manda
        width = short
        height = round(width * ah / aw)
    return (width - width % 2, height - height % 2)


def ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def run_ffmpeg(args: list[str], *, timeout: int = 900) -> None:
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-6:]
        raise ProviderError("ffmpeg falló: " + " | ".join(tail))


def probe(path: Path) -> dict[str, Any]:
    cmd = [ffprobe_bin(), "-v", "quiet", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return {}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}
    out: dict[str, Any] = {}
    fmt = data.get("format", {})
    if dur := fmt.get("duration"):
        out["duration"] = float(dur)
    if size := fmt.get("size"):
        out["size_bytes"] = int(size)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and "width" not in out:
            out["width"] = stream.get("width")
            out["height"] = stream.get("height")
            rate = stream.get("avg_frame_rate") or "0/1"
            try:
                num, den = rate.split("/")
                if float(den):
                    out["fps"] = round(float(num) / float(den), 3)
            except (ValueError, ZeroDivisionError):
                pass
        if stream.get("codec_type") == "audio":
            out["has_audio"] = True
            out.setdefault("audio_codec", stream.get("codec_name"))
    return out


def make_thumbnail(src: Path, dest: Path, *, at: float = 0.4, width: int = 640) -> Path | None:
    """Extrae una miniatura JPEG de un vídeo o reescala una imagen."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        info = probe(src)
        if info.get("duration"):
            ts = max(0.0, min(info["duration"] * at, max(info["duration"] - 0.1, 0)))
            run_ffmpeg(["-ss", f"{ts:.2f}", "-i", str(src), "-frames:v", "1",
                        "-vf", f"scale={width}:-2:flags=lanczos", "-q:v", "4", str(dest)],
                       timeout=120)
        else:
            run_ffmpeg(["-i", str(src), "-frames:v", "1",
                        "-vf", f"scale={width}:-2:flags=lanczos", "-q:v", "4", str(dest)],
                       timeout=120)
        return dest if dest.exists() else None
    except Exception:
        return None


def extract_frame(src: Path, dest: Path, *, at: str = "last") -> Path | None:
    """Saca el primer o el último fotograma de un vídeo (para extender planos)."""
    info = probe(src)
    duration = float(info.get("duration") or 0)
    ts = 0.0 if at == "first" else max(duration - 0.1, 0.0)
    try:
        run_ffmpeg(["-ss", f"{ts:.3f}", "-i", str(src), "-frames:v", "1",
                    "-q:v", "2", str(dest)], timeout=120)
        return dest if dest.exists() else None
    except ProviderError:
        return None
