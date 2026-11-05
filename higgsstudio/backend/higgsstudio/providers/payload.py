"""Traducción de una `GenRequest` al cuerpo que espera cada proveedor.

fal.ai y Replicate comparten casi los mismos nombres de campo, así que se
construye un diccionario común y luego cada adaptador ajusta lo suyo.
"""
from __future__ import annotations

from typing import Any

from .base import GenRequest, dimensions

# Campos que cada modo necesita de verdad; el resto se descarta para no
# enviar parámetros que el modelo rechace.
MODE_FIELDS: dict[str, set[str]] = {
    "t2v": {"prompt", "negative_prompt", "duration", "aspect_ratio", "resolution",
            "seed", "num_frames", "generate_audio"},
    "i2v": {"prompt", "negative_prompt", "image_url", "duration", "aspect_ratio",
            "resolution", "seed", "generate_audio"},
    "frames": {"prompt", "image_url", "tail_image_url", "duration", "aspect_ratio",
               "resolution", "seed"},
    "motion": {"prompt", "image_url", "video_url", "duration", "resolution", "seed"},
    "effects": {"prompt", "image_url", "duration", "aspect_ratio", "seed"},
    "t2i": {"prompt", "negative_prompt", "image_size", "aspect_ratio", "seed",
            "num_images", "output_format"},
    "i2i": {"prompt", "negative_prompt", "image_url", "image_urls", "strength",
            "seed", "num_images", "aspect_ratio"},
    "edit": {"prompt", "image_url", "image_urls", "seed", "num_images", "aspect_ratio"},
    "style": {"prompt", "image_url", "seed", "num_images", "aspect_ratio"},
    "soul_id": {"prompt", "image_urls", "seed", "num_images", "aspect_ratio"},
    "speak": {"image_url", "audio_url", "prompt", "text_input", "resolution",
              "num_frames", "seed"},
    "lipsync": {"video_url", "audio_url", "text_input", "voice_id"},
    "tts": {"text", "voice", "voice_id", "language"},
    "music": {"prompt", "duration", "music_length_ms"},
    "sfx": {"text", "prompt", "duration_seconds"},
    "v2a": {"video_url", "prompt", "duration", "num_steps"},
    "upscale_video": {"video_url", "upscale_factor", "target_fps"},
    "upscale_image": {"image_url", "upscale_factor", "scale"},
    "interpolate": {"video_url", "target_fps", "num_frames"},
    "reframe": {"video_url", "image_url", "aspect_ratio"},
    "outpaint": {"image_url", "video_url", "aspect_ratio", "canvas_size"},
    "bg_remove": {"image_url", "video_url"},
    "extend": {"video_url", "prompt", "duration"},
    "to_3d": {"image_url", "input_image_url", "textured_mesh"},
    "train": {"images_data_url", "steps", "trigger_word"},
}

IMAGE_SIZES = {
    "16:9": "landscape_16_9", "9:16": "portrait_16_9", "1:1": "square_hd",
    "4:3": "landscape_4_3", "3:4": "portrait_4_3", "4:5": "portrait_4_3",
    "21:9": "landscape_16_9", "2:3": "portrait_4_3", "3:2": "landscape_4_3",
}


def build(req: GenRequest, *, uri_of) -> dict[str, Any]:
    """Crea el payload común. `uri_of(Path) -> str` sube o codifica el fichero."""
    prompt = req.full_prompt()
    width, height = dimensions(req.aspect, req.resolution)
    payload: dict[str, Any] = {
        "prompt": prompt,
        "text": prompt,
        "text_input": req.extra.get("script") or prompt,
        "negative_prompt": req.negative_prompt or None,
        "duration": int(round(req.duration)),
        "duration_seconds": round(req.duration, 2),
        "music_length_ms": int(req.duration * 1000),
        "num_frames": int(round(req.duration * req.fps)),
        "aspect_ratio": req.aspect,
        "resolution": req.resolution,
        "image_size": IMAGE_SIZES.get(req.aspect, "landscape_16_9"),
        "canvas_size": [width, height],
        "seed": req.seed,
        "num_images": req.count,
        "output_format": "jpeg",
        "generate_audio": bool(req.extra.get("with_audio")),
        "strength": req.extra.get("strength", 0.75),
        "upscale_factor": req.extra.get("factor", 2),
        "scale": req.extra.get("factor", 2),
        "target_fps": req.extra.get("target_fps"),
        "num_steps": 25,
        "textured_mesh": True,
        "steps": req.extra.get("steps", 1000),
        "trigger_word": req.extra.get("trigger_word", "SUBJECT"),
        "language": req.extra.get("language", "es"),
    }

    if req.images:
        payload["image_url"] = uri_of(req.images[0])
        payload["input_image_url"] = payload["image_url"]
        payload["image_urls"] = [uri_of(p) for p in req.images[:8]]
    if req.end_image:
        payload["tail_image_url"] = uri_of(req.end_image)
    if req.video:
        payload["video_url"] = uri_of(req.video)
    if req.audio:
        payload["audio_url"] = uri_of(req.audio)
    if req.voice:
        payload["voice_id"] = req.voice.get("provider_voice_id") or req.voice.get("id")
        payload["voice"] = payload["voice_id"]

    # Reencuadre y expansión apuntan a un formato distinto del de entrada.
    if target := req.extra.get("target_aspect"):
        payload["aspect_ratio"] = target

    allowed = MODE_FIELDS.get(req.mode)
    if allowed:
        payload = {k: v for k, v in payload.items() if k in allowed}
    payload = {k: v for k, v in payload.items() if v is not None}

    # Lo que el usuario fije a mano manda sobre todo lo anterior.
    payload.update(req.extra.get("provider_input", {}))
    return payload
