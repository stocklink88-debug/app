"""Adaptador de ElevenLabs: voz, música, efectos, doblaje y clonado."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..config import get_settings
from .base import (
    GenRequest, GenResult, Output, ProviderError, ProviderUnavailable, probe,
)
from .http import client

EMOTION_SETTINGS = {
    "neutral": {"stability": 0.5, "style": 0.0},
    "alegre": {"stability": 0.35, "style": 0.55},
    "serio": {"stability": 0.75, "style": 0.1},
    "susurro": {"stability": 0.8, "style": 0.25},
    "entusiasta": {"stability": 0.3, "style": 0.75},
    "triste": {"stability": 0.7, "style": 0.35},
    "enfadado": {"stability": 0.3, "style": 0.8},
    "narrador": {"stability": 0.65, "style": 0.2},
}


class ElevenLabsProvider:
    name = "elevenlabs"

    def available(self) -> bool:
        return bool(get_settings().elevenlabs_api_key)

    def supports(self, req: GenRequest) -> bool:
        return self.available() and req.mode in (
            "tts", "music", "sfx", "dubbing", "voice_change")

    def _headers(self, content_type: str | None = "application/json") -> dict[str, str]:
        settings = get_settings()
        if not settings.elevenlabs_api_key:
            raise ProviderUnavailable("Falta ELEVENLABS_API_KEY")
        headers = {"xi-api-key": settings.elevenlabs_api_key}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def run(self, req: GenRequest) -> GenResult:
        handlers = {
            "tts": self._tts, "music": self._music, "sfx": self._sfx,
            "dubbing": self._dubbing, "voice_change": self._voice_change,
        }
        handler = handlers.get(req.mode)
        if handler is None:
            raise ProviderUnavailable(f"ElevenLabs no cubre el modo «{req.mode}»")
        return handler(req)

    # ------------------------------------------------------------------
    def _tts(self, req: GenRequest) -> GenResult:
        settings = get_settings()
        voice = req.voice or {}
        voice_id = voice.get("provider_voice_id") or voice.get("id")
        if not voice_id:
            raise ProviderError("Elige una voz antes de generar la locución.")
        emotion = str(req.extra.get("emotion", "neutral"))
        tuning = EMOTION_SETTINGS.get(emotion, EMOTION_SETTINGS["neutral"])
        body = {
            "text": req.extra.get("script") or req.prompt,
            "model_id": settings.elevenlabs_model,
            "voice_settings": {
                "stability": tuning["stability"],
                "similarity_boost": float(req.extra.get("similarity", 0.75)),
                "style": tuning["style"],
                "use_speaker_boost": True,
                "speed": float(req.extra.get("speed", 1.0)),
            },
        }
        if language := req.extra.get("language"):
            body["language_code"] = str(language)[:2]
        req.progress(0.3, "Generando la locución")
        dest = req.workdir / "voice.mp3"
        self._post_audio(
            f"{settings.elevenlabs_base_url}/text-to-speech/{voice_id}", body, dest)
        return GenResult([Output(dest, "audio", probe(dest))], self.name,
                         {"voice_id": voice_id, "emotion": emotion})

    def _music(self, req: GenRequest) -> GenResult:
        settings = get_settings()
        length_ms = int(max(5.0, min(req.duration or 30, 300)) * 1000)
        body = {
            "prompt": req.full_prompt(),
            "music_length_ms": length_ms,
            "model_id": settings.elevenlabs_music_model,
        }
        req.progress(0.3, "Componiendo la pista")
        dest = req.workdir / "music.mp3"
        self._post_audio(f"{settings.elevenlabs_base_url}/music", body, dest)
        return GenResult([Output(dest, "audio", probe(dest))], self.name,
                         {"length_ms": length_ms})

    def _sfx(self, req: GenRequest) -> GenResult:
        settings = get_settings()
        body: dict[str, Any] = {
            "text": req.full_prompt(),
            "duration_seconds": max(0.5, min(req.duration or 3, 22)),
            "prompt_influence": float(req.extra.get("prompt_influence", 0.4)),
        }
        if req.extra.get("loop"):
            body["loop"] = True
        req.progress(0.3, "Generando el efecto")
        dest = req.workdir / "sfx.mp3"
        self._post_audio(f"{settings.elevenlabs_base_url}/sound-generation", body, dest)
        return GenResult([Output(dest, "audio", probe(dest))], self.name, {})

    def _voice_change(self, req: GenRequest) -> GenResult:
        settings = get_settings()
        if not req.audio:
            raise ProviderError("Hace falta un audio de entrada.")
        voice = req.voice or {}
        voice_id = voice.get("provider_voice_id") or voice.get("id")
        if not voice_id:
            raise ProviderError("Elige la voz de destino.")
        dest = req.workdir / "voice_changed.mp3"
        req.progress(0.35, "Cambiando la voz")
        with client(self._headers(None)) as http:
            with req.audio.open("rb") as fh:
                response = http.post(
                    f"{settings.elevenlabs_base_url}/speech-to-speech/{voice_id}",
                    files={"audio": (req.audio.name, fh, "audio/mpeg")},
                    data={"model_id": "eleven_multilingual_sts_v2"},
                )
            self._check(response)
            dest.write_bytes(response.content)
        return GenResult([Output(dest, "audio", probe(dest))], self.name,
                         {"voice_id": voice_id})

    def _dubbing(self, req: GenRequest) -> GenResult:
        settings = get_settings()
        source = req.video or req.audio
        if not source:
            raise ProviderError("Hace falta un vídeo o un audio para doblar.")
        target = str(req.extra.get("language", "es"))
        req.progress(0.2, f"Enviando a doblaje ({target})")
        with client(self._headers(None)) as http:
            with source.open("rb") as fh:
                response = http.post(
                    f"{settings.elevenlabs_base_url}/dubbing",
                    files={"file": (source.name, fh, "video/mp4")},
                    data={"target_lang": target,
                          "num_speakers": str(req.extra.get("speakers", 0)),
                          "watermark": "false"},
                )
            self._check(response)
            dubbing_id = response.json().get("dubbing_id")
            if not dubbing_id:
                raise ProviderError("ElevenLabs no devolvió un identificador de doblaje")

            deadline = time.time() + settings.job_timeout_s
            while time.time() < deadline:
                time.sleep(settings.provider_poll_interval_s)
                status = http.get(f"{settings.elevenlabs_base_url}/dubbing/{dubbing_id}")
                self._check(status)
                state = status.json()
                if state.get("status") == "dubbed":
                    break
                if state.get("status") == "failed":
                    raise ProviderError(f"El doblaje falló: {state.get('error')}")
                req.progress(0.5, "Doblando")
            else:
                raise ProviderError("El doblaje tardó demasiado")

            req.progress(0.85, "Descargando el doblaje")
            dest = req.workdir / f"dubbed_{target}.mp4"
            audio = http.get(
                f"{settings.elevenlabs_base_url}/dubbing/{dubbing_id}/audio/{target}")
            self._check(audio)
            dest.write_bytes(audio.content)
        return GenResult([Output(dest, "video", probe(dest))], self.name,
                         {"dubbing_id": dubbing_id, "language": target})

    # ------------------------------------------------------------------
    def _post_audio(self, url: str, body: dict[str, Any], dest: Path) -> None:
        with client(self._headers()) as http:
            response = http.post(url, json=body)
            self._check(response)
            dest.write_bytes(response.content)
        if dest.stat().st_size == 0:
            raise ProviderError("ElevenLabs devolvió un audio vacío")

    def _check(self, response) -> None:
        if response.status_code < 400:
            return
        detail = ""
        try:
            data = response.json()
            detail = json.dumps(data.get("detail", data), ensure_ascii=False)[:300]
        except Exception:
            detail = (response.text or "")[:300]
        if response.status_code == 401:
            raise ProviderError("ElevenLabs rechazó la clave (401).")
        if response.status_code == 422:
            raise ProviderError(f"ElevenLabs no aceptó los parámetros: {detail}")
        if response.status_code == 429:
            raise ProviderError("ElevenLabs te está limitando (429).")
        raise ProviderError(f"ElevenLabs respondió {response.status_code}: {detail}")


# ---------------------------- utilidades de cuenta ----------------------------

def list_remote_voices() -> list[dict[str, Any]]:
    """Voces reales de la cuenta, para mezclarlas con el catálogo local."""
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        return []
    try:
        with client({"xi-api-key": settings.elevenlabs_api_key}) as http:
            response = http.get(f"{settings.elevenlabs_base_url}/voices")
            if response.status_code >= 400:
                return []
            data = response.json()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for voice in data.get("voices", []):
        out.append({
            "id": voice.get("voice_id"),
            "name": voice.get("name", ""),
            "provider": "elevenlabs",
            "provider_voice_id": voice.get("voice_id"),
            "kind": voice.get("category", "stock"),
            "description": voice.get("description") or "",
            "labels": voice.get("labels", {}),
            "preview_url": voice.get("preview_url"),
        })
    return out


def clone_voice(name: str, samples: list[Path], description: str = "") -> dict[str, Any]:
    """Clona una voz a partir de muestras de audio."""
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        raise ProviderUnavailable(
            "Clonar voces necesita una clave de ElevenLabs (ELEVENLABS_API_KEY).")
    files = []
    handles = []
    try:
        for path in samples[:25]:
            fh = path.open("rb")
            handles.append(fh)
            files.append(("files", (path.name, fh, "audio/mpeg")))
        with client({"xi-api-key": settings.elevenlabs_api_key}) as http:
            response = http.post(f"{settings.elevenlabs_base_url}/voices/add",
                                 files=files,
                                 data={"name": name, "description": description})
            if response.status_code >= 400:
                raise ProviderError(
                    f"No se pudo clonar la voz ({response.status_code}): "
                    f"{(response.text or '')[:200]}")
            return response.json()
    finally:
        for fh in handles:
            fh.close()
