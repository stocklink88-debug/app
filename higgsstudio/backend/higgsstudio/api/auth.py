"""Registro, inicio de sesión y perfil."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from .. import credits, db, security
from ..catalog import find_plan
from ..config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = ""
    invite_code: str | None = None


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class ProfileBody(BaseModel):
    name: str | None = None
    avatar_url: str | None = None
    prefs: dict[str, Any] | None = None


class PasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        security.SESSION_COOKIE, token,
        max_age=settings.session_days * 86400,
        httponly=True, samesite="lax", path="/",
    )


@router.post("/signup")
def signup(body: SignupBody, request: Request, response: Response) -> dict[str, Any]:
    settings = get_settings()
    if not settings.allow_signup:
        raise HTTPException(403, "El registro está cerrado en esta instancia")
    if settings.invite_code and body.invite_code != settings.invite_code:
        raise HTTPException(403, "El código de invitación no es correcto")
    first_user = db.query_one("SELECT id FROM users LIMIT 1") is None
    user = security.create_user(body.email, body.password, name=body.name,
                                is_admin=first_user)
    token = security.create_session(user["id"], request.headers.get("user-agent", ""))
    _set_cookie(response, token)
    return {"user": security.public_user(user), "token": token}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response) -> dict[str, Any]:
    user = security.authenticate(body.email, body.password)
    token = security.create_session(user["id"], request.headers.get("user-agent", ""))
    _set_cookie(response, token)
    return {"user": security.public_user(user), "token": token}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    if token := request.cookies.get(security.SESSION_COOKIE):
        security.destroy_session(token)
    response.delete_cookie(security.SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(security.current_user)) -> dict[str, Any]:
    plan = find_plan(user.get("plan", "free"))
    return {
        "user": security.public_user(user),
        "plan": plan,
        "credits": credits.balance(user["id"]),
    }


@router.patch("/me")
def update_me(body: ProfileBody, user: dict = Depends(security.current_user)) -> dict:
    fields = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if fields:
        db.update("users", user["id"], fields)
    fresh = db.row_to_dict(db.get("users", user["id"]))
    assert fresh is not None
    return {"user": security.public_user(fresh)}


@router.post("/password")
def change_password(body: PasswordBody, user: dict = Depends(security.current_user)) -> dict:
    row = db.row_to_dict(db.get("users", user["id"]))
    assert row is not None
    if not security.verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(400, "La contraseña actual no es correcta")
    db.update("users", user["id"],
              {"password_hash": security.hash_password(body.new_password)})
    db.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
    return {"ok": True}


@router.get("/sessions")
def list_sessions(user: dict = Depends(security.current_user)) -> dict:
    rows = db.rows_to_dicts(db.query(
        "SELECT token, user_agent, created_at, expires_at FROM sessions "
        "WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)))
    for row in rows:
        row["token"] = row["token"][:8] + "…"
    return {"sessions": rows}


@router.delete("/sessions")
def revoke_sessions(user: dict = Depends(security.current_user)) -> dict:
    db.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
    return {"ok": True}
