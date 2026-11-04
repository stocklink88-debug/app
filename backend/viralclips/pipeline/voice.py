"""Locución con voces de IA (ElevenLabs).

Dos usos en la app:
  * Sustituir el audio original de un clip por una voz sintética.
  * Diseñar una voz nueva a partir de una descripción en texto.

El endpoint `with-timestamps` devuelve el audio junto a los tiempos de cada
carácter. Los agrupamos en palabras para que los subtítulos encajen con la voz
generada, en lugar de arrastrar los tiempos del audio original.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import Settings
from ..models import Word

log = logging.getLogger(__name__)

API_BASE = "https://api.elevenlabs.io"
TIMEOUT = httpx.Timeout(connect=20.0, read=180.0, write=120.0, pool=20.0)

# El audio se pide en MP3 estándar: lo acepta cualquier plan de ElevenLabs.
OUTPUT_FORMAT = "mp3_44100_128"
# ElevenLabs corta los textos largos; avisamos antes de gastar caracteres.
MAX_CHARS = 5000


class VoiceError(RuntimeError):
    pass


@dataclass
class Voice:
    voice_id: str
    name: str
    category: str | None = None
    description: str | None = None
    preview_url: str | None = None
    labels: dict[str, str] | None = None

    def to_dict(self) -> dict:
        return {
            "voice_id": self.voice_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "preview_url": self.preview_url,
            "labels": self.labels or {},
        }


@dataclass
class VoicePreview:
    generated_voice_id: str
    audio_base64: str
    media_type: str
    duration_secs: float

    def to_dict(self) -> dict:
        return {
            "generated_voice_id": self.generated_voice_id,
            "audio_data_url": f"data:{self.media_type};base64,{self.audio_base64}",
            "duration_secs": self.duration_secs,
        }


@dataclass
class Speech:
    """Resultado de una locución: el archivo y los tiempos de sus palabras."""
    path: Path
    words: list[Word]
    duration: float


def _headers(settings: Settings) -> dict[str, str]:
    if not settings.elevenlabs_api_key:
        raise VoiceError(
            "Falta ELEVENLABS_API_KEY. Consíguela en elevenlabs.io y añádela al .env"
        )
    return {"xi-api-key": settings.elevenlabs_api_key}


def _raise_for_status(resp: httpx.Response, action: str) -> None:
    if resp.status_code == 200:
        return
    if resp.status_code == 401:
        raise VoiceError("ElevenLabs rechazó la clave de API (401).")
    if resp.status_code == 429:
        raise VoiceError("ElevenLabs ha limitado las peticiones (429). Inténtalo en un minuto.")
    detail = resp.text[:300]
    raise VoiceError(f"ElevenLabs devolvió {resp.status_code} al {action}: {detail}")


# --------------------------------------------------------------------------
# Catálogo de voces
# --------------------------------------------------------------------------

def list_voices(settings: Settings, *, limit: int = 100) -> list[Voice]:
    """Voces disponibles en la cuenta, incluidas las diseñadas por el usuario."""
    voices: list[Voice] = []
    token: str | None = None

    with httpx.Client(timeout=TIMEOUT) as client:
        while len(voices) < limit:
            params: dict[str, object] = {"page_size": min(100, limit - len(voices))}
            if token:
                params["next_page_token"] = token
            resp = client.get(
                f"{API_BASE}/v2/voices", headers=_headers(settings), params=params
            )
            _raise_for_status(resp, "listar las voces")
            payload = resp.json()

            for item in payload.get("voices") or []:
                voices.append(
                    Voice(
                        voice_id=item["voice_id"],
                        name=item.get("name") or item["voice_id"],
                        category=item.get("category"),
                        description=item.get("description"),
                        preview_url=item.get("preview_url"),
                        labels=item.get("labels") or {},
                    )
                )
            token = payload.get("next_page_token")
            if not payload.get("has_more") or not token:
                break

    return voices


# --------------------------------------------------------------------------
# Texto a voz con tiempos
# --------------------------------------------------------------------------

def synthesize(
    text: str,
    *,
    voice_id: str,
    settings: Settings,
    out_path: Path,
    language: str | None = None,
) -> Speech:
    """Genera la locución y devuelve el audio junto a los tiempos por palabra."""
    clean = " ".join(text.split())
    if not clean:
        raise VoiceError("No hay texto que locutar.")
    if len(clean) > MAX_CHARS:
        raise VoiceError(
            f"El texto tiene {len(clean)} caracteres y el máximo es {MAX_CHARS}. "
            "Acorta el clip o el texto de la locución."
        )

    body: dict[str, object] = {"text": clean, "model_id": settings.elevenlabs_model}
    # multilingual_v2 deduce el idioma solo y rechaza language_code.
    if language and "multilingual_v2" not in settings.elevenlabs_model:
        body["language_code"] = language[:2]

    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(
            f"{API_BASE}/v1/text-to-speech/{voice_id}/with-timestamps",
            headers={**_headers(settings), "Content-Type": "application/json"},
            params={"output_format": OUTPUT_FORMAT},
            json=body,
        )
        _raise_for_status(resp, "generar la locución")
        payload = resp.json()

    audio_b64 = payload.get("audio_base64")
    if not audio_b64:
        raise VoiceError("ElevenLabs no devolvió audio.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(audio_b64))

    # `normalized_alignment` casa mejor con el texto tal y como se pronuncia.
    alignment = payload.get("normalized_alignment") or payload.get("alignment") or {}
    words = words_from_alignment(alignment)
    duration = words[-1].end if words else 0.0

    return Speech(path=out_path, words=words, duration=duration)


def words_from_alignment(alignment: dict) -> list[Word]:
    """Convierte los tiempos por carácter de ElevenLabs en tiempos por palabra."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not chars or len(chars) != len(starts) or len(chars) != len(ends):
        return []

    words: list[Word] = []
    buffer: list[str] = []
    start: float | None = None
    end = 0.0

    for char, char_start, char_end in zip(chars, starts, ends):
        if char.isspace():
            if buffer:
                words.append(Word("".join(buffer), start or 0.0, end))
                buffer, start = [], None
            continue
        if start is None:
            start = float(char_start)
        buffer.append(char)
        end = float(char_end)

    if buffer:
        words.append(Word("".join(buffer), start or 0.0, end))

    return words


# --------------------------------------------------------------------------
# Diseño de voces nuevas
# --------------------------------------------------------------------------

# El endpoint exige entre 100 y 1000 caracteres de muestra.
DEFAULT_SAMPLE_ES = (
    "Hoy te voy a contar algo que cambió por completo mi forma de trabajar. "
    "Durante años hice justo lo contrario de lo que debía, y nadie me avisó. "
    "Presta atención, porque esto no te lo cuentan en ningún sitio."
)


def design_voice(
    description: str,
    *,
    settings: Settings,
    sample_text: str | None = None,
) -> list[VoicePreview]:
    """Crea previsualizaciones de una voz a partir de su descripción."""
    description = description.strip()
    if len(description) < 20:
        raise VoiceError(
            "Describe la voz con más detalle (al menos 20 caracteres): edad, "
            "tono, acento, ritmo…"
        )

    body: dict[str, object] = {
        "voice_description": description,
        "model_id": settings.elevenlabs_design_model,
    }
    sample = " ".join((sample_text or "").split())
    if sample and 100 <= len(sample) <= 1000:
        body["text"] = sample
    elif sample:
        raise VoiceError("El texto de muestra debe tener entre 100 y 1000 caracteres.")
    else:
        body["text"] = DEFAULT_SAMPLE_ES

    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(
            f"{API_BASE}/v1/text-to-voice/design",
            headers={**_headers(settings), "Content-Type": "application/json"},
            params={"output_format": OUTPUT_FORMAT},
            json=body,
        )
        _raise_for_status(resp, "diseñar la voz")
        payload = resp.json()

    previews: list[VoicePreview] = []
    for item in payload.get("previews") or []:
        # Ojo: aquí el campo lleva guion bajo (audio_base_64), distinto del TTS.
        audio = item.get("audio_base_64") or item.get("audio_base64") or ""
        if not audio:
            continue
        previews.append(
            VoicePreview(
                generated_voice_id=item["generated_voice_id"],
                audio_base64=audio,
                media_type=item.get("media_type") or "audio/mpeg",
                duration_secs=float(item.get("duration_secs") or 0.0),
            )
        )

    if not previews:
        raise VoiceError("ElevenLabs no devolvió ninguna previsualización.")
    return previews


def save_designed_voice(
    *,
    name: str,
    description: str,
    generated_voice_id: str,
    settings: Settings,
) -> Voice:
    """Guarda en la cuenta la previsualización elegida y devuelve la voz."""
    if not name.strip():
        raise VoiceError("Ponle un nombre a la voz.")

    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(
            f"{API_BASE}/v1/text-to-voice",
            headers={**_headers(settings), "Content-Type": "application/json"},
            json={
                "voice_name": name.strip()[:60],
                "voice_description": description.strip(),
                "generated_voice_id": generated_voice_id,
            },
        )
        _raise_for_status(resp, "guardar la voz")
        item = resp.json()

    return Voice(
        voice_id=item["voice_id"],
        name=item.get("name") or name,
        category=item.get("category"),
        description=item.get("description"),
        preview_url=item.get("preview_url"),
        labels=item.get("labels") or {},
    )
