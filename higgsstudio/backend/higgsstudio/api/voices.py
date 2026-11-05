"""Voces: catálogo, clonado, diseño y previsualización."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import db, security
from ..catalog import EMOTIONS, LANGUAGES, STOCK_VOICES
from ..config import get_settings
from ..providers import ProviderError, clone_voice, list_remote_voices
from ..providers.base import GenRequest
from ..providers.local import LocalProvider
from ..serving import file_response

router = APIRouter(prefix="/api/voices", tags=["voces"])


class PreviewBody(BaseModel):
    voice_id: str
    text: str = Field(default="Así suena esta voz en tu proyecto.", max_length=400)


@router.get("")
def list_voices(user: dict = Depends(security.current_user)) -> dict[str, Any]:
    own = db.rows_to_dicts(db.query(
        "SELECT * FROM voices WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)))
    remote = list_remote_voices()
    stock = [dict(v) for v in STOCK_VOICES]
    seen = {v["id"] for v in own}
    merged = own + [v for v in remote if v["id"] not in seen]
    seen |= {v["id"] for v in remote}
    merged += [v for v in stock if v["id"] not in seen]
    return {
        "voices": merged,
        "emotions": EMOTIONS,
        "languages": LANGUAGES,
        "cloning_available": bool(get_settings().elevenlabs_api_key),
    }


@router.post("/clone")
async def clone(
    name: str = Form(...),
    description: str = Form(""),
    files: list[UploadFile] = File(...),
    user: dict = Depends(security.current_user),
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        raise HTTPException(
            400,
            "Clonar una voz necesita una clave de ElevenLabs. "
            "Añade ELEVENLABS_API_KEY en el fichero .env.",
        )
    temp_paths: list[Path] = []
    try:
        for upload in files[:25]:
            path = settings.uploads_dir / f"{db.new_id('vs')}{Path(upload.filename or '.mp3').suffix}"
            path.write_bytes(await upload.read())
            temp_paths.append(path)
        try:
            result = clone_voice(name, temp_paths, description)
        except ProviderError as exc:
            raise HTTPException(400, str(exc)) from exc
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)

    voice_id = db.new_id("voz")
    db.insert("voices", {
        "id": voice_id, "user_id": user["id"], "name": name,
        "provider": "elevenlabs",
        "provider_voice_id": result.get("voice_id", ""),
        "kind": "cloned", "description": description,
        "created_at": db.now(),
    })
    return {"voice": db.row_to_dict(db.get("voices", voice_id))}


@router.post("/preview")
def preview(body: PreviewBody, user: dict = Depends(security.current_user)) -> dict:
    """Genera una muestra corta y la deja guardada para escucharla."""
    voice = db.row_to_dict(db.query_one(
        "SELECT * FROM voices WHERE id = ? AND (user_id IS NULL OR user_id = ?)",
        (body.voice_id, user["id"])))
    if voice is None:
        voice = next((dict(v) for v in STOCK_VOICES if v["id"] == body.voice_id), None)
    if voice is None:
        remote = next((v for v in list_remote_voices() if v["id"] == body.voice_id), None)
        voice = remote
    if voice is None:
        raise HTTPException(404, "No encuentro esa voz")

    settings = get_settings()
    workdir = settings.cache_dir / f"preview_{body.voice_id}"
    workdir.mkdir(parents=True, exist_ok=True)
    from ..catalog import find_model
    request = GenRequest(
        job_id="preview", type="audio", mode="tts",
        model=find_model("voice-v3"), workdir=workdir,
        prompt=body.text, voice=voice, duration=6,
    )
    try:
        if voice.get("provider") == "elevenlabs" and settings.elevenlabs_api_key:
            from ..providers.elevenlabs import ElevenLabsProvider
            result = ElevenLabsProvider().run(request)
        else:
            result = LocalProvider().run(request)
    except ProviderError as exc:
        raise HTTPException(400, str(exc)) from exc
    path = result.outputs[0].path
    return {"preview_url": f"/api/voices/preview-file/{body.voice_id}{path.suffix}",
            "voice": voice}


@router.get("/preview-file/{filename}")
def preview_file(filename: str, _: dict = Depends(security.current_user)):
    settings = get_settings()
    voice_id = Path(filename).stem
    workdir = settings.cache_dir / f"preview_{voice_id}"
    for candidate in ("voice.mp3", "voice.m4a"):
        path = workdir / candidate
        if path.exists():
            return file_response(path, None)
    raise HTTPException(404, "No hay muestra generada todavía")


@router.delete("/{voice_id}")
def delete_voice(voice_id: str, user: dict = Depends(security.current_user)) -> dict:
    voice = db.row_to_dict(db.get("voices", voice_id))
    if not voice or voice.get("user_id") != user["id"]:
        raise HTTPException(404, "No encuentro esa voz")
    db.execute("DELETE FROM voices WHERE id = ?", (voice_id,))
    return {"ok": True}
