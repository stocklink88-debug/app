"""Catálogo público: modelos, presets, estilos, planes, voces y capacidades."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import db, security
from ..catalog import (
    AD_TEMPLATES, ASPECTS, AVATAR_PRESETS, CATEGORIES, CREDIT_PACKS, EMOTIONS,
    IMAGE_STYLES, LANGUAGES, MODELS, MUSIC_GENRES, PLANS, PRESETS, RESOLUTIONS,
    STYLE_GROUPS, presets_for,
)
from ..config import get_settings
from ..providers import available_providers

router = APIRouter(prefix="/api", tags=["catálogo"])


@router.get("/capabilities")
def capabilities() -> dict[str, Any]:
    settings = get_settings()
    return {
        **settings.capabilities(),
        "providers_available": available_providers(),
        "version": "1.0.0",
    }


@router.get("/models")
def models(family: str | None = None, mode: str | None = None) -> dict[str, Any]:
    out = MODELS
    if family:
        out = [m for m in out if m["family"] == family]
    if mode:
        out = [m for m in out if mode in m.get("modes", [])]
    return {"models": out, "aspects": ASPECTS, "resolutions": RESOLUTIONS}


@router.get("/presets")
def presets(
    category: str | None = None,
    search: str | None = None,
    limit: int = Query(500, le=1000),
    user: dict | None = Depends(security.optional_user),
) -> dict[str, Any]:
    items = presets_for(category=category, search=search)[:limit]
    favorites: set[str] = set()
    if user:
        favorites = {r["preset_id"] for r in db.query(
            "SELECT preset_id FROM preset_favorites WHERE user_id = ?", (user["id"],))}
    return {
        "presets": [{**p, "favorite": p["id"] in favorites} for p in items],
        "categories": CATEGORIES,
        "total": len(PRESETS),
    }


@router.post("/presets/{preset_id}/favorite")
def toggle_favorite(preset_id: str, user: dict = Depends(security.current_user)) -> dict:
    existing = db.query_one(
        "SELECT 1 FROM preset_favorites WHERE user_id = ? AND preset_id = ?",
        (user["id"], preset_id))
    if existing:
        db.execute("DELETE FROM preset_favorites WHERE user_id = ? AND preset_id = ?",
                   (user["id"], preset_id))
        return {"favorite": False}
    db.insert("preset_favorites", {"user_id": user["id"], "preset_id": preset_id,
                                   "created_at": db.now()})
    return {"favorite": True}


@router.get("/styles")
def styles() -> dict[str, Any]:
    return {"styles": IMAGE_STYLES, "groups": STYLE_GROUPS}


@router.get("/plans")
def plans() -> dict[str, Any]:
    return {"plans": PLANS, "packs": CREDIT_PACKS}


@router.get("/options")
def options() -> dict[str, Any]:
    """Todo lo que los selectores del frontend necesitan de una sola vez."""
    return {
        "aspects": ASPECTS,
        "resolutions": RESOLUTIONS,
        "emotions": EMOTIONS,
        "languages": LANGUAGES,
        "music_genres": MUSIC_GENRES,
        "ad_templates": AD_TEMPLATES,
        "avatar_presets": AVATAR_PRESETS,
        "preset_categories": CATEGORIES,
        "style_groups": STYLE_GROUPS,
        "transitions": ["corte", "fundido", "desenfoque", "zoom", "deslizar",
                        "circulo", "pixel", "limpiar"],
    }
