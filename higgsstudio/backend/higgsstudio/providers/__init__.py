"""Registro de proveedores y selección automática.

El orden lo marca la configuración: si hay clave del proveedor preferido se
usa ese; si no, se va bajando hasta el motor local, que siempre responde.
"""
from __future__ import annotations

from ..config import get_settings
from .base import (  # noqa: F401
    GenRequest, GenResult, Output, ProviderError, ProviderUnavailable,
    dimensions, extract_frame, make_thumbnail, probe, run_ffmpeg,
)
from .elevenlabs import ElevenLabsProvider, clone_voice, list_remote_voices  # noqa: F401
from .fal import FalProvider
from .local import LocalProvider, motion_chain, palette  # noqa: F401
from .openai_images import OpenAIImageProvider
from .replicate import ReplicateProvider

_LOCAL = LocalProvider()
_REGISTRY = {
    "fal": FalProvider(),
    "replicate": ReplicateProvider(),
    "elevenlabs": ElevenLabsProvider(),
    "openai": OpenAIImageProvider(),
    "local": _LOCAL,
}

# Modos que siempre conviene hacer en local: son deterministas, rápidos y
# gratis, y el resultado no mejora pasando por un modelo.
ALWAYS_LOCAL = {"stitch", "reframe", "extend"}


def get_provider(name: str):
    return _REGISTRY.get(name)


def available_providers() -> list[str]:
    return [name for name, provider in _REGISTRY.items() if provider.available()]


def preferred_order(req: GenRequest) -> list[str]:
    settings = get_settings()
    if req.mode in ALWAYS_LOCAL:
        return ["local"]
    if req.type == "image":
        first = settings.resolved_image_provider()
        chain = [first, "fal", "replicate", "openai", "local"]
    elif req.type == "audio":
        first = settings.resolved_audio_provider()
        chain = [first, "elevenlabs", "fal", "replicate", "local"]
    else:                                     # video, speak, tool
        first = settings.resolved_video_provider()
        chain = [first, "fal", "replicate", "local"]
    seen: set[str] = set()
    return [p for p in chain if not (p in seen or seen.add(p))]


def resolve(req: GenRequest, *, forced: str | None = None):
    """Devuelve el primer proveedor capaz de atender la petición."""
    if forced:
        provider = _REGISTRY.get(forced)
        if provider is None:
            raise ProviderError(f"Proveedor desconocido: {forced}")
        if not provider.available():
            raise ProviderUnavailable(f"El proveedor «{forced}» no tiene clave configurada")
        return provider
    for name in preferred_order(req):
        provider = _REGISTRY.get(name)
        if provider and provider.available() and provider.supports(req):
            return provider
    return _LOCAL
