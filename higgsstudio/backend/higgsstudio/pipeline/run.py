"""Ejecución de un trabajo: de los parámetros al asset en la biblioteca."""
from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Callable

from .. import db
from ..catalog import find_model, find_preset, find_style
from ..providers import (
    GenRequest, ProviderError, extract_frame, probe, resolve as resolve_provider,
)
from . import assets as asset_store
from . import prompts as prompt_tools

ProgressFn = Callable[[float, str], None]

# Qué modo le corresponde a cada tipo de trabajo cuando no viene explícito.
DEFAULT_MODE = {
    "video": "t2v", "image": "t2i", "speak": "speak", "audio": "tts",
    "train_character": "train", "virality": "virality",
}

VIDEO_MODES = {"t2v", "i2v", "frames", "motion", "effects"}
IMAGE_MODES = {"t2i", "i2i", "edit", "style", "soul_id"}
TOOL_MODES = {"upscale_video", "upscale_image", "interpolate", "reframe",
              "outpaint", "bg_remove", "extend", "stitch", "to_3d"}
AUDIO_MODES = {"tts", "music", "sfx", "v2a", "dubbing", "voice_change"}
SPEAK_MODES = {"speak", "lipsync"}


def asset_path(user_id: str, asset_id: str | None) -> Path | None:
    """Ruta en disco de un asset propio (o None)."""
    if not asset_id:
        return None
    row = db.row_to_dict(db.get("assets", asset_id))
    if not row or row["user_id"] != user_id:
        return None
    path = Path(row["path"])
    return path if path.exists() else None


def _voice(user_id: str, voice_id: str | None) -> dict[str, Any] | None:
    if not voice_id:
        return None
    row = db.row_to_dict(db.query_one(
        "SELECT * FROM voices WHERE id = ? AND (user_id IS NULL OR user_id = ?)",
        (voice_id, user_id)))
    if row:
        return row
    from ..catalog import STOCK_VOICES
    for voice in STOCK_VOICES:
        if voice["id"] == voice_id:
            return voice
    return None


def build_request(job: dict[str, Any], user: dict[str, Any],
                  progress: ProgressFn) -> GenRequest:
    params = job.get("params", {}) or {}
    mode = params.get("mode") or DEFAULT_MODE.get(job["type"], job["type"])
    model = find_model(job.get("model") or params.get("model") or "")
    if not model:
        raise ProviderError(f"Modelo desconocido: {job.get('model')}")

    user_id = job["user_id"]
    images = [p for p in (asset_path(user_id, a)
                          for a in params.get("image_asset_ids", [])) if p]
    workdir = db.job_dir(job["id"])

    family = model.get("family", "video")
    job_kind = ("image" if mode in IMAGE_MODES else
                "audio" if mode in AUDIO_MODES else
                "speak" if mode in SPEAK_MODES else
                "tool" if mode in TOOL_MODES else family)

    seed = params.get("seed")
    if seed in ("", None) and model.get("supports", {}).get("seed"):
        seed = random.Random(job["id"]).randint(1, 2**31 - 1)

    duration = float(params.get("duration") or model.get("durations", [5])[0] or 5)
    extra = dict(params.get("extra", {}))
    for key in ("with_audio", "script", "language", "emotion", "factor",
                "target_fps", "target_aspect", "extra_seconds", "transition",
                "fill", "slow_factor", "tolerance", "trigger_word", "strength",
                "speed", "clips", "music_path", "motion"):
        if key in params:
            extra[key] = params[key]

    request = GenRequest(
        job_id=job["id"],
        type=job_kind,
        mode=mode,
        model=model,
        workdir=workdir,
        prompt=params.get("prompt", ""),
        negative_prompt=params.get("negative_prompt", ""),
        duration=duration,
        aspect=params.get("aspect", "16:9"),
        resolution=params.get("resolution", "720p"),
        fps=int(params.get("fps", 24)),
        seed=int(seed) if seed not in ("", None) else None,
        count=max(1, min(int(params.get("count", 1)), 8)),
        images=images,
        end_image=asset_path(user_id, params.get("end_image_asset_id")),
        video=asset_path(user_id, params.get("video_asset_id")),
        audio=asset_path(user_id, params.get("audio_asset_id")),
        preset=find_preset(params["preset"]) if params.get("preset") else None,
        style=find_style(params["style"]) if params.get("style") else None,
        voice=_voice(user_id, params.get("voice_id")),
        extra=extra,
        progress=progress,
    )
    return request


def execute(job: dict[str, Any], user: dict[str, Any],
            progress: ProgressFn) -> dict[str, Any]:
    """Ejecuta un trabajo y devuelve su resultado ya registrado."""
    job_type = job["type"]
    if job_type == "virality":
        return _virality(job)
    if job_type == "ad_campaign":
        return _ad_campaign(job, user, progress)
    if job_type == "influencer_sheet":
        return _character_sheet(job, user, progress)

    request = build_request(job, user, progress)
    _prepare_special_modes(request, job)

    forced = (job.get("params") or {}).get("provider")
    provider = resolve_provider(request, forced=forced)
    progress(0.1, f"Generando con {provider.name}")
    result = provider.run(request)
    progress(0.9, "Guardando en la biblioteca")

    params = job.get("params", {}) or {}
    stored = _store_outputs(job, user, result, params, request)
    return {
        "provider": provider.name,
        "model": request.model["id"],
        "assets": stored,
        "meta": result.meta,
        "seed": request.seed,
    }


def _prepare_special_modes(request: GenRequest, job: dict[str, Any]) -> None:
    """Ajustes que necesitan tocar los ficheros antes de llamar al proveedor."""
    params = job.get("params", {}) or {}

    # Extender un plano: el proveedor parte del último fotograma.
    if request.mode == "extend" and request.video and not request.images:
        frame = extract_frame(request.video, request.workdir / "last_frame.jpg", at="last")
        if frame:
            request.images = [frame]

    # Montaje: resolver los assets de cada toma a rutas de disco.
    if request.mode == "stitch":
        clips = []
        for asset_id in params.get("clip_asset_ids", []):
            if path := asset_path(job["user_id"], asset_id):
                clips.append(str(path))
        request.extra["clips"] = clips
        if music_id := params.get("music_asset_id"):
            if music := asset_path(job["user_id"], music_id):
                request.extra["music_path"] = str(music)

    # Personaje: las referencias entrenadas se añaden como imágenes guía.
    if character_id := params.get("character_id"):
        character = db.row_to_dict(db.get("characters", character_id))
        if character and character["user_id"] == job["user_id"]:
            refs = character.get("sheet_asset_ids") or character.get("ref_asset_ids") or []
            paths = [p for p in (asset_path(job["user_id"], a) for a in refs[:4]) if p]
            request.images = (request.images + paths)[:6]
            if trigger := character.get("trigger_word"):
                request.prompt = f"{trigger}, {request.prompt}".strip(", ")
            request.extra.setdefault("character", character["name"])


def _store_outputs(job: dict[str, Any], user: dict[str, Any], result,
                   params: dict[str, Any], request: GenRequest) -> list[dict[str, Any]]:
    stored: list[dict[str, Any]] = []
    watermark = asset_store.needs_watermark(user)
    for index, output in enumerate(result.outputs):
        path = output.path
        if watermark and output.kind in ("video", "image"):
            marked = path.with_name(f"wm_{path.name}")
            try:
                path = asset_store.watermark(path, marked)
            except Exception:
                path = output.path
        asset = asset_store.store(
            job["user_id"], path,
            kind=output.kind,
            job_id=job["id"],
            project_id=job.get("project_id"),
            folder_id=params.get("folder_id"),
            prompt=request.full_prompt(),
            model=request.model["id"],
            preset=params.get("preset"),
            params={**params, "output_index": index, "provider_meta": output.meta},
            seed=request.seed,
        )
        stored.append(asset_store.public_asset(asset))
    return stored


# ------------------------------------------------------------------ compuestos

def _virality(job: dict[str, Any]) -> dict[str, Any]:
    params = job.get("params", {}) or {}
    asset = None
    if asset_id := params.get("asset_id"):
        asset = db.row_to_dict(db.get("assets", asset_id))
    duration = float(params.get("duration") or (asset or {}).get("duration") or 10)
    width = (asset or {}).get("width") or 1080
    height = (asset or {}).get("height") or 1920
    aspect = params.get("aspect") or ("9:16" if height > width else
                                      "1:1" if height == width else "16:9")
    has_audio = bool(params.get("has_audio"))
    if asset:
        has_audio = bool(probe(Path(asset["path"])).get("has_audio"))
    report = prompt_tools.virality(
        prompt=params.get("prompt") or (asset or {}).get("prompt", ""),
        duration=duration,
        aspect=aspect,
        has_audio=has_audio,
        motion=str(params.get("motion") or
                   (find_preset(params["preset"])["motion"] if params.get("preset") else "static")),
        caption=params.get("caption", ""),
    )
    return {"provider": "local", "model": "virality", "assets": [], "report": report}


def _ad_campaign(job: dict[str, Any], user: dict[str, Any],
                 progress: ProgressFn) -> dict[str, Any]:
    """Estudio de anuncios: guion → planos → montaje final."""
    from ..catalog import AD_TEMPLATES

    params = job.get("params", {}) or {}
    template = next((t for t in AD_TEMPLATES if t["id"] == params.get("template")),
                    AD_TEMPLATES[0])
    product = db.row_to_dict(db.get("products", params.get("product_id", ""))) or {}
    brand = db.row_to_dict(db.get("brands", params.get("brand_id", ""))) or {}

    progress(0.08, "Escribiendo el guion")
    script = prompt_tools.ad_script(
        product=params.get("product_name") or product.get("name", "el producto"),
        benefit=params.get("benefit") or product.get("description", "mejor resultado"),
        audience=params.get("audience", "gente que busca algo que funcione"),
        template=template,
        tone=params.get("tone") or brand.get("tone") or "cercano",
        language=params.get("language", "es"),
    )

    shots = script.get("shots", [])[: int(params.get("max_shots", 5))]
    aspect = params.get("aspect") or template.get("format", "9:16")
    model_id = params.get("model") or "higgs-dop-turbo"
    product_assets = params.get("image_asset_ids") or product.get("asset_ids", [])
    clip_paths: list[Path] = []
    shot_assets: list[dict[str, Any]] = []

    for index, shot in enumerate(shots):
        progress(0.15 + 0.6 * index / max(len(shots), 1),
                 f"Plano {index + 1} de {len(shots)}: {shot.get('beat', '')}")
        sub_job = {
            "id": f"{job['id']}_s{index}",
            "user_id": job["user_id"],
            "project_id": job.get("project_id"),
            "type": "video",
            "model": model_id,
            "params": {
                "mode": "i2v" if product_assets else "t2v",
                "prompt": shot.get("visual", ""),
                "duration": float(shot.get("seconds", 3)),
                "aspect": aspect,
                "resolution": params.get("resolution", "720p"),
                "preset": params.get("preset"),
                "image_asset_ids": product_assets[:1] if product_assets else [],
                "seed": params.get("seed"),
            },
        }
        request = build_request(sub_job, user, lambda *_: None)
        request.workdir = db.job_dir(job["id"]) / f"shot_{index}"
        request.workdir.mkdir(parents=True, exist_ok=True)
        provider = resolve_provider(request)
        result = provider.run(request)
        for output in result.outputs:
            if output.kind == "video":
                clip_paths.append(output.path)
        stored = _store_outputs(
            {**job, "id": job["id"]}, user, result,
            {**sub_job["params"], "ad_shot": shot.get("beat")}, request)
        shot_assets.extend(stored)

    final_assets: list[dict[str, Any]] = []
    if len(clip_paths) >= 2:
        progress(0.82, "Montando el anuncio")
        from ..providers.local import LocalProvider
        stitch_request = GenRequest(
            job_id=job["id"], type="tool", mode="stitch",
            model=find_model("stitch"), workdir=db.job_dir(job["id"]),
            aspect=aspect, resolution=params.get("resolution", "720p"),
            extra={"clips": [str(p) for p in clip_paths],
                   "transition": params.get("transition", "fundido")},
            progress=progress,
        )
        montage = LocalProvider().run(stitch_request)
        final_assets = _store_outputs(
            job, user, montage,
            {**params, "ad_final": True, "template": template["id"]}, stitch_request)

    return {
        "provider": "composite",
        "model": model_id,
        "assets": final_assets + shot_assets,
        "script": script,
        "template": template["id"],
    }


def _character_sheet(job: dict[str, Any], user: dict[str, Any],
                     progress: ProgressFn) -> dict[str, Any]:
    """Hoja de personaje: varias poses coherentes del mismo sujeto."""
    params = job.get("params", {}) or {}
    description = params.get("description", "")
    progress(0.08, "Definiendo el personaje")
    traits = params.get("traits") or prompt_tools.character_traits(description)
    poses = params.get("poses") or [
        "retrato frontal, luz suave de estudio",
        "perfil de tres cuartos mirando fuera de cámara",
        "plano medio de cuerpo, postura relajada",
        "primer plano sonriendo con naturalidad",
        "plano general de cuerpo entero",
        "retrato a contraluz al atardecer",
    ]
    base = ", ".join(str(v) for k, v in traits.items()
                     if k in ("edad", "etnia", "pelo", "ojos", "complexion", "estilo") and v)
    model_id = params.get("model") or "soul-2"
    stored: list[dict[str, Any]] = []
    for index, pose in enumerate(poses[: int(params.get("count", 6))]):
        progress(0.15 + 0.7 * index / max(len(poses), 1), f"Pose {index + 1}")
        sub_job = {
            "id": f"{job['id']}_p{index}",
            "user_id": job["user_id"],
            "project_id": job.get("project_id"),
            "type": "image",
            "model": model_id,
            "params": {
                "mode": "soul_id" if params.get("image_asset_ids") else "t2i",
                "prompt": f"{description}, {base}, {pose}".strip(", "),
                "aspect": params.get("aspect", "3:4"),
                "resolution": params.get("resolution", "1k"),
                "style": params.get("style", "soul-realism"),
                "image_asset_ids": params.get("image_asset_ids", []),
                "seed": params.get("seed"),
                "count": 1,
            },
        }
        request = build_request(sub_job, user, lambda *_: None)
        request.workdir = db.job_dir(job["id"]) / f"pose_{index}"
        request.workdir.mkdir(parents=True, exist_ok=True)
        provider = resolve_provider(request)
        result = provider.run(request)
        stored.extend(_store_outputs(job, user, result,
                                     {**sub_job["params"], "pose": pose}, request))

    if character_id := params.get("character_id"):
        character = db.row_to_dict(db.get("characters", character_id))
        if character and character["user_id"] == job["user_id"]:
            db.update("characters", character_id, {
                "sheet_asset_ids": [a["id"] for a in stored],
                "cover_asset_id": stored[0]["id"] if stored else None,
                "traits": traits,
                "status": "listo",
            })
    return {"provider": "composite", "model": model_id,
            "assets": stored, "traits": traits}
