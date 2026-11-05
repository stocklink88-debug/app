"""Personajes: Soul ID e influencers de IA."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import credits, db, security, worker
from ..catalog import AVATAR_PRESETS, find_plan
from ..pipeline import prompts as prompt_tools
from ..pipeline.assets import public_asset
from ..worker import public_job

router = APIRouter(prefix="/api/characters", tags=["personajes"])


class CharacterBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = "soul_id"              # soul_id | influencer
    description: str = ""
    ref_asset_ids: list[str] = Field(default_factory=list)
    traits: dict[str, Any] = Field(default_factory=dict)
    voice_id: str | None = None
    trigger_word: str = ""


class CharacterPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    traits: dict[str, Any] | None = None
    ref_asset_ids: list[str] | None = None
    cover_asset_id: str | None = None
    voice_id: str | None = None
    trigger_word: str | None = None
    status: str | None = None


class TrainBody(BaseModel):
    model: str = "soul-id"
    steps: int = Field(default=1000, ge=200, le=4000)
    trigger_word: str = ""


def _own(character_id: str, user_id: str) -> dict[str, Any]:
    character = db.row_to_dict(db.get("characters", character_id))
    if not character or character["user_id"] != user_id:
        raise HTTPException(404, "No encuentro ese personaje")
    return character


def _hydrate(character: dict[str, Any]) -> dict[str, Any]:
    out = dict(character)
    sheet = []
    for asset_id in (character.get("sheet_asset_ids") or [])[:24]:
        if asset := db.row_to_dict(db.get("assets", asset_id)):
            sheet.append(public_asset(asset))
    out["sheet"] = sheet
    refs = []
    for asset_id in (character.get("ref_asset_ids") or [])[:24]:
        if asset := db.row_to_dict(db.get("assets", asset_id)):
            refs.append(public_asset(asset))
    out["references"] = refs
    if cover := character.get("cover_asset_id"):
        asset = db.row_to_dict(db.get("assets", cover))
        out["cover"] = public_asset(asset) if asset else None
    return out


@router.get("")
def list_characters(kind: str | None = None,
                    user: dict = Depends(security.current_user)) -> dict[str, Any]:
    sql = "SELECT * FROM characters WHERE user_id = ?"
    params: list[Any] = [user["id"]]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    sql += " ORDER BY updated_at DESC"
    rows = db.rows_to_dicts(db.query(sql, params))
    limits = find_plan(user.get("plan", "free"))["limits"]
    return {
        "characters": [_hydrate(c) for c in rows],
        "limit": limits.get("soul_ids", 0),
        "avatar_presets": AVATAR_PRESETS,
    }


@router.post("")
def create_character(body: CharacterBody,
                     user: dict = Depends(security.current_user)) -> dict[str, Any]:
    limits = find_plan(user.get("plan", "free"))["limits"]
    allowed = int(limits.get("soul_ids", 0))
    count = db.query_one("SELECT COUNT(*) AS n FROM characters WHERE user_id = ?",
                         (user["id"],))
    if allowed and count and int(count["n"]) >= allowed:
        raise HTTPException(
            403, f"Tu plan permite {allowed} personajes. Sube de plan para crear más.")
    if not allowed:
        raise HTTPException(
            403, "El plan gratuito no incluye personajes guardados. Sube a Creador.")

    character_id = db.new_id("chr")
    traits = body.traits or (prompt_tools.character_traits(body.description)
                             if body.description else {})
    db.insert("characters", {
        "id": character_id, "user_id": user["id"], "name": body.name,
        "kind": body.kind, "description": body.description, "traits": traits,
        "ref_asset_ids": body.ref_asset_ids, "voice_id": body.voice_id,
        "trigger_word": body.trigger_word or body.name.split()[0].upper(),
        "status": "borrador", "created_at": db.now(), "updated_at": db.now(),
    })
    return {"character": _hydrate(_own(character_id, user["id"]))}


@router.get("/{character_id}")
def get_character(character_id: str,
                  user: dict = Depends(security.current_user)) -> dict[str, Any]:
    return {"character": _hydrate(_own(character_id, user["id"]))}


@router.patch("/{character_id}")
def patch_character(character_id: str, body: CharacterPatch,
                    user: dict = Depends(security.current_user)) -> dict[str, Any]:
    _own(character_id, user["id"])
    fields = body.model_dump(exclude_none=True)
    if fields:
        db.update("characters", character_id, fields)
    return {"character": _hydrate(_own(character_id, user["id"]))}


@router.delete("/{character_id}")
def delete_character(character_id: str,
                     user: dict = Depends(security.current_user)) -> dict[str, Any]:
    _own(character_id, user["id"])
    db.execute("DELETE FROM characters WHERE id = ?", (character_id,))
    return {"ok": True}


@router.post("/{character_id}/train")
def train_character(character_id: str, body: TrainBody,
                    user: dict = Depends(security.current_user)) -> dict[str, Any]:
    character = _own(character_id, user["id"])
    refs = character.get("ref_asset_ids") or []
    if len(refs) < 4:
        raise HTTPException(400, "Sube al menos 4 fotos de referencia para entrenar")
    params = {
        "mode": "train", "character_id": character_id,
        "image_asset_ids": refs, "steps": body.steps,
        "trigger_word": body.trigger_word or character.get("trigger_word", "SUBJECT"),
        "prompt": character.get("description", ""), "count": 6,
    }
    estimate = credits.quote("train_character", body.model, params)
    credits.ensure_balance(user["id"], estimate["credits"])
    db.update("characters", character_id, {"status": "entrenando"})
    job = worker.enqueue(user=user, job_type="train_character", model=body.model,
                         params=params, cost=estimate["credits"])
    return {"job": public_job(job), "quote": estimate}
