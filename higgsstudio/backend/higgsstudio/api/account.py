"""Claves de API, webhooks y administración."""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from .. import credits, db, security
from ..worker import public_job

router = APIRouter(prefix="/api/account", tags=["cuenta"])


class KeyBody(BaseModel):
    name: str = Field(default="", max_length=80)


class WebhookBody(BaseModel):
    url: HttpUrl
    events: list[str] = Field(default_factory=lambda: ["job.succeeded", "job.failed"])


# --------------------------------- API keys ---------------------------------

@router.get("/api-keys")
def list_keys(user: dict = Depends(security.current_user)) -> dict[str, Any]:
    rows = db.rows_to_dicts(db.query(
        "SELECT id, name, prefix, scopes, last_used_at, revoked, created_at "
        "FROM api_keys WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)))
    return {"keys": rows}


@router.post("/api-keys")
def create_key(body: KeyBody, user: dict = Depends(security.current_user)) -> dict:
    record, raw = security.create_api_key(user["id"], body.name)
    return {"key": record, "secret": raw,
            "note": "Guárdala ahora: no se vuelve a mostrar."}


@router.delete("/api-keys/{key_id}")
def revoke_key(key_id: str, user: dict = Depends(security.current_user)) -> dict:
    row = db.row_to_dict(db.get("api_keys", key_id))
    if not row or row["user_id"] != user["id"]:
        raise HTTPException(404, "No encuentro esa clave")
    db.update("api_keys", key_id, {"revoked": 1})
    return {"ok": True}


# --------------------------------- webhooks ---------------------------------

@router.get("/webhooks")
def list_webhooks(user: dict = Depends(security.current_user)) -> dict[str, Any]:
    rows = db.rows_to_dicts(db.query(
        "SELECT * FROM webhooks WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],)))
    for hook in rows:
        hook["secret"] = hook["secret"][:6] + "…"
        deliveries = db.rows_to_dicts(db.query(
            "SELECT event, status, status_code, created_at FROM webhook_deliveries "
            "WHERE webhook_id = ? ORDER BY created_at DESC LIMIT 5", (hook["id"],)))
        hook["recent"] = deliveries
    return {"webhooks": rows,
            "events": ["job.succeeded", "job.failed"]}


@router.post("/webhooks")
def create_webhook(body: WebhookBody,
                   user: dict = Depends(security.current_user)) -> dict:
    hook_id = db.new_id("whk")
    secret = secrets.token_urlsafe(24)
    db.insert("webhooks", {
        "id": hook_id, "user_id": user["id"], "url": str(body.url),
        "secret": secret, "events": body.events, "created_at": db.now(),
    })
    return {"webhook": db.row_to_dict(db.get("webhooks", hook_id)),
            "secret": secret,
            "note": "Firma HMAC-SHA256 en la cabecera X-HiggsStudio-Signature."}


@router.delete("/webhooks/{hook_id}")
def delete_webhook(hook_id: str, user: dict = Depends(security.current_user)) -> dict:
    row = db.row_to_dict(db.get("webhooks", hook_id))
    if not row or row["user_id"] != user["id"]:
        raise HTTPException(404, "No encuentro ese webhook")
    db.execute("DELETE FROM webhook_deliveries WHERE webhook_id = ?", (hook_id,))
    db.execute("DELETE FROM webhooks WHERE id = ?", (hook_id,))
    return {"ok": True}


# --------------------------------- resumen ---------------------------------

@router.get("/usage")
def usage(user: dict = Depends(security.current_user)) -> dict[str, Any]:
    recent = db.rows_to_dicts(db.query(
        "SELECT * FROM jobs WHERE user_id = ? "
        "ORDER BY created_at DESC, rowid DESC LIMIT 10",
        (user["id"],)))
    daily = db.rows_to_dicts(db.query(
        "SELECT substr(created_at,1,10) AS day, COUNT(*) AS jobs, "
        "COALESCE(SUM(cost_credits),0) AS credits FROM jobs "
        "WHERE user_id = ? GROUP BY day ORDER BY day DESC LIMIT 30", (user["id"],)))
    return {
        "balance": credits.balance(user["id"]),
        "recent_jobs": [public_job(j) for j in recent],
        "daily": daily,
    }


# ------------------------------ administración ------------------------------

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


@admin_router.get("/stats")
def stats(_: dict = Depends(security.admin_user)) -> dict[str, Any]:
    def count(table: str) -> int:
        row = db.query_one(f"SELECT COUNT(*) AS n FROM {table}")
        return int(row["n"]) if row else 0
    return {
        "users": count("users"), "jobs": count("jobs"), "assets": count("assets"),
        "posts": count("posts"), "characters": count("characters"),
        "by_status": db.rows_to_dicts(db.query(
            "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")),
        "top_models": db.rows_to_dicts(db.query(
            "SELECT model, COUNT(*) AS n FROM jobs GROUP BY model "
            "ORDER BY n DESC LIMIT 10")),
    }


@admin_router.get("/users")
def list_users(limit: int = 100, _: dict = Depends(security.admin_user)) -> dict:
    rows = db.rows_to_dicts(db.query(
        "SELECT id, email, name, plan, credits, is_admin, created_at FROM users "
        "ORDER BY created_at DESC LIMIT ?", (limit,)))
    return {"users": rows}


class GrantBody(BaseModel):
    user_id: str
    amount: int = Field(ge=1, le=1_000_000)
    reason: str = "Ajuste manual"


@admin_router.post("/grant")
def grant_credits(body: GrantBody, _: dict = Depends(security.admin_user)) -> dict:
    if not db.get("users", body.user_id):
        raise HTTPException(404, "Ese usuario no existe")
    balance = credits.grant(body.user_id, body.amount, reason=body.reason)
    return {"balance": balance}


@admin_router.post("/feature/{post_id}")
def feature_post(post_id: str, featured: bool = True,
                 _: dict = Depends(security.admin_user)) -> dict:
    if not db.get("posts", post_id):
        raise HTTPException(404, "No encuentro esa publicación")
    db.update("posts", post_id, {"featured": int(featured)}, id_col="id")
    return {"ok": True, "featured": featured}
