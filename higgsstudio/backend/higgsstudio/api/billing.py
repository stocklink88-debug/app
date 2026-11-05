"""Créditos, planes y consumo."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import credits, db, security
from ..catalog import CREDIT_PACKS, PLANS, find_plan
from ..pipeline.assets import storage_usage

router = APIRouter(prefix="/api/billing", tags=["créditos"])


class PlanBody(BaseModel):
    plan_id: str


class PackBody(BaseModel):
    pack_id: str


@router.get("/summary")
def summary(user: dict = Depends(security.current_user)) -> dict[str, Any]:
    plan = find_plan(user.get("plan", "free"))
    spent = db.query_one(
        "SELECT COALESCE(SUM(-amount),0) AS n FROM credit_tx "
        "WHERE user_id = ? AND kind = 'spend'", (user["id"],))
    jobs = db.query_one(
        "SELECT COUNT(*) AS n FROM jobs WHERE user_id = ? AND status = 'succeeded'",
        (user["id"],))
    by_type = db.rows_to_dicts(db.query(
        "SELECT type, COUNT(*) AS jobs, COALESCE(SUM(cost_credits),0) AS credits "
        "FROM jobs WHERE user_id = ? AND status = 'succeeded' GROUP BY type",
        (user["id"],)))
    return {
        "balance": credits.balance(user["id"]),
        "plan": plan,
        "plans": PLANS,
        "packs": CREDIT_PACKS,
        "spent_total": int(spent["n"]) if spent else 0,
        "jobs_total": int(jobs["n"]) if jobs else 0,
        "by_type": by_type,
        "storage": storage_usage(user["id"]),
    }


@router.get("/transactions")
def transactions(limit: int = 100,
                 user: dict = Depends(security.current_user)) -> dict[str, Any]:
    return {"transactions": credits.history(user["id"], limit)}


@router.post("/plan")
def change_plan(body: PlanBody, user: dict = Depends(security.current_user)) -> dict:
    """Cambia de plan.

    Esta instancia no cobra: no hay pasarela de pago conectada. Cambiar de
    plan ajusta límites y entrega los créditos del mes. Si lo publicas de
    verdad, conecta aquí Stripe antes de abrirlo a desconocidos.
    """
    plan = next((p for p in PLANS if p["id"] == body.plan_id), None)
    if not plan:
        raise HTTPException(404, "Ese plan no existe")
    db.update("users", user["id"], {"plan": plan["id"]})
    granted = 0
    if plan["monthly_credits"]:
        credits.grant(user["id"], plan["monthly_credits"],
                      reason=f"Créditos del plan {plan['name']}", kind="grant")
        granted = plan["monthly_credits"]
    return {"plan": plan, "granted": granted, "balance": credits.balance(user["id"]),
            "note": "Instancia sin pasarela de pago: el cambio es inmediato."}


@router.post("/packs")
def buy_pack(body: PackBody, user: dict = Depends(security.current_user)) -> dict:
    pack = next((p for p in CREDIT_PACKS if p["id"] == body.pack_id), None)
    if not pack:
        raise HTTPException(404, "Ese paquete no existe")
    credits.grant(user["id"], pack["credits"],
                  reason=f"Paquete {pack['credits']} créditos", kind="purchase")
    return {"pack": pack, "balance": credits.balance(user["id"]),
            "note": "Instancia sin pasarela de pago: los créditos se añaden directamente."}
