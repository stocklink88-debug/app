"""Generación: vídeo, imagen, avatares que hablan, audio y herramientas."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import credits, db, security, worker
from ..catalog import AD_TEMPLATES, default_model, find_model, find_preset
from ..pipeline import prompts as prompt_tools
from ..worker import public_job

router = APIRouter(prefix="/api", tags=["generar"])

VIDEO_MODES = ("t2v", "i2v", "frames", "motion", "effects")
IMAGE_MODES = ("t2i", "i2i", "edit", "style", "soul_id")
SPEAK_MODES = ("speak", "lipsync")
AUDIO_MODES = ("tts", "music", "sfx", "v2a", "dubbing", "voice_change")
TOOL_MODES = ("upscale_video", "upscale_image", "interpolate", "reframe",
              "outpaint", "bg_remove", "extend", "stitch", "to_3d")


class GenerateBody(BaseModel):
    """Un único cuerpo para todos los tipos de generación."""
    model: str | None = None
    mode: str | None = None
    prompt: str = ""
    negative_prompt: str = ""
    duration: float | None = None
    aspect: str = "16:9"
    resolution: str = "720p"
    fps: int = Field(default=24, ge=8, le=60)
    seed: int | None = None
    count: int = Field(default=1, ge=1, le=8)
    preset: str | None = None
    style: str | None = None
    character_id: str | None = None
    voice_id: str | None = None
    project_id: str | None = None
    folder_id: str | None = None
    image_asset_ids: list[str] = Field(default_factory=list)
    end_image_asset_id: str | None = None
    video_asset_id: str | None = None
    audio_asset_id: str | None = None
    clip_asset_ids: list[str] = Field(default_factory=list)
    music_asset_id: str | None = None
    with_audio: bool = False
    enhance_prompt: bool = False
    provider: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class QuoteBody(GenerateBody):
    type: str = "video"


class EnhanceBody(BaseModel):
    prompt: str
    kind: str = "video"
    style: str = ""
    preset: str = ""


class VariationsBody(BaseModel):
    prompt: str
    count: int = Field(default=4, ge=2, le=8)


class ViralityBody(BaseModel):
    asset_id: str | None = None
    prompt: str = ""
    caption: str = ""
    duration: float = 10
    aspect: str = "9:16"
    has_audio: bool = True
    preset: str | None = None


class AdBody(BaseModel):
    template: str = "ugc-testimonial"
    product_id: str | None = None
    brand_id: str | None = None
    product_name: str = ""
    benefit: str = ""
    audience: str = ""
    tone: str = "cercano"
    language: str = "es"
    aspect: str = "9:16"
    resolution: str = "720p"
    model: str = "kling-2.5-turbo"
    preset: str | None = None
    transition: str = "fundido"
    max_shots: int = Field(default=5, ge=2, le=8)
    image_asset_ids: list[str] = Field(default_factory=list)
    project_id: str | None = None
    seed: int | None = None


class SheetBody(BaseModel):
    character_id: str | None = None
    description: str = ""
    count: int = Field(default=6, ge=2, le=12)
    aspect: str = "3:4"
    resolution: str = "1k"
    style: str = "soul-realism"
    model: str = "soul-2"
    image_asset_ids: list[str] = Field(default_factory=list)
    poses: list[str] | None = None
    traits: dict[str, Any] | None = None
    project_id: str | None = None
    seed: int | None = None


class BatchBody(BaseModel):
    type: str = "video"
    base: GenerateBody
    prompts: list[str] = Field(default_factory=list)
    presets: list[str] = Field(default_factory=list)
    seeds: list[int] = Field(default_factory=list)


# ------------------------------------------------------------------ helpers

def _params(body: GenerateBody, mode: str) -> dict[str, Any]:
    data = body.model_dump()
    data["mode"] = mode
    data.pop("enhance_prompt", None)
    return {k: v for k, v in data.items() if v not in (None, [], {})} | {"mode": mode}


def _pick_model(body: GenerateBody, family: str, mode: str) -> dict[str, Any]:
    model = find_model(body.model or default_model(family))
    if not model:
        raise HTTPException(400, f"No conozco el modelo «{body.model}»")
    if mode not in model.get("modes", []):
        raise HTTPException(
            400,
            f"{model['name']} no admite el modo «{mode}». "
            f"Admite: {', '.join(model.get('modes', []))}.",
        )
    return model


def _validate(body: GenerateBody, model: dict[str, Any], mode: str) -> None:
    if model.get("aspects") and body.aspect not in model["aspects"]:
        raise HTTPException(400,
                            f"{model['name']} no soporta el formato {body.aspect}. "
                            f"Usa uno de: {', '.join(model['aspects'])}.")
    if model.get("resolutions") and body.resolution not in model["resolutions"]:
        raise HTTPException(400,
                            f"{model['name']} no soporta {body.resolution}. "
                            f"Usa uno de: {', '.join(model['resolutions'])}.")
    if body.duration and model.get("max_duration"):
        if body.duration > float(model["max_duration"]):
            raise HTTPException(400,
                                f"{model['name']} llega hasta {model['max_duration']} s.")
    if body.preset and not find_preset(body.preset):
        raise HTTPException(400, f"El preset «{body.preset}» no existe")
    if mode in ("i2v", "frames", "i2i", "edit", "style", "speak") and not body.image_asset_ids:
        raise HTTPException(400, "Este modo necesita al menos una imagen de partida")
    if mode == "frames" and not (body.end_image_asset_id or len(body.image_asset_ids) > 1):
        raise HTTPException(400, "El modo primer/último fotograma necesita las dos imágenes")
    if mode in ("lipsync", "motion", "v2a", "upscale_video", "interpolate",
                "extend", "dubbing") and not body.video_asset_id:
        raise HTTPException(400, "Este modo necesita un vídeo de partida")
    if mode == "voice_change" and not body.audio_asset_id:
        raise HTTPException(400, "Hace falta un audio de partida")
    if mode == "stitch" and len(body.clip_asset_ids) < 2:
        raise HTTPException(400, "Para montar hacen falta al menos dos tomas")


def _submit(body: GenerateBody, user: dict[str, Any], *, job_type: str,
            family: str, mode: str) -> dict[str, Any]:
    model = _pick_model(body, family, mode)
    _validate(body, model, mode)

    if body.enhance_prompt and body.prompt:
        improved = prompt_tools.enhance(body.prompt, kind=family,
                                        style=body.style or "", preset=body.preset or "")
        body.prompt = improved["prompt"]

    params = _params(body, mode)
    if body.duration is None:
        params["duration"] = float(model.get("durations", [5])[0] or 5)
    credits.check_plan_limits(user, params, kind=job_type)
    estimate = credits.quote(job_type, model["id"], params)
    credits.ensure_balance(user["id"], estimate["credits"])

    job = worker.enqueue(user=user, job_type=job_type, model=model["id"],
                         params=params, project_id=body.project_id,
                         cost=estimate["credits"])
    return {"job": public_job(job), "quote": estimate,
            "credits_left": credits.balance(user["id"])}


# ------------------------------------------------------------------ endpoints

@router.post("/generate/quote")
def quote(body: QuoteBody, user: dict = Depends(security.current_user)) -> dict[str, Any]:
    mode = body.mode or ("t2i" if body.type == "image" else "t2v")
    model = find_model(body.model or default_model(body.type))
    if not model:
        raise HTTPException(400, f"No conozco el modelo «{body.model}»")
    params = _params(body, mode)
    if body.duration is None:
        params["duration"] = float(model.get("durations", [5])[0] or 5)
    estimate = credits.quote(body.type, model["id"], params)
    return {**estimate, "balance": credits.balance(user["id"]),
            "affordable": credits.balance(user["id"]) >= estimate["credits"]}


@router.post("/generate/video")
def generate_video(body: GenerateBody, user: dict = Depends(security.current_user)) -> dict:
    mode = body.mode or ("i2v" if body.image_asset_ids else "t2v")
    if mode not in VIDEO_MODES:
        raise HTTPException(400, f"Modo de vídeo no válido: {mode}")
    return _submit(body, user, job_type="video", family="video", mode=mode)


@router.post("/generate/image")
def generate_image(body: GenerateBody, user: dict = Depends(security.current_user)) -> dict:
    mode = body.mode or ("i2i" if body.image_asset_ids else "t2i")
    if mode not in IMAGE_MODES:
        raise HTTPException(400, f"Modo de imagen no válido: {mode}")
    body.resolution = body.resolution if body.resolution in ("1k", "2k", "4k") else "1k"
    return _submit(body, user, job_type="image", family="image", mode=mode)


@router.post("/generate/speak")
def generate_speak(body: GenerateBody, user: dict = Depends(security.current_user)) -> dict:
    mode = body.mode or ("lipsync" if body.video_asset_id else "speak")
    if mode not in SPEAK_MODES:
        raise HTTPException(400, f"Modo no válido: {mode}")
    return _submit(body, user, job_type="speak", family="speak", mode=mode)


@router.post("/generate/audio")
def generate_audio(body: GenerateBody, user: dict = Depends(security.current_user)) -> dict:
    mode = body.mode or "tts"
    if mode not in AUDIO_MODES:
        raise HTTPException(400, f"Modo de audio no válido: {mode}")
    return _submit(body, user, job_type="audio", family="audio", mode=mode)


@router.post("/tools/{tool}")
def run_tool(tool: str, body: GenerateBody,
             user: dict = Depends(security.current_user)) -> dict:
    if tool not in TOOL_MODES:
        raise HTTPException(404, f"No existe la herramienta «{tool}»")
    tool_model = {
        "upscale_video": "upscale-video", "upscale_image": "upscale-image",
        "interpolate": "interpolate", "reframe": "reframe", "outpaint": "outpaint",
        "bg_remove": "bg-remove", "extend": "extend-video", "stitch": "stitch",
        "to_3d": "gen-3d",
    }[tool]
    body.model = body.model or tool_model
    return _submit(body, user, job_type="tool", family="tool", mode=tool)


@router.post("/generate/batch")
def generate_batch(body: BatchBody, user: dict = Depends(security.current_user)) -> dict:
    """Varias generaciones de golpe cambiando prompt, preset o semilla."""
    combos: list[dict[str, Any]] = []
    prompts = body.prompts or [body.base.prompt]
    presets = body.presets or [body.base.preset]
    seeds = body.seeds or [body.base.seed]
    for prompt in prompts:
        for preset in presets:
            for seed in seeds:
                combos.append({"prompt": prompt, "preset": preset, "seed": seed})
    if not combos:
        raise HTTPException(400, "No hay nada que generar")
    if len(combos) > 24:
        raise HTTPException(400, f"El lote sale de {len(combos)} generaciones: el máximo son 24")

    family = body.type
    mode = body.base.mode or ("t2i" if family == "image" else
                              "i2v" if body.base.image_asset_ids else "t2v")
    model = _pick_model(body.base, family, mode)
    batch_id = db.new_id("bat")

    total = 0
    for combo in combos:
        item = body.base.model_copy(update={k: v for k, v in combo.items()
                                            if v is not None})
        params = _params(item, mode)
        if item.duration is None:
            params["duration"] = float(model.get("durations", [5])[0] or 5)
        total += credits.quote(family, model["id"], params)["credits"]
    credits.ensure_balance(user["id"], total)

    jobs = []
    for combo in combos:
        item = body.base.model_copy(update={k: v for k, v in combo.items()
                                            if v is not None})
        params = _params(item, mode)
        if item.duration is None:
            params["duration"] = float(model.get("durations", [5])[0] or 5)
        cost = credits.quote(family, model["id"], params)["credits"]
        job = worker.enqueue(user=user, job_type=family, model=model["id"],
                             params=params, project_id=item.project_id,
                             cost=cost, batch_id=batch_id)
        jobs.append(public_job(job))
    return {"batch_id": batch_id, "jobs": jobs, "total_credits": total,
            "credits_left": credits.balance(user["id"])}


@router.post("/generate/ad")
def generate_ad(body: AdBody, user: dict = Depends(security.current_user)) -> dict:
    """Estudio de anuncios: guion, planos y montaje en un solo trabajo."""
    if not any(t["id"] == body.template for t in AD_TEMPLATES):
        raise HTTPException(400, f"La plantilla «{body.template}» no existe")
    params = body.model_dump()
    params["mode"] = "t2v"
    # Coste estimado: un plano por beat.
    per_shot = credits.quote("video", body.model,
                             {"duration": 4, "resolution": body.resolution})["credits"]
    total = per_shot * body.max_shots
    credits.ensure_balance(user["id"], total)
    job = worker.enqueue(user=user, job_type="ad_campaign", model=body.model,
                         params=params, project_id=body.project_id, cost=total)
    return {"job": public_job(job), "estimated_credits": total,
            "credits_left": credits.balance(user["id"])}


@router.post("/generate/character-sheet")
def generate_sheet(body: SheetBody, user: dict = Depends(security.current_user)) -> dict:
    params = body.model_dump()
    params["mode"] = "t2i"
    per_image = credits.quote("image", body.model,
                              {"resolution": body.resolution})["credits"]
    total = per_image * body.count
    credits.ensure_balance(user["id"], total)
    job = worker.enqueue(user=user, job_type="influencer_sheet", model=body.model,
                         params=params, project_id=body.project_id, cost=total)
    return {"job": public_job(job), "estimated_credits": total,
            "credits_left": credits.balance(user["id"])}


@router.post("/prompt/enhance")
def enhance_prompt(body: EnhanceBody, _: dict = Depends(security.current_user)) -> dict:
    return prompt_tools.enhance(body.prompt, kind=body.kind, style=body.style,
                                preset=body.preset)


@router.post("/prompt/variations")
def prompt_variations(body: VariationsBody, _: dict = Depends(security.current_user)) -> dict:
    return {"variations": prompt_tools.variations(body.prompt, body.count)}


@router.get("/prompt/negative")
def negative_prompt(kind: str = "video") -> dict:
    return {"negative_prompt": prompt_tools.negative_defaults(kind)}


@router.post("/analyze/virality")
def analyze_virality(body: ViralityBody, user: dict = Depends(security.current_user)) -> dict:
    motion = "static"
    if body.preset and (preset := find_preset(body.preset)):
        motion = preset["motion"]
    duration, aspect, has_audio = body.duration, body.aspect, body.has_audio
    prompt = body.prompt
    if body.asset_id:
        asset = db.row_to_dict(db.get("assets", body.asset_id))
        if not asset or asset["user_id"] != user["id"]:
            raise HTTPException(404, "No encuentro ese material")
        duration = float(asset.get("duration") or duration)
        width, height = asset.get("width") or 0, asset.get("height") or 0
        if width and height:
            aspect = "9:16" if height > width else "1:1" if height == width else "16:9"
        prompt = prompt or asset.get("prompt", "")
    return prompt_tools.virality(prompt=prompt, duration=duration, aspect=aspect,
                                 has_audio=has_audio, motion=motion,
                                 caption=body.caption)
