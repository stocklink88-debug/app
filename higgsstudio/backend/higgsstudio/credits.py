"""Créditos: presupuesto, cobro y devolución.

El precio sale del catálogo: `credits_base` más la parte proporcional a la
duración o al número de imágenes, multiplicado por la resolución y por el
preset. Siempre se cobra al encolar y se devuelve si el trabajo falla o se
cancela, igual que en Higgsfield.
"""
from __future__ import annotations

import math
from typing import Any

from fastapi import HTTPException

from . import db
from .catalog import find_model, find_plan, find_preset
from .config import get_settings

VIDEO_LADDER = ["480p", "540p", "720p", "768p", "1080p", "2k", "4k"]
IMAGE_LADDER = ["1k", "2k", "4k"]

RESOLUTION_MULT = {
    "480p": 0.7, "540p": 0.8, "720p": 1.0, "768p": 1.05,
    "1080p": 1.5, "1k": 1.0, "2k": 1.8, "4k": 3.0,
}

MODE_MULT = {
    "t2v": 1.0, "i2v": 1.0, "frames": 1.1, "motion": 1.25, "effects": 1.0,
    "t2i": 1.0, "i2i": 1.0, "edit": 1.1, "style": 1.0, "soul_id": 1.2,
    "speak": 1.0, "lipsync": 0.9,
}


def quote(job_type: str, model_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Calcula el coste en créditos de una generación, sin cobrarla."""
    model = find_model(model_id)
    if not model:
        raise HTTPException(400, f"Modelo desconocido: {model_id}")

    settings = get_settings()
    base = float(model.get("credits_base", 5))
    detail: dict[str, Any] = {"base": base}

    duration = float(params.get("duration") or model.get("durations", [5])[0] or 5)
    per_second = float(model.get("credits_per_second", 0))
    if per_second:
        detail["duracion"] = {"segundos": duration, "por_segundo": per_second}
        base += per_second * duration

    n = int(params.get("count") or params.get("num_images") or 1)
    per_image = float(model.get("credits_per_image", 0))
    if per_image and n > 1:
        detail["imagenes"] = {"cantidad": n, "por_imagen": per_image}
        base += per_image * (n - 1)
    elif per_second == 0 and per_image == 0 and n > 1:
        base *= n
        detail["lote"] = n

    res = str(params.get("resolution") or "720p")
    res_mult = RESOLUTION_MULT.get(res, 1.0)
    if res_mult != 1.0:
        detail["resolucion"] = {"valor": res, "factor": res_mult}
    base *= res_mult

    mode = str(params.get("mode") or "")
    if mode in MODE_MULT and MODE_MULT[mode] != 1.0:
        detail["modo"] = {"valor": mode, "factor": MODE_MULT[mode]}
        base *= MODE_MULT[mode]

    if preset_id := params.get("preset"):
        preset = find_preset(str(preset_id))
        if preset and preset.get("credits_mult", 1.0) != 1.0:
            detail["preset"] = {"valor": preset_id, "factor": preset["credits_mult"]}
            base *= float(preset["credits_mult"])

    if params.get("upscale"):
        detail["upscale"] = 1.4
        base *= 1.4
    if params.get("with_audio") and model.get("supports", {}).get("audio"):
        detail["audio"] = 1.15
        base *= 1.15
    if job_type == "train_character":
        base = float(model.get("credits_train", 180))
        detail = {"entrenamiento": base}

    total = max(1, int(math.ceil(base * settings.credit_multiplier)))
    return {
        "credits": total,
        "model": model_id,
        "model_name": model["name"],
        "detail": detail,
        "currency": "credits",
    }


def balance(user_id: str) -> int:
    row = db.query_one("SELECT credits FROM users WHERE id = ?", (user_id,))
    return int(row["credits"]) if row else 0


def ensure_balance(user_id: str, amount: int) -> None:
    if balance(user_id) < amount:
        raise HTTPException(
            402,
            f"No te quedan créditos suficientes: hacen falta {amount} y tienes {balance(user_id)}.",
        )


def _record(user_id: str, amount: int, kind: str, reason: str,
            job_id: str | None, new_balance: int) -> None:
    db.insert("credit_tx", {
        "id": db.new_id("ctx"),
        "user_id": user_id,
        "amount": amount,
        "kind": kind,
        "reason": reason,
        "job_id": job_id,
        "balance_after": new_balance,
        "created_at": db.now(),
    })


def charge(user_id: str, amount: int, *, reason: str = "", job_id: str | None = None) -> int:
    """Cobra créditos de forma atómica. Devuelve el saldo restante."""
    if amount <= 0:
        return balance(user_id)
    conn = db.get_conn()
    cur = conn.execute(
        "UPDATE users SET credits = credits - ?, updated_at = ? "
        "WHERE id = ? AND credits >= ?",
        (amount, db.now(), user_id, amount),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(402, "No te quedan créditos suficientes para esta generación.")
    new_balance = balance(user_id)
    _record(user_id, -amount, "spend", reason, job_id, new_balance)
    return new_balance


def refund(user_id: str, amount: int, *, reason: str = "", job_id: str | None = None) -> int:
    if amount <= 0:
        return balance(user_id)
    conn = db.get_conn()
    conn.execute(
        "UPDATE users SET credits = credits + ?, updated_at = ? WHERE id = ?",
        (amount, db.now(), user_id),
    )
    conn.commit()
    new_balance = balance(user_id)
    _record(user_id, amount, "refund", reason or "Devolución por trabajo fallido", job_id, new_balance)
    return new_balance


def grant(user_id: str, amount: int, *, reason: str = "", kind: str = "grant") -> int:
    conn = db.get_conn()
    conn.execute(
        "UPDATE users SET credits = credits + ?, updated_at = ? WHERE id = ?",
        (amount, db.now(), user_id),
    )
    conn.commit()
    new_balance = balance(user_id)
    _record(user_id, amount, kind, reason, None, new_balance)
    return new_balance


def history(user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    return db.rows_to_dicts(db.query(
        "SELECT * FROM credit_tx WHERE user_id = ? "
        "ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (user_id, limit),
    ))


def check_plan_limits(user: dict[str, Any], params: dict[str, Any],
                      *, kind: str = "video") -> None:
    """Valida resolución, duración y paralelismo según el plan.

    Vídeo e imagen usan escalas distintas ("720p" frente a "1k"), así que
    cada una se compara contra su propio tope. La duración solo limita planos
    de vídeo: una locución o una pista de música larga no es un "plano".
    """
    limits = find_plan(user.get("plan", "free"))["limits"]

    res = str(params.get("resolution") or "")
    if res:
        if res in IMAGE_LADDER:
            ladder, cap = IMAGE_LADDER, limits.get("max_image_resolution", "1k")
        elif res in VIDEO_LADDER:
            ladder, cap = VIDEO_LADDER, limits.get("max_resolution", "720p")
        else:
            ladder, cap = [], ""
        if ladder and cap in ladder and ladder.index(res) > ladder.index(cap):
            raise HTTPException(
                403,
                f"Tu plan ({user.get('plan')}) llega hasta {cap}. "
                f"Sube de plan para usar {res}.",
            )

    duration = float(params.get("duration") or 0)
    if kind in ("video", "speak") and duration > float(limits.get("max_duration", 60)):
        raise HTTPException(
            403,
            f"Tu plan permite planos de hasta {limits['max_duration']} s.",
        )

    running = db.query_one(
        "SELECT COUNT(*) AS n FROM jobs WHERE user_id = ? AND status IN ('queued','running')",
        (user["id"],),
    )
    if running and int(running["n"]) >= int(limits.get("concurrent_jobs", 1)) * 4:
        raise HTTPException(429, "Tienes demasiados trabajos en cola. Espera a que terminen.")
