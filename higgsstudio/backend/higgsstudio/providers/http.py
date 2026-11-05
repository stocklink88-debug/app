"""Utilidades HTTP compartidas por los proveedores remotos."""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import httpx

from .base import ProviderError

TIMEOUT = httpx.Timeout(connect=20.0, read=180.0, write=180.0, pool=20.0)
MAX_INLINE_MB = 18


def client(headers: dict[str, str] | None = None) -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers=headers or {}, follow_redirects=True)


def data_uri(path: Path) -> str:
    """Codifica un fichero como data URI (fal y Replicate los aceptan)."""
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_INLINE_MB:
        raise ProviderError(
            f"«{path.name}» ocupa {size_mb:.0f} MB y el proveedor no admite "
            f"más de {MAX_INLINE_MB} MB en línea. Reduce el fichero o súbelo a una URL."
        )
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def download(url: str, dest: Path, *, headers: dict[str, str] | None = None) -> Path:
    """Descarga un resultado a disco, por trozos."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with client(headers) as http:
        with http.stream("GET", url) as response:
            if response.status_code >= 400:
                raise ProviderError(f"No se pudo descargar el resultado ({response.status_code})")
            with dest.open("wb") as fh:
                for chunk in response.iter_bytes(chunk_size=1 << 16):
                    fh.write(chunk)
    if dest.stat().st_size == 0:
        raise ProviderError("El proveedor devolvió un fichero vacío")
    return dest


def collect_urls(payload: object) -> list[tuple[str, str]]:
    """Busca recursivamente URLs de medios en la respuesta del proveedor.

    Devuelve pares (url, tipo) donde tipo es video | image | audio | model3d.
    """
    found: list[tuple[str, str]] = []

    def kind_of(url: str, hint: str = "") -> str:
        lower = (url.split("?")[0] + " " + hint).lower()
        if any(lower.endswith(e) or e in lower for e in (".mp4", ".webm", ".mov", "video")):
            return "video"
        if any(lower.endswith(e) or e in lower for e in (".mp3", ".wav", ".m4a", ".ogg", "audio")):
            return "audio"
        if any(lower.endswith(e) or e in lower for e in (".glb", ".gltf", ".obj", "mesh", "model")):
            return "model3d"
        return "image"

    def walk(node: object, hint: str = "") -> None:
        if isinstance(node, str):
            if node.startswith(("http://", "https://")):
                found.append((node, kind_of(node, hint)))
        elif isinstance(node, dict):
            for key, value in node.items():
                if key in {"url", "video_url", "image_url", "audio_url", "file_url", "uri"}:
                    walk(value, hint or key)
                else:
                    walk(value, key)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item, hint)

    walk(payload)
    # Quita duplicados conservando el orden.
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for url, kind in found:
        if url not in seen:
            seen.add(url)
            out.append((url, kind))
    return out
